from listen_gen.sentences import MAX_SENTENCE_WORDS, is_sentence_end, split_sentences


def cue(text, start=0.0, end=None):
    n = len(text.split())
    return {"start": start, "end": end if end is not None else start + n, "text": text}


def test_sentence_spanning_several_cues():
    cues = [cue("It took them almost two", 0), cue("years, and honestly it was", 5), cue("a mess. Let's start", 10)]
    s = split_sentences(cues)
    assert [x["text"] for x in s] == [
        "It took them almost two years, and honestly it was a mess.",
        "Let's start",
    ]
    assert s[0]["from"] == [0, 0] and s[0]["to"] == [2, 1]
    assert s[1]["from"] == [2, 2] and s[1]["to"] == [2, 3]


def test_several_sentences_in_one_cue():
    s = split_sentences([cue("Hi. How are you? Fine!")])
    assert [x["text"] for x in s] == ["Hi.", "How are you?", "Fine!"]
    assert [(x["from"], x["to"]) for x in s] == [([0, 0], [0, 0]), ([0, 1], [0, 3]), ([0, 4], [0, 4])]


def test_every_word_belongs_to_exactly_one_sentence():
    cues = [cue("One two. Three"), cue("four five? Six"), cue("seven eight")]
    covered = []
    for x in split_sentences(cues):
        (c0, w0), (c1, w1) = x["from"], x["to"]
        for ci in range(c0, c1 + 1):
            n = len(cues[ci]["text"].split())
            lo = w0 if ci == c0 else 0
            hi = w1 if ci == c1 else n - 1
            covered += [(ci, wi) for wi in range(lo, hi + 1)]
    expected = [(ci, wi) for ci, c in enumerate(cues) for wi in range(len(c["text"].split()))]
    assert covered == expected


def test_abbreviations_do_not_end_sentence():
    s = split_sentences([cue("We talk with Dr. Smith and Mr. Jones today.")])
    assert len(s) == 1


def test_closing_quotes_and_brackets():
    assert is_sentence_end('done."')
    assert is_sentence_end("done.)")
    assert is_sentence_end("really?”")
    assert not is_sentence_end("word,")
    assert not is_sentence_end("e.g.")


def test_run_on_text_is_split_at_a_comma():
    words = [f"w{i}" for i in range(MAX_SENTENCE_WORDS + 10)]
    words[30] += ","
    s = split_sentences([cue(" ".join(words))])
    assert s[0]["text"].endswith("w30,")
    assert len(s[0]["text"].split()) == 31
    assert all(len(x["text"].split()) <= MAX_SENTENCE_WORDS for x in s)


def test_run_on_text_without_commas_is_split_hard():
    s = split_sentences([cue(" ".join(f"w{i}" for i in range(MAX_SENTENCE_WORDS * 2)))])
    assert [len(x["text"].split()) for x in s] == [MAX_SENTENCE_WORDS, MAX_SENTENCE_WORDS]


def test_times_are_interpolated_inside_cues():
    # cue 0: 4 words over 0..4s, cue 1: 4 words over 10..14s
    cues = [cue("a b c. d", 0, 4), cue("e f. g h", 10, 14)]
    s = split_sentences(cues)
    assert (s[0]["start"], s[0]["end"]) == (0.0, 3.0)    # a..c.
    assert (s[1]["start"], s[1]["end"]) == (3.0, 12.0)   # d (cue0 word 3) .. f. (cue1 word 1)
    assert (s[2]["start"], s[2]["end"]) == (12.0, 14.0)


def test_empty():
    assert split_sentences([]) == []
