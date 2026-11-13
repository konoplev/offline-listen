"""Real mlx-whisper on a short clip spoken by macOS `say`.

Skipped when the model isn't in the local HF cache (it is never downloaded)
or `say`/`ffmpeg` are missing. Run only these with: pytest -m slow
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from listen_gen.transcribe import group_words, transcribe

MODEL = "mlx-community/whisper-large-v3-mlx"
CACHE = Path.home() / ".cache/huggingface/hub" / ("models--" + MODEL.replace("/", "--"))

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (CACHE / "snapshots").exists(), reason=f"{MODEL} not in local cache"),
    pytest.mark.skipif(not (shutil.which("say") and shutil.which("ffmpeg")), reason="needs say + ffmpeg"),
]


def test_transcribes_say_clip(tmp_path):
    aiff, mp3 = tmp_path / "a.aiff", tmp_path / "a.mp3"
    subprocess.run(["say", "-v", "Samantha", "-o", str(aiff),
                    "Welcome back to the show. Today we talk about the weather in London."], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(aiff), str(mp3)], check=True)

    words = transcribe(mp3, MODEL, "en")
    text = " ".join(w["word"] for w in words).lower()
    assert "welcome" in text and "london" in text
    assert all(w["start"] <= w["end"] for w in words)
    cues = group_words(words)
    assert len(cues) >= 2 and all(len(c["text"].split()) <= 8 for c in cues)
