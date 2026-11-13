import re

import pytest

ITEM_RE = re.compile(r"^(\d+): (.*)$")


def parse_items(user_prompt: str) -> list[tuple[int, str]]:
    """Extract "id: text" lines from the Items: section of a prompt."""
    section = user_prompt.split("Items:", 1)[1].split("\n\nContext after:", 1)[0]
    return [(int(m[1]), m[2]) for line in section.splitlines() if (m := ITEM_RE.match(line))]


class FakeLLM:
    """Stands in for openai_json_call. Fix: returns text unchanged (or via `fix`).
    Translate: returns "RU(<text>)". Records every call."""

    def __init__(self, fix=lambda t: t, fail_translate=False):
        self.fix = fix
        self.fail_translate = fail_translate
        self.calls = []

    def __call__(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        items = parse_items(user)
        if "Translate" in system:
            if self.fail_translate:
                raise RuntimeError("boom")
            return {"items": [{"id": i, "tr": f"RU({t})"} for i, t in items]}
        return {"items": [{"id": i, "text": self.fix(t)} for i, t in items]}

    def count(self, kind: str) -> int:
        return sum(1 for s, _ in self.calls if (kind == "translate") == ("Translate" in s))


@pytest.fixture
def fake_llm():
    return FakeLLM()


def make_words(text: str, step: float = 0.4, dur: float = 0.3, start: float = 0.0) -> list[dict]:
    return [{"start": round(start + i * step, 3), "end": round(start + i * step + dur, 3), "word": w}
            for i, w in enumerate(text.split())]
