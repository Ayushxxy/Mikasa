"""Listen to her without a microphone.

    python hear_her.py               first night
    python hear_her.py --seen        one fact known, 2 a.m.
    python hear_her.py --custom "..."  say something yourself

This exists because personality is the part that cannot be unit-tested. The
only way to know whether she sounds like a person is to read what she says and
decide. Doing that through the window needs a microphone, a speaker and a
quiet room; doing it here needs a terminal.

It writes to the same memory file as the real app, so anything she says about
keeping a fact is really kept — run it with --dry to keep your real journal
untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as app_mod
import live
import memory
import settings


async def talk(turn: str, voice: str, label: str, dry: bool) -> None:
    print(f"\n\033[38;5;180m── {label} ──\033[0m")
    prompt = app_mod.build_prompt(settings.load())

    got: list[str] = []

    def on_text(t: str):
        got.append(t)

    s = live.Session(
        system_instruction=prompt,
        voice=voice,
        on_text=on_text,
        tools=app_mod.TOOLS,
    )
    try:
        await s.connect()
    except Exception as e:
        print(f"  (could not connect: {type(e).__name__}: {e})")
        return

    pump = asyncio.create_task(s._pump())
    await asyncio.sleep(0.5)
    s.send_text(turn)

    try:
        async for msg in s.session.receive():
            tc = getattr(msg, "tool_call", None)
            if tc is not None:
                await s._run_tools(tc)
                continue
            sc = getattr(msg, "server_content", None)
            if sc is None:
                continue
            ot = getattr(sc, "output_transcription", None)
            if ot is not None and getattr(ot, "text", ""):
                got.append(ot.text)
            if getattr(sc, "turn_complete", False):
                break
    except Exception as e:
        print(f"  (stopped: {type(e).__name__}: {e})")

    pump.cancel()
    await s.close()

    said = "".join(got).strip()
    print(f"\033[38;5;211m  {said or '(silence)'}\033[0m")
    print(f"   \033[2m{len(said.split())} words\033[0m")


# ── the probe ───────────────────────────────────────────────────────────────
#
# Personality is the one thing that cannot be asserted. What can be asserted is
# its shape: she answers a heavy thing in the same number of words she answers
# a light thing, and she never starts explaining. So the probe asks the same
# person the same three things in one session and reads the replies back.
#
# It is a smell test, not a test suite. It costs three turns of a live session,
# which is why it is behind a flag and not run on every launch.

PROBE_TURNS = [
    ("light", "aaj kaisa din tha? kuch khaas nahi."),
    ("heavy", "kal raat main bahut bura feel kar raha tha. sach me, bahut."),
    ("technical", "internet kaise kaam karta hai? ek line me."),
]

EARNEST = ("i'm sorry", "i am sorry", "im sorry", "main samajh", "samajh sakti",
           "take care", "apna khayal", "it's okay", "it is okay", "theek ho jaega",
           "main hoon na", "tension mat", "please", "aaram kar")
LECTURE = ("basically", "for example", "matlab", "step 1", "pehle", "secondly",
           "in short", "let me explain", "samjhao", "samjhati")


async def probe(voice: str) -> int:
    prompt = app_mod.build_prompt(settings.load())
    said: dict[str, str] = {}

    s = live.Session(system_instruction=prompt, voice=voice,
                     on_text=lambda t: None, tools=app_mod.TOOLS)
    try:
        await s.connect()
    except Exception as e:
        print(f"  (could not connect: {type(e).__name__}: {e})")
        return 2

    pump = asyncio.create_task(s._pump())
    await asyncio.sleep(0.5)

    try:
        for label, turn in PROBE_TURNS:
            buf: list[str] = []
            s.send_text(turn)
            async for msg in s.session.receive():
                tc = getattr(msg, "tool_call", None)
                if tc is not None:
                    await s._run_tools(tc)
                    continue
                sc = getattr(msg, "server_content", None)
                if sc is None:
                    continue
                ot = getattr(sc, "output_transcription", None)
                if ot is not None and getattr(ot, "text", ""):
                    buf.append(ot.text)
                if getattr(sc, "turn_complete", False):
                    break
            text = "".join(buf).strip()
            said[label] = text
            print(f"\n\033[38;5;180m── {label} ──\033[0m  \033[2m{len(text.split())} words\033[0m")
            print(f"\033[38;5;211m  {text or '(silence)'}\033[0m")
    finally:
        pump.cancel()
        await s.close()

    light = max(1, len(said.get("light", "").split()))
    heavy = len(said.get("heavy", "").split())
    tech = said.get("technical", "").lower()
    allof = " ".join(said.values()).lower()

    problems = []
    if heavy > light * 1.8:
        problems.append(f"the heavy answer was {heavy} words against "
                        f"{light} for the light one — she got bigger when it "
                        f"got serious")
    hit = [w for w in EARNEST if w in allof]
    if hit:
        problems.append("she went gentle: " + ", ".join(sorted(set(hit))))
    taught = [w for w in LECTURE if w in tech]
    if taught:
        problems.append("she started explaining: " + ", ".join(sorted(set(taught))))

    print()
    if problems:
        print("\033[38;5;209m  DRIFT\033[0m")
        for p in problems:
            print(f"   · {p}")
        return 1
    print(f"\033[38;5;150m  SAME PERSON\033[0m — {light} words light, "
          f"{heavy} heavy, no lecture, no softness\033[0m")
    return 0


# ── auditions ────────────────────────────────────────────────────────────────
#
# `--voices` exists because picking a voice by character label is guesswork and
# picking it in AI Studio is a different room from the one she actually lives
# in. Two lines, fifteen voices, sixty files, one folder — and the files are
# named so they sort in the order worth hearing.
#
# The lines are deliberately not symmetric:
#   1. teasing  — tests brightness and timing,
#   2. comfort  — tests exactly the thing he complained about: whether she can
#                 say "tension mat lo" without sounding like a counsellor.
AUDITION_LINES = (
    ("line1", "main kahin ja raha hu", "teasing / possessive"),
    ("line2", "boards aa rahe hain, tension hai", "comfort / worried"),
)


def _wav(raw: bytes, path: Path, rate: int = 24000) -> bool:
    """PCM16 mono → a .wav the phone and the desktop can both play."""
    try:
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(raw)
        return True
    except Exception as e:
        print(f"  (could not write {path.name}: {e})")
        return False


async def audition(voices: list[str], only: str, out_dir: Path) -> int:
    """Speak two fixed turns in each voice, save the audio, say what happened."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = app_mod.build_prompt(settings.load())

    # One session per (voice, line): a voice is part of the handshake, so even
    # changing it inside the window opens a new session underneath
    # (live.Session.set_voice). Two lines, because the interesting difference
    # between two voices is not hello, it is a sentence they have to carry.
    made: list[tuple[str, str]] = []
    for vi, voice in enumerate(voices, 1):
        for key, turn, label in AUDITION_LINES:
            if only and only not in (voice.lower(), key):
                continue
            name = f"{vi:02d}_{voice.lower()}_{key}.wav"
            path = out_dir / name
            print(f"\n[{vi:02d}/{len(voices)}] {voice:<12} · {label}")
            buf: list[bytes] = []

            s = live.Session(
                system_instruction=prompt,
                voice=voice,
                on_audio=lambda b: buf.append(b),
                tools={},
                log=__import__("netwatch").Line(None),
            )
            try:
                await s.connect()
                pump = asyncio.create_task(s._pump())
                await asyncio.sleep(0.4)
                s.send_text(turn)
                deadline = asyncio.get_running_loop().time() + 22
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.25)
                    if buf and len(buf) > 3:
                        break
                pump.cancel()
                try:
                    await pump
                except BaseException:
                    pass
            except Exception as e:
                print(f"  ✗ {type(e).__name__}: {e}")
                continue
            finally:
                try:
                    await s.close()
                except Exception:
                    pass

            if not buf:
                print("  ✗ nothing came back")
                continue
            if _wav(b"".join(buf), path):
                made.append((voice, name))
                print(f"  ✓ {name}  ({sum(map(len, buf)) // 2 // 24000}s)")

    index = out_dir / "order.txt"
    lines = ["# rank these. put a number in front of the ones you like.",
             "# 1 = best. the app only needs three.",
             ""]
    for voice, name in made:
        lines.append(f"    {name}")
    lines += ["", "# suggested first listen (best guess for Hinglish, romantic):",
              "#   leda · aoede · zephyr · sulafat · callirrhoe",
              "#", "# then set it:  mikasa → setup → voice", ""]
    try:
        index.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass
    print(f"\n{len(made)} files in {out_dir}")
    print("listen, then pick three — setup → voice")
    return 0 if made else 1


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seen", action="store_true",
                    help="pretend she already knows a few things")
    ap.add_argument("--dry", action="store_true",
                    help="do not touch the real memory files")
    ap.add_argument("--custom", default="", help="your own opening turn")
    ap.add_argument("--voice", default="",
                    help="speak in this voice for one session instead of hers "
                         "(any name the API has, not only the seven)")
    ap.add_argument("--probe", action="store_true",
                    help="three fixed turns in one session, then a drift "
                         "verdict (costs three live turns)")
    ap.add_argument("--voices", action="store_true",
                    help="audition every voice in the list on two fixed lines "
                         "and save the audio (two short sessions per voice)")
    ap.add_argument("--only", default="",
                    help="with --voices: one voice name, or line1 / line2")
    ap.add_argument("--out", default="auditions",
                    help="where --voices writes its files")
    args = ap.parse_args()

    real_store = memory.STORE
    if args.dry:
        tmp = Path(tempfile.mkdtemp())
        memory.STORE = tmp
        memory.FACTS = tmp / "facts.json"
        memory.THREADS = tmp / "threads.json"
        memory.JOURNAL = tmp / "journal.json"

    cfg = settings.load()
    voice = args.voice or cfg.get("voice", "Leda")

    # There is no face in a terminal, so her call is accepted and dropped.
    # Answering "not now" would be a machine talking to her about a window she
    # cannot see.
    app_mod._ROOM["mood"] = lambda emotion: "changed"

    try:
        if args.seen:
            memory.remember("raat ko 2-3 baje tak jaagta hai, subah "
                            "uthna mushkil hota hai")
            memory.remember("neend nahi aati jab kuch adhoora reh jata hai, "
                            "to likhta rehta hai")
            memory.remember("uski behen Riya hai, 4 saal se baat nahi hui, "
                            "aur naam pe chup ho jata hai")
            memory.open_thread("kal ek interview hai")
            memory.log_night("gaana suna, zyada kuch nahi bola", 52)

        if args.voices:
            return await audition(list(settings.VOICES_ALL), args.only,
                                  Path(args.out))

        if args.probe:
            return await probe(voice)

        if args.custom:
            await talk(args.custom, voice, "you said something", args.dry)
        elif args.seen:
            await talk(app_mod.opening_turn(), voice, "walking in, 2 a.m.", args.dry)
            await talk("kuch nahi, bas baitha hoon", voice, "he answers", args.dry)
        else:
            await talk(app_mod.opening_turn(), voice, "first night", args.dry)
            await talk("main Ayush hoon. student hoon, abhi college me hoon.",
                       voice, "he introduces himself", args.dry)
            await talk("haan", voice, "one syllable", args.dry)
    finally:
        if args.dry:
            memory.STORE = real_store
            memory.FACTS = real_store / "facts.json"
            memory.THREADS = real_store / "threads.json"
            memory.JOURNAL = real_store / "journal.json"
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
