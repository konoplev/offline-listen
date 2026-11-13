"""One audio file -> X.json (+ X.srt, X.<tgt>.srt).

Steps, cached in <folder>/.listen-cache/ so a failed run resumes cheaply:
  1. whisper words        -> X.words.json   (redone only with retranscribe)
  2. group into cues (8 words / 5 s)
     optional (--fix): LLM fixes recognition errors -> X.fixed.json
  3. split cues into sentences and translate them:
     macOS built-in translator (default, free) or LLM (--translator llm)
  4. write X.json for the player, plus plain SRTs for other players
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import apple, llm, srt
from .sentences import split_sentences
from .transcribe import group_words

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"}
CACHE_DIR = ".listen-cache"
FORMAT_VERSION = 1


@dataclass
class Options:
    src: str = "en"
    tgt: str = "ru"
    whisper: str = "mlx-community/whisper-large-v3-mlx"
    hint: str | None = None
    fix_batch: int = 40
    translate_batch: int = 30
    workers: int = 4
    fix: bool = False
    translator: str = "apple"  # "apple" | "llm"
    force: bool = False
    retranscribe: bool = False


def find_audio(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in AUDIO_EXT and not p.name.startswith("."))


def output_path(audio: Path) -> Path:
    return audio.with_suffix(".json")


def is_done(audio: Path) -> bool:
    return output_path(audio).exists()


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _save(p: Path, data) -> None:
    p.parent.mkdir(exist_ok=True)
    srt.atomic_write(p, json.dumps(data, ensure_ascii=False, indent=1))


# (texts, src, tgt) -> translations
AppleFn = Callable[[list[str], str, str], list[str]]


def process(audio: Path, opts: Options, call: Callable[[], llm.JsonCall],
            transcribe_fn: Callable[[Path, str, str], list[dict]],
            apple_fn: AppleFn = apple.translate, log=print) -> Path:
    """`call` is a factory: the LLM client is only created when a step needs it."""
    cache = audio.parent / CACHE_DIR
    words_p = cache / f"{audio.stem}.words.json"
    fixed_p = cache / f"{audio.stem}.fixed.json"
    title = audio.stem

    # 1. recognition
    if words_p.exists() and not opts.retranscribe:
        words = _load(words_p)
        log(f"  whisper: cached ({len(words)} words)")
    else:
        words = transcribe_fn(audio, opts.whisper, opts.src)
        _save(words_p, words)
        log(f"  whisper: {len(words)} words")
    if not words:
        raise RuntimeError("no speech recognized")

    # 2. cues (+ optional LLM fix)
    cues = group_words(words)
    if not opts.fix:
        log(f"  cues: {len(cues)} (no LLM fix)")
    elif fixed_p.exists() and not (opts.force or opts.retranscribe):
        cues = _load(fixed_p)
        log(f"  fix: cached ({len(cues)} cues)")
    else:
        cues = llm.fix_cues(call(), cues, opts.src, title, opts.hint, opts.fix_batch, opts.workers)
        _save(fixed_p, cues)
        log(f"  fix: {len(cues)} cues")

    # 3. sentences + translation
    sentences = split_sentences(cues)
    if opts.translator == "llm":
        sentences = llm.translate_sentences(call(), sentences, opts.src, opts.tgt, title,
                                            opts.hint, opts.translate_batch, opts.workers)
    else:
        trs = apple_fn([s["text"] for s in sentences], opts.src, opts.tgt)
        sentences = [{**s, "tr": t} for s, t in zip(sentences, trs)]
    log(f"  translate ({opts.translator}): {len(sentences)} sentences")

    # 4. outputs
    data = build_output(audio, opts, cues, sentences)
    out = output_path(audio)
    srt.write(audio.with_suffix(".srt"), cues, "text")
    srt.write(audio.with_suffix(f".{opts.tgt}.srt"), sentences, "tr")
    srt.atomic_write(out, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return out


def build_output(audio: Path, opts: Options, cues: list[dict], sentences: list[dict]) -> dict:
    """The file the player reads. Short keys: it can be large for long audio."""
    return {
        "version": FORMAT_VERSION,
        "title": audio.stem,
        "audio": audio.name,
        "src": opts.src,
        "tgt": opts.tgt,
        "fixed": opts.fix,
        "translator": opts.translator,
        "cues": [{"s": round(c["start"], 3), "e": round(c["end"], 3), "t": c["text"]} for c in cues],
        "sentences": [{"s": s["start"], "e": s["end"], "from": s["from"], "to": s["to"],
                       "t": s["text"], "tr": s["tr"]} for s in sentences],
    }
