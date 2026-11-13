"""LLM steps: fix recognition errors in cues, translate sentences.

Both steps send numbered items in batches; the model must return exactly the
same ids, otherwise the batch is retried. Neighbouring items go along as
read-only context. Any OpenAI-compatible endpoint works (OpenAI, Ollama via
--base-url http://localhost:11434/v1, Groq, ...).
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

LANG_NAMES = {"en": "English", "ru": "Russian", "de": "German", "fr": "French", "es": "Spanish",
              "it": "Italian", "uk": "Ukrainian", "pl": "Polish", "nl": "Dutch", "pt": "Portuguese"}

FIX_SYSTEM = """You receive numbered cues of an automatic speech-recognition transcript in {src}. \
Cues are short pieces of continuous speech; a sentence often spans several cues.
Fix recognition errors in every cue: misheard words, names and terms, spelling, \
punctuation and capitalization. Sentence-final punctuation (. ? !) matters: it is used \
to split the text into sentences, so put it where sentences really end.
Keep the speaker's wording; do not rephrase, shorten, or move words between cues. \
Return every requested cue; if a cue is fine, return it unchanged. Never return an empty cue.
Context cues are only for understanding; do not return them.
Answer with JSON only: {{"items": [{{"id": <int>, "text": "..."}}, ...]}} with exactly the requested ids."""

TRANSLATE_SYSTEM = """Translate numbered sentences from a {src} transcript into {tgt}.
The translation must be natural and faithful, understandable on its own, and consistent \
with the surrounding sentences (terms, names, register).
Translate every item, even greetings, filler and very short phrases — the listener taps \
any sentence and must always see its translation.
Context sentences are only for understanding; do not return them.
Answer with JSON only: {{"items": [{{"id": <int>, "tr": "..."}}, ...]}} with exactly the requested ids."""

# (system prompt, user prompt) -> parsed JSON object
JsonCall = Callable[[str, str], dict]


def openai_json_call(model: str, base_url: str | None) -> JsonCall:
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY") or ("none" if base_url else None)
    client = OpenAI(base_url=base_url, api_key=key)

    def call(system: str, user: str) -> dict:
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return json.loads(resp.choices[0].message.content)

    return call


def lang_name(code: str) -> str:
    return LANG_NAMES.get(code, code)


def run_batches(call: JsonCall, system: str, texts: list[str], field: str, header: str,
                batch: int, workers: int, ctx: int, label: str, attempts: int = 4) -> list[str]:
    """Send texts in numbered batches, return the `field` value for every text.

    Valid answers are kept; a retry asks only for the ids still missing
    (models like to drop "unimportant" items such as greetings)."""
    ranges = [(a, min(a + batch, len(texts))) for a in range(0, len(texts), batch)]

    def prompt(ids: list[int]) -> str:
        a, b = ids[0], ids[-1] + 1
        lines = [header]
        if a > 0:
            lines += ["", "Context before:"] + [f"- {t}" for t in texts[max(0, a - ctx):a]]
        lines += ["", "Items:"] + [f"{i}: {texts[i]}" for i in ids]
        if b < len(texts):
            lines += ["", "Context after:"] + [f"- {t}" for t in texts[b:b + ctx]]
        lines += ["", f"Return all {len(ids)} items (ids: {', '.join(map(str, ids))}), "
                      "including greetings and short phrases."]
        return "\n".join(lines)

    def one(r):
        a, b = r
        done: dict[int, str] = {}
        err = None
        for _ in range(attempts):
            missing = [i for i in range(a, b) if i not in done]
            try:
                for it in call(system, prompt(missing))["items"]:
                    i, v = int(it["id"]), str(it.get(field, "")).strip()
                    if i in missing and v:
                        done[i] = v
            except Exception as e:  # noqa: BLE001 — retry on any API/format problem
                err = e
            still = [i for i in range(a, b) if i not in done]
            if not still:
                print(f"  {label} {a}-{b - 1} ok", file=sys.stderr)
                return [done[i] for i in range(a, b)]
            err = err or ValueError(f"missing ids {still}")
            print(f"  {label} {a}-{b - 1}: {err}; retrying", file=sys.stderr)
            err = None
        raise RuntimeError(f"LLM failed for {label} {a}-{b - 1}: missing ids "
                           f"{[i for i in range(a, b) if i not in done]}")

    with ThreadPoolExecutor(max(1, workers)) as pool:
        parts = list(pool.map(one, ranges))
    return [t for part in parts for t in part]


def _header(title: str, hint: str | None) -> str:
    return f"Title: {title}" + (f"\nNotes about the content: {hint}" if hint else "")


def fix_cues(call: JsonCall, cues: list[dict], src: str, title: str, hint: str | None,
             batch: int = 40, workers: int = 4) -> list[dict]:
    texts = run_batches(call, FIX_SYSTEM.format(src=lang_name(src)), [c["text"] for c in cues],
                        "text", _header(title, hint), batch, workers, ctx=3, label="fix cues")
    return [{**c, "text": t} for c, t in zip(cues, texts)]


def translate_sentences(call: JsonCall, sentences: list[dict], src: str, tgt: str, title: str,
                        hint: str | None, batch: int = 30, workers: int = 4) -> list[dict]:
    system = TRANSLATE_SYSTEM.format(src=lang_name(src), tgt=lang_name(tgt))
    trs = run_batches(call, system, [s["text"] for s in sentences], "tr", _header(title, hint),
                      batch, workers, ctx=2, label="translate sentences")
    return [{**s, "tr": t} for s, t in zip(sentences, trs)]
