"""Mikasa's settings — and the one thing she must never see.

WHAT LIVES HERE
    Everything that would break the illusion if she could read it: the code,
    the voice profile, whether the camera is allowed, how far the persona is
    permitted to go. She never receives any of it. The prompt she is given is
    built from `prompt.txt` plus facts about the clock and her shelf — never
    from this file.

THE CODE IS NEVER STORED
    Only a salted hash of it. There is no way to read it back, no way to show
    it, and therefore no way for it to leak into a conversation, a log, or a
    screenshot. If it is lost, it is replaced — which is the correct behaviour
    for a passphrase nobody is supposed to be able to recover.

    The salt is generated once and stored beside it, so two machines with the
    same code do not have the same hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
FILE       = CONFIG_DIR / "mikasa.json"

# ── voices ───────────────────────────────────────────────────────────────────
# Three, and only three. Every one of them is a soft voice — the kind you would
# rather be told "so jao" in than "your call is important to us". Aoede was
# dropped on request: bright and quick, which reads as friendly on a demo and
# tiring at 1 a.m.
#
# Leda is the default and has been since v3.
VOICES = [
    "Leda",          # youthful — the softest of the three; her default
    "Sulafat",       # warm     — lower, slower; carries a plea best
    "Callirrhoe",    # easy     — unhurried; the one for a long night
]
VOICES_ALL = list(VOICES)      # hear_her.py auditions the lot


DEFAULTS = {
    "voice":        "Leda",        # see VOICES; changeable while she is open
    # Set the moment a voice is chosen in the window. A config written by an
    # older build says "Aoede" because that used to be the default, not because
    # anybody chose it — see _voice_of().
    "voice_picked": False,
    # "studio" sends her words through a real TTS pass with a style direction;
    # "live" keeps the Live session's own audio. Studio costs about a second
    # and buys the acting, and it falls back to live by itself the moment the
    # TTS quota or the network says no.
    "voice_mode":   "studio",
    "language":     "Hindi and English mixed, the way people here actually talk",
    # Where she thinks she is. A city makes her clock mean something: "subah 7
    # baje" lands differently in a place where it is still dark than in one
    # where it is not, and she should sound like she lives where he lives.
    # A city and a zone, never an address — and never a coordinate.
    "city":         "Agra",
    "tz":           "Asia/Kolkata",
    # Opens full screen. She is a room, not a window you keep in the corner of
    # a desktop — and half of the drawing is wasted at 1080x760. Esc gives the
    # window back, F11 toggles, and the last choice is remembered.
    "fullscreen":   True,
    # set the first time he presses Esc or F11; before that the value above is
    # the shipped default and an old file's `false` is not a choice he made
    "fullscreen_picked": False,
    "camera":       "ask",         # ask | off
    "alarm":        True,
    # off | on. There is no "ask": she does not request permission to remember
    # him, she remembers him. A config written by a build that had "ask" is
    # read as "on" — see app._notes_rule.
    "her_writing":  "on",
    "code_on":      False,         # does a typed passphrase exist yet
    "code_salt":    "",
    "code_hash":    "",
    "first_night":  True,          # cleared the moment she has learned anything
}


def _ensure() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not FILE.exists():
        FILE.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
        return dict(DEFAULTS)
    try:
        raw = json.loads(FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("not an object")
    except Exception:
        # A corrupt settings file must not stop her from existing. The defaults
        # are the safe state: no code, no filters, nothing armed.
        raw = {}
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in raw.items() if k in DEFAULTS})
    merged["voice"] = _voice_of(raw)

    # "ask" was a mode of the memory notebook and it was the bug: asking him
    # turned a bad night into a form. It is not a mode any more, and a config
    # that still says it means the notebook is open, so it is read as "on"
    # rather than left sitting in the file pretending to be a third choice.
    if str(merged.get("her_writing")).lower() == "ask":
        merged["her_writing"] = "on"

    # Full screen is the shipped default. There has never been a control for
    # it in the window, so a `false` in an old file can only be the old
    # default — not a decision. Once he presses Esc or F11 it is a decision,
    # and `fullscreen_picked` remembers that.
    if not raw.get("fullscreen_picked"):
        merged["fullscreen"] = DEFAULTS["fullscreen"]
    return merged


def _voice_of(raw: dict) -> str:
    """Which voice a config that has just been read should actually use.

    Two rules, both about not trusting an old file:

    * a voice that is not in VOICES anymore (Aoede, Zephyr, the rest) is not a
      choice he can make now, so it falls back to the default instead of being
      passed to the API and failing at connect time;
    * a config that still says Aoede without `voice_picked` is carrying the old
      default, not a decision — that one has moved to Leda since v3.
    """
    voice = str(raw.get("voice") or DEFAULTS["voice"])
    if voice not in VOICES:
        return DEFAULTS["voice"]
    if not raw.get("voice_picked") and voice == "Aoede":
        return DEFAULTS["voice"]
    return voice


def load() -> dict:
    return _ensure()


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)


def get(key: str, default=None):
    return load().get(key, DEFAULTS.get(key, default))


# ── the door ─────────────────────────────────────────────────────────────────
def set_code(code: str) -> None:
    """Hash and store. The plaintext is not kept, not logged, not returned."""
    code = (code or "").strip()
    cfg = load()
    if not code:
        cfg["code_on"], cfg["code_hash"], cfg["code_salt"] = False, "", ""
        save(cfg)
        return
    salt = secrets.token_hex(16)
    cfg["code_salt"] = salt
    cfg["code_hash"] = _hash(code, salt)
    cfg["code_on"]   = True
    save(cfg)


def check_code(typed: str) -> bool:
    cfg = load()
    if not cfg.get("code_on"):
        return True                      # no door yet: the first night is open
    if not typed:
        return False
    return secrets.compare_digest(_hash(typed.strip(), cfg.get("code_salt", "")),
                                  str(cfg.get("code_hash", "")))


def _hash(code: str, salt: str) -> str:
    return hashlib.sha256((salt + "|" + code).encode("utf-8")).hexdigest()


def has_code() -> bool:
    return bool(load().get("code_on"))
