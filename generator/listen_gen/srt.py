"""SRT writer. A cue is a dict with "start", "end" (seconds) and a text field."""
from pathlib import Path


def stamp(t: float) -> str:
    ms = round(max(0.0, t) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def render(cues: list[dict], key: str = "text") -> str:
    return "\n".join(
        f"{n}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c[key].strip()}\n"
        for n, c in enumerate(cues, 1)
    )


def write(path: Path, cues: list[dict], key: str = "text") -> None:
    atomic_write(path, render(cues, key))


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
