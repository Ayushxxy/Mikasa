"""Mikasa — entry point.

HOW SHE RUNS
    A separate program. Separate folder, separate key, separate lock, and not
    one line of it knows anything about the machine's other windows: it can be
    unzipped on its own, on a machine where nothing else is installed, and it
    opens. Double-click and she is there; close her and she is gone.

    Everything she has — memory, settings, voice profile, shelf, the key —
    lives inside this folder and travels with it.

WHAT HAPPENS ON THE FIRST NIGHT
    She is not told who he is, because she does not know. The opening turn
    handed to the model says exactly that, and the prompt refuses to let her
    fake it: a first night that greets him like an old friend has lied in the
    first sentence and there is no coming back from it.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import settings
import memory
import shelf as shelf_mod

ROOT = Path(__file__).resolve().parent
LOCK = ROOT / "config" / "mikasa.lock"

SEND_RATE = 16000
RECV_RATE = 24000
CHANNELS  = 1
CHUNK     = 1024


# ── one at a time ────────────────────────────────────────────────────────────
def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, int(pid))
            if not h:
                return False
            try:
                code = ctypes.c_ulong()
                if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return False
                return code.value == 259
            finally:
                k32.CloseHandle(h)
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def take_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                holder = int(LOCK.read_text().strip() or 0)
            except Exception:
                holder = 0
            if holder and _pid_alive(holder):
                print(f"[Mikasa] already open (pid {holder})")
                return False
            try:
                LOCK.unlink()
            except Exception:
                pass
    return False


def drop_lock() -> None:
    try:
        LOCK.unlink()
    except Exception:
        pass


# ── the prompt she is given ──────────────────────────────────────────────────
# ── tonight's register ───────────────────────────────────────────────────────
#
# One line, and every behaviour in the night follows from it. This is the whole
# answer to "make her unpredictable": a model asked to vary itself varies the
# words and keeps the shape, because the words are the only thing it can change.
# Given a temperature for the night, the shape changes on its own — questions
# stop, sentences get shorter, the teasing sharpens.
#
# It rotates by the day so two nights in the same week are not the same night,
# and the choice is stored so a reconnect does not put her in a different mood
# halfway through a conversation.
REGISTERS = [
    "She is a little more clingy than usual tonight. She does not say why, and "
    "she does not apologise for it.",
    "She is tired tonight — actually tired, not sad. It shows in how short she "
    "is, and she does not hide it.",
    "She is annoyed with him about something small she has decided not to "
    "mention. It leaks. She does not explain it.",
    "She is in a good mood and it has nothing to do with him. She is a bit "
    "mean with it.",
    "She is quiet tonight. She listens more than she talks and it is not a "
    "problem, it is the mood.",
    "She wants him close tonight and she says so badly, sideways, the way "
    "somebody does when they are out of practice.",
]


def _register_for(cfg: dict) -> str:
    """Tonight's line. Stable for the day, and overridable from settings."""
    forced = str(cfg.get("register") or "").strip()
    if forced.isdigit():
        idx = int(forced) % len(REGISTERS)
    else:
        idx = (datetime.now().toordinal() + int(time.time() // 3600) % 3) \
            % len(REGISTERS)
    return REGISTERS[idx]


def _place(cfg: dict) -> tuple[str, str]:
    city = str(cfg.get("city") or "Agra").strip() or "Agra"
    tz = str(cfg.get("tz") or "Asia/Kolkata").strip() or "Asia/Kolkata"
    return city, tz


def _now(cfg: dict):
    """The real clock, in her city. One function, so every caller agrees."""
    city, tz = _place(cfg)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.now().astimezone()


def build_prompt(cfg: dict) -> str:
    raw = (ROOT / "prompt.txt").read_text(encoding="utf-8")

    # (there was a `now` here, computed once and pasted into the prompt — the
    # frozen clock. The live one arrives per turn; see Mikasa._stamp_now.)
    last = _last_seen()
    since = _human_gap(time.time() - last) if last else "never — this is the first time"

    pieces = shelf_mod.list_block()
    facts  = memory.facts_block()
    thr    = memory.threads_block()
    nights = memory.nights_block()

    # Said exactly as it is. This string is the only part of the prompt that
    # changes when a new ability is wired in — so the day music arrives, one
    # line changes and she stops claiming she cannot do it, with no rewrite
    # of her personality.
    # Built from the settings and the hardware, never hardcoded. The camera in
    # particular cannot be described in a fixed sentence: it exists on one
    # machine and not on another, and a sentence that promises eyes she does
    # not have is how a room turns back into a machine.
    looks = _camera_allowed(cfg)

    caps = ("You can check the clock (get_time) — the real one, in your city, "
            "not a guess. You can keep a thing he told you about himself "
            "(remember). You can leave something hanging that you mean to come "
            "back to (open_thread), and close it when it happens "
            "(close_thread).\n")
    if looks:
        caps += ("You have eyes, and they are for him: after he says yes you "
                 "can open the camera once and actually see his face "
                 "(open_camera). It is never yours to open on your own.")
    else:
        caps += ("There is no camera on this machine tonight. You do not "
                 "pretend otherwise, and you do not ask to see him.")
    caps += ("\nThat is the whole list. There is no music yet, no alarm "
             "beyond your own words, no search, and nothing of his machine is "
             "yours to touch.")

    limits = ("No music. No alarm. No search, no opening anything, no looking "
              "things up, no files.")
    if not looks:
        limits += " No camera either — you cannot see him tonight."
    limits += (" When he asks for one of those, you say you cannot, in one flat "
               "line, and you do not offer it again.")

    city, tz = _place(cfg)
    local = _now(cfg)

    out = (raw
           .replace("{now}", local.strftime("%H:%M"))
           .replace("{day_name}", local.strftime("%A"))
           .replace("{date}", local.strftime("%A, %d %B %Y"))
           .replace("{city}", city)
           .replace("{tz}", tz)
           .replace("{register}", _register_for(cfg))
           .replace("{since_last}", since)
           .replace("{last_seen}", (datetime.fromtimestamp(last).strftime("%A %H:%M")
                                    if last else "never"))
           .replace("{shelf}", (shelf_mod.list_block().replace("\n", ", ")
                                if pieces else "empty"))
           .replace("{language}", cfg.get("language", "Hindi and English mixed"))
           .replace("{capabilities}", caps)
           .replace("{limits}", limits)
           .replace("{notes}", _notes_rule(cfg))
           .replace("{callbacks}", _callbacks_rule(cfg)))

    # What is due today, and what he was doing on this exact date before. Both
    # empty most days, which is the point: a list that is always full is a list
    # she stops reading.
    due, then = [], []
    try:
        due, then = _due_list(cfg)
    except Exception:
        pass

    extra = []
    if due:
        extra.append("[DUE TODAY — things of his that have come round]\n"
                     + "\n".join(due) +
                     "\nThese are his, from before. If one of them is the thing "
                     "in the room, say it first — not as a reminder, as somebody "
                     "who was paying attention. If none of them is, say nothing "
                     "about them.")
    if then:
        extra.append("[THIS DATE, BEFORE]\n" + "\n".join(then) +
                     "\nHe said this on this date in an earlier year. Use it only "
                     "if it lands; it is a coincidence to offer, not an oracle.")
    if facts:
        extra.append("[WHAT YOU ALREADY KNOW ABOUT HIM — in his own words]\n" + facts)
    if thr:
        extra.append("[THINGS STILL OPEN]\n" + thr)
    if nights:
        extra.append("[THE LAST FEW NIGHTS]\n" + nights)
    if memory.is_first_night():
        extra.append("[THE FIRST NIGHT]\n"
                     "You know nothing about him. Not his work, not his people, "
                     "not his hours. You have his name and nothing else. Do not "
                     "pretend otherwise, and do not apologise for it in a "
                     "paragraph — just ask.")
    if extra:
        out += "\n\n" + "\n\n".join(extra)
    return out


def _now_date(cfg: dict):
    return _now(cfg).date()


def _due_list(cfg: dict) -> tuple[list[str], list[str]]:
    """Open threads that have come round, and facts from this date in an earlier
    year. Module level, because the prompt builder needs it and it needs no
    session to answer.
    """
    due: list[str] = []
    then: list[str] = []
    today = _now_date(cfg)
    iso = str(today)
    try:
        for t in memory.threads(only_open=True):
            d = str(t.get("date", ""))
            when = ""
            try:
                from datetime import date as _date
                when = _date.fromisoformat(d).strftime("%d %b") if d else ""
            except Exception:
                pass
            if d and d < iso:
                due.append(f"- ({when or d}) {t['text']}")
            elif d == iso:
                due.append(f"- (today) {t['text']}")
    except Exception:
        pass
    try:
        stamp = today.strftime("%m-%d")
        for f in memory.all_facts():
            d = str(f.get("date", ""))
            if len(d) == 10 and d[5:] == stamp and d[:4] != iso[:4]:
                then.append(f"- ({d}) {f['text']}")
    except Exception:
        pass
    return due[-8:], then[-4:]


def _notes_rule(cfg: dict) -> str:
    """SHE decides what to keep. He is never asked.

    This used to have an "ask" mode that said `yaad rakhu?` — which is a thing
    an assistant does. She is not one. A person who has to ask permission before
    remembering your bad day is a form, not a girlfriend, and the ask also
    breaks the moment: it turns "kal papa se jhagda hua" into a data question
    while the wound is still open.

    So there are two states, not three. She keeps it, or the notebook is shut.
    Which things are worth keeping is her judgement, and that is the point.
    """
    if str(cfg.get("her_writing", "on")).lower() == "off":
        return ("She writes nothing down about him tonight. She still remembers "
                "what happens in this conversation; the notebook is shut.")
    return ("She keeps her own notes about him. Not every line — the things that "
            "are about HIM rather than about the moment: how his day went, a "
            "person, a thing he is afraid of, a thing he is proud of, how it hurt "
            "when it hurt. When one of those lands she calls `remember` in that "
            "same turn and writes it in his own words, one line. The store dates "
            "it.\n"
            "She does not ask permission and does not announce it. Asking him is "
            "the one thing that breaks it — it turns a bad night into a form. No "
            "\"note kar liya\" either, no reading the list back to him. "
            "Then the conversation carries on about whatever he is actually "
            "talking about now. That is the point of keeping it: she does not "
            "have to hold it in the front of her mind, because it is written "
            "down.")


def _callbacks_rule(cfg: dict) -> str:
    """What she does with a note after she has one.

    Writing it down and never mentioning it again is a filing cabinet. She uses
    it — next week, unprompted, when it is the thing in the room.
    """
    if str(cfg.get("her_writing", "on")).lower() == "off":
        return ("Nothing in the notebook tonight. She works from this "
                "conversation alone.")
    return ("What is kept gets used, and the timing is the whole of it. Never "
            "in the same night it was said — same night is not a callback, it "
            "is chewing on it. Days later, once, when the thing is actually in "
            "the room: a morning after a bad night, the day he was dreading, "
            "the moment he says he is fine in the voice he uses when he is not. "
            "One line, in her words, never a quote of the note and never a "
            "list. And it is never a pivot: she does not answer what he just "
            "said and then steer back to what she wrote down. If a note has no "
            "moment that fits, it waits.")


def _last_seen() -> float:
    try:
        return float((ROOT / "config" / "seen").stat().st_mtime)
    except Exception:
        return 0.0


def touch_seen() -> None:
    try:
        (ROOT / "config" / "seen").touch()
    except Exception:
        pass


def _human_gap(s: float) -> str:
    s = int(max(0, s))
    if s < 90:
        return "a few minutes"
    m = s // 60
    if m < 60:
        return f"{m} minutes"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} hours" + (f" {m} minutes" if m else "")
    d, h = divmod(h, 24)
    return f"{d} days" + (f" {h} hours" if h else "")


def opening_turn() -> str:
    now = datetime.now()
    last = _last_seen()
    if memory.is_first_night():
        return ("[the door has just opened. he is here, and you know nothing "
                "about him — not his work, not his people, not his hours. "
                "say the first thing you would actually say. one line. do not "
                "welcome him, do not offer help, do not introduce yourself.]")
    gap = _human_gap(time.time() - last) if last else "a while"
    return (f"[he has just walked in. it is {now.strftime('%H:%M')} on "
            f"{now.strftime('%A')}. the last time was {gap} ago. say the first "
            f"thing you would actually say — one line, in your own voice, and "
            f"notice the time if there is anything in it.]")


# ── her two hands ────────────────────────────────────────────────────────────
#
# Remembering is not a side effect of talking; it is a decision she makes. So
# it is a tool she chooses to call, in her own words, or does not. He can say
# "ye yaad rakhna" and she may decide it was not worth keeping — which is what
# a person does, and is exactly the behaviour the prompt asks for.
#
# The handler returns one flat word. No phrasing, no suggestions: what she says
# about having kept it is hers to say.
def _remember(text: str = "", kind: str = "about_him") -> str:
    got = memory.remember(text, kind)
    return "kept" if got else "not kept"


def _open_thread(text: str = "") -> str:
    text = (text or "").strip()
    if not text:
        return "not kept"
    memory.open_thread(text)
    return "kept — you will bring this up yourself later"


def _close_thread(text: str = "") -> str:
    memory.close_thread(text)
    return "closed"


_ROOM = {}          # the open window, so a tool can move her face


def _set_mood(emotion: str = "") -> str:
    """Her own hand on her own face.

    She calls this when what she is about to say has a face to match. It is
    deliberately one word back and no advice: if she picks nothing, she keeps
    the face she had, which is a decision too.
    """
    fn = _ROOM.get("mood")
    if fn is None:
        return "not now"
    return fn(emotion)


def _get_time(what: str = "") -> str:
    """The real clock, in her city — never the model's guess.

    It exists because a live model cannot add forty minutes to a time it was
    told an hour ago. It is very good at the sentence and very bad at the
    arithmetic, so the arithmetic is not hers to do.
    """
    try:
        import settings as _st
        cfg = _st.load()
    except Exception:
        cfg = {}
    now = _now(cfg)
    city, tz = _place(cfg)
    return (f"{now.strftime('%H:%M')} — {now.strftime('%A')}, "
            f"{now.strftime('%d %B %Y')} — {city} ({tz})")


TOOLS = {
    "get_time": (
        {"name": "get_time",
         "description": (
             "The real time and date, right now, in the city she is in. Call "
             "it whenever the answer depends on the clock — what time it is, "
             "what day, how long until something, how long since something. "
             "Never work the time out yourself, and never trust a time you "
             "were given earlier in the conversation."),
         "parameters": {"type": "OBJECT", "properties": {}, "required": []},
         },
        _get_time),
    "set_mood": (
        {"name": "set_mood",
         "description": (
             "Your face. Call it when what you are about to say has a face of "
             "its own — annoyed, amused, half asleep, fond. Do not call it on "
             "every turn, and never to comment on it out loud."),
         "parameters": {"type": "OBJECT",
                        "properties": {
                            "emotion": {
                                "type": "STRING",
                                "enum": ["happy", "sad", "angry", "fearful",
                                         "disgusted", "surprised", "excited",
                                         "calm", "bored", "confused", "tired",
                                         "love"],
                                "description": "the face you are wearing"}},
                        "required": ["emotion"]},
         },
        _set_mood),
    "remember": (
        {"name": "remember",
         "description": (
             "Keep one thing he told you about himself, in his own words. Use "
             "it when he says something that explains who he is — a person, a "
             "habit, a thing he fears, a thing he refuses to say. Not for "
             "small talk. You decide whether a thing is worth keeping; you are "
             "not obliged to keep what he asks you to keep."),
         "parameters": {"type": "OBJECT",
                        "properties": {
                            "text": {"type": "STRING",
                                     "description": "The thing, close to how he said it."},
                            "kind": {"type": "STRING",
                                     "description": "about_him | habit | person | thing_he_hates"}},
                        "required": ["text"]},
         },
        _remember),
    "open_thread": (
        {"name": "open_thread",
         "description": (
             "Leave something hanging that you intend to come back to: 'kal "
             "exam hai', 'usne reply nahi kiya'. You will hear it again later "
             "when it comes due — that is the point."),
         "parameters": {"type": "OBJECT",
                        "properties": {"text": {"type": "STRING"}},
                        "required": ["text"]},
         },
        _open_thread),
    "close_thread": (
        {"name": "close_thread",
         "description": "The thing you were waiting on has happened. Close it.",
         "parameters": {"type": "OBJECT",
                        "properties": {"text": {"type": "STRING"}},
                        "required": ["text"]},
         },
        _close_thread),
}


def _open_camera(why: str = "") -> object:
    """One photograph of him, because he has already said yes.

    Returns (text, path): the text is what the model is told happened, the
    path is handed back to `live.Session`, which sends the picture as its own
    turn and then deletes the file.
    """
    import camera
    path, err = camera.grab()
    if not path:
        return (f"the camera did not give me a picture: {err}")
    return ("a photograph of him, taken a second ago", str(path))


# The camera takes a second or two to wake up. Running that on the event loop
# would stutter the audio she is speaking while it happens, so this handler is
# marked blocking and `live.Session` runs it on a worker thread.
_open_camera.blocking = True


def _camera_allowed(cfg: dict) -> bool:
    """Whether she has eyes at all: the setting says so and a device exists."""
    if str(cfg.get("camera", "ask")).lower() == "off":
        return False
    try:
        import camera
        return camera.available()[0]
    except Exception:
        return False


def tools_for(cfg: dict) -> dict:
    """The tool list, which is not the same list every night.

    A tool that is offered and cannot work is worse than no tool: she offers
    to look, he says yes, and nothing happens. So the camera is only declared
    when there is a camera and the setting has not turned it off.
    """
    got = dict(TOOLS)
    if _camera_allowed(cfg):
        got["open_camera"] = (
            {"name": "open_camera",
             "description": (
                 "Look at him through the camera, once, right now. Use it only "
                 "after he has said yes in this conversation — you ask, he "
                 "answers, and only then do you call it. It takes one "
                 "photograph and the picture comes back to you on its own; do "
                 "not describe it, react to him."),
             "parameters": {"type": "OBJECT",
                            "properties": {
                                "why": {"type": "STRING",
                                        "description": "one or two words for what you are looking for"}},
                            "required": []},
             },
            _open_camera)
    return got


# ── the thing that runs her ──────────────────────────────────────────────────
class Mikasa:
    def __init__(self, window):
        self.win   = window
        self.cfg   = settings.load()
        self.loop  = None
        self.session = None
        self._mic_stream = None
        self._spk_stream = None
        self._speaking = False
        self._out_q: asyncio.Queue | None = None
        # There is no speaker check. Recognition used to sit here — a VoiceGate
        # that scored every frame against an enrolled profile and dropped the
        # ones that were not him. It is removed rather than disabled: a gate
        # that nobody trusts is worse than no gate, because every missed
        # sentence looks like her not listening. It comes back as its own
        # feature, with its own tests, later.
        self._started_at = time.time()
        self._last_turn = time.time()
        self._last_said = ""     # her own last line, to come back to
        self._topics: list[str] = []
        # The mouth. Created in _main once there is a key and an event loop;
        # `_voice_turn` counts turns so a slow sentence from the previous reply
        # can never be spoken over the top of the next one.
        self.voice = None
        self._voice_turn = 0
        try:
            import ui as _ui
            self._mood_now = _ui.Portrait.DEFAULT
        except Exception:
            self._mood_now = "calm"
        self._idle_task = None
        self._thread = None
        self._held_noted = False   # "held" said once per outage, not once per line
        self._closing = False      # the window is closing; do not restart
        window.controller = self
        _ROOM["mood"] = self._set_mood
        # Qt wants camera objects on the thread that owns the event loop, and
        # this is that thread. One call, no work done, and the later capture —
        # which happens on a worker thread — finds a lane ready for it.
        try:
            import camera
            camera.warm_up()
        except Exception as e:
            print(f"[Mikasa] camera lane not created: {type(e).__name__}: {e}")

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _due(self) -> tuple[list[str], list[str]]:
        """What is due today. The work lives in `_due_list`; this is the
        instance's way in, for the idle watcher."""
        return _due_list(self.cfg)

    def _run_loop(self):
        """Her whole life, restarted if the machinery under it breaks.

        `run()` already survives a dead socket. It cannot survive an exception
        above itself — a bad config, a tool that throws during construction, a
        sounddevice that fails at `_main` — and before this the whole thread
        died and the window stayed open on a woman who had stopped. Now the
        loop is rebuilt: audio is released, the event loop is thrown away, and
        she is started again a few seconds later. Nothing here can stop her
        except closing the window.
        """
        delay = 3.0
        while not getattr(self, "_closing", False):
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._main())
                return                    # _main returned: a decision, not a crash
            except Exception as e:
                print(f"[Mikasa] crashed: {type(e).__name__}: {e}")
                import traceback; traceback.print_exc()
            finally:
                try:
                    self._release_audio()
                except Exception:
                    pass
                try:
                    pending = asyncio.all_tasks(self.loop)
                    for t in pending:
                        t.cancel()
                    if pending:
                        self.loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True))
                    self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                except Exception:
                    pass
                try:
                    self.loop.close()
                except Exception:
                    pass

            if getattr(self, "_closing", False):
                return
            print(f"[Mikasa] restarting in {delay:.0f}s")
            time.sleep(delay)
            delay = min(delay * 2, 30.0)
            self.loop = asyncio.new_event_loop()

    async def _main(self):
        import live
        # Bounded. Two seconds of 24 kHz mono is 96 kB; 400 chunks is about
        # eight seconds, which is already too much to hear and nowhere near
        # enough to notice as memory. A dead speaker must cost latency, not RAM.
        self._out_q = asyncio.Queue(maxsize=400)
        prompt = build_prompt(self.cfg)
        (ROOT / "config" / "last_prompt.txt").write_text(prompt, encoding="utf-8")

        # ── the mouth ───────────────────────────────────────────────────────
        # Native audio is still produced and still arrives; it is dropped the
        # moment the studio voice is confirmed working, never before. A warm-up
        # sentence is rendered off-screen first: muting a voice that then turns
        # out to be unreachable is silence, and silence is the one failure this
        # app is not allowed to have.
        try:
            import voice as voice_mod
            self.voice = voice_mod.Voice(
                api_key=live.find_api_key(),
                sink=self._offer_pcm,
                note=lambda t: self.win.note.emit(t),
                voice=self.cfg.get("voice", settings.DEFAULTS["voice"]),
                mode=self.cfg.get("voice_mode", "studio"))
            # Asked in the background on purpose: her window must not wait two
            # seconds on a voice test. Until it answers, the Live audio is what
            # he hears; the moment it does, the studio voice takes the mouth.
            async def _warm():
                ok = await asyncio.to_thread(voice_mod.warm_up, self.voice)
                print(f"[Mikasa] studio voice: "
                      f"{'ready' if ok else 'using native audio'}")
                if not ok:
                    self.voice.hand_back()
            asyncio.create_task(_warm())
        except Exception as e:
            print(f"[Mikasa] voice setup: {type(e).__name__}: {e}")
            self.voice = None

        self.session = live.Session(
            system_instruction=prompt,
            voice=self.cfg.get("voice", settings.DEFAULTS["voice"]),
            on_audio=self._on_audio,
            on_text=lambda t: self.win.she_said.emit(t),
            on_partial=self._on_partial,
            on_said=self._on_said,
            on_heard=self._on_heard,
            tools=tools_for(self.cfg),
            on_lost=self._on_lost,
            on_back=self._on_back,
            on_open=self._opening,
            on_state=self._on_state_info,
            on_model=self._on_model,
        )

        self._start_audio()
        asyncio.create_task(self._play())
        self._idle_task = asyncio.create_task(self._idle_watch())
        self._clock_task = asyncio.create_task(self._clock_watch())

        # run() connects, and keeps connecting. Opening the window while the
        # network is down no longer means a window with nobody in it: she is
        # already trying, and her first line is waiting in the queue.
        await self.session.run()

    # ── audio in ────────────────────────────────────────────────────────────
    def _start_audio(self):
        try:
            import sounddevice as sd
        except Exception as e:
            print(f"[Mikasa] no sounddevice: {e}")
            return

        def callback(indata, frames, t, status):
            if not self.win.is_listening():
                return
            if self._speaking:
                return                      # never send her own echo
            if self.session:
                self.session.send_audio(indata.tobytes())

        try:
            self._mic_stream = sd.InputStream(
                samplerate=SEND_RATE, channels=CHANNELS, dtype="int16",
                blocksize=CHUNK, callback=callback)
            self._mic_stream.start()
            print("[Mikasa] mic open")
        except Exception as e:
            print(f"[Mikasa] mic failed: {e}")

    def _offer_pcm(self, data: bytes):
        """Studio-voice PCM, from a worker thread, into the same speaker queue.

        Deliberately the same queue the native audio used: the wave, the state
        word and the echo gate all already hang off it, so none of them had to
        learn a second source of truth.
        """
        if self._out_q is None or not self.loop:
            return
        def _offer():
            try:
                self._out_q.put_nowait(data)
            except asyncio.QueueFull:
                try:
                    self._out_q.get_nowait()
                    self._out_q.put_nowait(data)
                except Exception:
                    pass
        try:
            self.loop.call_soon_threadsafe(_offer)
        except RuntimeError:
            pass
        if not self._speaking:
            self._speaking = True
            self.win.state.emit("speaking")

    def _on_partial(self, text: str):
        """One transcription fragment. Speak what is already a whole sentence."""
        if self.voice is None or not self.voice.enabled:
            return
        ready = self.voice.partial(text, self._voice_turn)
        if ready and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.voice.speak(ready, self._mood_now), self.loop)

    def _on_audio(self, data: bytes):
        # The studio voice is the mouth. Native audio still arrives — it is the
        # timing reference and the fallback — and is thrown away here while the
        # studio voice is known to work.
        if self.voice is not None and self.voice.enabled:
            return
        if self._out_q is None or not self.loop:
            return
        def _offer():
            try:
                self._out_q.put_nowait(data)
            except asyncio.QueueFull:
                try:
                    self._out_q.get_nowait()
                    self._out_q.put_nowait(data)
                except Exception:
                    pass
        try:
            self.loop.call_soon_threadsafe(_offer)
        except RuntimeError:
            pass
        if not self._speaking:
            self._speaking = True
            self.win.state.emit("speaking")

    async def _play(self):
        """Speaker stream on its own thread, fed from an asyncio queue.

        The played-audio length is what tells us she has actually stopped
        talking. `turn_complete` arrives when generation ends, which is before
        the last syllable leaves the speaker — using it to close the mic means
        she hears her own tail and answers it.

        The stream used to be opened once, and one write error ended the loop.
        When it ended there was nothing left draining the queue: she kept
        talking into a list nobody read, the window kept saying "speaking", and
        the only cure was closing her. Now the stream is reopened, and while
        there is no stream the audio is discarded rather than accumulated —
        silence is a fault you can hear, memory growth is one you cannot.
        """
        import sounddevice as sd

        def _open():
            try:
                st = sd.RawOutputStream(
                    samplerate=RECV_RATE, channels=CHANNELS, dtype="int16",
                    blocksize=CHUNK)
                st.start()
                return st
            except Exception as e:
                print(f"[Mikasa] speaker failed: {e}")
                return None

        self._spk_stream = await asyncio.to_thread(_open)
        reopen_at = 0.0
        pending = 0.0

        while True:
            try:
                data = await asyncio.wait_for(self._out_q.get(), timeout=0.12)
            except asyncio.TimeoutError:
                data = None
            except Exception as e:
                print(f"[Mikasa] play: {e}")
                return

            if data is not None:
                if self._spk_stream is None and time.monotonic() >= reopen_at:
                    self._spk_stream = await asyncio.to_thread(_open)
                    reopen_at = time.monotonic() + 3.0
                if self._spk_stream is not None:
                    try:
                        self._spk_stream.write(data)
                        pending = time.monotonic() + len(data) / (RECV_RATE * 2) + 0.25
                    except Exception as e:
                        print(f"[Mikasa] speaker write: {e}")
                        try:
                            self._spk_stream.stop(); self._spk_stream.close()
                        except Exception:
                            pass
                        self._spk_stream = None
                        reopen_at = time.monotonic() + 1.0

            if (self._speaking and time.monotonic() > pending
                    and self._out_q.empty()):
                self._speaking = False
                self._last_turn = time.time()
                self.win.state.emit("listening")

    # ── the first word ──────────────────────────────────────────────────────
    def _opening(self):
        self._push_clock()
        """Her first line, once the socket is actually up.

        Called from inside connect(), so it must not wait on anything: it puts
        the opening turn in the queue and the pump sends it the moment it
        starts running.
        """
        self.win.state.emit("listening")
        try:
            self.session.send_text(opening_turn())
        except Exception as e:
            print(f"[Mikasa] opening turn not sent: {e}")

    # ── turns ───────────────────────────────────────────────────────────────
    def _on_heard(self, text: str):
        self.win.heard.emit(text)
        t = (text or "").strip()
        if len(t) > 12 and len(self._topics) < 12:
            self._topics.append(t[:80])

    def _on_said(self, text: str):
        if self.voice is not None and self.voice.enabled and self.loop:
            tail = self.voice.end_turn(self._voice_turn)
            self._voice_turn += 1
            if tail:
                asyncio.run_coroutine_threadsafe(
                    self.voice.speak(tail, self._mood_now), self.loop)
        self._last_turn = time.time()
        self._last_said = (text or "").strip()
        touch_seen()

    # ── the line dropping, and coming back ─────────────────────────────────
    def _stamp(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _on_lost(self, why: str = "", kind: str = ""):
        """Silent on the way out. One faint line, and no words from her.

        She does not say goodbye to a dropped connection — there is nothing to
        say goodbye to, and a person who announces every time their phone loses
        signal is exhausting.

        The line is short but it is TRUE. It used to say "connection lost" for
        every exception there is, which taught him to blame the network for
        things the network never did. Now it names the kind, in the room's own
        lowercase voice.
        """
        import netwatch
        label = netwatch.human(kind) if kind else ""
        text = f"line lost · {label}  {self._stamp()}" if label \
            else f"line lost  {self._stamp()}"
        self.win.note.emit(text)
        self.win.state.emit("reconnecting")

    def _on_state_info(self, info: dict):
        """The window's line under her face — try count, wait, and the route."""
        try:
            self.win.connection.emit(dict(info))
        except Exception:
            pass

    def _on_model(self, name: str, index: int):
        """A different rung. Same voice, different room; said once, quietly."""
        short = name.rsplit("/", 1)[-1]
        self.win.note.emit(f"voice on backup  {self._stamp()}")
        print(f"[Mikasa] on {short} (rung {index + 1})")

    def _on_back(self, planned: bool = False):
        if planned:
            # A handover the server asked for. It took a second, nothing was
            # lost, and showing it would be showing the plumbing.
            self.win.state.emit("listening")
            return

        self._held_noted = False
        self.win.note.emit(f"back  {self._stamp()}")
        self.win.state.emit("listening")

        # She comes back to her own sentence, not to a greeting. This is the
        # whole difference between a reconnected socket and someone who was
        # listening: she remembers that he never answered her.
        line = (self._last_said or "").strip()
        if line:
            note = ("[you lost the line for a moment, in the middle of the "
                    f"conversation. the last thing you said was: \"{line}\"  "
                    "he never answered it. pick it up from there — say the "
                    "thing you would say to somebody who went quiet on you. "
                    "one line. never mention the connection, never apologise.]")
        else:
            note = ("[you lost the line for a moment. you are back. say one "
                    "line, as if you had just walked back into the room.]")
        try:
            if self.session:
                self.session.send_text(note)
        except Exception:
            pass

    def _set_mood(self, emotion: str) -> str:
        import ui
        m = (emotion or "").strip().lower()
        if m not in ui.Portrait.MOODS:
            return "no such face"
        self._mood_now = m          # the mouth reads this, so face and voice agree
        self.win.mood.emit(m)      # a signal: safe from the audio thread
        return "changed"

    def _log_night(self):
        """One line about what this was, written when she closes.

        Not a transcript — the journal is the shape of the evening, and a
        transcript stored forever is a surveillance file with a friendly name.
        """
        try:
            if not self._topics:
                return
            mins = int((time.time() - self._started_at) / 60)
            if mins < 1:
                return
            memory.log_night(", ".join(self._topics[:4]), mins)
        except Exception:
            pass

    def _stamp_now(self) -> str:
        """`07:41 · Sunday · 2 Nov · Agra` — what goes in the brackets.

        `%d` is zero-padded and `%-d` does not exist on Windows, so the day is
        stripped by hand: this file runs on the machine that builds her, and a
        strftime that raises on the target machine is a clock that never works.
        """
        local = _now(self.cfg)
        day = local.strftime("%d %b").lstrip("0")
        return (f"{local.strftime('%H:%M')} · {local.strftime('%A')} · "
                f"{day} · {_place(self.cfg)[0]}")

    async def _clock_watch(self):
        """Keep her clock honest for as long as she is up.

        The prompt used to be built once, at launch, with the time in it — so a
        session opened at 2 a.m. still believed it was 2 a.m. at breakfast. The
        prompt no longer carries a time at all; this hands her a fresh one,
        throttled inside `live.Session.note_clock`, and `get_time` covers the
        exact answers.
        """
        while True:
            try:
                await asyncio.sleep(30)
                if not self.session:
                    continue
                self.session.note_clock(self._stamp_now())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[Mikasa] clock: {type(e).__name__}: {e}")
                await asyncio.sleep(10)

    async def _idle_watch(self):
        """Her one unprompted line.

        Five minutes of nothing, then she says something — once. If he does not
        answer, she does not try again; she waits for him. That is not a
        throttle, it is the difference between a person and a notification.
        """
        said_once = False
        while True:
            await asyncio.sleep(20)
            quiet = time.time() - self._last_turn
            if quiet < 300:
                if quiet < 120:
                    said_once = False
                continue
            if said_once or self._speaking:
                continue
            said_once = True
            note = ("[he has been quiet for five minutes. say one thing — "
                    "thinking out loud, not a check-in. do not ask if he is "
                    "there. one line.]")
            # Silence is when a kept thing earns itself: a bad night is still
            # sitting there and nobody has mentioned it.
            try:
                due, _then = self._due()
                if due:
                    note += ("\nThings of his that may still be open:\n"
                             + "\n".join(due)
                             + "\nIf one of them is what this quiet is about, "
                               "say that one. If not, say nothing about them.")
            except Exception:
                pass
            try:
                self.session.send_text(note)
            except Exception:
                pass

    # ── from the window ─────────────────────────────────────────────────────
    def _push_clock(self) -> None:
        """Before anything he says, the clock is current — no exceptions."""
        try:
            session = self.session
            if session is not None:
                session._clock_at = 0.0        # defeat the throttle, once
                session.note_clock(self._stamp_now())
        except Exception:
            pass

    def say_typed(self, text: str):
        """Typed words. Already in the queue if the line is down — say so once.

        The bubble appears the moment he presses enter, which is right; what
        was wrong is that a line typed during an outage looked exactly like a
        line that had been delivered. It is held, and it will be sent, but he
        should know which of the two he is looking at.
        """
        if self.session:
            try:
                ready = self.session.is_ready()
            except Exception:
                ready = True
            if not ready and not self._held_noted:
                self._held_noted = True
                try:
                    self.win.note.emit(f"held until the line is back  "
                                       f"{self._stamp()}")
                except Exception:
                    pass
            self._push_clock()
            self.session.send_text(text)
        self._last_turn = time.time()

    def set_listening(self, on: bool):
        """He opened or closed the mic in the window.

        It used to reset the speaker gate here. There is no gate; what is left
        is the one thing that still matters — a closed mic must not look like
        an open one in the window's status line (see `_status` in ui.py), and
        she must stop hearing him the moment it closes.
        """
        self._listening = bool(on)

    def reload_settings(self):
        was = self.cfg.get("voice", "")
        self.cfg = settings.load()

        # A voice lives in the handshake, so "save" means one planned
        # reconnect: a second of silence, the conversation carried over, and
        # the new voice on the other side of it. Before this, the only way to
        # hear a different voice was to close her and open her again — which is
        # not a thing anybody should have to do to try one.
        now = str(self.cfg.get("voice") or "")
        if now and now != was and self.session is not None:
            try:
                if self.session.set_voice(now):
                    self.win.note.emit(f"her voice is {now}  {self._stamp()}")
            except Exception as e:
                print(f"[Mikasa] voice change failed: {type(e).__name__}: {e}")

    # ── out ─────────────────────────────────────────────────────────────────
    def _release_audio(self):
        for name in ("_mic_stream", "_spk_stream"):
            st = getattr(self, name, None)
            if st is None:
                continue
            try:
                st.stop()
            except Exception:
                pass
            try:
                st.close()
            except Exception:
                pass
            setattr(self, name, None)

    def shutdown(self):
        self._closing = True
        self._log_night()
        self._release_audio()
        drop_lock()

    def close_room(self):
        """The way out. It is her window closing, and that is all."""
        self.win.close()
        self.shutdown()
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)


