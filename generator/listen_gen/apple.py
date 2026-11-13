"""Translation with the built-in macOS translator (free, on-device).

The Swift helper (apple_translate.swift) is compiled on first use with the
Xcode toolchain and cached by source hash in ~/Library/Caches/listen-gen/.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name("apple_translate.swift")
CACHE_DIR = Path.home() / "Library/Caches/listen-gen"

INSTALL_HINT = ("Translation languages {src}→{tgt} are not downloaded. Download them in System Settings → "
                "General → Language & Region → Translation Languages, or use --translator llm.")


class AppleTranslateError(RuntimeError):
    pass


class LanguagePackMissing(AppleTranslateError):
    """Same for every file — the CLI stops instead of failing each one."""


def helper_path() -> Path:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()[:12]
    binary = CACHE_DIR / f"apple-translate-{digest}"
    if not binary.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = binary.with_name(binary.name + f".{os.getpid()}.tmp")
        print("  compiling macOS translation helper (once)…", file=sys.stderr)
        r = subprocess.run(["xcrun", "swiftc", "-O", "-o", str(tmp), str(SOURCE)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AppleTranslateError(f"cannot compile {SOURCE.name} (needs Xcode / macOS 26):\n{r.stderr.strip()}")
        tmp.replace(binary)
    return binary


def translate(texts: list[str], src: str, tgt: str, binary: Path | None = None) -> list[str]:
    if not texts:
        return []
    binary = binary or helper_path()
    r = subprocess.run([str(binary)], input=json.dumps({"src": src, "tgt": tgt, "texts": texts}),
                       capture_output=True, text=True)
    if r.returncode == 3:
        raise LanguagePackMissing(INSTALL_HINT.format(src=src, tgt=tgt))
    if r.returncode == 4:
        raise AppleTranslateError(f"macOS cannot translate {src}→{tgt}; use --translator llm")
    if r.returncode != 0:
        raise AppleTranslateError(f"macOS translation failed: {r.stderr.strip()}")
    out = json.loads(r.stdout)["translations"]
    if len(out) != len(texts):
        raise AppleTranslateError(f"expected {len(texts)} translations, got {len(out)}")
    empty = [i for i, t in enumerate(out) if not t.strip()]
    if empty:
        raise AppleTranslateError(f"empty translations for items {empty[:10]}")
    return out
