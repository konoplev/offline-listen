from listen_gen import srt


def test_stamp():
    assert srt.stamp(0) == "00:00:00,000"
    assert srt.stamp(3723.4567) == "01:02:03,457"
    assert srt.stamp(-1) == "00:00:00,000"


def test_render_numbering_and_key():
    cues = [{"start": 0, "end": 1.5, "text": " Hi ", "tr": "Привет"},
            {"start": 2, "end": 3, "text": "Bye", "tr": "Пока"}]
    assert srt.render(cues) == "1\n00:00:00,000 --> 00:00:01,500\nHi\n\n2\n00:00:02,000 --> 00:00:03,000\nBye\n"
    assert "Привет" in srt.render(cues, "tr")


def test_write_is_atomic(tmp_path):
    p = tmp_path / "x.srt"
    srt.write(p, [{"start": 0, "end": 1, "text": "a"}])
    assert p.read_text(encoding="utf-8").startswith("1\n")
    assert list(tmp_path.iterdir()) == [p]
