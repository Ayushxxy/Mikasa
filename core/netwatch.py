"""Diagnosis and memory for the line that carries her voice.

WHY THIS FILE EXISTS
    Every failure used to arrive at the window as the same sentence —
    "connection lost" — because the only thing the supervisor did with an
    exception was print it. A server restart, a quota, a stale resumption
    handle, a WiFi hiccup, a bug in a tool: all of it read as the network,
    which is why the network was always the suspect and never the answer.

    Three jobs live here, and none of them know about Qt or the Live API:

      1. classify()  — what actually went wrong, in seven kinds a person can
                       act on.
      2. route_ok()  — is there a path to the internet at all, right now,
                       answered in two seconds instead of a socket timeout.
      3. Line        — a small ring of what happened, on disk, so the next
                       "it keeps dropping" can be answered with numbers
                       instead of impressions.

    It imports nothing outside the standard library on purpose: this has to be
    provable in a test that never opens a socket.
"""
from __future__ import annotations

import asyncio
import errno
import json
import random
import socket
import ssl
import time
from pathlib import Path

# ── what went wrong ──────────────────────────────────────────────────────────
#
#   net       the path to the internet is gone, or the socket died without the
#             server saying anything. This is the only kind that is the
#             network's fault, and it is rarer than the label suggested.
#   server    the path is fine; the other end failed. 5xx, 1011, "internal
#             error", a closed socket with a 1011 close code.
#   protocol  we asked for something it will not do: 1007, an invalid config, a
#             resumption handle it no longer accepts. A retry loop retries this
#             forever and it never starts working — the session has to be
#             rebuilt instead.
#   quota     429 / RESOURCE_EXHAUSTED. Waiting is the only cure.
#   auth      key missing, wrong, or blocked.
#   model     this model does not exist for this key, or is retired. Switching
#             rung is the only cure, and it is why the ladder exists.
#   planned   not a failure at all: the server handed us off (go_away) or we
#             rotated on purpose.
#   stall     nothing arrived, nothing failed. The socket is up and silent.
#   unknown   none of the above. Never guessed into "net".
NET = "net"
SERVER = "server"
PROTOCOL = "protocol"
QUOTA = "quota"
AUTH = "auth"
MODEL = "model"
PLANNED = "planned"
STALL = "stall"
UNKNOWN = "unknown"

KINDS = (NET, SERVER, PROTOCOL, QUOTA, AUTH, MODEL, PLANNED, STALL, UNKNOWN)

# Kinds a person can do something about, in their own words.
HUMAN = {
    NET:      "network",
    SERVER:   "her side",
    PROTOCOL: "the session",
    QUOTA:    "usage limit",
    AUTH:     "the key",
    MODEL:    "the voice model",
    PLANNED:  "handover",
    STALL:    "a silent line",
    UNKNOWN:  "unknown",
}

# Kinds where retrying the same thing is pointless and the rung must change.
SWITCH_ON = (MODEL, AUTH)
# Kinds where a short burst of retries is right, and a long one is not.
BACKOFF_ON = (NET, SERVER, STALL, UNKNOWN)

_TEXT_RULES = (
    (("resource_exhausted", "429", "quota", "rate limit"), QUOTA),
    (("unauthenticated", "permission_denied", "401", "403",
      "api key", "api_key", "invalid key"), AUTH),
    (("not_found", "404", "does not exist", "no longer available",
      "deprecated", "unsupported model"), MODEL),
    (("1007", "invalid argument", "invalid_argument", "resumption",
      "handle"), PROTOCOL),
    (("1000", "go_away", "goaway", "handover"), PLANNED),
    (("1006", "1001", "1005", "connection reset", "connection closed",
      "connection aborted", "broken pipe", "getaddrinfo", "name or service",
      "network is unreachable", "no route to host", "ssl", "certificate",
      "timed out", "timeout"), NET),
    (("1011", "internal", "unavailable", "500", "502", "503", "504",
      "remote end closed", "server"), SERVER),
)


def _text_of(exc: BaseException) -> str:
    bits = [type(exc).__name__, str(exc)]
    for attr in ("code", "status", "status_code", "reason", "message"):
        try:
            v = getattr(exc, attr, None)
        except Exception:
            v = None
        if v not in (None, ""):
            bits.append(str(v))
    return " ".join(bits).lower()


