"""Speech recognition with mlx-whisper + grouping words into short cues.

Grouping rule: a cue is closed once it has 8 words or spans 5 seconds.
"""
import os
from pathlib import Path

MAX_WORDS = 8
MAX_DURATION = 5.0


def transcribe(audio: Path, model: str, language: str) -> list[dict]:
    """Returns recognized words: [{"start", "end", "word"}]."""
    # only use models already in the local HF cache, never download
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    import mlx_whisper  # heavy import, only when actually transcribing

    result = mlx_whisper.transcribe(
        str(audio),
        path_or_hf_repo=model,
        language=language,
        word_timestamps=True,
        condition_on_previous_text=False,  # avoids repetition loops on long audio
        verbose=None,
    )
    return [
        {"start": w["start"], "end": w["end"], "word": w["word"].strip()}
        for seg in result["segments"]
        for w in seg.get("words", [])
        if w["word"].strip()
    ]


def _make_cue(words: list[dict]) -> dict:
    return {
        "start": words[0]["start"],
        "end": words[-1]["end"],
        "text": " ".join(w["word"].strip() for w in words),
    }


def group_words(words: list[dict]) -> list[dict]:
    """Words -> cues [{"start", "end", "text"}]."""
    cues, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= MAX_WORDS or w["end"] - cur[0]["start"] >= MAX_DURATION:
            cues.append(_make_cue(cur))
            cur = []
    if cur:
        cues.append(_make_cue(cur))
    return cues
