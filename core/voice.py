"""Her voice — the same words, rendered instead of generated.

WHY THIS FILE EXISTS
    Gemini Live answers with audio, and that audio is good but it is one
    register: the same pace, the same brightness, whether she is teasing or
    saying something that costs her. ElevenLabs sounds like a person because
    the director reads the line before the voice does. This file is the
    director.

HOW IT WORKS
    Nothing about listening changes. The Live session still hears him, still
    decides when he is done, still calls her tools — the native audio it
    produces is simply dropped. Her words already arrive as
    `output_audio_transcription`; those fragments feed a sentence splitter,
    each finished sentence goes to a real TTS pass with a style instruction
    chosen from her own mood, and the PCM it returns is pushed into the same
    speaker queue the native audio used to fill.

    So: same ears, same brain, same window. Only the mouth is different.

WHAT IT COSTS
    One extra round trip per sentence. The first syllable lands about a second
    or two after it used to. That is the price of acting, and it was paid on
    purpose.

WHAT IT DOES WHEN THE VOICE IS NOT AVAILABLE
    It says so once, quietly, and hands the mouth back to the Live session. A
    quota wall must never be silence: she keeps talking in the older voice and
    the window shows one dim line explaining why.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Callable, Optional

# The two models that can be asked for a performance. Both are on the free
# tier; the second is the current name and the first is the one every example
# on the internet still uses, so both are tried before giving up.
TTS_MODELS = ("gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts")

# 24 kHz mono, signed 16-bit little endian, which is what both the Live API and
# `sounddevice` already speak. Nothing in the audio path had to change.
SAMPLE_RATE = 24000

# A sentence shorter than this is not worth a round trip; it gets glued to the
# next one. Long enough to skip "haan.", short enough to keep the first words
# moving.
MIN_CHUNK = 12
# If a fragment has no full stop and is already this long, cut it at the last
# comma. A long sentence with no punctuation is common in speech and waiting
# for a full stop there is waiting for the whole answer.
MAX_CHUNK = 110

# Where a sentence can end, including the Devanagari danda.
_END = re.compile(r"(?<=[.!?…।])\s+")

# How she sounds. Keyed by the mood she has already shown on her face, so the
# mouth and the drawing never disagree — that mismatch is worse than a flat
# voice.
STYLES = {
    "love":      "very soft and close, almost a whisper, a smile you can hear",
    "calm":      "quiet, unhurried, warm — someone talking in a dark room",
    "happy":     "light and warm, the words smiling",
    "excited":   "bright and quick, laughing under the words",
    "sad":       "low and slow, a little unsteady, holding something back",
    "angry":     "clipped and low, anger held on a leash, never shouted",
    "bored":     "flat and slow, unimpressed, half the energy of usual",
    "tired":     "sleepy, trailing off, heavy",
    "surprised": "quick, breath caught, eyebrows up",
    "fearful":   "small and careful, breath shallow",
    "disgusted": "dry, pulled back, nose wrinkled",
    "confused":  "hesitant, thinking while speaking, a small pause before the point",
}
_FALLBACK_STYLE = "conversational, warm, close-mic, a real person not a narrator"

# Cues that only ever add to the mood, never fight it: a question lifts, an
# ellipsis trails, an exclamation is brighter. No cue is ever the whole style.
def _cues(text: str) -> str:
    out = []
    if text.rstrip().endswith("?"):
        out.append("a question, genuinely asking")
    elif text.rstrip().endswith("!"):
        out.append("a little brighter than the rest")
    if "..." in text or "…" in text:
        out.append("trailing off at the end")
    return (", " + ", ".join(out)) if out else ""


def style_for(mood: str, text: str) -> str:
    """The one line that turns a script into a performance."""
    base = STYLES.get((mood or "").strip().lower(), _FALLBACK_STYLE)
    return base + _cues(text)


def said(text: str) -> str:
    """The exact instruction Gemini TTS is given.

    English on purpose: the style clause is followed far more reliably in
    English than in Hindi, while the line after the colon is spoken in whatever
    language it is written in. Hinglish therefore survives untouched.
    """
    return ("Read the following aloud as a young woman speaking privately, "
            "not a narrator and not an announcement. Do not add any words of "
            "your own: " + text)


class Splitter:
    """Fed fragments, yields whole things to say.

    Live sends transcription as it goes — half a clause at a time. Waiting for
    `turn_complete` before speaking the whole answer costs two seconds and
    makes her sound like she is reading. This starts the mouth on the first
    sentence while the rest is still being written.
    """

    def __init__(self, min_chunk: int = MIN_CHUNK, max_chunk: int = MAX_CHUNK):
        self.min_chunk = min_chunk
        self.max_chunk = max_chunk
        self._buf = ""

    def feed(self, fragment: str) -> list[str]:
        if fragment:
            self._buf += fragment
        out = []
        while True:
            text = self._buf
            parts = _END.split(text, maxsplit=1)
            if len(parts) == 2:
                head, rest = parts
                head = head.strip()
                if len(head) >= self.min_chunk // 2:
                    out.append(head)
                    self._buf = rest.lstrip()
                    continue
            # A fragment can end exactly on its full stop, with no space after
            # it — that is how a turn usually arrives. Waiting for a space that
            # never comes would hold the last sentence of every reply.
            if text.rstrip()[-1:] in ".!?…।" and len(text.strip()) >= self.min_chunk:
                out.append(text.strip())
                self._buf = ""
                continue
            if len(text) > self.max_chunk:
                window = text[:self.max_chunk]
                cut = max(window.rfind(", "), window.rfind("; "),
                          window.rfind(" — "))
                if cut < self.min_chunk:
                    # No punctuation at all: a space is still better than
                    # waiting for a full stop that may be two sentences away.
                    cut = window.rfind(" ")
                if cut > self.min_chunk:
                    out.append(text[:cut].rstrip(" ,;—"))
                    self._buf = text[cut:].lstrip()
                    continue
            break
        return out

    def flush(self) -> list[str]:
        """End of turn: whatever is left is said now, however short."""
        rest, self._buf = self._buf.strip(), ""
        return [rest] if rest else []


_TYPES = None


def _types():
    """google.genai types, imported once, or None if the package is missing.

    Module-level so a test can swap in a stub: the failure path below is the
    most important one in this file and it cannot be reached through a network
    call that is not allowed to happen during a test.
    """
    global _TYPES
    if _TYPES is not None:
        return _TYPES
    try:
        from google.genai import types as t
        _TYPES = t
    except Exception as e:
        print(f"[Mikasa] voice types: {e}")
        _TYPES = None
    return _TYPES


class Voice:
    """A mouth that can be swapped without touching anything around it.

    `sink` is called with 24 kHz int16 PCM. `note` is called with one short
    line for the room — used exactly once, when the studio voice dies and she
    goes back to the old one.
    """

    def __init__(self, api_key: str, sink: Callable[[bytes], None],
                 note: Optional[Callable[[str], None]] = None,
                 voice: str = "Leda", mode: str = "studio"):
        self.api_key = (api_key or "").strip()
        self.sink = sink
        self.note = note or (lambda _t: None)
        self.voice_name = voice
        self.mode = mode if mode in ("studio", "live") else "studio"
        self.splitters: dict[int, Splitter] = {}
        self._client = None
        self._fails = 0
        self._disabled_until = 0.0
        self.last_error = ""
        # False until warm_up() has proved the voice answers. The app keeps the
        # Live audio playing until then, so a slow or dead TTS is a delay, not
        # a silence.
        self.ready = False
        self.spoken = 0           # sentences actually rendered, for the tests
        self.fallback = False     # True once the Live audio is doing the talking

    # ── state ───────────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        """Whether the studio voice is the one talking right now."""
        return (self.mode == "studio" and self.ready and bool(self.api_key)
                and not self.fallback and time.monotonic() >= self._disabled_until)

    def _disable(self, why: str, seconds: float) -> None:
        # Once is information, twice is nagging. Every sentence after the wall
        # fails in the same way and he does not need a line per sentence.
        if time.monotonic() < self._disabled_until:
            self.last_error = why
            return
        self.last_error = why
        self._disabled_until = time.monotonic() + seconds
        self.note(f"voice: {why} — purani awaaz se bol rahi hoon")
        print(f"[Mikasa] voice off for {seconds:.0f}s: {why}")

    # ── feeding ─────────────────────────────────────────────────────────────
    def partial(self, text: str, turn: int = 0) -> list[str]:
        """A transcription fragment. Returns the sentences ready to speak."""
        sp = self.splitters.setdefault(turn, Splitter())
        ready = sp.feed(text)
        return ready if self.enabled else []

    def end_turn(self, turn: int = 0) -> list[str]:
        sp = self.splitters.pop(turn, None)
        if not sp:
            return []
        return sp.flush() if self.enabled else []

    # ── speaking ────────────────────────────────────────────────────────────
    async def speak(self, sentences: list[str], mood: str = "") -> None:
        """Render and play. Never raises: a failed sentence is a quiet one."""
        for s in sentences:
            if not self.enabled:
                return
            if len(s.strip()) < 2:
                continue
            pcm = await asyncio.to_thread(self._render, s, mood)
            if not pcm:
                continue
            self.spoken += 1
            try:
                self.sink(pcm)
            except Exception as e:                   # a dead speaker, not us
                print(f"[Mikasa] voice sink: {e}")

    def _client_or_none(self):
        if self._client is not None:
            return self._client
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as e:
            print(f"[Mikasa] voice client: {e}")
            self._client = None
        return self._client

    def _render(self, sentence: str, mood: str) -> bytes:
        """One sentence in, 24 kHz PCM out, or b'' with the reason kept."""
        client = self._client_or_none()
        if client is None:
            self._fails += 1
            return b""
        types = _types()
        if types is None:
            self._fails += 1
            if self._fails >= 2:
                self._disable("library nahi mili", 600.0)
            return b""

        prompt = f"{style_for(mood, sentence)}: {sentence}"
        last = ""
        for model in TTS_MODELS:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=
                                types.PrebuiltVoiceConfig(
                                    voice_name=self.voice_name)))))
                part = resp.candidates[0].content.parts[0]
                data = getattr(part, "inline_data", None)
                if data is not None and getattr(data, "data", None):
                    self._fails = 0
                    return data.data
                last = "empty audio"
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                msg = str(e).lower()
                # A quota wall or a retired model is not worth retrying for
                # every sentence of every turn: stop, say it once, hand the
                # mouth back.
                if any(k in msg for k in ("resource_exhausted", "quota",
                                          "rate limit", "429", "not found",
                                          "not_found", "permission")):
                    self._fails += 1
                    self._disable("abhi ke liye band", 600.0)
                    return b""
        self._fails += 1
        if self._fails >= 2:
            self._disable("jawab nahi de rahi", 120.0)
        print(f"[Mikasa] voice render failed: {last}")
        return b""

    def hand_back(self) -> None:
        """Give the mouth back to the Live session, for good, this session."""
        if not self.fallback:
            self.fallback = True
            print("[Mikasa] voice: native audio")


def warm_up(voice: Voice) -> bool:
    """Is the studio voice actually reachable? Asked once, at startup.

    The native audio is only muted after this returns True. Muting first and
    discovering the quota is gone would leave her silent, and silence from a
    person you were talking to is worse than any voice.
    """
    if not voice.enabled:
        return False
    try:
        pcm = voice._render("theek hai", "")
    except Exception as e:
        print(f"[Mikasa] voice warm-up: {e}")
        return False
    if pcm:
        voice.ready = True
    return bool(pcm)


# ── hearing her before the window opens ─────────────────────────────────────
# `python voice.py --demo` renders one line per mood into config/voice-demo/.
# It is the only honest way to judge a mouth: the same key, the same code the
# app uses, a file you can play twice. If a mood sounds wrong, that is a
# direction to change here, not a mystery to guess at.
DEMO = (
    ("calm",      "soja. main hoon na."),
    ("love",      "suno… aa jao idhar, kuch nahi kehna."),
    ("happy",     "arre aa gaye! haan baitho na."),
    ("excited",   "haan haan batao batao, phir kya hua?"),
    ("sad",       "theek hai… main samajh gayi."),
    ("angry",     "mat karo ye. maine bola tha na."),
    ("bored",     "hmm. acha. phir?"),
    ("tired",     "aaj bahut lamba din tha yaar…"),
    ("surprised", "kya?! sach me?"),
    ("fearful",   "arre dheere… koi sun lega."),
    ("disgusted", "eww. hat."),
    ("confused",  "matlab… wo kya bol raha tha?"),
)


def demo(api_key: str = "", voice: str = "Leda", mood: str = "") -> int:
    """Write one wav per mood. No window, no session, no audio device needed."""
    import wave as _wav
    from pathlib import Path

    if not api_key:
        try:
            import json
            api_key = json.loads(
                (Path(__file__).resolve().parent.parent / "config" /
                 "api_keys.json").read_text(encoding="utf-8")
            ).get("gemini_api_key", "").strip()
        except Exception:
            api_key = ""
    if not api_key:
        print("koi key nahi mili — config/api_keys.json me gemini_api_key daal do")
        return 2

    out = Path(__file__).resolve().parent.parent / "config" / "voice-demo"
    out.mkdir(parents=True, exist_ok=True)
    mouth = Voice(api_key=api_key, sink=lambda _b: None, voice=voice)
    picks = [d for d in DEMO if not mood or d[0] == mood]
    made = 0
    for name, line in picks:
        pcm = mouth._render(line, name)
        if not pcm:
            print(f"  {name:<10} — nahi bani ({mouth.last_error or 'no audio'})")
            if mouth.last_error:
                print("  ruk raha hoon: pehli galti hi wajah bata deti hai")
                break
            continue
        path = out / f"{name}.wav"
        with _wav.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        print(f"  {name:<10} {path.name}  {len(pcm) / (SAMPLE_RATE * 2):.1f}s")
        made += 1
    print(f"\n{made} files — {out}")
    return 0 if made else 1


if __name__ == "__main__":
    import sys as _sys
    if "--demo" in _sys.argv:
        i = _sys.argv.index("--demo")
        rest = _sys.argv[i + 1:]
        raise SystemExit(demo(mood=rest[0] if rest else ""))
    print("use:  python voice.py --demo [mood]")
