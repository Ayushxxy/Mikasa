"""Her head: the clock, the motive, the warmth, the ladder, the voice list.

Run:  python -m tests.test_persona      (from the mikasa/ folder)

These are the six complaints from the screenshot, one check each:

  1. she said "abhi to 2 baje wale hain" at 7:41 in the morning — the prompt
     was built once, at launch, with a frozen clock in it;
  2. she answered "tension hai" with "kaunsa subject hard lagta hai, main
     usme help kar sakti hu" — an assistant, because the prompt forbade every
     warm answer and allowed only the useful one;
  3. she has no idea what she is for;
  4. she asks a question at the end of every single turn;
  5. she writes clean sentences, so she is spoken as a clean sentence;
  6. two models but one voice list, and the list was five names long.

Nothing here needs a network, a key, a microphone or Qt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

_checks: list[tuple[str, callable]] = []


def check(name):
    def deco(fn):
        _checks.append((name, fn))
        return fn
    return deco


def _prompt() -> str:
    import app
    import settings
    return app.build_prompt(settings.load())


# ─────────────────────────────────────────────────────────────────────────────
@check("the prompt has no clock frozen in it, and every token is filled")
def _tokens():
    raw = (ROOT / "prompt.txt").read_text(encoding="utf-8")
    for dead in ("{now}", "{day_name}"):
        assert dead not in raw, (
            f"{dead} is back in prompt.txt — that is the token that was filled "
            f"once at launch and still said 2 a.m. at breakfast")
    out = _prompt()
    unfilled = sorted(set(re.findall(r"\{[a-z_]+\}", out)))
    assert not unfilled, f"unfilled tokens: {unfilled}"
    for need in ("Agra", "Asia/Kolkata", "[TONIGHT'S REGISTER]"):
        assert need in out, f"{need} is missing from the built prompt"
    return "no frozen clock, every token filled, city and zone present"


@check("the clock she is given is the current one, not the launch one")
def _clock():
    import app
    import settings

    m = app.Mikasa.__new__(app.Mikasa)
    m.cfg = settings.load()
    stamp = m._stamp_now()
    assert re.match(r"\d\d:\d\d · \w+ · \d+ \w+ · \w+", stamp), stamp

    # The stamp must be the real minute, in her zone, not the machine's.
    local = app._now(m.cfg)
    assert stamp.startswith(local.strftime("%H:%M")), (stamp, local)

    # ...and it must move. A stamp that cannot change is the bug.
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _clock_watch" in src, "nothing refreshes her clock during a session"
    assert "note_clock" in src, "the clock is never handed to the session"
    assert "def _push_clock" in src and "send_text" in src.split("def say_typed")[1], \
        "a typed line does not refresh the clock first"

    live_src = (ROOT / "live.py").read_text(encoding="utf-8")
    assert "def note_clock" in live_src
    assert "turn_complete=False" in live_src, \
        "the clock arrives as a turn — she would answer the clock"
    assert "CLOCK_EVERY" in live_src, "no throttle: a message every second"
    return f"real minute, refreshed, {stamp}"


@check("she can ask the clock instead of doing arithmetic")
def _get_time():
    import app

    tool = app.TOOLS.get("get_time")
    assert tool, "there is no get_time — so she guesses, and she is bad at it"
    decl, handler = tool
    assert decl["name"] == "get_time"
    assert "never work the time out" in decl["description"].lower()

    said = handler()
    assert re.match(r"\d\d:\d\d — \w+, \d\d \w+ \d{4} — \w+ \(", said), said

    # and the prompt has to tell her it exists, or she will not call it
    out = _prompt()
    assert "get_time" in out, "the tool exists but her prompt never mentions it"
    assert "never estimate the hour" in out
    return said.split(" — ")[0]


@check("she knows what she is for, and it is not his syllabus")
def _motive():
    out = _prompt()
    assert "[WHAT SHE IS FOR]" in out
    assert "the room is empty without" in out
    assert "She is his, not his problems'" in out

    # The lines that made every kind answer into a study question are gone —
    # and gone from the prompt *entirely*, not turned into examples of what not
    # to say. Naming them was the bug: the model reads a quoted sentence as
    # something in its vocabulary no matter which side of the ✗ it sits on.
    low = out.lower()
    for dead in ("which subject", "help kar", "syllabus", "timetable",
                 "study plan", "which chapter", "boards"):
        assert dead not in low, \
            f"the helper script is back in her prompt: {dead!r}"

    # and the general rule that replaced them is there instead
    assert "[WHAT YOU DO WHEN HE IS LOW]" in out
    assert "you answer him, not the thing that is heavy" in low
    return "motive stated, helper script gone, the low rule in its place"


@check("warmth is allowed and asking is rationed")
def _asking():
    out = _prompt()
    low = out.lower()          # the prompt capitalises its lines; the guard
                               # is about the rule, not the shift key
    # (the phrase wraps in the source, so match it without the line break)
    assert "Warmth is\n  allowed" in out or "Warmth is allowed" in out, \
        "she cannot be warm, so she is useful instead"
    assert "never two turns in a row that end in a question mark" in low, \
        "no budget: every turn ends in a question and it reads as an interview"
    assert "[HOW IT SOUNDS" in out, "no spoken-format section"
    for needle in ("achaaaa", "huh!", "tum… kab aaye"):
        assert needle in out, f"the spoken-format section lost {needle!r}"

    # the persona must not go back to writing clean sentences
    assert "never a clean, complete, well-formed sentence" in low
    return "warmth allowed, one question per two turns, spoken format present"


@check("possessive, with a release step that is softer and not colder")
def _ladder():
    out = _prompt()
    low = out.lower()
    assert "[HOW CLOSE SHE GETS]" in out
    for step in ("claim", "read", "release"):
        assert step in out, f"the ladder is missing its {step} step"

    # the whole point of what he asked for
    assert "gets softer, not colder" in low
    assert "refusing her must leave her warmer" in low
    assert "never punish him" in out, "a sulk is a punishment"

    # ...and it must not become the only thing she does
    assert "two or three of these in a night" in low, "no rate limit"
    return "claim → read → release, softer-not-colder, 2–3 a night"


@check("a topic he drops is dropped — she does not keep steering back to it")
def _one_topic():
    out = _prompt()
    low = out.lower()
    assert "[the topic is his, not hers]" in low, \
        "nothing stops her from chewing on the one heavy thing all night"
    for rule in ("one turn, not a subject for the night",
                 "you change with him, immediately",
                 "you never bring his heavy thing back",
                 "one mention of it in a night is enough"):
        assert rule in low, f"the topic rule lost: {rule}"

    # and the memory rules must not smuggle it back in
    import app
    cb = app._callbacks_rule({"her_writing": "on"}).lower()
    assert "never in the same night" in cb, \
        "a callback can fire the same night, which is the bug he just reported"
    assert "never a pivot" in cb, "a callback can be turned into a steer back"
    notes = app._notes_rule({"her_writing": "on"}).lower()
    assert "carries on about whatever he is actually talking about now" in notes
    return "one mention, no pivots, callbacks never same-night"


@check("the night has a temperature, and it changes")
def _register():
    import app

    assert len(app.REGISTERS) >= 5
    assert all(len(r) > 30 for r in app.REGISTERS), "a register card is a stub"
    cards = {app._register_for({"register": str(i)})
             for i in range(len(app.REGISTERS))}
    assert len(cards) == len(app.REGISTERS), "the cards are not distinct"
    assert app._register_for({"register": "0"}) == app.REGISTERS[0]
    # stable within a day: two calls give the same night
    a = app._register_for({})
    b = app._register_for({})
    assert a == b, "the mood changes between two calls in the same hour"
    out = _prompt()
    assert any(r[:40] in out for r in app.REGISTERS), \
        "the card is not in the prompt"
    return f"{len(app.REGISTERS)} cards, stable by the hour"


@check("the voices he kept are the picker, and Leda is hers by default")
def _voices():
    import settings

    KEPT = ["Leda", "Sulafat", "Callirrhoe"]
    assert settings.VOICES == KEPT, f"the shortlist changed: {settings.VOICES}"
    assert len(set(settings.VOICES)) == len(KEPT), "duplicates in the list"
    assert settings.DEFAULTS["voice"] == "Leda", \
        f"the default is {settings.DEFAULTS['voice']}, not the one he chose"
    for dropped in ("Aoede", "Zephyr", "Autonoe", "Sadachbia", "Kore", "Gacrux",
                    "Despina", "Erinome", "Achernar", "Pulcherrima",
                    "Vindemiatrix", "Laomedeia"):
        assert dropped not in settings.VOICES, f"{dropped} was supposed to go"

    # An old config says Aoede because that used to be the default. Aoede is
    # not a voice she can be any more, so it resolves to Leda — but so does
    # anything else that is gone, and that is the point: a stale name in
    # mikasa.json used to be handed to the API and fail at connect time.
    assert settings._voice_of({}) == "Leda"
    assert settings._voice_of({"voice": "Aoede"}) == "Leda", \
        "a voice that no longer exists was kept"
    assert settings._voice_of({"voice": "Aoede", "voice_picked": True}) == "Leda", \
        "a dropped voice is still being dialled"
    assert settings._voice_of({"voice": "Zephyr"}) == "Leda"
    assert settings._voice_of({"voice": "Kore"}) == "Leda", \
        "a hand-typed unknown voice is passed straight to the API"
    assert settings._voice_of({"voice": "Sulafat"}) == "Sulafat"
    assert settings._voice_of({"voice_picked": True}) == "Leda"

    # the picker offers the three, and saves the name and not the label
    ui = (ROOT / "ui.py").read_text(encoding="utf-8")
    assert "currentData()" in ui, \
        "the picker saves currentText — a label would be saved as a voice name"
    assert "settings.VOICES" in ui and "VOICE_MORE" not in ui.split("# ── helpers")[0]
    assert 'cfg["voice_picked"] = True' in ui, "saving does not mark the choice"

    # and there is still a way to hear them
    hh = (ROOT / "hear_her.py").read_text(encoding="utf-8")
    assert "--voices" in hh and "AUDITION_LINES" in hh, "no audition mode"
    return f"{len(settings.VOICES)} voices, default {settings.DEFAULTS['voice']}"


@check("the voice can change while she is talking, without a restart")
def _voice_live():
    import asyncio
    import time

    import live
    import netwatch

    real_route = netwatch.route_ok_async

    async def route_up():
        return True

    async def scenario():
        s = live.Session("x", voice="Leda", log=netwatch.Line(None))
        dialled, reads, backs, lost = [], [], [], []
        seen_at_redial: list[list] = []   # what the window knew, mid-flip
        entries: list = []                # what _reconnect was told, each time

        async def fake_connect():          # no network, no key, no google
            s._loop = asyncio.get_running_loop()
            s._ready = asyncio.Event()
            s._ready.set()
            s._session_t0 = time.monotonic()
            s._running = True
            s.session = object()           # enough to look connected
            dialled.append(s.voice)
            if len(dialled) > 1:           # the return: nothing was reported
                seen_at_redial.append(list(lost))
            return len(dialled) > 1

        async def fake_read():             # sits on the socket, like the real one
            reads.append(1)
            if len(reads) == 1:
                while s.session is not None:
                    await asyncio.sleep(0.01)
            else:
                s._alive = False           # the second connection is the last

        async def noop():
            await asyncio.sleep(3600)

        real_reconnect = s._reconnect

        async def spy_reconnect():
            entries.append(s._planned)
            return await real_reconnect()

        s.connect, s._read = fake_connect, fake_read
        s._reconnect = spy_reconnect
        s._pump = s._watchdog = noop
        s.on_back = lambda planned=False: backs.append(planned)
        s.on_lost = lambda why="", kind="": lost.append(kind)

        netwatch.route_ok_async = route_up
        try:
            # asking for the voice she already has is not a reconnect
            assert s.set_voice("Leda") is True
            assert s._kill is None, "it hung up to re-apply the same voice"

            task = asyncio.create_task(s.run())
            while not dialled:
                await asyncio.sleep(0.01)
            t0 = time.monotonic()
            assert s.set_voice("Sulafat") is True
            await asyncio.wait_for(task, timeout=5.0)
            took = time.monotonic() - t0
        finally:
            netwatch.route_ok_async = real_route

        assert dialled == ["Leda", "Sulafat"], dialled
        assert took < 1.0, (
            f"a deliberate voice change took {took:.2f}s — it is sitting in "
            f"the reconnect backoff")
        assert s._backoff.attempt == 0, \
            "a voice change used up an outage's worth of patience"
        assert seen_at_redial == [[]], (
            f"the window was told the line dropped during a voice change: "
            f"{seen_at_redial}")
        assert entries == [False, True], (
            f"the reconnect was told it was a handover on entry each time: "
            f"{entries} — it would print a 'back' line and tell her to pick up "
            f"a sentence nobody interrupted")
        assert backs == [True], (
            f"the return was filed as a failure (planned={backs}) — she would "
            f"greet the room instead of continuing")
        assert not [e for e in s.log.recent(40) if e.get("kind") == "drop"], \
            "a voice change was written to the netlog as a drop"

    asyncio.run(scenario())

    # the window has to actually ask for it on save
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "set_voice" in app_src, "saving a voice never reaches the session"
    return "one planned handover, no backoff, no line lost, same conversation"


@check("she hears the tone of the room, not only the words")
def _affective():
    src = (ROOT / "live.py").read_text(encoding="utf-8")
    assert "enable_affective_dialog" in src, \
        "affective dialog is off — a tired voice reads as a neutral sentence"
    assert "dataclasses.fields" in src, \
        "no capability check — an unknown key is a validation error on connect"
    return "affective dialog on, with a fallback for older SDKs"


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ok = fail = 0
    for name, fn in _checks:
        try:
            detail = fn()
            print(f"✅ {name:60}  {detail}")
            ok += 1
        except AssertionError as e:
            print(f"❌ {name:60}  {e}")
            fail += 1
        except Exception as e:
            import traceback
            print(f"❌ {name:60}  {type(e).__name__}: {e}")
            traceback.print_exc()
            fail += 1
    print("=" * 78)
    print(f"{ok} passed · {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
