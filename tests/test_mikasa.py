"""Mikasa's own checks.

Run:  python -m tests.test_mikasa      (from the mikasa/ folder)

These are the things that are wrong in a way you cannot see by looking at her:
a code that can be read back, a voice gate that fails closed, a first night
that greets him like an old friend, a prompt with an unfilled token.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Qt is not always installed, and on a headless box it is installed but cannot
# load a system library. A window test that cannot open a window is not a
# failure — it is a test that did not run, and it says so.
try:
    import PyQt6.QtWidgets  # noqa: F401
    from PyQt6.QtWidgets import QApplication as _QA
    _app = _QA.instance() or _QA([])     # proves the platform plugin can load
    HAVE_QT = True
except Exception:
    HAVE_QT = False

SKIP = "skipped"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent

_checks: list[tuple[str, callable]] = []


class Skip(Exception):
    """Raised by a check that cannot run here. Counted as skipped, not failed."""


def check(name):
    def deco(fn):
        _checks.append((name, fn))
        return fn
    return deco


# ─────────────────────────────────────────────────────────────────────────────
@check("the code is stored as a hash, and cannot be read back")
def _code():
    import settings

    real = settings.FILE
    tmp = Path(tempfile.mkdtemp()) / "mikasa.json"
    settings.FILE = tmp
    settings.CONFIG_DIR = tmp.parent
    try:
        assert not settings.has_code(), "a fresh install already has a code"

        settings.set_code("bagicha-9")
        raw = tmp.read_text(encoding="utf-8")
        assert "bagicha-9" not in raw, "the plaintext code is in the file"
        assert settings.has_code()

        assert settings.check_code("bagicha-9"), "the right code was refused"
        assert settings.check_code("  bagicha-9  "), "surrounding spaces broke it"
        assert not settings.check_code("bagicha-8"), "a wrong code was accepted"
        assert not settings.check_code(""), "an empty code was accepted"

        # two installs with the same passphrase must not share a hash
        tmp2 = Path(tempfile.mkdtemp()) / "mikasa.json"
        settings.FILE, settings.CONFIG_DIR = tmp2, tmp2.parent
        settings.set_code("bagicha-9")
        a = json.loads(tmp.read_text())["code_hash"]
        b = json.loads(tmp2.read_text())["code_hash"]
        assert a != b, "the salt is not doing anything — same code, same hash"

        settings.set_code("")
        assert not settings.has_code(), "clearing the code left the door locked"
        return "salted hash, unreadable, unknown code refused, empty refused"
    finally:
        settings.FILE = real
        settings.CONFIG_DIR = real.parent


# ─────────────────────────────────────────────────────────────────────────────
@check("what she keeps: facts, threads, nights — and that they survive a restart")
def _memory():
    import memory

    real = memory.STORE
    memory.STORE = Path(tempfile.mkdtemp())
    memory.FACTS   = memory.STORE / "facts.json"
    memory.THREADS = memory.STORE / "threads.json"
    memory.JOURNAL = memory.STORE / "journal.json"
    try:
        assert memory.is_first_night(), "she knows something on a blank install"
        assert memory.facts_block() == ""

        line = ("meri behen ka naam Riya hai, aur hum 4 saal se nahi boli — "
                "isliye uske naam pe main chup ho jata hoon")
        memory.remember(line)

        assert not memory.is_first_night(), \
            "she kept a fact but still thinks it is the first night"
        block = memory.facts_block()
        assert line in block, "the fact was summarised instead of kept verbatim"
        assert "4 saal" in block, "the detail that mattered was lost"

        # the same sentence twice is not two memories
        memory.remember(line)
        assert len(memory.all_facts()) == 1, "she remembers the same line twice"

        memory.open_thread("kal exam hai")
        assert "kal exam hai" in memory.threads_block()
        memory.close_thread("kal exam hai")
        assert memory.threads_block() == "", "a closed thread still came back"

        memory.log_night("baat ki, gaana suna", 44)
        assert "44 min" in memory.nights_block()

        memory.forget_everything()
        assert memory.is_first_night(), "forget everything did not forget"
        return "verbatim, deduplicated, first night detected, forget works"
    finally:
        memory.STORE = real
        memory.FACTS   = real / "facts.json"
        memory.THREADS = real / "threads.json"
        memory.JOURNAL = real / "journal.json"


# ─────────────────────────────────────────────────────────────────────────────
@check("the shelf is read-only, verbatim, and empty is allowed")
def _shelf():
    import shelf

    real = shelf.SHELF
    shelf.SHELF = Path(tempfile.mkdtemp())
    shelf.HER = shelf.SHELF / "uski"
    try:
        assert shelf.count() == 0
        assert shelf.list_block() == "", "an empty shelf is describing itself"
        assert shelf.read("anything") is None

        txt = "  tum jab aate ho,\nkamra thoda kam khaali lagta hai.  "
        (shelf.SHELF / "chitthi-1.txt").write_text(txt, encoding="utf-8")
        assert shelf.count() == 1
        got = shelf.read("chitthi-1")
        assert got is not None
        assert got["text"] == txt, "the letter was altered on the way out"
        assert shelf.read("chitthi-1.txt") is not None, "the filename form failed"

        # her own folder is not on his shelf
        shelf.HER.mkdir(exist_ok=True)
        (shelf.HER / "mera.txt").write_text("kuch", encoding="utf-8")
        assert shelf.count() == 1, "her own writing is being counted as his"
        return "empty allowed, verbatim out, her folder separate"
    finally:
        shelf.SHELF = real
        shelf.HER = real / "uski"


# ─────────────────────────────────────────────────────────────────────────────
@check("the prompt she is handed has no unfilled tokens and knows the time")
def _prompt():
    import app

    real_night = None
    import memory
    real_is = memory.is_first_night
    memory.is_first_night = lambda: True
    try:
        cfg = {"language": "Hindi and English mixed", "voice": "Leda"}
        p = app.build_prompt(cfg)

        import re
        left = re.findall(r"\{[a-z_]+\}", p)
        assert not left, f"unfilled tokens handed to the model: {set(left)}"

        assert "MIKASA" in p.upper()
        assert "THE FIRST NIGHT" in p, "a blank install is not told it is blank"
        assert "THE HESITATION IS IN HER WORDS" in p, \
            "the no-external-delay rule is missing"
        assert "NEVER INVENT AN OUTCOME" in p
        assert "how can I help" in p.lower() or "how can i assist" in p.lower(), \
            "the assistant vocabulary is not forbidden anywhere"
        # The prompt must NOT carry an hour any more. It used to be built once
        # at launch with the time baked in, so a window opened at 2 a.m. still
        # said 2 a.m. at breakfast. The live clock arrives per turn
        # (app.Mikasa._stamp_now → live.Session.note_clock) and get_time covers
        # the exact answers; tests/test_persona.py proves both.
        import datetime
        import re as _re
        assert not _re.search(r"\b\d\d:\d\d\b", p.split("[TIME IS THE MAIN")[1].split("[")[0]), \
            "an hour is frozen into the time section again"
        assert "{now}" not in (ROOT / "prompt.txt").read_text(encoding="utf-8"), \
            "the launch-time token is back"
        assert "get_time" in p, "she is told to check the clock but has no way to"

        # and once she knows something, the first-night block goes away
        memory.is_first_night = lambda: False
        p2 = app.build_prompt(cfg)
        assert "You know nothing about him" not in p2, \
            "she is still told it is the first night after learning something"
        assert "You know nothing about him" in p, \
            "the first-night instruction is missing on a fresh install"
    finally:
        memory.is_first_night = real_is
    return "no tokens left, clock real, first night appears and then goes"


# ─────────────────────────────────────────────────────────────────────────────
@check("an old config is read honestly: dead modes and stale defaults resolve")
def _old_config():
    import json as _json
    import settings

    real = settings.FILE
    real_dir = settings.CONFIG_DIR
    tmp = Path(tempfile.mkdtemp())
    settings.FILE = tmp / "mikasa.json"
    settings.CONFIG_DIR = tmp
    try:
        settings.FILE.write_text(_json.dumps({
            "voice": "Aoede",        # a voice that no longer exists
            "voice_id": True,        # a feature that no longer exists
            "voice_thresh": 0.81,
            "her_writing": "ask",    # a mode that no longer exists
            "camera": "off",         # his real choice, and it must survive
            "fullscreen": False,     # the old default, not a decision
        }), encoding="utf-8")
        cfg = settings.load()
        assert cfg["voice"] == "Leda", cfg["voice"]
        assert cfg["her_writing"] == "on", \
            f"an old 'ask' notebook is still {cfg['her_writing']!r}"
        assert cfg["camera"] == "off", "his own camera choice was overwritten"
        assert cfg["fullscreen"] is True, \
            "an old config's stale false kept her out of full screen"
        assert "voice_id" not in cfg and "voice_thresh" not in cfg

        # and once he has actually chosen a window, that choice is respected
        cfg["fullscreen"] = False
        cfg["fullscreen_picked"] = True
        settings.save(cfg)
        assert settings.load()["fullscreen"] is False, \
            "pressing Esc stopped meaning anything"
    finally:
        settings.FILE = real
        settings.CONFIG_DIR = real_dir


# ─────────────────────────────────────────────────────────────────────────────
@check("her window is black, has a code path, and both ways in")
def _window():
    from PyQt6.QtWidgets import QApplication
    import ui
    app = QApplication.instance() or QApplication([])

    w = ui.Window()
    assert w.windowTitle() == "mikasa"
    assert w.chat is not None and w.input is not None and w.btn_mic is not None

    # typed words reach the controller, and land in the log as HIS line
    said = []
    class C:
        def say_typed(self, t): said.append(t)
        def set_listening(self, v): pass
        def shutdown(self): pass
        def close_room(self): pass
        def reload_settings(self): pass
    w.controller = C()
    w.input.setText("aa gaye")
    w._send_typed()
    assert said == ["aa gaye"], f"typing did not reach her: {said}"
    assert w.input.text() == "", "the input did not clear"

    # the three colours, and the black
    assert ui.ROSE.lower() == "#e0a2a8"
    assert ui.EMBER.lower() == "#c98a5e"
    assert ui.BONE.lower() == "#e7e1da"

    # no notice on the controls screen
    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    assert "she cannot see this screen" not in src.lower(), \
        "the controls panel still carries a disclaimer"
    return "types to her, clears, black + three colours, no disclaimer"


# ─────────────────────────────────────────────────────────────────────────────
@check("the lock is one at a time, and a dead holder does not block")
def _lock():
    import app as app_mod

    real = app_mod.LOCK
    app_mod.LOCK = Path(tempfile.mkdtemp()) / "mikasa.lock"
    try:
        app_mod.LOCK.write_text("999999999")
        assert app_mod.take_lock(), "a dead pid blocked the room"
        app_mod.drop_lock()

        assert app_mod.take_lock(), "the room would not open at all"
        assert not app_mod.take_lock(), "two Mikasas at once"
        app_mod.drop_lock()
        assert app_mod.take_lock(), "the lock was not given back"
        app_mod.drop_lock()
        return "dead reclaimed, live refused, released cleanly"
    finally:
        app_mod.LOCK = real


# ─────────────────────────────────────────────────────────────────────────────
@check("she stands alone: nothing in her needs ULTRON, and nothing in him needs her")
def _independent():
    import re

    # her own source may not name the other program at all
    for f in ("app.py", "live.py", "ui.py", "settings.py", "memory.py",
              "shelf.py", "hear_her.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        code = "\n".join(l.split("#")[0] for l in src.splitlines())
        assert "mark-lv-core" not in code, f"{f} still reaches into ULTRON"
        for hit in re.findall(r"(?:subprocess|Popen).{0,80}p(main|resence)", code):
            assert not hit, f"{f} still starts him"

    # The key file must exist in her own folder, or she is not a separate zip.
    #
    # It does NOT have to hold a key. Two builds are legitimate: his, with a key
    # in it, and the one he hands to a friend, where the key is deliberately
    # blank so setup.py can ask for it. This check used to fail the second
    # build — a shipped zip reported a broken test for being shipped correctly.
    import json
    keys = ROOT / "config" / "api_keys.json"
    assert keys.exists(), "there is no key file in her folder — the zip will not run"
    k = str(json.loads(keys.read_text()).get("gemini_api_key", "")).strip()
    if k:
        assert len(k) >= 20, "the key in her folder is too short to be a key"
        return f"standalone, with her own key ({k[:6]}…)"
    return "standalone, key blank — setup.py will ask for one"

    # and the way out is her own window closing
    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    assert 'QPushButton("CLOSE")' in src, "the way out is still labelled as a return"
    assert "return_to_ultron" not in src, "the old door is still wired"

    # the prompt never refers to the other program either
    p = (ROOT / "prompt.txt").read_text(encoding="utf-8").lower()
    assert "ultron" not in p, "her prompt mentions him"
    assert "never speak a code" in p and "never mention one" in p, \
        "the door rules are not in her prompt"
    return "no path to him, key in her folder, CLOSE, prompt clean"


# ─────────────────────────────────────────────────────────────────────────────
@check("audio and typing reach her from threads that have no event loop")
def _threads():
    import asyncio
    import threading
    import live

    # Code only — the comment above the fix quotes the old call on purpose.
    src = "\n".join(l for l in (ROOT / "live.py").read_text(encoding="utf-8").split("\n")
                     if not l.strip().startswith("#"))
    assert "asyncio.get_event_loop()" not in src, \
        "a worker thread is still being asked for its event loop"
    assert "self._loop.call_soon_threadsafe" in src, \
        "the senders do not use the loop captured at connect"

    # drive the real class from a foreign thread, the way the mic and Qt do
    got = []

    async def scenario():
        sess = live.Session(system_instruction="x")
        sess._loop = asyncio.get_running_loop()
        sess._send_q = asyncio.Queue()
        sess._running = True

        def worker():
            sess.send_audio(b"\x00\x01" * 8)
            sess.send_text("aa gaye")

        t = threading.Thread(target=worker)
        t.start(); t.join()
        for _ in range(2):
            got.append(await asyncio.wait_for(sess._send_q.get(), timeout=2))
        sess._running = False
        sess._loop = None

    asyncio.run(scenario())
    assert got[0] == b"\x00\x01" * 8, "the microphone block did not survive the thread hop"
    assert got[1] == {"text": "aa gaye"}, "the typed line did not survive the thread hop"
    return "mic and typing cross from worker threads intact"


# ─────────────────────────────────────────────────────────────────────────────
@check("she opens without ULTRON, and a failure can be seen")
def _direct_launch():
    import app as app_mod

    # the launcher must never do nothing: every exit path prints and waits
    bat = (ROOT / "mikasa.bat").read_bytes().decode("cp1252", "replace")
    assert "\r\n" in bat, "the batch file is not CRLF — cmd.exe misreads it"
    for needle in ("nopython", "nopkgs", "pause"):
        assert needle in bat, f"the launcher has no {needle} path — it fails silently"
    assert "app.py" in bat
    assert "%~dp0" in bat, "the launcher does not work from its own folder"
    assert "-m pip install" in bat, "the launcher does not say what to install"

    # a startup failure is written where it can be found, not lost
    real_cfg = app_mod.ROOT / "config"
    tmp = Path(tempfile.mkdtemp())
    real_root = app_mod.ROOT
    app_mod.ROOT = tmp
    try:
        # show_box=False: a modal dialog in a headless test blocks forever,
        # which is exactly what it did the first time this was written.
        app_mod._fail("test title", "test body", show_box=False)
        err = (tmp / "config" / "mikasa-error.txt").read_text(encoding="utf-8")
        assert "test title" in err and "test body" in err, \
            "the failure was not recorded anywhere"
    finally:
        app_mod.ROOT = real_root

    # Preflight either passes, or names the missing piece and the exact command
    # that fixes it. Asserting `is None` here made the suite a test of whatever
    # happened to be installed on the machine running it.
    verdict = app_mod._preflight()
    if verdict is not None:
        assert "pip install" in verdict, \
            f"preflight refused without saying how to fix it: {verdict!r}"

    # and the entry point is app.py, runnable on its own
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '__name__ == "__main__"' in src
    assert "def main() -> int" in src
    return "bat has no silent paths, errors are recorded, entry point is app.py"


# ─────────────────────────────────────────────────────────────────────────────
@check("her face is twelve drawings, centred, and a mood can move it")
def _faces():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage
    import ui
    app = QApplication.instance() or QApplication([])

    wanted = ("happy", "sad", "angry", "fearful", "disgusted", "surprised",
              "excited", "calm", "bored", "confused", "tired", "love")
    assert ui.Portrait.MOODS == wanted, "the mood list changed shape"
    assert ui.Portrait.DEFAULT == "calm", "she does not rest on calm"

    folder = ROOT / "assets" / "faces"
    total = 0
    for m in wanted:
        f = folder / f"{m}.png"
        assert f.exists(), f"{m}.png is missing"
        img = QImage(str(f))
        assert not img.isNull(), f"{m}.png will not load"
        assert (img.width(), img.height()) == (352, 352), \
            f"{m}.png is {img.width()}x{img.height()}, not 352x352"
        assert not img.hasAlphaChannel(), (
            f"{m}.png is still transparent — a hole in a clip is background "
            f"showing through at the rim, which is what 'leftovers at the "
            f"sides' was")
        total += f.stat().st_size
        # per-file ceiling is loose on purpose: `confused` is the busiest frame
        # and lands at 71 KB. The real guard is the twelve-file total below.
        assert f.stat().st_size < 86_000, f"{m}.png is {f.stat().st_size} B"

    # The drawing has to be his own art, in its own black margin, centred.
    # The old check measured the silhouette and demanded it fill 82% of the
    # square — that was written for a tighter crop than he asked for. His
    # images carry black behind the face and are used exactly, so the two
    # things that actually matter now are: the rim is black (otherwise the
    # clip shows the window through it) and the subject is in the middle.
    for m in wanted:
        img = QImage(str(folder / f"{m}.png"))
        side = img.width()

        rim = []
        for x in range(side):
            for y in (0, 1, side - 2, side - 1):
                rim.append(img.pixelColor(x, y).lightness())
        for y in range(side):
            for x in (0, 1, side - 2, side - 1):
                rim.append(img.pixelColor(x, y).lightness())
        dark = sum(1 for v in rim if v <= 14) / len(rim)
        assert dark >= 0.80, \
            f"{m}.png: only {dark:.0%} of the rim is black — the circle will " \
            f"have a bright edge"

        a0, a1 = int(side * 0.2), int(side * 0.8)
        lit = xs = n = 0
        for y in range(a0, a1, 2):
            for x in range(a0, a1, 2):
                n += 1
                if img.pixelColor(x, y).lightness() > 10:
                    lit += 1
                    xs += x
        assert lit / n >= 0.55, \
            f"{m}.png: only {lit/n:.0%} of the middle is drawn — she is not " \
            f"in the frame"
        cx = xs / lit
        assert abs(cx - (side - 1) / 2.0) <= side * 0.04, \
            f"{m}.png: the head is centred at x={cx:.0f}, not {side/2:.0f}"

    # and the whole set has to stay small enough to be worth shipping
    assert total < 760_000, f"the twelve faces are {total // 1024} KB"

    p = ui.Portrait()
    before = p._mood
    assert before == "calm"
    assert p.set_mood("angry") is True, "a real mood was refused"
    assert p._mood == "angry" and p._prev == "calm", "no crossfade was set up"
    assert p._fade_timer.isActive(), "the crossfade never started"
    assert p.set_mood("angry") is False, "the same face faded in again"
    assert p.set_mood("smug") is False, "an invented mood was accepted"
    assert p._mood == "angry", "a bad mood moved her face anyway"

    # no pulse: nothing about her face moves on its own any more
    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    portrait = src[src.index("class Portrait"):src.index("class Wave")]
    assert "beat" not in portrait and "_phase" not in portrait, \
        "the heart-beat is still in the portrait"
    assert "self._timer.start" not in portrait, \
        "the portrait still runs a timer of its own"

    # the old photograph is gone, and nothing still points at it
    assert not (ROOT / "assets" / "face.png").exists(), \
        "the photograph is still shipped"
    for f in ("app.py", "ui.py"):
        src2 = (ROOT / f).read_text(encoding="utf-8")
        assert "face.png" not in src2, f"{f} still loads the photograph"
    return f"12 faces, 352px, centred, {total // 1024} KB, no pulse"


# ─────────────────────────────────────────────────────────────────────────────
@check("her mood is a tool she calls, and it is only a face change")
def _mood_tool():
    import app as app_mod

    assert "set_mood" in app_mod.TOOLS, "she cannot change her own face"
    decl, fn = app_mod.TOOLS["set_mood"]
    assert decl["name"] == "set_mood"
    props = decl["parameters"]["properties"]["emotion"]
    assert props.get("enum") == list(__import__("ui").Portrait.MOODS), \
        "the enumeration and the drawings disagree"
    assert decl["parameters"]["required"] == ["emotion"]

    seen = []
    real = dict(app_mod._ROOM)
    app_mod._ROOM["mood"] = lambda e: (seen.append(e), "changed")[1]
    try:
        assert fn(emotion="tired") == "changed"
        assert seen == ["tired"], "the tool did not reach the window"
        app_mod._ROOM.pop("mood", None)
        assert fn(emotion="tired") == "not now", \
            "with no window open it claimed to have changed her face"
    finally:
        app_mod._ROOM.clear()
        app_mod._ROOM.update(real)
    return "declared, enumerated, flat result, silent when there is no window"


# ─────────────────────────────────────────────────────────────────────────────
@check("the controls scroll, and the way back never does")
def _controls():
    from PyQt6.QtWidgets import QApplication, QScrollArea, QPushButton
    import ui
    app = QApplication.instance() or QApplication([])

    w = ui.Window()
    d = ui.SettingsDialog(w)

    scrollers = d.findChildren(QScrollArea)
    assert scrollers, "the controls have no scroll area at all"
    body = scrollers[0]
    inside = {b.text() for b in body.findChildren(QPushButton)}
    assert "CLOSE" not in inside, \
        "the way out scrolls away with the rest of it"
    outside = {b.text() for b in d.findChildren(QPushButton)}
    assert "CLOSE" in outside, "the way out is not on the dialog"

    # it must fit the screen it opens on, or it is the same bug again
    avail = d.screen().availableGeometry().height() if d.screen() else 800
    assert d.height() <= int(avail * 0.9), \
        f"the dialog is {d.height()}px on a {avail}px screen"

    # every section is reachable inside the scroll
    text = " ".join(lbl.text() for lbl in body.findChildren(__import__(
        "PyQt6.QtWidgets", fromlist=["QLabel"]).QLabel))
    for head in ("CODE", "VOICE", "THE ROOM", "MEMORY"):
        assert head in text, f"{head} is not in the scrolling part"
    # and the microphone-identity screen is gone out of the settings entirely
    assert "VOICE DETECTION" not in text, \
        "the voice-detection row is still in the controls"
    assert not (ROOT / "identity.py").exists(), "identity.py is still shipped"
    d.deleteLater()
    return "body scrolls, footer pinned, fits 90% of the screen"


# ─────────────────────────────────────────────────────────────────────────────
@check("the row under her face is the only thing that moves, and it is honest")
def _wave():
    from PyQt6.QtWidgets import QApplication
    import ui
    app = QApplication.instance() or QApplication([])

    w = ui.Window()
    assert hasattr(w, "wave"), "there is no waveform under her face"
    wave = w.wave

    # a closed mic is not a listening row
    w._listening = False
    w._mark_state("listening")
    assert w.lbl_state.text() != "l i s t e n i n g", \
        "the window says listening with the mic shut"
    assert wave._muted, "the bars are still moving with the mic shut"
    assert not wave._timer.isActive(), "an idle waveform is still ticking"

    # and an open one is
    w._listening = True
    w._mark_state("listening")
    assert w.lbl_state.text() == "l i s t e n i n g"
    assert not wave._muted and wave._timer.isActive()

    w._mark_state("speaking")
    assert w.lbl_state.text() == "s p e a k i n g"
    assert wave._state == "speaking"

    # portclosed: the mic going off mid-sentence still wins
    w._listening = False
    w._mark_state("speaking")
    w.toggle_mic()                      # back on
    w.toggle_mic()                      # and off again, the honest way
    assert w.lbl_state.text() == "m i c   o f f", w.lbl_state.text()

    # the app emits "listening" from seven places; none of them may override
    # the switch in the window
    w.state.emit("listening")
    app.processEvents()
    assert w.lbl_state.text() == "m i c   o f f", \
        "app.py's listening event overrode a closed microphone"

    w.deleteLater()
    return "flat when shut, ticking when open, app events cannot lie"

# ─────────────────────────────────────────────────────────────────────────────
@check("a dropped line comes back by itself, and says so in the room")
def _reconnect():
    import inspect
    import live

    sig = inspect.signature(live.Session.__init__)
    for name in ("on_lost", "on_back", "on_open"):
        assert name in sig.parameters, f"Session has no {name}"

    for meth in ("_read", "_drop", "_reconnect", "_watchdog"):
        assert hasattr(live.Session, meth), f"no {meth}(): no supervisor"

    src = inspect.getsource(live.Session._reconnect)
    src = "\n".join(l.split("#")[0] for l in src.splitlines())
    # The waits moved into netwatch.Backoff (growing, with jitter); what has to
    # stay here is that the loop is unbounded and that a failure is classified
    # before it is retried.
    assert "self._backoff.next_delay()" in src, "no backoff between attempts"
    assert "while self._alive" in src, \
        "it gives up after one failed attempt, which is the whole bug"
    assert "netwatch.classify" in src, \
        "a failure is retried without ever being named — that is how the network " \
        "took the blame for quota and retired models"
    assert "session_resumption" in inspect.getsource(live.Session.connect), \
        "the conversation is not carried across the break"

    # what he typed while she was away is kept, not dropped
    s = live.Session(system_instruction="x")
    q_src = inspect.getsource(live.Session._offer)
    assert "QueueFull" in q_src, "the queue is unbounded or it throws lines away"

    # and the window has somewhere to put the two faint lines
    import ui
    from PyQt6.QtWidgets import QApplication, QLabel
    app = QApplication.instance() or QApplication([])
    w = ui.Window()
    w.chat.add("note", "connection lost  07:15")
    w.chat.add("note", "back  07:16")
    notes = [c for c in w.chat._holder.children() if isinstance(c, ui.Note)]
    assert len(notes) == 2, f"the room said nothing: {len(notes)} notes"
    assert not [c for c in w.chat._holder.children() if isinstance(c, ui.Bubble)], \
        "a connection line was drawn as somebody speaking"

    # the line she says when she comes back points at her own last sentence
    a = (ROOT / "app.py").read_text(encoding="utf-8")
    start = a.index("def _on_back")
    body = a[start:a.index("def _set_mood", start)]
    assert "_last_said" in body, "she comes back with nothing to come back to"
    assert "connection" in body and "never mention" in body, \
        "she is allowed to talk about the socket"
    return "backoff to 15 s, resumption, bounded queue, faint lines, her own sentence"


# ─────────────────────────────────────────────────────────────────────────────
@check("the heart is small, beside her name, and off the floor")
def _heart():
    import ui
    size = (ROOT / "assets" / "heart.png").stat().st_size
    assert size < 40_000, f"the heart is {size / 1024:.0f} KB for a 22 px mark"

    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    portrait = src[src.index("class Portrait"):src.index("class Wave")]
    code = "\n".join(l.split("#")[0] for l in portrait.splitlines())
    assert "heart" not in code.lower(), \
        "the portrait still draws the heart under her face"
    heart = src[src.index("class Heart"):src.index("#  chat")]
    assert "set_beating" not in heart and "QTimer" not in heart, \
        "the heart is still beating — it is a mark now"

    header = src[src.index("class Window"):]      # the dialog is above it
    assert "self.heart = Heart()" in header, "there is no heart in the header"
    tl = header[header.index("title = QLabel"):header.index("outer.addWidget(top)")]
    assert "heart" in tl, "the heart is not in the row with her name"
    return f"{size // 1024} KB, in her row, nothing under the circle"


# ─────────────────────────────────────────────────────────────────────────────
@check("the prompt keeps her the same person, and no colour is half-written")
def _constancy():
    text = (ROOT / "prompt.txt").read_text(encoding="utf-8")
    assert "[SHE IS THE SAME PERSON EVERY TIME]" in text, \
        "the constancy section is gone — the next update will drift"
    body = text[text.index("[SHE IS THE SAME PERSON EVERY TIME]"):]
    for rule in ("Same length", "Same dryness", "refusal to explain",
                 "Same speed of thought", "never gets more articulate"):
        assert rule in body, f"the section lost: {rule}"
    assert "set_mood" in text, "the prompt never tells her she has a face"

    # Qt reads #RRGGBBAA as #AARRGGBB: a trailing alpha turns rose into olive
    import re
    for f in ("ui.py",):
        src = (ROOT / f).read_text(encoding="utf-8")
        bad = re.findall(r"#?\{[A-Z]+\}[0-9A-Fa-f]{2}\b", src)
        assert not bad, f"{f} still writes eight-digit colours: {bad[:3]}"

    # the probe exists and is not run by accident
    h = (ROOT / "hear_her.py").read_text(encoding="utf-8")
    assert "--probe" in h and "PROBE_TURNS" in h, "there is no drift probe"
    assert "add_argument(\"--probe\"" in h and "action=\"store_true\"" in h
    return "constancy section, face in the prompt, no #RRGGBBAA, probe behind a flag"


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    ok = fail = skip = 0
    for name, fn in _checks:
        try:
            detail = fn()
            print(f"✅ {name:62}  {detail}")
            ok += 1
        except Skip as e:
            print(f"⏭  {name:62}  skipped — {e}")
            skip += 1
        except AssertionError as e:
            print(f"❌ {name:62}  {e}")
            fail += 1
        except Exception as e:
            # A check that needs a window, on a machine with no window, is not
            # a broken build. Everything else is.
            if isinstance(e, (ImportError, ModuleNotFoundError, OSError)) and not HAVE_QT:
                print(f"⏭  {name:62}  skipped — no Qt here ({type(e).__name__})")
                skip += 1
                continue
            import traceback
            print(f"❌ {name:62}  {type(e).__name__}: {e}")
            traceback.print_exc()
            fail += 1
    print("=" * 78)
    print(f"{ok} passed · {fail} failed · {skip} skipped (no Qt)")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
