"""What Mikasa remembers — which is most of what she is.

FOUR STORES, because they decay differently.

    facts.json     what he told her about himself, in HIS words, dated
    threads.json   things left open -- "kal exam hai", "usne reply nahi kiya"
    journal.json   one line per night: what it was about, how it ended
    mood.jsonl     the trend in numbers, not a transcript

WHY FACTS ARE STORED VERBATIM
    "Meri behen ka naam Riya hai" survives being summarised.
    "Uski behen Riya, jisse wo 4 saal se nahi boli" does not -- the summary
    keeps the name and loses the thing that made it worth knowing. So the line
    he said is kept exactly, and the model reads it back in full.

WHY NOTHING EXPIRES
    Every other thing on this machine forgets on a schedule. She does not.
    A memory that quietly ages out is a memory that makes her wrong about him
    six weeks later, in a way he will notice and not be able to explain.

MEMORY IS HERS TO MANAGE
    He can say "ye yaad rakhna" and she may not write it down -- not out of
    stubbornness, but because a person decides what stays with them. The
    prompt says so. The code therefore offers `remember()` and does not force
    it; what the model chooses to keep, it keeps by calling the tool.

    The one exception is the night itself: the journal is written whatever she
    decides, because it is the record of what happened rather than a fact she
    has chosen to keep.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parent

STORE = ROOT / "config" / "memory"

FACTS   = STORE / "facts.json"
THREADS = STORE / "threads.json"
JOURNAL = STORE / "journal.json"

MAX_FACTS   = 600        # a year of heavy talking; not a limit he will reach
MAX_THREADS = 40
MAX_JOURNAL = 400


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path: Path, data) -> None:
    try:
        STORE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:
        print(f"[Mikasa] memory write failed: {type(e).__name__}: {e}")


def _now() -> dict:
    n = datetime.now()
    return {"date": n.strftime("%Y-%m-%d"), "at": n.strftime("%H:%M"),
            "ts": int(n.timestamp())}


# ── facts ────────────────────────────────────────────────────────────────────
def remember(text: str, kind: str = "about_him") -> dict | None:
    """Keep one thing he said, in his own words."""
    text = (text or "").strip()
    if not text:
        return None
    data = _read(FACTS, {"facts": []})
    if not isinstance(data, dict):
        data = {"facts": []}
    facts = data.get("facts", [])
    if not isinstance(facts, list):
        facts = []
    # the same sentence twice is noise, not memory
    for f in facts[-40:]:
        if isinstance(f, dict) and f.get("text", "").strip().lower() == text.lower():
            return f
    entry = dict(_now(), text=text[:600], kind=kind or "about_him")
    facts.append(entry)
    data["facts"] = facts[-MAX_FACTS:]
    _write(FACTS, data)
    return entry


def all_facts() -> list[dict]:
    data = _read(FACTS, {"facts": []})
    got = data.get("facts", []) if isinstance(data, dict) else []
    return [f for f in got if isinstance(f, dict) and f.get("text")]


# ── threads ──────────────────────────────────────────────────────────────────
def open_thread(text: str) -> None:
    """Something left hanging that she should come back to."""
    text = (text or "").strip()
    if not text:
        return
    data = _read(THREADS, {"threads": []})
    got = data.get("threads", []) if isinstance(data, dict) else []
    if not isinstance(got, list):
        got = []
    got.append(dict(_now(), text=text[:300], closed=False))
    _write(THREADS, {"threads": got[-MAX_THREADS:]})


def threads(only_open: bool = True) -> list[dict]:
    data = _read(THREADS, {"threads": []})
    got = data.get("threads", []) if isinstance(data, dict) else []
    got = [t for t in got if isinstance(t, dict) and t.get("text")]
    return [t for t in got if not t.get("closed")] if only_open else got


def close_thread(text: str) -> None:
    data = _read(THREADS, {"threads": []})
    got = data.get("threads", []) if isinstance(data, dict) else []
    hit = False
    for t in got:
        if isinstance(t, dict) and text and text[:40] in str(t.get("text", "")):
            t["closed"] = True
            hit = True
    if hit:
        _write(THREADS, {"threads": got})


# ── nights ───────────────────────────────────────────────────────────────────
def log_night(summary: str, minutes: int) -> None:
    data = _read(JOURNAL, {"nights": []})
    got = data.get("nights", []) if isinstance(data, dict) else []
    if not isinstance(got, list):
        got = []
    got.append(dict(_now(), about=(summary or "").strip()[:280],
                    minutes=int(minutes or 0)))
    _write(JOURNAL, {"nights": got[-MAX_JOURNAL:]})


def nights(n: int = 6) -> list[dict]:
    data = _read(JOURNAL, {"nights": []})
    got = data.get("nights", []) if isinstance(data, dict) else []
    return [x for x in got if isinstance(x, dict)][-n:]
def is_first_night() -> bool:
    """True until she actually knows one thing about him.

    Not a flag somebody set — the absence of anything remembered. That way the
    first night ends when it ends: on the sentence where he told her something
    and she kept it.
    """
    return not all_facts()


def facts_block(limit: int = 40) -> str:
    """The facts as the model reads them. Oldest first, so the newest land last
    and closest."""
    got = all_facts()[-limit:]
    if not got:
        return ""
    lines = []
    for f in got:
        d = f.get("date", "")
        lines.append(f"- ({d}) {f['text']}")
    return "\n".join(lines)


def threads_block() -> str:
    got = threads(only_open=True)
    if not got:
        return ""
    return "\n".join(f"- ({t.get('date','')}) {t['text']}" for t in got)


def nights_block(n: int = 5) -> str:
    got = nights(n)
    if not got:
        return ""
    out = []
    for x in got:
        out.append(f"- {x.get('date','')} at {x.get('at','')}, "
                   f"{x.get('minutes',0)} min: {x.get('about','')}")
    return "\n".join(out)


def forget_everything() -> None:
    """The one deletion, and it is his to make."""
    for p in (FACTS, THREADS, JOURNAL):
        try:
            p.unlink()
        except Exception:
            pass
