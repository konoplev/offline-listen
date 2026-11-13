"""Split the (fixed) cue stream into sentences.

Cues are short display units (8 words / 5 s) that cut sentences anywhere.
For translation we need whole sentences, so we walk the words of all cues
and close a sentence at sentence-final punctuation. Each sentence remembers
where it starts and ends as (cue index, word index in that cue); the player
uses that to find the sentence for a tapped word.

Words are whitespace-separated tokens — the player splits cue text the same
way (/\\S+/g), so the indices line up.
"""
MAX_SENTENCE_WORDS = 40  # force a split in run-on text without punctuation
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "vs.", "etc.", "e.g.", "i.e.",
                 "jr.", "sr.", "u.s.", "no."}
_CLOSERS = "\"'”’)»]"


def is_sentence_end(word: str) -> bool:
    w = word.rstrip(_CLOSERS)
    return w.endswith((".", "?", "!", "…")) and word.lower() not in ABBREVIATIONS


def _soft_break(word: str) -> bool:
    return word.rstrip(_CLOSERS).endswith((",", ";", ":", "—", "–"))


def split_sentences(cues: list[dict]) -> list[dict]:
    """cues [{"start","end","text"}] -> sentences
    [{"from": [ci, wi], "to": [ci, wi], "text", "start", "end"}]."""
    words = [(ci, wi, w) for ci, c in enumerate(cues) for wi, w in enumerate(c["text"].split())]
    sentences, cur = [], []

    def close(n):
        part = cur[:n]
        del cur[:n]
        (c0, w0, _), (c1, w1, _) = part[0], part[-1]
        sentences.append({
            "from": [c0, w0],
            "to": [c1, w1],
            "text": " ".join(w for _, _, w in part),
            "start": _word_time(cues[c0], w0, start=True),
            "end": _word_time(cues[c1], w1, start=False),
        })

    for item in words:
        cur.append(item)
        if is_sentence_end(item[2]):
            close(len(cur))
        elif len(cur) >= MAX_SENTENCE_WORDS:
            cut = next((k + 1 for k in range(len(cur) - 1, len(cur) // 2, -1) if _soft_break(cur[k][2])), len(cur))
            close(cut)
    if cur:
        close(len(cur))
    return sentences


def _word_time(cue: dict, wi: int, start: bool) -> float:
    """Word timings are lost after the LLM fix (word count may change), so
    estimate by the word's position inside its cue."""
    n = max(1, len(cue["text"].split()))
    frac = (wi if start else wi + 1) / n
    return round(cue["start"] + (cue["end"] - cue["start"]) * frac, 3)
