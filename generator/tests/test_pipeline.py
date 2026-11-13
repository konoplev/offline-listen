import json

import pytest

from listen_gen import cli, pipeline
from listen_gen.apple import AppleTranslateError, LanguagePackMissing
from conftest import FakeLLM, make_words

SPEECH = ("Welcome back to the show. Today we talk with Dr. Smith about the Kuber Netties "
          "migration at Spotify. It took them almost two years, and honestly, it was a mess at first.")


class FakeWhisper:
    def __init__(self, text=SPEECH):
        self.text = text
        self.calls = 0

    def __call__(self, audio, model, lang):
        self.calls += 1
        assert model == "mlx-community/whisper-large-v3-mlx" and lang == "en"
        return make_words(self.text)


class FakeApple:
    """Stands in for the macOS translator."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, texts, src, tgt):
        self.calls.append((list(texts), src, tgt))
        if self.fail:
            raise self.fail
        return [f"MAC({t})" for t in texts]


class NoLLM:
    """LLM factory stand-in that must never be used."""

    def __call__(self, *a):
        raise AssertionError("LLM must not be called")


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "ep1.mp3").write_bytes(b"fake")
    (tmp_path / "notes.txt").write_text("ignore me")
    return tmp_path


def run(folder, *args, llm=None, whisper=None, apple=None):
    llm = llm if llm is not None else FakeLLM(fix=lambda t: t.replace("Kuber Netties", "Kubernetes"))
    whisper = whisper or FakeWhisper()
    apple = apple or FakeApple()
    code = cli.main([str(folder), *args], call=llm, transcribe_fn=whisper, apple_fn=apple)
    return code, llm, whisper, apple


def load(folder, name="ep1.json"):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def check_positions(data):
    for s in data["sentences"]:
        (c0, w0), (c1, w1) = s["from"], s["to"]
        assert data["cues"][c0]["t"].split()[w0] == s["t"].split()[0]
        assert data["cues"][c1]["t"].split()[w1] == s["t"].split()[-1]


def test_default_is_free_macos_translation_without_llm(folder):
    code, _, whisper, apple = run(folder, llm=NoLLM())
    assert code == 0 and whisper.calls == 1
    data = load(folder)
    assert data["version"] == 1 and data["audio"] == "ep1.mp3" and data["title"] == "ep1"
    assert (data["src"], data["tgt"], data["fixed"], data["translator"]) == ("en", "ru", False, "apple")

    # cues: raw whisper text, 8 words each
    assert all(len(c["t"].split()) <= 8 for c in data["cues"])
    assert "Kuber Netties" in " ".join(c["t"] for c in data["cues"])

    # sentences across cues, translated by macOS in one call
    texts = [s["t"] for s in data["sentences"]]
    assert texts == [
        "Welcome back to the show.",
        "Today we talk with Dr. Smith about the Kuber Netties migration at Spotify.",
        "It took them almost two years, and honestly, it was a mess at first.",
    ]
    assert apple.calls == [(texts, "en", "ru")]
    assert [s["tr"] for s in data["sentences"]] == [f"MAC({t})" for t in texts]
    check_positions(data)

    assert (folder / "ep1.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> ")
    assert "MAC(Welcome back to the show.)" in (folder / "ep1.ru.srt").read_text(encoding="utf-8")
    assert (folder / ".listen-cache" / "ep1.words.json").exists()
    assert not (folder / ".listen-cache" / "ep1.fixed.json").exists()


def test_llm_client_is_not_even_created_by_default(folder, monkeypatch):
    from listen_gen import llm as llm_mod
    monkeypatch.setattr(llm_mod, "openai_json_call", lambda *a: (_ for _ in ()).throw(AssertionError("created")))
    code = cli.main([str(folder)], transcribe_fn=FakeWhisper(), apple_fn=FakeApple())
    assert code == 0


def test_fix_flag_uses_llm_for_fixing_and_macos_for_translation(folder):
    code, llm, _, apple = run(folder, "--fix")
    assert code == 0
    data = load(folder)
    assert data["fixed"] is True and data["translator"] == "apple"
    assert "Kubernetes" in " ".join(c["t"] for c in data["cues"])
    assert llm.count("fix") == 1 and llm.count("translate") == 0
    assert "Kubernetes" in apple.calls[0][0][1]
    assert (folder / ".listen-cache" / "ep1.fixed.json").exists()
    check_positions(data)


def test_translator_llm_fallback(folder):
    code, llm, _, apple = run(folder, "--translator", "llm")
    assert code == 0 and apple.calls == []
    assert llm.count("fix") == 0 and llm.count("translate") == 1
    data = load(folder)
    assert data["translator"] == "llm" and data["fixed"] is False
    assert all(s["tr"] == f"RU({s['t']})" for s in data["sentences"])


def test_fix_and_llm_translation_together(folder):
    code, llm, _, apple = run(folder, "--fix", "--translator", "llm")
    assert code == 0 and apple.calls == []
    assert llm.count("fix") == 1 and llm.count("translate") == 1
    data = load(folder)
    assert "Today we talk with Dr. Smith about the Kubernetes migration at Spotify." in [s["t"] for s in data["sentences"]]


def test_done_files_are_skipped(folder):
    run(folder)
    code, _, whisper, apple = run(folder)
    assert code == 0 and whisper.calls == 0 and apple.calls == []


def test_force_redoes_translation_but_not_whisper(folder):
    run(folder)
    code, _, whisper, apple = run(folder, "--force")
    assert code == 0 and whisper.calls == 0 and len(apple.calls) == 1


def test_force_with_fix_redoes_fix(folder):
    run(folder, "--fix")
    code, llm, whisper, _ = run(folder, "--fix", "--force")
    assert code == 0 and whisper.calls == 0 and llm.count("fix") == 1


def test_retranscribe_reruns_whisper(folder):
    run(folder)
    code, _, whisper, _ = run(folder, "--retranscribe")
    assert code == 0 and whisper.calls == 1


def test_failed_translation_resumes_from_fix_cache(folder):
    code, _, _, _ = run(folder, "--fix", apple=FakeApple(fail=AppleTranslateError("boom")))
    assert code == 1
    assert not (folder / "ep1.json").exists()
    assert (folder / ".listen-cache" / "ep1.fixed.json").exists()

    code, llm, whisper, apple = run(folder, "--fix")
    assert code == 0 and whisper.calls == 0
    assert llm.count("fix") == 0 and len(apple.calls) == 1
    assert (folder / "ep1.json").exists()


def test_missing_language_packs_stop_the_whole_run(folder):
    (folder / "ep2.mp3").write_bytes(b"fake")
    apple = FakeApple(fail=LanguagePackMissing("download language packs"))
    code, _, whisper, apple = run(folder, apple=apple)
    assert code == 1
    assert len(apple.calls) == 1 and whisper.calls == 1  # stopped after the first file
    assert not (folder / "ep1.json").exists() and not (folder / "ep2.json").exists()


def test_one_failing_file_does_not_stop_the_others(folder):
    (folder / "ep2.m4a").write_bytes(b"fake")

    def whisper(audio, model, lang):
        if audio.name == "ep1.mp3":
            raise RuntimeError("broken audio")
        return make_words("Hello there.")

    code, _, _, _ = run(folder, whisper=whisper)
    assert code == 1
    assert not (folder / "ep1.json").exists()
    assert (folder / "ep2.json").exists()


def test_no_speech_is_an_error(folder):
    code, _, _, _ = run(folder, whisper=lambda *a: [])
    assert code == 1 and not (folder / "ep1.json").exists()


def test_languages_and_hint_flags(folder):
    seen = {}

    def whisper(audio, model, lang):
        seen["lang"] = lang
        return make_words("Hallo Welt.")

    code, llm, _, apple = run(folder, "--src", "de", "--tgt", "uk", "--hint", "Nachrichten", "--fix", whisper=whisper)
    assert code == 0 and seen["lang"] == "de"
    assert apple.calls[0][1:] == ("de", "uk")
    assert (folder / "ep1.uk.srt").exists()
    data = load(folder)
    assert (data["src"], data["tgt"]) == ("de", "uk")
    assert any("Notes about the content: Nachrichten" in u for _, u in llm.calls)


def test_find_audio_ignores_hidden_and_non_audio(tmp_path):
    for n in ["a.mp3", "b.M4A", ".hidden.mp3", "c.json", "d.srt"]:
        (tmp_path / n).write_bytes(b"")
    assert [p.name for p in pipeline.find_audio(tmp_path)] == ["a.mp3", "b.M4A"]


def test_empty_folder_and_missing_folder(tmp_path):
    assert cli.main([str(tmp_path)], call=FakeLLM(), transcribe_fn=FakeWhisper(), apple_fn=FakeApple()) == 1
    assert cli.main([str(tmp_path / "nope")], call=FakeLLM(), transcribe_fn=FakeWhisper(), apple_fn=FakeApple()) == 2