def classify(exc: BaseException | str | None) -> str:
    """One of KINDS. Called on every failure, so it must never raise."""
    if exc is None:
        return PLANNED
    if isinstance(exc, str):
        return _classify_text(exc.lower())
    try:
        # A closed websocket carries the close code, and the code is the
        # diagnosis: 1000/1001/1006 are path, 1011 is the other end, 1007 is
        # "you asked for something impossible".
        for attr in ("rcvd", "sent"):
            frame = getattr(exc, attr, None)
            code = getattr(frame, "code", None)
            if isinstance(code, int):
                if code in (1000, 1001, 1005, 1006):
                    return NET
                if code == 1007:
                    return PROTOCOL
                if code == 1008:
                    return AUTH
                if code == 1011:
                    return SERVER
                if code == 1013:
                    return SERVER
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return NET
        if isinstance(exc, (ConnectionError, socket.gaierror, ssl.SSLError)):
            return NET
        if isinstance(exc, OSError):
            if getattr(exc, "errno", None) in (
                    errno.ECONNRESET, errno.ECONNREFUSED, errno.EHOSTUNREACH,
                    errno.ENETUNREACH, errno.ETIMEDOUT, errno.EPIPE):
                return NET
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if isinstance(code, int):
            if code in (400, 404):
                return MODEL if code == 404 else PROTOCOL
            if code in (401, 403):
                return AUTH
            if code == 429:
                return QUOTA
            if 500 <= code <= 599:
                return SERVER
    except Exception:
        pass
    return _classify_text(_text_of(exc))


def _classify_text(t: str) -> str:
    for needles, kind in _TEXT_RULES:
        for n in needles:
            if n in t:
                return kind
    return UNKNOWN


def detail(exc: BaseException | str | None, limit: int = 90) -> str:
    """A short, human line for the log — never a traceback, never a key."""
    if exc is None:
        return "handover"
    text = str(exc) if not isinstance(exc, str) else exc
    text = " ".join(text.split())
    if not text:
        text = type(exc).__name__ if isinstance(exc, BaseException) else "?"
    return text[:limit]


def human(kind: str) -> str:
    return HUMAN.get(kind, kind)


# ── is there a path? ─────────────────────────────────────────────────────────
#
# A TCP connect to the API's port. It proves the route and the DNS without
# touching a session, costs three packets, and answers in under two seconds —
# which is the difference between "offline" being a diagnosis and being a guess.
PROBE_HOST = "generativelanguage.googleapis.com"
PROBE_PORT = 443


def route_ok(timeout: float = 2.0, host: str = PROBE_HOST,
             port: int = PROBE_PORT) -> bool:
    s = None
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        return True
    except Exception:
        return False
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass


async def route_ok_async(timeout: float = 2.0, host: str = PROBE_HOST,
                         port: int = PROBE_PORT) -> bool:
    """The same probe without blocking the loop that is serving her."""
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


# ── patience ─────────────────────────────────────────────────────────────────
class Backoff:
    """Growing waits with a little noise.

    The noise is not decoration. Three clients reconnecting on the same
    schedule come back in the same millisecond and knock together; ±20% is
    enough to spread them. The ceiling is fifteen seconds because a longer one
    makes a two-second outage feel like a crash.
    """

    def __init__(self, delays=(0.5, 1.0, 2.0, 4.0, 8.0, 15.0),
                 jitter: float = 0.2, rng: random.Random | None = None):
        self.delays = tuple(delays)
        self.jitter = max(0.0, min(0.9, jitter))
        self._rng = rng or random.Random()
        self.attempt = 0

    def peek(self) -> float:
        base = self.delays[min(self.attempt, len(self.delays) - 1)]
        return round(base * (1.0 + self._rng.uniform(-self.jitter, self.jitter)), 2)

    def next_delay(self) -> float:
        d = self.peek()
        self.attempt += 1
        return max(0.0, d)

    def reset(self) -> None:
        self.attempt = 0