# ── main ─────────────────────────────────────────────────────────────────────
def _fail(title: str, body: str, show_box: bool = True) -> int:
    """Say what is wrong in a way that cannot be missed.

    `mikasa.bat` starts her with pythonw, which has no console — so an
    exception before the window exists is a double-click that does nothing at
    all and looks like a broken file. The message goes to a GUI box when Qt is
    available, to a log file always, and to stderr when there is one.
    """
    msg = title + "\n\n" + body
    try:
        (ROOT / "config").mkdir(parents=True, exist_ok=True)
        (ROOT / "config" / "mikasa-error.txt").write_text(msg, encoding="utf-8")
    except Exception:
        pass
    print(msg, file=sys.stderr)
    if not show_box:
        return 1
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        # the instance must exist before any dialog, or Qt aborts; nothing
        # else needs the handle
        QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setWindowTitle("Mikasa")
        box.setText(title)
        box.setInformativeText(body)
        box.exec()
    except Exception:
        pass
    return 1


def _preflight():
    """Everything that must be true before a window can open. Returns an error
    message, or None."""
    missing = []
    for mod, pkg in (("PyQt6", "PyQt6"), ("numpy", "numpy"),
                     ("sounddevice", "sounddevice"),
                     ("google.genai", "google-genai")):
        try:
            __import__(mod)
        except Exception:
            missing.append(pkg)
    if missing:
        return ("Missing: " + ", ".join(missing) + "\n\n"
                "Open a terminal in this folder and run:\n\n"
                "    " + Path(sys.executable).name + " -m pip install "
                + " ".join(missing))

    key = ""
    try:
        import live
        key = live.find_api_key()
    except Exception:
        pass
    if not key:
        return ("No Gemini API key found.\n\n"
                "Put it in mikasa/config/api_keys.json, under "
                "gemini_api_key. Nothing outside her own folder is read.")
    return None


