import pytest

from listen_gen import llm
from conftest import FakeLLM, parse_items


def test_fix_cues_keeps_timings_and_replaces_text():
    fake = FakeLLM(fix=lambda t: t.replace("Kuber Netties", "Kubernetes"))
    cues = [{"start": 1.0, "end": 2.0, "text": "about Kuber Netties"}, {"start": 2.0, "end": 3.0, "text": "ok"}]
    out = llm.fix_cues(fake, cues, "en", "ep", None)
    assert out == [{"start": 1.0, "end": 2.0, "text": "about Kubernetes"}, {"start": 2.0, "end": 3.0, "text": "ok"}]


def test_batches_cover_all_items_in_order():
    fake = FakeLLM()
    texts = [f"t{i}" for i in range(95)]
    out = llm.run_batches(fake, "fix", texts, "text", "H", batch=40, workers=3, ctx=2, label="x")
    assert out == texts
    assert len(fake.calls) == 3
    assert [parse_items(u)[0][0] for _, u in fake.calls] == [0, 40, 80]


def test_prompt_has_header_and_neighbour_context():
    fake = FakeLLM()
    texts = [f"t{i}" for i in range(10)]
    llm.run_batches(fake, "fix", texts, "text", "Title: ep", batch=4, workers=1, ctx=2, label="x")
    middle = fake.calls[1][1]
    assert middle.startswith("Title: ep")
    assert "Context before:\n- t2\n- t3" in middle
    assert "Context after:\n- t8\n- t9" in middle
    assert [i for i, _ in parse_items(middle)] == [4, 5, 6, 7]
    assert "Context before" not in fake.calls[0][1]
    assert "Context after" not in fake.calls[2][1]


def test_retry_asks_only_for_missing_ids_and_keeps_good_answers():
    replies = [{"items": [{"id": 0, "tr": "a"}, {"id": 2, "tr": "c"}]},  # dropped id 1
               {"items": [{"id": 1, "tr": "b"}]}]
    prompts = []

    def call(system, user):
        prompts.append(user)
        return replies[len(prompts) - 1]

    assert llm.run_batches(call, "s", ["x", "y", "z"], "tr", "H", 10, 1, 1, "x") == ["a", "b", "c"]
    assert [i for i, _ in parse_items(prompts[0])] == [0, 1, 2]
    assert [i for i, _ in parse_items(prompts[1])] == [1]
    assert "Return all 1 items (ids: 1)" in prompts[1]
    assert "Context before:\n- x" in prompts[1]


def test_prompt_states_expected_count():
    fake = FakeLLM()
    llm.run_batches(fake, "fix", ["a", "b"], "text", "H", 10, 1, 0, "x")
    assert "Return all 2 items (ids: 0, 1), including greetings and short phrases." in fake.calls[0][1]


def test_ignores_unknown_ids_and_empty_values():
    replies = [{"items": [{"id": 0, "text": " "}, {"id": 7, "text": "stray"}]},
               ValueError("not json"),
               {"items": [{"id": 0, "text": "ok"}]}]

    def call(system, user):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    assert llm.run_batches(call, "s", ["x"], "text", "H", 10, 1, 0, "x") == ["ok"]


def test_gives_up_after_attempts():
    calls = []

    def call(system, user):
        calls.append(user)
        return {"items": []}

    with pytest.raises(RuntimeError, match=r"missing ids \[0\]"):
        llm.run_batches(call, "s", ["x"], "text", "H", 10, 1, 0, "x", attempts=2)
    assert len(calls) == 2


def test_translate_sentences_adds_tr_and_uses_language_names():
    fake = FakeLLM()
    out = llm.translate_sentences(fake, [{"text": "Hello."}], "en", "ru", "ep", "a podcast")
    assert out == [{"text": "Hello.", "tr": "RU(Hello.)"}]
    system, user = fake.calls[0]
    assert "from a English transcript into Russian" in system
    assert "Notes about the content: a podcast" in user


def test_unknown_language_code_is_passed_through():
    assert llm.lang_name("xx") == "xx"
