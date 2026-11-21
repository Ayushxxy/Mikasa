"""The voice — one Gemini Live session, and nothing else.

WHY THIS FILE EXISTS SEPARATELY
    ULTRON's session lives inside a 3,700-line class because it grew a tool
    registry, a screen watcher, a phone relay and a wake word. Mikasa needs
    none of that: two streams, one loop. Keeping hers apart means a change to
    ULTRON cannot quietly change her, and the day she breaks there is one file
    to read instead of one class with forty entry points.

WHERE THE KEY COMES FROM
    Her own config/api_keys.json, or the environment. Nothing outside this
    folder is read: she has to run on a machine where nothing else is
    installed, or she is not a separate program.

WHAT IS DELIBERATELY MISSING
    Proactivity config, affective dialog, tool declarations, screen context,
    phone relay. She has none of them. When music arrives in the next phase it
    arrives as one declaration, added here, on purpose.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import netwatch

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(sys.executable).parent if "__compiled__" in globals() \
        else Path(__file__).resolve().parent

# ── the ladder ───────────────────────────────────────────────────────────────
#
# One model is a single point of failure, and the failure looks exactly like a
# network problem: the socket opens, nothing comes back, the window says
# "reconnecting" forever. The second rung exists so that a model which is
# retired, rate-limited or having a bad hour is a slow sentence and not a
# silent evening.
#
# The voice NAME does not change between rungs — Leda is available on
# both — so a switch moves the room's electricity, not her voice. It is still
# announced in the room with one dim line, because a person who notices her
# sounding slightly different deserves to know why.
MODELS       = ("models/gemini-3.1-flash-live-preview",
                "models/gemini-2.5-flash-native-audio-latest")
MODEL        = MODELS[0]
SEND_RATE    = 16000
RECV_RATE    = 24000
CHANNELS     = 1
CHUNK        = 1024

# How long a session is allowed to live before she moves house on purpose.
# The server will eventually send go_away; arriving there uninvited means a cut
# in the middle of a sentence. Leaving at a turn boundary, a little early, is
# the same journey without the seam.
ROTATE_AFTER = 8 * 60

# A typed line is a promise of an answer. If nothing at all arrives in this
# long, the socket is not slow, it is dead — and dead sockets do not raise.
# Twenty, not five: a tool call and a slow first token are allowed to take a
# while, and killing a session that was about to answer is its own outage.
REPLY_GRACE  = 20.0

# A send that hangs is a socket that is gone. Six seconds is longer than any
# healthy write and shorter than a person's patience.
SEND_TIMEOUT = 6.0

# How often the clock is refreshed in her context. Ninety seconds is well under
# the hour-scale errors this exists to prevent and far above anything the model
# would notice as a stream of messages.
CLOCK_EVERY  = 90.0


# ── the key, wherever it already is ──────────────────────────────────────────
def find_api_key() -> str:
    env = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
           or "").strip()
    if env:
        return env
    # Her own folder, full stop. She used to look inside ULTRON as a courtesy,
    # which is what made the two impossible to move or break separately.
    here = Path(__file__).resolve().parent
    for candidate in (here / "config" / "api_keys.json",
                      here.parent / "config" / "api_keys.json"):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            key = str(data.get("gemini_api_key") or "").strip()
            if key:
                print(f"[Mikasa] key: {candidate}")
                return key
        except Exception:
            continue
    return ""


def _client():
    from google import genai
    key = find_api_key()
    if not key:
        raise RuntimeError(
            "no Gemini API key found — put one in "
            "mikasa/config/api_keys.json")
    return genai.Client(api_key=key)


# ── the session ──────────────────────────────────────────────────────────────
class Session:
    """Owns the socket. Everything else owns her."""

    def __init__(self, system_instruction: str, voice: str = "Leda",
                 on_audio=None, on_text=None, on_said=None,
                 on_partial=None,
                 on_heard=None, tools=None, on_lost=None, on_back=None,
                 on_open=None, on_state=None, on_model=None, log=None,
                 models=None):
        self.system_instruction = system_instruction
        self.voice      = voice or "Leda"
        self.on_audio   = on_audio or (lambda b: None)
        # Fires on every transcription fragment, not once per turn: the
        # mouth needs the first sentence while the rest is still being
        # written, and buffering to turn_complete costs two seconds.
        self.on_partial = on_partial or (lambda t: None)
        self.on_text    = on_text or (lambda t: None)     # her words, as text
        self.on_said    = on_said or (lambda t: None)     # turn finished
        self.on_heard   = on_heard or (lambda t: None)    # what reached her
        # {name: (declaration, handler)} — remembering, and nothing else for
        # now. A tool is a machine in the room; every one of them costs some
        # of her personhood, so they arrive one at a time and deliberately.
        self.tools = dict(tools or {})
        # Told when the socket goes, and when it is back. The window writes one
        # faint line to the conversation and nothing else — an error box in the
        # middle of a good evening is worse than a minute of silence.
        self.on_lost = on_lost or (lambda why: None)
        # Told whether this was a plan or a failure: a handover that lasts a
        # second must not leave a scar in the conversation.
        self.on_back = on_back or (lambda planned: None)
        # Once, on the first connection — including a first connection that
        # took three tries because the machine was offline when she opened.
        self.on_open = on_open or (lambda: None)
        # The window's line under her face. A dict, not a word, because
        # "reconnecting" on its own was a word that told him nothing: not
        # whether it was the network, not how many tries, not how long.
        self.on_state = on_state or (lambda info: None)
        # Told once, when the rung changes. The voice name stays the same; the
        # room still deserves the line.
        self.on_model = on_model or (lambda name, index: None)
        self.log = log if log is not None else netwatch.Line(
            Path(__file__).resolve().parent / "config" / "netlog.json")
        self.models = tuple(models or MODELS)
        self._model_idx = 0

        self._resume = None            # the server's continuation handle
        self._ever_connected = False
        self._alive = True             # False only when the user is done
        self._planned = False          # the server asked us to move
        self._saw = 0                  # messages read on this connection
        self._ready: asyncio.Event | None = None   # socket is writable
        self.session    = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._send_q: asyncio.Queue | None = None
        self._running   = False
        self._out_buf   = []

        # ── supervision ─────────────────────────────────────────────────────
        self._backoff   = netwatch.Backoff()
        self._session_t0 = 0.0         # when this connection was made
        self._last_msg  = 0.0          # when the last one arrived
        self._expect    = 0.0          # asked for an answer, none yet arrived
        self._kill: tuple[str, str] | None = None   # (kind, why) decided by us
        self._route     = True         # last probe's answer
        self._route_at  = 0.0
        self._empties   = 0            # consecutive empty ends of receive()
        self._empties_at = 0.0
        self._send_fails = 0           # consecutive failed sends
        self._replay    = False        # the handle died; rebuild from the log
        self._restart   = False        # an intentional change; reconnect at once
        self._transcript: list[tuple[str, str]] = []   # last few turns, local
        self._msgs_out  = 0

    # ── who owns the ladder ────────────────────────────────────────────────
    @property
    def model(self) -> str:
        return self.models[min(self._model_idx, len(self.models) - 1)]

    def _state(self, kind: str, **extra) -> None:
        """Tell the window what is happening, truthfully and briefly."""
        info = {"kind": kind, "model": self.model,
                "attempt": self._backoff.attempt, "route": self._route}
        info.update(extra)
        try:
            self.on_state(info)
        except Exception:
            pass

    def _next_model(self, why: str) -> bool:
        """Move one rung down. False when there is nowhere left to go."""
        if self._model_idx + 1 >= len(self.models):
            return False
        was = self.model
        self._model_idx += 1
        self._replay = True                 # a new rung is a new conversation
        self.log.add("model", frm=was.rsplit("/", 1)[-1],
                     to=self.model.rsplit("/", 1)[-1], why=why)
        print(f"[Mikasa] model → {self.model} ({why})")
        try:
            self.on_model(self.model, self._model_idx)
        except Exception:
            pass
        return True

    def _remember(self, role: str, text: str) -> None:
        """The last few turns, kept here so a rebuilt session is not a stranger."""
        text = " ".join((text or "").split())
        if not text:
            return
        self._transcript.append((role, text[:400]))
        if len(self._transcript) > 12:
            self._transcript = self._transcript[-12:]

    def _replay_note(self) -> str:
        if not self._transcript:
            return ""
        lines = [f"{'he said' if r == 'user' else 'you said'}: {t}"
                 for r, t in self._transcript[-8:]]
        return ("[the line to you was replaced. nothing the two of you said is "
                "lost — here is the end of the conversation you were in:]\n"
                + "\n".join(lines)
                + "\n[do not greet him again and do not mention the line. "
                  "continue from where this leaves off, in one line.]")

    async def connect(self) -> None:
        from google.genai import types
        client = _client()
        # The running loop, kept. `asyncio.get_event_loop()` called from a
        # worker thread raises on Python 3.10+ — and both of this class's
        # public senders are called from worker threads: the microphone
        # callback and the Qt window. Asking the thread that has no loop for
        # its loop is how audio and typing both go silently nowhere.
        self._loop = asyncio.get_running_loop()
        # Bounded, and created once. Re-creating it on a reconnect would throw
        # away the line he was typing while she was gone, which is the exact
        # moment he is most likely to be typing one.
        if self._send_q is None:
            self._send_q = asyncio.Queue(maxsize=128)
        if self._ready is None:
            self._ready = asyncio.Event()

        cfg = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=self.system_instruction,
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice))),
            # A live session has a maximum age and the server says so with a
            # go_away. Resumption lets the replacement carry the conversation
            # instead of starting a stranger in the same room.
            session_resumption=types.SessionResumptionConfig(handle=self._resume))
        # No trailing comma on the closing paren above. It turned `cfg` into a
        # one-element tuple and every key assignment after it raised — a bug
        # that reads as "the voice API is broken" and is a typo.

        # She should hear HOW he said it, not only what. With this on, the
        # model reads the tone of the room — flat, rushed, tired — and answers
        # the tone. It is the difference between "tension hai" being handled as
        # information and being heard as a tired voice at eleven at night.
        #
        # Enabled only if this SDK knows the field: an unknown key is a
        # validation error on connect, and a session that will not open is a
        # much worse outcome than a session without the feature.
        for key, value in (("enable_affective_dialog", True),):
            try:
                import dataclasses
                fields = {f.name for f in dataclasses.fields(types.LiveConnectConfig)}
            except Exception:
                fields = set()
            if key in fields:
                cfg[key] = value
            else:
                print(f"[Mikasa] {key} not supported by this google-genai — off")
        if self.tools:
            cfg["tools"] = [{"function_declarations":
                             [d for d, _h in self.tools.values()]}]
        self._client = client
        self._cfg = cfg
        self._cm = client.aio.live.connect(model=self.model,
                                          config=types.LiveConnectConfig(**cfg))
        self.session = await self._cm.__aenter__()
        self._running = True
        self._session_t0 = time.monotonic()
        self._last_msg = self._session_t0
        self._expect = 0.0
        self._empties = 0
        self._send_fails = 0
        self._kill = None
        self._ready.set()
        again = self._ever_connected
        self._ever_connected = True
        if not again:
            try:
                self.on_open()
            except Exception:
                pass
        print(f"[Mikasa] connected, voice {self.voice} on {self.model}"
              + ("  (reconnected)" if again else ""))
        if self._replay:
            self._replay = False
            note = self._replay_note()
            if note:
                # One turn, in his voice, so she continues rather than greets.
                try:
                    await self.session.send_client_content(
                        turns={"role": "user", "parts": [{"text": note}]},
                        turn_complete=True)
                    self.log.add("replay", turns=len(self._transcript))
                except Exception as e:
                    print(f"[Mikasa] replay failed: {type(e).__name__}: {e}")
        return again

    async def close(self) -> None:
        self._alive = False
        self._running = False
        if self._ready is not None:
            self._ready.set()          # let the pump out of its wait
        self._loop = None
        try:
            if self._cm:
                await self._cm.__aexit__(None, None, None)
        except Exception:
            pass
        self.session = None

    # ── outgoing ────────────────────────────────────────────────────────────
    def _offer(self, item) -> None:
        """Put it in the queue; if the queue is full, lose the oldest thing.

        The queue fills only while she is disconnected. The oldest item in it
        is always audio recorded in a room he has already left, so dropping
        the oldest is the only choice that keeps the line he just typed.
        """
        q = self._send_q
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(item)
            except Exception:
                pass

    def send_audio(self, pcm: bytes) -> None:
        """Called from the microphone thread. Never blocks the audio path."""
        if not self._running or self._send_q is None or self._loop is None:
            return
        if self._ready is not None and not self._ready.is_set():
            return                    # gone: nobody is listening to the room
        try:
            self._loop.call_soon_threadsafe(self._offer, pcm)
        except RuntimeError:
            pass                      # loop closed: the session is going away

    def send_text(self, text: str) -> None:
        """Something typed. It reaches her as a turn, not as a command."""
        if not self._running or self._send_q is None or self._loop is None:
            return
        # Remembered here, not in the pump: what he typed while the socket was
        # down never reaches the pump until later, and by then a reconnect may
        # already have rebuilt the conversation without it.
        self._remember("user", text)
        try:                          # kept even while she is away
            self._loop.call_soon_threadsafe(self._offer, {"text": text})
        except RuntimeError:
            pass                      # loop closed: the session is going away

    def note_clock(self, stamp: str) -> None:
        """Hand her the current time as context, not as a turn.

        `turn_complete=False` appends to the conversation without asking for an
        answer, which is exactly what a clock should do. Throttled: the model
        does not need the minute, it needs to not be an hour behind.
        """
        if not self.session or not self._running:
            return
        now = time.monotonic()
        if now - getattr(self, "_clock_at", 0.0) < CLOCK_EVERY:
            return
        self._clock_at = now
        text = (f"[[{stamp}]]  (the current time. know it. never read it out, "
                f"never mention that you were told it.)")
        try:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._send_clock(text)))
        except Exception:
            pass

    async def _send_clock(self, text: str) -> None:
        try:
            await asyncio.wait_for(
                self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": text}]},
                    turn_complete=False),
                timeout=SEND_TIMEOUT)
        except Exception as e:
            print(f"[Mikasa] clock not sent: {type(e).__name__}: {e}")

    def set_voice(self, name: str) -> bool:
        """Change her voice under a conversation that is already open.

        The voice is not a property of the model — it is part of the handshake.
        It goes into `speech_config` when the socket opens and cannot be
        altered on an open one. So "change the voice" honestly means "hang up
        and dial again", and that is what this does: the same planned handover
        the server asks for when a session gets old, which the supervisor
        already survives without a backoff, without a "line lost" in the
        conversation, and with the transcript carried across on the resumption
        handle.

        The alternative — the thing it used to do — was nothing, and the voice
        only changed after restarting the program.

        Safe from any thread. True when the voice is (or already was) hers.
        """
        name = (name or "").strip()
        if not name:
            return False
        if name == self.voice:
            return True
        self.voice = name
        self.log.add("voice", to=name)
        # Nothing is open, so there is nothing to hang up: the next connect
        # reads self.voice on its way out.
        if not (self._running and self.session is not None and self._loop):
            return True

        def _flip() -> None:
            self._planned = True        # run() will not call it a failure
            self._restart = True        # and _reconnect() will not wait
            if self._kill is None:
                self._kill = (netwatch.PLANNED, "voice change")
            asyncio.ensure_future(self._drop())

        try:
            self._loop.call_soon_threadsafe(_flip)
        except Exception:
            pass                        # loop closed: shutting down anyway
        return True

    def is_ready(self) -> bool:
        """True when a line spoken now would actually reach her."""
        return bool(self._ready is not None and self._ready.is_set()
                    and self.session is not None)

    async def _pump(self) -> None:
        from google.genai import types
        # The queue is made in connect(), and run() now starts the pump before
        # the first connection exists. Without this wait the first thing the
        # pump does is call .get() on None, the task dies, and every line he
        # ever types goes into a queue nobody is reading. Silently.
        while self._send_q is None and self._alive:
            await asyncio.sleep(0.05)
        while self._alive:
            item = await self._send_q.get()
            await self._ready.wait()   # hold it, do not throw it away
            if not self._alive:
                return
            try:
                if isinstance(item, dict) and "text" in item:
                    # A write that hangs is a socket that is gone. Without this
                    # timeout the await never returns, nothing behind it in the
                    # queue moves, and every line he types afterwards joins a
                    # queue nobody is draining — which reads as "she stopped
                    # answering" with no error anywhere.
                    await asyncio.wait_for(
                        self.session.send_client_content(
                            turns={"role": "user",
                                   "parts": [{"text": item["text"]}]},
                            turn_complete=True),
                        timeout=SEND_TIMEOUT)
                    # Typed words earn an answer. If none arrives, the watchdog
                    # asks the route and decides.
                    self._expect = max(self._expect, time.monotonic())
                    self._msgs_out += 1
                else:
                    await asyncio.wait_for(
                        self.session.send_realtime_input(
                            audio=types.Blob(data=item, mime_type="audio/pcm")),
                        timeout=SEND_TIMEOUT)
                    self._msgs_out += 1
                self._send_fails = 0
            except asyncio.CancelledError:
                raise
            except BaseException as e:
                name = type(e).__name__
                if name in ("GeneratorExit", "SystemExit", "KeyboardInterrupt"):
                    print(f"[Mikasa] pump stopping: {name}: {e}")
                    raise
                self._send_fails += 1
                print(f"[Mikasa] send: {name}: {e}")
                # Two in a row is not a bad packet, it is a dead socket.
                if self._send_fails >= 2 and self._kill is None:
                    self._kill = (netwatch.classify(e),
                                  f"send failed twice: {netwatch.detail(e)}")
                await asyncio.sleep(0.2)

    # ── incoming ────────────────────────────────────────────────────────────
    async def _run_tools(self, call) -> None:
        """Run what she asked for, then hand the result back as data.

        The result is deliberately flat — "kept" or "not kept" — because a
        tool response is not a place to put words in her mouth. What she says
        about it is hers.

        Two things a handler is allowed to be, beyond "a function that returns
        a string":

        * `handler.blocking = True` — it may take seconds (a camera takes one).
          It is then run on a worker thread, so the audio she is already
          speaking does not stutter while a device wakes up.
        * it may return `(text, picture_path)`. The text goes back as the tool
          result; the picture is sent as its own turn immediately afterwards,
          because a photograph is not a tool result and pretending otherwise
          makes the model describe a file name.
        """
        from google.genai import types
        out: list = []
        pictures: list[tuple[str, str]] = []      # (path, caption)
        for fc in (getattr(call, "function_calls", None) or []):
            entry = self.tools.get(fc.name)
            picture = None
            if entry is None:
                text = "no such thing"
            else:
                _decl, handler = entry
                try:
                    args = dict(fc.args or {})
                    if getattr(handler, "blocking", False):
                        res = await asyncio.to_thread(handler, **args)
                    else:
                        res = handler(**args)
                except Exception as e:
                    res = f"failed: {type(e).__name__}: {e}"
                if isinstance(res, tuple):
                    text, picture = str(res[0]), res[1]
                else:
                    text = str(res)
            print(f"[Mikasa] tool {fc.name} -> {text}"
                  + (f" (+picture {picture})" if picture else ""))
            out.append(types.FunctionResponse(id=fc.id, name=fc.name,
                                              response={"result": text}))
            if picture:
                pictures.append((picture, ""))
        if out:
            try:
                await self.session.send_tool_response(function_responses=out)
            except Exception as e:
                print(f"[Mikasa] tool response failed: {e}")
        for path, caption in pictures:
            await self.send_picture(path, caption)

    async def send_picture(self, path, caption: str = "") -> bool:
        """One image, then forget it.

        The frame is read, sent, and deleted in the same breath — what stays on
        his disk afterwards is nothing. A failed send still deletes it.
        """
        from google.genai import types
        try:
            data = Path(path).read_bytes()
        except Exception as e:
            print(f"[Mikasa] picture unreadable: {e}")
            return False
        if not data:
            return False
        parts = [types.Part(inline_data=types.Blob(data=data,
                                                   mime_type="image/jpeg"))]
        if caption:
            parts.append(types.Part(text=caption))
        try:
            await asyncio.wait_for(
                self.session.send_client_content(
                    turns={"role": "user", "parts": parts},
                    turn_complete=True),
                timeout=SEND_TIMEOUT)
            print(f"[Mikasa] picture sent ({len(data) // 1024} KB)")
            return True
        except Exception as e:
            print(f"[Mikasa] picture not sent: {type(e).__name__}: {e}")
            return False
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

    async def _read(self) -> None:
        """One connection, read to the end of it. Returns or raises.

        receive() ends at every turn boundary — it is not a socket that stays
        open and keeps yielding. The old loop knew that and re-entered it, but
        it had no answer for the other case: a socket that is gone makes
        receive() end instantly, over and over, and the loop then spins at
        20 Hz forever. `_read` never returned, so `run` never reconnected, so
        the window sat on "listening" over a dead line and every send went
        nowhere. That is fixed in two places: an empty end is counted, and
        three of them in a row inside two seconds is a dead socket, not a
        quiet turn.
        """
        while self._alive:
            if self.session is None:
                return
            if self._kill is not None:
                return                       # the watchdog has already decided
            got = 0
            async for msg in self.session.receive():
                if not self._alive:
                    return
                got += 1
                self._saw += 1
                self._last_msg = time.monotonic()
                self._expect = 0.0           # an answer is arriving
                self._empties = 0

                # The server hands over a new handle every turn. Keeping it is what
                # lets the replacement session continue this conversation instead
                # of meeting him for the first time again.
                upd = getattr(msg, "session_resumption_update", None)
                if upd is not None and getattr(upd, "new_handle", None):
                    self._resume = upd.new_handle

                sc = getattr(msg, "server_content", None)
                if sc is not None and getattr(sc, "go_away", None) is not None:
                    # Not a failure: the session has reached its maximum age and
                    # has told us so. Reconnect at once, with no line in the chat,
                    # because nothing was lost and he should not see a seam.
                    self._planned = True
                    return

                tc = getattr(msg, "tool_call", None)
                if tc is not None:
                    await self._run_tools(tc)
                    continue

                if getattr(msg, "data", None):
                    try:
                        self.on_audio(msg.data)
                    except Exception:
                        pass

                if sc is None:
                    continue

                ot = getattr(sc, "output_transcription", None)
                if ot is not None and getattr(ot, "text", ""):
                    self._out_buf.append(ot.text)
                    try:
                        self.on_partial(ot.text)
                    except Exception:
                        pass

                it = getattr(sc, "input_transcription", None)
                if it is not None and getattr(it, "text", ""):
                    try:
                        self.on_heard(it.text)
                    except Exception:
                        pass

                if getattr(sc, "turn_complete", False):
                    said = "".join(self._out_buf).strip()
                    self._out_buf = []
                    if said:
                        self._remember("her", said)
                        try:
                            self.on_text(said)
                            self.on_said(said)
                        except Exception:
                            pass

            # ── the stream ended without a message ───────────────────────────
            #
            # A legitimate turn boundary usually carries at least one message.
            # Several empty ends in quick succession cannot be a turn boundary;
            # it is a socket that is closed and does not know it yet.
            now = time.monotonic()
            if got == 0:
                if now - self._empties_at > 2.0:
                    self._empties = 0
                self._empties_at = now
                self._empties += 1
                if self._empties >= 3:
                    raise RuntimeError("receive() ended empty three times — "
                                       "the socket is dead")
                await asyncio.sleep(0.05)
            else:
                self._empties = 0

    async def _drop(self) -> None:
        self._ready.clear()            # senders hold, the pump waits
        cm, self._cm = getattr(self, "_cm", None), None
        try:
            if cm:
                # Bounded: a socket that is already gone can make __aexit__
                # wait on a close handshake that will never be answered.
                await asyncio.wait_for(cm.__aexit__(None, None, None), timeout=3.0)
        except Exception:
            pass                       # it is already dead; this is a formality
        self.session = None
        self._running = False
        self._out_buf = []

    async def _reconnect(self) -> bool:
        """Come back, or keep trying until the window is closed.

        What changed, and why it is not a loop with a sleep in it any more:

        * the wait grows and has noise in it (netwatch.Backoff), and it is
          PRINTED — "try 3, next 4s, route down" is the difference between a
          spinner and a person telling you what is happening;
        * a failed connect is classified before it is retried. A dead key or a
          retired model is not retried on the same rung forever;
        * a stale resumption handle is rebuilt rather than retried: the
          conversation is replayed from the local transcript, so she comes
          back to the sentence they were in;
        * every attempt, every failure and every return is written to the
          netlog, so "it drops all the time" can be answered with numbers.
        """
        planned = self._planned
        self._planned = False
        # A voice change is the one reconnect that should feel instant. It is
        # not a failure, so it neither waits nor counts against the patience
        # that a real outage has to climb.
        fast = self._restart
        self._restart = False
        # A session that lasted a minute is a normal session; one that lasted
        # two seconds is a flap, and resetting the patience after a flap is how
        # a broken server turns into a reconnect loop at full speed.
        lived = (time.monotonic() - self._session_t0) if self._session_t0 else 1e9
        rapid = lived < 60.0

        # A handover gets no wait — but only if the socket actually carried
        # something first. A server that hands us off before saying a word
        # would otherwise spin this loop as fast as the CPU allows.
        if planned and self._saw > 2:
            self._backoff.reset()

        while self._alive:
            if fast:
                delay, fast = 0.0, False
            else:
                delay = self._backoff.next_delay()
            route = await netwatch.route_ok_async()
            self._route = route
            self._route_at = time.monotonic()
            if not route:
                self.log.add("route", up=False, attempt=self._backoff.attempt)
            self._state("offline" if not route else "reconnecting",
                        delay=delay)
            if delay:
                await asyncio.sleep(delay)
            if not self._alive:
                return False

            try:
                again = await self.connect()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                kind = netwatch.classify(e)
                why = netwatch.detail(e)
                self.log.add("fail", why=kind, detail=why,
                             attempt=self._backoff.attempt, model=self.model)
                print(f"[Mikasa] connect failed [{kind}] {why}")

                # A handle the server no longer honours is not something a
                # retry can fix — the session has to be rebuilt from scratch,
                # and the conversation carried by hand.
                if kind == netwatch.PROTOCOL and self._resume:
                    self._resume = None
                    self._replay = True
                    self.log.add("handle", dropped=True)
                    print("[Mikasa] resumption handle refused — rebuilding "
                          "without it, and replaying the last turns")
                    continue

                # Dead key, retired model: waiting cannot help, a different
                # rung might. Three ordinary failures in a row is also worth a
                # rung, because a model having a bad hour looks exactly like
                # the network having one.
                if kind in netwatch.SWITCH_ON or (
                        rapid and self._backoff.attempt >= 4
                        and kind in (netwatch.SERVER, netwatch.NET,
                                     netwatch.UNKNOWN, netwatch.STALL)):
                    if kind == netwatch.AUTH:
                        self.log.add("auth", detail=why)
                    if not self._next_model(f"{kind}: {why}"):
                        # Every rung has failed. Standing on the last one
                        # forever means that if the FIRST one was only having a
                        # bad minute, she never goes back to it — so the ladder
                        # cycles after a while. Nothing works at this point, so
                        # trying the top again cannot cost anything.
                        if self._backoff.attempt >= 6:
                            self._model_idx = 0
                            self._replay = True
                            self.log.add("model", to=self.model,
                                         why="cycle to the top")
                            print("[Mikasa] every rung failed — cycling to the top")
                continue

            tries = self._backoff.attempt + 1          # this attempt succeeded
            if not rapid:
                self._backoff.reset()                  # a real session earns it
            self._state("live", backup=self._model_idx > 0)
            if again:
                # Only a return is worth a line. The first connection of an
                # evening is not news, and "back" printed at launch would be
                # the window saying hello to itself.
                self.log.add("back", model=self.model, route=route, tries=tries)
                try:
                    self.on_back(planned)
                except Exception:
                    pass
            return True
        return False

    async def _watchdog(self) -> None:
        """The three failures a socket never reports.

        1. a typed line that gets no answer at all — the socket is up, the
           route is up, and nothing comes back;
        2. a session older than ROTATE_AFTER — leave at a turn boundary
           instead of being cut off in the middle of one;
        3. the route disappearing under a connection that has stopped
           delivering — being able to say "offline" is most of being able to
           explain it.

        It never raises. When it decides the connection is finished it sets
        `_kill` and closes the socket, which ends `_read` the way a real
        failure would.
        """
        while self._alive:
            try:
                await asyncio.sleep(1.0)
                if not self._alive or self.session is None:
                    continue
                now = time.monotonic()

                # 1 — asked for an answer, got nothing
                if self._expect and now - self._expect > REPLY_GRACE:
                    route = await netwatch.route_ok_async()
                    self._route = route
                    kind = netwatch.STALL if route else netwatch.NET
                    self.log.add("stall", why=kind, waited=round(now - self._expect, 1))
                    if self._kill is None:
                        self._kill = (kind, "no answer within "
                                           f"{REPLY_GRACE:.0f}s")
                        await self._drop()
                    continue

                # 2 — old enough to move house politely
                age = now - (self._session_t0 or now)
                if (age > ROTATE_AFTER and not self._expect
                        and now - self._last_msg > 3.0):
                    self.log.add("rotate", age=round(age, 1))
                    print(f"[Mikasa] rotating a {age:.0f}s session at a turn boundary")
                    self._planned = True
                    if self._kill is None:
                        self._kill = (netwatch.PLANNED, "scheduled rotation")
                        await self._drop()
                    continue

                # 3 — the route went away
                if now - self._route_at > 15.0:
                    route = await netwatch.route_ok_async()
                    self._route_at = now
                    if route != self._route:
                        self._route = route
                        self.log.add("route", up=route)
                        if not route:
                            self._state("offline")
                    if not route and now - self._last_msg > 10.0:
                        if self._kill is None:
                            self._kill = (netwatch.NET, "route lost")
                            await self._drop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[Mikasa] watchdog: {type(e).__name__}: {e}")
                await asyncio.sleep(1.0)

    async def run(self) -> None:
        """Connect, read, and put it back together, for as long as the room is open.

        The loop now also owns a watchdog, and it distinguishes a handover from
        a failure on the way in rather than on the way out — a scheduled
        rotation must not print "connection lost" in the conversation.
        """
        pump = asyncio.create_task(self._pump())
        watch = asyncio.create_task(self._watchdog())
        try:
            while self._alive:
                if self.session is None:
                    if not await self._reconnect():
                        return
                before = self._session_t0 or time.monotonic()
                try:
                    await self._read()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if not self._alive:
                        return
                    kind = netwatch.classify(e)
                    why = netwatch.detail(e)
                    print(f"[Mikasa] lost [{kind}]: {why}")
                    self._kill = self._kill or (kind, why)
                # ── the connection is over, whoever ended it ────────────────
                kill, self._kill = self._kill, None
                planned = self._planned or (kill is not None and
                                            kill[0] == netwatch.PLANNED)
                # `_planned` is NOT cleared here. `_reconnect()` reads it to
                # decide whether the return is news, and clearing it in this
                # loop made every handover — a rotation, or a voice change —
                # look like a drop on the way back: a "back" line in the
                # conversation and a prompt telling her to pick up a sentence
                # nobody interrupted.
                lived = max(0.0, time.monotonic() - before)
                if kill is not None and not planned:
                    self.log.add("drop", why=kill[0], detail=kill[1],
                                 after=round(lived, 1), msgs=self._saw,
                                 model=self.model)
                await self._drop()
                if not planned:
                    try:
                        self.on_lost(kill[1] if kill else "", kill[0] if kill else "")
                    except Exception:
                        pass
                self._saw = 0
        finally:
            for t in (watch, pump):
                t.cancel()
            await self._drop()