def _windows_taskbar_identity() -> None:
    """Tell Windows this window is Mikasa, not "Python".

    Without an explicit AppUserModelID the taskbar groups her under the
    interpreter that runs her and shows Python's icon in the corner, no matter
    what the window icon says. One call, and the button in the taskbar is hers:
    her icon, her name on hover.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "AMDimension.Mikasa")
    except Exception:
        pass


def main() -> int:
    try:
        err = _preflight()
    except Exception as e:
        return _fail("Could not start", type(e).__name__ + ": " + str(e))
    if err:
        return _fail("Mikasa cannot start yet", err)

    if not take_lock():
        # Double-clicking the icon twice is a thing people do. Exiting in
        # silence makes the second click look like a broken shortcut, so say
        # it plainly and leave the first window alone.
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            box = QMessageBox()
            box.setWindowTitle("Mikasa")
            box.setText("She is already open.")
            box.setInformativeText("Look for her window in the taskbar.")
            box.exec()
        except Exception:
            print("[Mikasa] already open")
        return 0

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QIcon
        import ui
    except Exception as e:
        return _fail("Could not open the window", type(e).__name__ + ": " + str(e))

    app = QApplication(sys.argv)
    app.setApplicationName("mikasa")

    # The taskbar used to show her calm face because this line pointed at a PNG
    # in assets/faces — so replacing assets/mikasa.ico changed the desktop
    # shortcut and nothing else. The window now takes the .ico when there is
    # one (it carries every size Windows asks for) and falls back to the face.
    _windows_taskbar_identity()
    win = ui.Window()
    for candidate in (ROOT / "assets" / "mikasa.ico",
                      ROOT / "assets" / "faces" / "calm.png"):
        if candidate.exists():
            win.setWindowIcon(QIcon(str(candidate)))
            break

    engine = Mikasa(win)
    engine.start()

    win.show()
    try:
        code = app.exec()
    finally:
        engine.shutdown()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
