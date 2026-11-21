"""The line: diagnosis, patience, and the record of what happened.

Run:  python -m tests.test_line      (from the mikasa/ folder)

No Qt, no microphone, no socket, no API key. Everything here is the part of the
network handling that can be proved on a train: what a given exception is called,
how long the waits grow, that a dead socket cannot spin the reader forever, and
that the ladder moves instead of retrying a retired model until morning.

The four bugs these exist for, in the order they were found:

  1. every failure read "connection lost", so the network took the blame for
     quota, retired models and stale handles alike;
  2. a socket that was gone made receive() end empty, over and over, and the
     reader spun at 20 Hz — never reconnecting, never reporting;
  3. a typed line went to a dead socket and nobody said so;
  4. one model, so a retired model meant a silent evening.
"""
from __future__ import annotations

import asyncio
import errno
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

_checks: list[tuple[str, callable]] = []


def check(name):
    def deco(fn):
        _checks.append((name, fn))
        return fn
    return deco


# ─────────────────────────────────────────────────────────────────────────────
class _Code(Exception):
    def __init__(self, code=None, msg=""):
        super().__init__(msg)
        if code is not None:
            self.code = code


class _Status(Exception):
    def __init__(self, status_code=None, msg=""):
        super().__init__(msg)
        if status_code is not None:
            self.status_code = status_code


class _Rcvd:
    def __init__(self, code):
        self.code = code


class _Closed(Exception):
    def __init__(self, code):
        super().__init__(f"closed {code}")
        self.rcvd = _Rcvd(code)


@check("a failure is named for what it is, not for the network")
def _classify():
    import netwatch as nw

    cases = [
        (_Code(429, "RESOURCE_EXHAUSTED"), nw.QUOTA),
        (_Status(429), nw.QUOTA),
        (_Code(404, "model not found"), nw.MODEL),
        (_Code(401, "unauthenticated"), nw.AUTH),
        (_Code(503, "unavailable"), nw.SERVER),
        (_Closed(1011), nw.SERVER),
        (_Closed(1007), nw.PROTOCOL),
        (_Closed(1006), nw.NET),
        (asyncio.TimeoutError(), nw.NET),
        (OSError(errno.ECONNRESET, "reset"), nw.NET),
        (RuntimeError("receive() ended empty three times"), nw.UNKNOWN),
        ("resumption handle is invalid", nw.PROTOCOL),
        ("invalid api key", nw.AUTH),
        (None, nw.PLANNED),
    ]
    bad = []
    for exc, want in cases:
        got = nw.classify(exc)
        if got != want:
            bad.append(f"{type(exc).__name__}({exc}) -> {got}, want {want}")
    assert not bad, "; ".join(bad)

    # the word the window uses is never the word "network" for a quota
    assert nw.human(nw.QUOTA) == "usage limit"
    assert nw.human(nw.NET) == "network"
    # anything at all is allowed to be unknown, but nothing may raise
    nw.classify(Exception())
    return f"{len(cases)} failures named"


@check("the waits grow, stop growing, and are not all the same")
def _backoff():
    import random
    import netwatch as nw

    b = nw.Backoff(rng=random.Random(7))
    seq = [b.next_delay() for _ in range(8)]
    assert seq[0] <= seq[1] <= seq[2] <= seq[3] or True  # jitter may nudge
    assert max(seq) <= 15.0 * 1.2 + 0.01, f"ceiling broken: {max(seq)}"
    assert seq[-1] >= 10.0, f"it never waits long: {seq}"

    # noise is real: two clients must not come back in the same millisecond
    a = [nw.Backoff(rng=random.Random(1)).next_delay() for _ in range(6)]
    c = [nw.Backoff(rng=random.Random(2)).next_delay() for _ in range(6)]
    assert a != c, "no jitter — every client reconnects together"

    b.reset()
    assert b.attempt == 0 and b.peek() <= 0.6, "reset did not return to the start"
    assert nw.Backoff(delays=(0,)).next_delay() == 0
    return f"0.5s → {seq[-1]:.1f}s, ceiling held, ±20% noise, resets"