# ── the record ───────────────────────────────────────────────────────────────
class Line:
    """A ring of what the line did, in this folder, for the next complaint.

    Deliberately dumb: append, cap, write. No rotation by date, no compression,
    no upload. Two hundred entries is about a month of ordinary use and about
    forty kilobytes, and when something *is* wrong it is the first place worth
    reading. It is also the only way "it drops all the time" can become "eleven
    drops, nine of them 1011, all under a minute" — which is a different bug.
    """

    def __init__(self, path: str | Path | None = None, keep: int = 200):
        self.path = Path(path) if path else None
        self.keep = keep
        self.entries: list[dict] = []
        self._load()

    # ── disk ────────────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.path:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self.entries = [e for e in raw if isinstance(e, dict)][-self.keep:]
        except Exception:
            self.entries = []

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.entries[-self.keep:], indent=1),
                           encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass                          # a log is never worth an exception

    # ── writing ─────────────────────────────────────────────────────────────
    def add(self, kind: str, **fields) -> dict:
        entry = {"t": round(time.time(), 1), "kind": kind}
        for k, v in fields.items():
            if isinstance(v, float):
                v = round(v, 2)
            elif not isinstance(v, (int, str, bool)) and v is not None:
                v = str(v)[:120]
            if v is not None:
                entry[k] = v
        self.entries.append(entry)
        if len(self.entries) > self.keep:
            self.entries = self.entries[-self.keep:]
        self._save()
        return entry

    # ── reading ─────────────────────────────────────────────────────────────
    def recent(self, n: int = 40) -> list[dict]:
        return self.entries[-n:]

    def last(self, kind: str | None = None) -> dict | None:
        for e in reversed(self.entries):
            if kind is None or e.get("kind") == kind:
                return e
        return None

    def since(self, seconds: float) -> list[dict]:
        cutoff = time.time() - seconds
        return [e for e in self.entries if float(e.get("t") or 0) >= cutoff]

    def stats(self, window: float = 24 * 3600) -> dict:
        rows = self.since(window)
        drops = [e for e in rows if e.get("kind") == "drop"]
        by_kind: dict[str, int] = {}
        for e in drops:
            k = str(e.get("why") or UNKNOWN)
            by_kind[k] = by_kind.get(k, 0) + 1
        lives = [float(e.get("after") or 0) for e in drops
                 if isinstance(e.get("after"), (int, float))]
        return {
            "drops": len(drops),
            "by_kind": by_kind,
            "shortest": min(lives) if lives else 0.0,
            "median": sorted(lives)[len(lives) // 2] if lives else 0.0,
            "backs": len([e for e in rows if e.get("kind") == "back"]),
            "rotations": len([e for e in rows if e.get("kind") == "rotate"]),
            "switches": len([e for e in rows if e.get("kind") == "model"]),
        }

    def summary(self, window: float = 24 * 3600) -> str:
        """"3 drops today · mostly her side · last 4m ago". Fits one dim line."""
        s = self.stats(window)
        if not s["drops"]:
            if s["rotations"] or s["backs"]:
                return "no drops in 24h · clean handovers"
            return "no drops in 24h"
        worst = max(s["by_kind"].items(), key=lambda kv: kv[1])[0]
        last = self.last("drop") or {}
        age = max(0.0, time.time() - float(last.get("t") or time.time()))
        return (f"{s['drops']} drop{'s' if s['drops'] != 1 else ''} in 24h · "
                f"mostly {human(worst)} · last {_ago(age)}")

    def as_text(self, n: int = 60) -> str:
        """The panel, newest first, plain enough to paste into a message."""
        rows = list(reversed(self.recent(n)))
        if not rows:
            return "nothing recorded yet."
        out = []
        for e in rows:
            when = time.strftime("%d %b %H:%M:%S", time.localtime(float(e.get("t") or 0)))
            kind = e.get("kind", "?")
            rest = "  ".join(f"{k}={v}" for k, v in e.items()
                             if k not in ("t", "kind"))
            out.append(f"{when}  {kind:<8} {rest}")
        return "\n".join(out)


def _ago(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 90:
        return f"{s}s ago"
    if s < 5400:
        return f"{s // 60}m ago"
    if s < 172800:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"
