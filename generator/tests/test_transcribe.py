from listen_gen.transcribe import group_words
from conftest import make_words


def test_closes_cue_after_8_words():
    cues = group_words(make_words(" ".join(f"w{i}" for i in range(20))))
    assert [c["text"].split() for c in cues] == [
        [f"w{i}" for i in range(0, 8)],
        [f"w{i}" for i in range(8, 16)],
        [f"w{i}" for i in range(16, 20)],
    ]


def test_closes_cue_after_5_seconds():
    # one word per second: word 5 ends at 5.9s -> 5.9 - 0 >= 5 closes the cue (6 words)
    cues = group_words(make_words("a b c d e f g h", step=1.0, dur=0.9))
    assert [len(c["text"].split()) for c in cues] == [6, 2]
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 5.9
    assert cues[1]["start"] == 6.0


def test_cue_times_come_from_first_and_last_word():
    cues = group_words(make_words("one two three", start=10.0))
    assert cues == [{"start": 10.0, "end": 11.1, "text": "one two three"}]


def test_words_are_stripped_and_joined_with_single_spaces():
    words = [{"start": 0, "end": 0.2, "word": " Hello,"}, {"start": 0.3, "end": 0.5, "word": " world. "}]
    assert group_words(words)[0]["text"] == "Hello, world."


def test_no_words_no_cues():
    assert group_words([]) == []