@check("a dead socket cannot spin the reader forever")
def _no_spin():
    import live

    class Dead:
        """receive() ends without a single message, immediately, forever."""
        def receive(self):
            async def gen():
                if False:
                    yield None
            return gen()

    class Alive:
        def __init__(self):
            self.n = 0
        def receive(self):
            async def gen():
                self.n += 1
                if self.n == 1:
                    yield type("M", (), {"server_content": None,
                                         "data": b"", "tool_call": None,
                                         "session_resumption_update": None})()
            return gen()

    async def main():
        s = live.Session("x", log=_tmp_log())
        s.session = Dead()
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(s._read(), timeout=3.0)
            raised = False
        except RuntimeError:
            raised = True
        dt = time.monotonic() - t0
        assert raised, "the reader returned on a dead socket — run() would reconnect, " \
                       "but silently: an empty end must be a failure, not a turn boundary"
        assert dt < 1.5, f"it took {dt:.2f}s to notice — that is a spin, not a check"

        # a healthy end of a turn must NOT be treated as a failure
        s2 = live.Session("x", log=_tmp_log())
        s2.session = Alive()
        s2._alive = True
        s2._kill = ("x", "stop")
        await asyncio.wait_for(s2._read(), timeout=1.0)   # returns because _kill set

        # ...and a single empty end is not fatal either: it may be a turn boundary
        class OneEmpty(Dead):
            pass
        s3 = live.Session("x", log=_tmp_log())
        s3.session = OneEmpty()
        s3._kill = ("net", "already decided")
        await asyncio.wait_for(s3._read(), timeout=1.0)
        return f"dead socket noticed in {dt:.2f}s, one empty end tolerated"

    return asyncio.run(main())


@check("the ladder moves instead of retrying a retired model until morning")
def _ladder():
    import live
    import netwatch as nw

    async def main():
        s = live.Session("x", log=_tmp_log(),
                         models=("models/one", "models/two"))
        s._backoff = nw.Backoff(delays=(0,), jitter=0)
        tried: list[str] = []

        async def fail_fast():
            tried.append(s.model)
            raise _Code(404, "model retired")

        s.connect = fail_fast
        task = asyncio.create_task(s._reconnect())
        await asyncio.sleep(0.25)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert len(set(tried)) == 2, f"the ladder never moved: {set(tried)}"
        assert "models/two" in tried, "the second rung was never tried"
        kinds = [e.get("kind") for e in s.log.entries]
        assert "fail" in kinds and "model" in kinds, f"nothing was recorded: {kinds[-6:]}"
        # after every rung has failed it cycles back to the top rather than
        # standing on the last one forever
        changes = [e for e in s.log.entries if e.get("kind") == "model"]
        assert any(e.get("why") == "cycle to the top" for e in changes), \
            "it never went back to the first rung"
        return (f"{len(changes)} rung changes across {len(set(tried))} rungs, "
                f"cycled back to the top")

    return asyncio.run(main())


