"""Her shelf — the things he put there.

    mikasa/shelf/
      chitthi-1.txt
      shayari.txt
      uski/            ← what she wrote herself, if he lets her keep it

READ, NEVER EDITED. A letter he wrote is not source material and not
something to be summarised into a nicer version of itself. `read()` returns
the file's text unchanged, wrapped in nothing, and the prompt tells her to
say it exactly as it is.

EMPTY IS A VALID STATE. On a fresh install there is nothing on the shelf, and
she must not fill the silence with something she made up. `list()` returns an
empty list and she simply has nothing to offer.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parent.parent

SHELF  = ROOT / "shelf"
HER    = SHELF / "uski"
EXTS   = {".txt", ".md"}
MAXLEN = 4000


def _ensure() -> None:
    try:
        SHELF.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def pieces() -> list[dict]:
    """Everything he put there, newest last. Never her own folder."""
    _ensure()
    out = []
    try:
        for p in sorted(SHELF.iterdir()):
            if not p.is_file() or p.suffix.lower() not in EXTS:
                continue
            try:
                st = p.stat()
                out.append({"name": p.stem, "path": p,
                            "size": st.st_size, "at": st.st_mtime})
            except Exception:
                continue
    except Exception:
        pass
    return out


def list_block() -> str:
    got = pieces()
    if not got:
        return ""
    return "\n".join(f"- {p['name']}" for p in got)


def read(name: str) -> dict | None:
    """One piece, verbatim. `name` may be the stem or the filename."""
    _ensure()
    want = (name or "").strip().lower()
    if not want:
        return None
    for p in SHELF.iterdir():
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        if p.stem.lower() == want or p.name.lower() == want:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
            return {"name": p.stem, "text": text[:MAXLEN],
                    "at": time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))}
    return None


def count() -> int:
    return len(pieces())
