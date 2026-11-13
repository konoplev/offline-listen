"""macOS translator wrapper: protocol with the Swift helper, errors, compile cache.

The helper is replaced by a small Python script speaking the same stdin/stdout
protocol; the real helper is exercised in test_apple_integration.py.
"""
import json
import stat
import sys
import textwrap

import pytest

from listen_gen import apple


def fake_helper(tmp_path, body: str):
    p = tmp_path / "helper"
    p.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def test_sends_texts_and_returns_translations(tmp_path):
    helper = fake_helper(tmp_path, """
        import json, sys
        d = json.load(sys.stdin)
        print(json.dumps({"translations": [f"{d['src']}>{d['tgt']}:{t}" for t in d["texts"]]}))
    """)
    assert apple.translate(["Hi.", "Привет — ok"], "en", "ru", helper) == ["en>ru:Hi.", "en>ru:Привет — ok"]


def test_empty_input_does_not_run_helper(tmp_path):
    assert apple.translate([], "en", "ru", tmp_path / "does-not-exist") == []


@pytest.mark.parametrize("code, exc, text", [
    (3, apple.LanguagePackMissing, "Language & Region → Translation Languages"),
    (4, apple.AppleTranslateError, "cannot translate en→ru"),
    (1, apple.AppleTranslateError, "macOS translation failed: kaboom"),
])
def test_helper_errors(tmp_path, code, exc, text):
    helper = fake_helper(tmp_path, f"""
        import sys
        sys.stdin.read()
        sys.stderr.write("kaboom")
        sys.exit({code})
    """)
    with pytest.raises(exc, match=text):
        apple.translate(["x"], "en", "ru", helper)


def test_wrong_count_or_empty_translation_is_an_error(tmp_path):
    short = fake_helper(tmp_path, """
        import json, sys; sys.stdin.read(); print(json.dumps({"translations": ["a"]}))
    """)
    with pytest.raises(apple.AppleTranslateError, match="expected 2"):
        apple.translate(["x", "y"], "en", "ru", short)
    empty = fake_helper(tmp_path, """
        import json, sys; sys.stdin.read(); print(json.dumps({"translations": ["a", " "]}))
    """)
    with pytest.raises(apple.AppleTranslateError, match=r"empty translations for items \[1\]"):
        apple.translate(["x", "y"], "en", "ru", empty)


def test_helper_is_compiled_once_and_cached_by_source_hash(tmp_path, monkeypatch):
    src = tmp_path / "a.swift"
    src.write_text("v1")
    monkeypatch.setattr(apple, "SOURCE", src)
    monkeypatch.setattr(apple, "CACHE_DIR", tmp_path / "cache")
    runs = []

    def fake_run(cmd, **kw):
        runs.append(cmd)
        out = cmd[cmd.index("-o") + 1]
        open(out, "w").write("bin")
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(apple.subprocess, "run", fake_run)
    first = apple.helper_path()
    assert apple.helper_path() == first and len(runs) == 1
    assert runs[0][:3] == ["xcrun", "swiftc", "-O"]
    src.write_text("v2")
    assert apple.helper_path() != first and len(runs) == 2


def test_compile_error_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(apple, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(apple.subprocess, "run",
                        lambda cmd, **kw: type("R", (), {"returncode": 1, "stderr": "no Translation module"})())
    with pytest.raises(apple.AppleTranslateError, match="no Translation module"):
        apple.helper_path()
