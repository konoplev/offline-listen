import json
import shutil
import subprocess

import pytest

from listen_gen import audio, cli, pipeline
from test_pipeline import FakeApple, FakeWhisper, NoLLM

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")

# 2 s of silence, then 2 s of noise: a VBR encoder picks very different bitrates
SOURCE = "anullsrc=r=44100:cl=stereo:d=2[a];anoisesrc=d=2:a=0.3[b];[a][b]concat=n=2:v=0:a=1"


def mp3(path, *enc):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", SOURCE, "-ac", "2",
                    "-c:a", "libmp3lame", *enc, str(path)], check=True)
    return path


def codec(path):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=codec_name", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.parametrize("enc, vbr", [
    (["-q:a", "4"], True),                       # VBR with Xing tag
    (["-q:a", "4", "-write_xing", "0"], True),   # VBR without tag: bitrate changes
    (["-b:a", "64k"], False),                    # CBR with LAME "Info" tag
    (["-b:a", "64k", "-write_xing", "0"], False),
    (["-b:a", "64k", "-ac", "1"], False),        # mono: different tag offset
    (["-q:a", "4", "-ac", "1"], True),
    (["-q:a", "4", "-ar", "22050"], True),       # MPEG-2: different tag offset
])
def test_detects_vbr(tmp_path, enc, vbr):
    assert audio.is_vbr_mp3(mp3(tmp_path / "a.mp3", *enc)) is vbr


def test_non_mp3_and_garbage_are_left_alone(tmp_path):
    (tmp_path / "x.mp3").write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x05hello" + b"\xff" * 50)
    (tmp_path / "y.mp3").write_bytes(b"")
    (tmp_path / "z.m4a").write_bytes(b"whatever")
    for n in ["x.mp3", "y.mp3", "z.m4a"]:
        assert audio.seekable_path(tmp_path / n) == tmp_path / n


def run(folder, *args):
    return cli.main([str(folder), *args], call=NoLLM(), transcribe_fn=FakeWhisper(), apple_fn=FakeApple())


def test_vbr_mp3_gets_an_m4a_copy_the_player_loads(tmp_path):
    mp3(tmp_path / "ep1.mp3", "-q:a", "4")
    assert run(tmp_path) == 0
    data = json.loads((tmp_path / "ep1.json").read_text(encoding="utf-8"))
    assert data["audio"] == "ep1.m4a" and data["title"] == "ep1"
    assert codec(tmp_path / "ep1.m4a") == "aac"
    assert not list(tmp_path.glob(".*.part"))
    # the copy is not a second episode, also with --force
    assert pipeline.find_audio(tmp_path) == [tmp_path / "ep1.mp3"]
    assert run(tmp_path, "--force") == 0
    assert sorted(p.name for p in tmp_path.glob("ep1*")) == ["ep1.json", "ep1.m4a", "ep1.mp3", "ep1.ru.srt", "ep1.srt"]


def test_cbr_mp3_is_used_as_is(tmp_path):
    mp3(tmp_path / "ep1.mp3", "-b:a", "64k")
    assert run(tmp_path) == 0
    assert json.loads((tmp_path / "ep1.json").read_text(encoding="utf-8"))["audio"] == "ep1.mp3"
    assert not (tmp_path / "ep1.m4a").exists()


def test_failed_conversion_fails_the_file(tmp_path, monkeypatch):
    mp3(tmp_path / "ep1.mp3", "-q:a", "4")
    monkeypatch.setattr(audio, "to_m4a", lambda s, d: (_ for _ in ()).throw(RuntimeError("ffmpeg failed")))
    assert run(tmp_path) == 1
    assert not (tmp_path / "ep1.json").exists()
