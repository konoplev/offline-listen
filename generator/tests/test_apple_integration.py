"""Real Swift helper + macOS Translation framework.

Always compiles the helper (needs Xcode). If the en/ru language packs are not
installed, checks that we get the friendly "install packs" error; otherwise
checks a real translation.
"""
import shutil

import pytest

from listen_gen import apple

pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not shutil.which("xcrun"), reason="needs Xcode toolchain")]


def test_real_macos_translation_or_clear_install_hint():
    texts = ["Welcome back to the show.", "It took them almost two years, and honestly, it was a mess at first."]
    try:
        out = apple.translate(texts, "en", "ru")
    except apple.LanguagePackMissing as e:
        assert "Translation Languages" in str(e)
        pytest.skip("en/ru language packs not installed — got the expected hint")
    assert len(out) == 2
    assert all(any("а" <= ch <= "я" for ch in t.lower()) for t in out), out  # Cyrillic
