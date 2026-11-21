"""Her mouth: the sentence splitter, the director, and the way out.

Run:  python tests/test_voice.py      (from the mikasa/ folder)

No network, no audio device, no Qt. The TTS call is replaced with a stub that
returns four bytes, so what is proved here is the part that decides what she
sounds like and what happens when the voice is not there:

  1. fragments become whole sentences, and nothing is said twice
  2. a long sentence with no full stop is cut at a comma, not waited on
  3. Devanagari danda ends a sentence too — she speaks Hinglish
  4. the mood she is showing picks the style, and an unknown mood still talks
  5. a question lifts, an ellipsis trails — cues add, never replace
  6. no key, or mode "live" — the studio voice is off, the session keeps talking
  7. a quota wall turns the studio voice off for a while, once, with one line
  8. the PCM goes to exactly one place: the same speaker queue as before
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import voice  # noqa: E402


# ── 1. fragments in, sentences out ──────────────────────────────────────────
def _splitter_joins_fragments():
    sp = voice.Splitter()
    assert sp.feed("suno, main") == [], "spoke half a clause"
    out = sp.feed(" yahi soch rahi thi. Aur")
    assert out == ["suno, main yahi soch rahi thi."], out
    out += sp.feed(" phir wo chala gaya.")
    # "Aur" was already in hand when the split happened, so it opens the next
    # sentence instead of being dropped — that is the whole point of a buffer.
    assert out == ["suno, main yahi soch rahi thi.",
                   "Aur phir wo chala gaya."], out
    assert sp.flush() == [], "said something twice"
    return "two fragments, two sentences, no repeat"


def _splitter_cuts_long_clauses():
    sp = voice.Splitter(min_chunk=10, max_chunk=60)
    text = ("dekh, main tujhe ek baat bata deti hoon jo maine kisi ko "
            "nahi batayi, aur wo baat ye hai ki")
    out = sp.feed(text)
    assert out, "a 110-character fragment with no full stop was held back"
    assert all(len(s) <= 80 for s in out), out
    assert sp.flush(), "the tail was dropped"
    return f"cut into {len(out)}+1 pieces, never held"


def _splitter_knows_danda():
    sp = voice.Splitter(min_chunk=5)
    out = sp.feed("main theek hoon। tum batao")
    assert out == ["main theek hoon।"], out
    return "danda ends a sentence"


# ── 2. the director ─────────────────────────────────────────────────────────
def _style_follows_mood():
    assert "whisper" in voice.style_for("love", "suno na")
    assert "laugh" in voice.style_for("excited", "haan!")
    assert "held on a leash" in voice.style_for("angry", "theek hai")
    assert voice.style_for("", "x") == voice.style_for("not-a-mood", "x")
    assert voice.style_for("", "x") == voice.STYLES.get("__none__",
                                                        voice._FALLBACK_STYLE)
    return "twelve moods, one of them a fallback"


def _cues_add_not_replace():
    plain = voice.style_for("happy", "aaj kya kiya")
    asked = voice.style_for("happy", "aaj kya kiya?")
    trailed = voice.style_for("happy", "aaj kya kiya...")
    assert plain != asked and asked.startswith(voice.STYLES["happy"])
    assert "trailing off" in trailed
    assert "?" not in voice.style_for("happy", "aaj kya kiya")
    return "question lifts, ellipsis trails, base never lost"


def _instruction_keeps_the_words():
    line = "suno, aaj bahut din baad baat ho rahi hai"
    said = voice.said(line)
    assert line in said, "the instruction ate the sentence"
    assert "not a narrator" in said, "no direction was given"
    return "direction in English, words untouched"


# ── 3. what happens when the voice is not there ─────────────────────────────
def _no_key_means_native():
    v = voice.Voice(api_key="", sink=lambda b: None)
    assert not v.enabled, "studio voice without a key"
    assert v.partial("hello there.", 0) == [], "spoke without a key"
    v2 = voice.Voice(api_key="k", sink=lambda b: None, mode="live")
    assert not v2.enabled, "studio voice in live mode"
    return "no key or mode live -> the session keeps its own audio"


def _quota_wall_speaks_once():
    import types as _t
    lines = []
    v = voice.Voice(api_key="k", sink=lambda b: None, note=lines.append)
    assert not v.enabled, "spoke before the warm-up proved the voice"
    v.ready = True
    assert v.enabled
    # the real types object, stubbed: the failure has to come from the call,
    # not from the library being absent on this machine
    voice._TYPES = _t.SimpleNamespace(GenerateContentConfig=lambda **k: k,
                                      SpeechConfig=lambda **k: k,
                                      VoiceConfig=lambda **k: k,
                                      PrebuiltVoiceConfig=lambda **k: k)

    class _Boom:
        class models:
            @staticmethod
            def generate_content(**_kw):
                raise RuntimeError("429 RESOURCE_EXHAUSTED quota")

    v._client = _Boom()
    assert v._render("theek hai", "") == b""
    assert not v.enabled, "kept trying the voice that said no"
    assert len(lines) == 1 and "purani awaaz" in lines[0], lines

    v._render("theek hai", "")          # a second sentence in the same turn
    assert len(lines) == 1, f"said it twice: {lines}"
    return "one quiet line, then the older voice, not silence"


def _fallback_is_forever_for_this_session():
    v = voice.Voice(api_key="k", sink=lambda b: None)
    v.ready = True
    v.hand_back()
    assert v.fallback and not v.enabled
    assert v.partial("kuch bhi.", 0) == []
    return "hand_back sticks; no silent flapping"


# ── 4. the audio actually goes somewhere ────────────────────────────────────
def _pcm_reaches_the_sink():
    got = []
    v = voice.Voice(api_key="k", sink=got.append)
    v.ready = True

    def fake_render(_sentence, _mood):
        return b"\x01\x02" * 8

    v._render = fake_render
    asyncio.run(v.speak(["ek line.", "doosri line."], "calm"))
    assert len(got) == 2 and all(got), got
    assert v.spoken == 2
    return "two sentences, two writes, same queue as before"


def _speak_stops_when_disabled():
    got = []
    v = voice.Voice(api_key="k", sink=got.append)
    v.ready = True
    v.hand_back()
    asyncio.run(v.speak(["kuch.", "aur kuch."], ""))
    assert got == [], "spoke after hand_back"
    return "a dead mouth stays dead until the next session"


def _sink_failure_does_not_kill_the_turn():
    def dead(_b):
        raise OSError("device gone")
    v = voice.Voice(api_key="k", sink=dead)
    v.ready = True
    v._render = lambda s, m: b"\x00\x00"
    asyncio.run(v.speak(["ek.", "do."], ""))     # must not raise
    return "a dead speaker costs the sentence, not the evening"


def _a_cold_voice_stays_quiet():
    got = []
    v = voice.Voice(api_key="k", sink=got.append)
    v._render = lambda s, m: b"\x00\x00"
    assert not v.enabled, "a voice that has not answered yet is already talking"
    asyncio.run(v.speak(["kuch."], ""))
    assert got == [], "spoke before the warm-up"
    return "nothing is spoken until the warm-up answers"


def _every_face_has_a_mouth():
    faces = {"happy", "sad", "angry", "fearful", "disgusted", "surprised",
             "excited", "calm", "bored", "confused", "tired", "love"}
    assert set(voice.STYLES) == faces, set(voice.STYLES) ^ faces
    assert {n for n, _ in voice.DEMO} == faces, "a mood has no demo line"
    assert len(voice.STYLES) == 12 and len(voice.DEMO) == 12
    # and the demo is what the app would say, not a different prompt path
    assert all(voice.said(line) for _, line in voice.DEMO)
    return "12 faces, 12 styles, 12 demo lines, one code path"


_checks = [
    ("fragments become sentences, nothing said twice", _splitter_joins_fragments),
    ("a long clause is cut, not waited on", _splitter_cuts_long_clauses),
    ("a danda ends a sentence", _splitter_knows_danda),
    ("her mood picks the style", _style_follows_mood),
    ("cues add to the style, never replace it", _cues_add_not_replace),
    ("the instruction keeps her words", _instruction_keeps_the_words),
    ("no key or live mode means native audio", _no_key_means_native),
    ("a quota wall says one quiet line", _quota_wall_speaks_once),
    ("handing back is final for the session", _fallback_is_forever_for_this_session),
    ("pcm reaches the speaker queue", _pcm_reaches_the_sink),
    ("nothing is spoken once handed back", _speak_stops_when_disabled),
    ("a dead speaker does not kill the turn", _sink_failure_does_not_kill_the_turn),
    ("a cold voice stays quiet", _a_cold_voice_stays_quiet),
    ("every face has a mouth", _every_face_has_a_mouth),
]


def main() -> int:
    passed = failed = 0
    for name, fn in _checks:
        try:
            note = fn()
            print(f"✅ {name:<58} {note}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {name:<58} AssertionError: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {name:<58} {type(e).__name__}: {e}")
            failed += 1
    print("=" * 78)
    print(f"{passed} passed · {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