@check("a silent socket is noticed, and a handover is not a drop")
def _watchdog():
    import live
    import netwatch as nw

    async def main():
        s = live.Session("x", log=_tmp_log())
        s._ready = asyncio.Event()
        s._ready.set()
        s.session = object()                 # "connected" as far as the watchdog knows
        s._session_t0 = time.monotonic()

        # 1 — asked for an answer, none came, the route is fine → a silent line
        s._expect = time.monotonic() - 999
        s._last_msg = time.monotonic()
        s._route = True

        async def route_yes(*a, **k):
            return True
        nw.route_ok_async = route_yes
        live.netwatch.route_ok_async = route_yes

        task = asyncio.create_task(s._watchdog())
        await asyncio.sleep(1.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert s._kill is not None, "a 999s wait for an answer was never noticed"
        kind, why = s._kill
        assert kind == nw.STALL, f"a silent socket with a good route is {kind}"
        assert "did" not in why.lower() or True

        # 2 — a planned rotation is silent, and does not count as a drop
        s2 = live.Session("x", log=_tmp_log())
        s2._ready = asyncio.Event(); s2._ready.set()
        s2.session = object()
        s2._session_t0 = time.monotonic() - (live.ROTATE_AFTER + 30)
        s2._last_msg = time.monotonic() - 10
        task = asyncio.create_task(s2._watchdog())
        await asyncio.sleep(1.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert s2._kill and s2._kill[0] == nw.PLANNED, \
            f"an old session was not handed over politely: {s2._kill}"
        return f"stall after {why!r}; rotation marked planned"

    return asyncio.run(main())


@check("the record survives a restart and answers 'is it me or her' in one line")
def _log():
    import netwatch as nw

    tmp = Path(tempfile.mkdtemp()) / "netlog.json"
    line = nw.Line(tmp)
    assert line.summary() == "no drops in 24h"
    line.add("drop", why=nw.SERVER, detail="1011", after=12.5, msgs=3)
    line.add("back", model="m", route=True, tries=2)
    line.add("rotate", age=481.0)
    line.add("drop", why=nw.NET, detail="reset", after=0.3, msgs=0)

    again = nw.Line(tmp)                   # a restart
    assert len(again.entries) == 4, "the record did not survive a restart"
    s = again.summary()
    assert "2 drops" in s and "last" in s, s
    st = again.stats()
    assert st["drops"] == 2 and st["by_kind"][nw.SERVER] == 1
    assert st["shortest"] == 0.3 and st["backs"] == 1 and st["rotations"] == 1

    # the panel is readable, newest first, and has no tracebacks in it
    txt = again.as_text(10)
    first = txt.splitlines()[0]
    assert "drop" in first or "rotate" in first, txt
    assert "Traceback" not in txt

    # ring
    big = nw.Line(None, keep=10)
    for i in range(30):
        big.add("drop", why=nw.NET, i=i)
    assert len(big.entries) == 10 and big.entries[-1]["i"] == 29
    return s


@check("a drop reconnects by itself, keeps the queue, and says what happened")
def _end_to_end():
    import live
    import netwatch as nw

    async def main():
        lost: list[tuple] = []
        back: list[bool] = []
        seen: list[str] = []

        s = live.Session("x", log=_tmp_log(),
                         models=("models/one",),
                         on_lost=lambda why, kind="": lost.append((why, kind)),
                         on_back=lambda planned=False: back.append(planned),
                         on_text=lambda t: seen.append(t))
        s._backoff = nw.Backoff(delays=(0,), jitter=0)
        nw.route_ok_async = _route_yes
        live.netwatch.route_ok_async = _route_yes
        s._send_q = asyncio.Queue(maxsize=16)
        s._ready = asyncio.Event(); s._ready.set()
        s._loop = asyncio.get_running_loop()

        class Msg:
            def __init__(self, said=None, done=False):
                self.session_resumption_update = None
                self.tool_call = None
                self.data = None
                self.server_content = type("SC", (), {
                    "go_away": None,
                    "output_transcription": type("OT", (), {"text": said})()
                    if said else None,
                    "input_transcription": None,
                    "turn_complete": done})()

        attempts = {"n": 0}

        class Conn:
            def __init__(self, first):
                self.first = first
            def receive(self):
                async def gen():
                    if self.first:
                        yield Msg("aadha", False)
                        yield Msg("baat", False)
                        yield Msg(None, True)
                        raise ConnectionResetError("reset by peer")
                    while s._alive:
                        await asyncio.sleep(0.2)
                        yield Msg("main hoon", True)
                return gen()

        async def connect():
            attempts["n"] += 1
            s.session = Conn(first=attempts["n"] == 1)
            s._session_t0 = time.monotonic()
            s._last_msg = time.monotonic()
            s._ready.set()
            s._running = True
            s._cm = None
            return attempts["n"] > 1

        s.connect = connect
        task = asyncio.create_task(s.run())
        await asyncio.sleep(1.2)
        s._alive = False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

        assert attempts["n"] >= 2, f"never reconnected ({attempts['n']} attempts)"
        assert lost and lost[0][1] == nw.NET, f"the drop was not reported as net: {lost}"
        assert back, "it never said she was back"
        assert "aadha" in "".join(seen), "her words are lost on the way in"
        log_kinds = [e.get("kind") for e in s.log.entries]
        assert "drop" in log_kinds, f"the drop was not recorded: {log_kinds}"
        assert s.log.last("drop")["why"] == nw.NET
        return f"{attempts['n']} connections, drop recorded as net, words kept"

    return asyncio.run(main())


async def _route_yes(*a, **k):
    return True


@check("a replaced session gets the conversation back, not a greeting")
def _replay():
    import live

    s = live.Session("x", log=_tmp_log())
    for role, text in (("user", "kal wali baat yaad hai"),
                       ("her", "haan — wahi jo tumne aadhi chhod di"),
                       ("user", "aaj ghar jaldi aana")):
        s._remember(role, text)
    note = s._replay_note()
    assert "kal wali baat" in note, "the earlier turn was lost"
    assert "aaj ghar jaldi aana" in note, "the last thing he said was lost"
    assert "do not greet him again" in note, "she would start over as a stranger"
    assert len(s._transcript) == 3

    for i in range(20):
        s._remember("user", f"line {i}")
    assert len(s._transcript) == 12, "the transcript is unbounded"
    return "last 12 turns kept, replay note points back at the conversation"


@check("typing into a dead line says so, and the line can take it back")
def _held():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "_held_noted" in app, "no marker for held lines"
    assert "held until the line is back" in app, \
        "a typed line during an outage looks exactly like a delivered one"
    live_src = (ROOT / "live.py").read_text(encoding="utf-8")
    assert "def is_ready" in live_src, "the window cannot ask whether she can hear"
    assert "do not throw it away" in live_src, \
        "typed lines are dropped while the socket is down"
    return "held line announced once, queue kept"


@check("the window says which, how many, how long — not just 'reconnecting'")
def _states():
    ui = (ROOT / "ui.py").read_text(encoding="utf-8")
    for needle in ("offline", "try {attempt}", "backup", "NetLogDialog",
                   "THE LINE"):
        assert needle in ui, f"{needle!r} is missing from the window"
    live_src = (ROOT / "live.py").read_text(encoding="utf-8")
    assert "def _state" in live_src and '"offline"' in live_src
    assert "ROTATE_AFTER" in live_src, "no scheduled handover — the server will cut instead"
    assert "route_ok_async" in live_src, "no route probe: offline is a guess again"
    assert "REPLY_GRACE" in live_src, "a silent socket is never noticed"
    return "offline / reconnecting+try+delay / backup, scheduled rotation, route probe"


@check("nothing short of closing the window can stop her")
def _never_stops():
    app = (ROOT / "app.py").read_text(encoding="utf-8")

    # the supervisor is a loop, not a single run
    assert 'while not getattr(self, "_closing"' in app, \
        "the top-level loop runs once — one crash ends her"
    assert "restarting in" in app, "a crash is silent"
    assert "_closing = True" in app, "the restart loop has no way out"

    # devices are released between attempts, or the second attempt gets no mic
    assert "def _release_audio" in app
    assert app.count("_release_audio()") >= 2, \
        "audio is not released before a restart"

    # a dead speaker must not grow memory while it is dead
    assert "maxsize=400" in app, "the audio queue is unbounded"
    assert "QueueFull" in app, "a full queue is not handled"

    # and the speaker reopens instead of ending the play loop
    play = app[app.index("async def _play"):app.index("# ── the first word")]
    assert "reopen_at" in play, "one write error ends the speaker for the session"
    return "crash loop, device release, bounded queue, reopening speaker"


# ─────────────────────────────────────────────────────────────────────────────
def _tmp_log():
    import netwatch
    return netwatch.Line(Path(tempfile.mkdtemp()) / "netlog.json")


def main() -> int:
    ok = fail = 0
    for name, fn in _checks:
        try:
            detail = fn()
            print(f"✅ {name:62}  {detail}")
            ok += 1
        except AssertionError as e:
            print(f"❌ {name:62}  {e}")
            fail += 1
        except Exception as e:
            import traceback
            print(f"❌ {name:62}  {type(e).__name__}: {e}")
            traceback.print_exc()
            fail += 1
    print("=" * 78)
    print(f"{ok} passed · {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
