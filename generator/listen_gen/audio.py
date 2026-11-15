"""Make sure the player can seek the audio exactly.

Safari / iOS seek inside a VBR MP3 by its coarse Xing table of contents (100 points for
the whole file), so after a seek the audio can be tens of seconds away from what
`currentTime` says, and the subtitles drift. CBR MP3 and AAC (.m4a) seek exactly.
So a VBR MP3 gets an AAC copy X.m4a next to it, and X.json points to that copy.
"""
import os
import subprocess
from pathlib import Path

# MPEG audio Layer III tables
_BITRATES = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
             2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}

SCAN_BYTES = 4 << 20
SCAN_FRAMES = 3000


def _frame(buf: bytes, i: int):
    """(length, bitrate index, xing offset) of a Layer III frame header at i, or None."""
    if i + 4 > len(buf) or buf[i] != 0xFF or buf[i + 1] & 0xE0 != 0xE0:
        return None
    ver, layer = (buf[i + 1] >> 3) & 3, (buf[i + 1] >> 1) & 3
    br_i, sr_i, pad = buf[i + 2] >> 4, (buf[i + 2] >> 2) & 3, (buf[i + 2] >> 1) & 1
    if ver == 1 or layer != 1 or br_i in (0, 15) or sr_i == 3:
        return None
    mpeg1 = ver == 3
    br = _BITRATES[1 if mpeg1 else 2][br_i] * 1000
    sr = _RATES[ver][sr_i]
    length = (144 if mpeg1 else 72) * br // sr + pad
    mono = buf[i + 3] >> 6 == 3
    xing = 4 + (17 if mpeg1 and mono else 32 if mpeg1 else 9 if mono else 17)
    return length, br_i, xing


def _first_frame(buf: bytes, i: int) -> int:
    """Offset of the first frame that is followed by another valid frame, or -1."""
    while (i := buf.find(b"\xff", i)) != -1:
        f = _frame(buf, i)
        if f and _frame(buf, i + f[0]):
            return i
        i += 1
    return -1


def is_vbr_mp3(path: Path) -> bool:
    if path.suffix.lower() != ".mp3":
        return False
    with open(path, "rb") as fh:
        buf = fh.read(SCAN_BYTES)
    start = 0
    if buf[:3] == b"ID3" and len(buf) >= 10:  # skip the ID3v2 tag
        size = (buf[6] & 0x7F) << 21 | (buf[7] & 0x7F) << 14 | (buf[8] & 0x7F) << 7 | (buf[9] & 0x7F)
        start = 10 + size + (10 if buf[5] & 0x10 else 0)
    i = _first_frame(buf, start)
    if i < 0:
        return False
    length, _, xing = _frame(buf, i)
    tag = buf[i + xing:i + xing + 4]
    if tag == b"Xing" or buf[i + 36:i + 40] == b"VBRI":
        return True
    if tag == b"Info":  # LAME's tag for CBR
        return False
    # no tag: VBR if the bitrate changes between frames
    seen = set()
    for _ in range(SCAN_FRAMES):
        f = _frame(buf, i)
        if not f:
            break
        seen.add(f[1])
        i += f[0]
    return len(seen) > 1


def seekable_path(audio: Path) -> Path:
    """The file the player should load for this audio."""
    return audio.with_suffix(".m4a") if is_vbr_mp3(audio) else audio


def to_m4a(src: Path, dst: Path, bitrate: str = "96k") -> None:
    tmp = dst.with_name(f".{dst.name}.part")
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(src), "-map", "0:a:0",
                        "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart", "-f", "mp4", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed converting to m4a: {r.stderr.strip()[-300:]}")
    os.replace(tmp, dst)
