"""listen-gen: prepare audio files for the offline player.

For every audio file X.* in FOLDER writes
    X.json        cues + sentences + translations — load it into the player with X.mp3
    X.srt         transcript (short cues, 8 words / 5 s)
    X.<tgt>.srt   translation, one entry per sentence
Translation uses the free built-in macOS translator by default (language packs:
System Settings → General → Language & Region → Translation Languages);
--translator llm uses an OpenAI-compatible model instead. --fix lets the LLM fix
speech-recognition errors before translating.
Intermediate results are cached in FOLDER/.listen-cache/.
Files that already have X.json are skipped (use --force).
"""
import argparse
import sys
import time
from pathlib import Path

from . import pipeline
from .apple import LanguagePackMissing


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="listen-gen", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--src", default="en", help="audio language (default: en)")
    ap.add_argument("--tgt", default="ru", help="translation language (default: ru)")
    ap.add_argument("--whisper", default="mlx-community/whisper-large-v3-mlx",
                    help="mlx-whisper model from the local HF cache (never downloaded)")
    ap.add_argument("--translator", choices=["apple", "llm"], default="apple",
                    help="apple: built-in macOS translator, free (default); llm: --model via API")
    ap.add_argument("--fix", action="store_true", help="let the LLM fix recognition errors (off by default)")
    ap.add_argument("--model", default="gpt-4o-mini", help="LLM model for --fix / --translator llm")
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. http://localhost:11434/v1 for Ollama")
    ap.add_argument("--hint", help="what the audio is about, names/terms — helps fix recognition")
    ap.add_argument("--workers", type=int, default=4, help="parallel LLM requests")
    ap.add_argument("--force", action="store_true", help="redo fix/translation even if X.json exists")
    ap.add_argument("--retranscribe", action="store_true", help="also re-run whisper")
    return ap.parse_args(argv)


def main(argv=None, call=None, transcribe_fn=None, apple_fn=None) -> int:
    a = parse_args(argv)
    if not a.folder.is_dir():
        print(f"not a folder: {a.folder}", file=sys.stderr)
        return 2
    files = pipeline.find_audio(a.folder)
    if not files:
        print(f"no audio files in {a.folder}", file=sys.stderr)
        return 1

    opts = pipeline.Options(src=a.src, tgt=a.tgt, whisper=a.whisper, hint=a.hint, workers=a.workers,
                            fix=a.fix, translator=a.translator, force=a.force, retranscribe=a.retranscribe)
    if transcribe_fn is None:
        from .transcribe import transcribe as transcribe_fn
    if apple_fn is None:
        from .apple import translate as apple_fn

    def get_call():  # the LLM client is created only if --fix / --translator llm need it
        nonlocal call
        if call is None:
            from .llm import openai_json_call
            call = openai_json_call(a.model, a.base_url)
        return call

    failed = []
    for audio in files:
        if pipeline.is_done(audio) and not (a.force or a.retranscribe):
            print(f"skip {audio.name} (done)")
            continue
        print(f"== {audio.name}")
        try:
            t = time.time()
            out = pipeline.process(audio, opts, get_call, transcribe_fn, apple_fn)
            print(f"  -> {out.name} in {time.time() - t:.0f}s")
        except LanguagePackMissing as e:
            print(f"  {e}", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001 — keep going with the other files
            print(f"  FAILED: {e}", file=sys.stderr)
            failed.append(audio.name)
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
