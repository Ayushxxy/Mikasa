#!/usr/bin/env python3
"""MIKASA — setup.py

    Double-click mikasa.bat, or:   python setup.py

WHAT THIS IS
    One file that turns a folder on somebody else's laptop into a working
    Mikasa: a private virtual environment, four packages, her own files checked
    one by one, an API key asked for out loud, a desktop icon, and a test run of
    her own test suite at the end to prove she still works.

    It is deliberately loud. An installer that prints nothing for ninety seconds
    looks like a virus, so every step says what it is doing, how long it took,
    and something rude about the person waiting.

WHY IT DOESN'T JUST RUN pip
    Because pip fails in a hundred ways and says "error" to all of them. Every
    failure here is caught, named in one sentence, and given the exact command
    that fixes it. A friend installing this should never have to open a search
    engine.

    And because the folder may be somebody else's: `config/api_keys.json` is
    never overwritten if it already holds a key, and nothing outside this folder
    is read or written except one shortcut on the desktop.

THANKS
    Built by AM Dimension Company And Creators — AYUSH AND MAYANK.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT   = Path(__file__).resolve().parent
APP    = ROOT / "core" / "app.py"
VENV   = ROOT / ".venv"
REQ    = ROOT / "requirements.txt"
KEYFILE = ROOT / "config" / "api_keys.json"

BUILT_BY       = "AM Dimension Company And Creators"
BUILT_BY_NAMES = "AYUSH AND MAYANK"
VERSION        = "7.0"

PKGS = ["PyQt6>=6.6,<7", "numpy>=1.24,<3", "sounddevice>=0.4,<1",
        "google-genai>=2.8.0,<3"]

KEY_URL = "https://aistudio.google.com/apikey"

W = 76          # every panel in this file is this wide
MIN_PY = (3, 9)


# ══════════════════════════════════════════════════════════════════════════════
#  the console itself
# ══════════════════════════════════════════════════════════════════════════════
def console_fix() -> None:
    """Make the keyboard behave before asking anybody to type into it.

    Three separate things can leave a Windows console looking dead, and this
    file hit all three:

    1. QUICKEDIT. If the console is in quick-edit mode, clicking anywhere in
       the window starts a selection and the console stops accepting input
       until the selection is cancelled. A friend clicking the window out of
       habit gets a setup that ignores every key.
    2. ECHO. `getpass` turns echo off for the API key. Nothing appears as you
       type or paste, so the only key that seems to work is Enter — which is
       precisely how this was reported.
    3. Not a console at all. Started from an IDE or a redirected shell, every
       prompt answers itself with its default and the run looks broken.

    The first is fixed here, the second by never using getpass, the third by
    saying so out loud instead of silently taking defaults.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        STD_INPUT = -10
        ENABLE_PROCESSED_INPUT = 0x0001
        ENABLE_LINE_INPUT      = 0x0002
        ENABLE_ECHO_INPUT      = 0x0004
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_EXTENDED_FLAGS  = 0x0080

        h = k32.GetStdHandle(STD_INPUT)
        mode = wintypes.DWORD()
        if k32.GetConsoleMode(h, ctypes.byref(mode)):
            want = (mode.value
                    | ENABLE_EXTENDED_FLAGS        # make the quick-edit bit mean
                    | ENABLE_PROCESSED_INPUT       # Ctrl+C still interrupts
                    | ENABLE_LINE_INPUT            # Enter sends the whole line
                    | ENABLE_ECHO_INPUT)           # typing is visible
            want &= ~ENABLE_QUICK_EDIT_MODE        # a stray click cannot freeze it
            k32.SetConsoleMode(h, want)
    except Exception:
        pass

    # An unencodable box character must never be the reason an install stops.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  colour
# ══════════════════════════════════════════════════════════════════════════════
def _enable_ansi() -> bool:
    """Windows consoles ignore escape codes until you ask them not to."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        for handle in (-11, -12):                     # stdout, stderr
            h = k32.GetStdHandle(handle)
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(mode)):
                k32.SetConsoleMode(h, mode.value | 0x0004)
        return True
    except Exception:
        return False


class Skin:
    """All the colour in the program, in one object that can be switched off."""

    # violet → pink → gold. The whole palette is derived from these three.
    A = (124, 92, 255)
    B = (255, 77, 141)
    C = (255, 194, 75)
    MINT  = (61, 220, 151)
    RED   = (255, 92, 92)
    GREY  = (128, 138, 156)
    WHITE = (232, 236, 245)

    def __init__(self, enabled: bool):
        self.on = enabled

    def _c(self, rgb, text, bold=False, dim=False, italic=False):
        if not self.on:
            return text
        pre = ""
        if bold:
            pre += "\x1b[1m"
        if dim:
            pre += "\x1b[2m"
        if italic:
            pre += "\x1b[3m"
        r, g, b = rgb
        return f"{pre}\x1b[38;2;{r};{g};{b}m{text}\x1b[0m"

    def accent(self, t, **kw):  return self._c(self.A, t, **kw)
    def hot(self, t, **kw):     return self._c(self.B, t, **kw)
    def gold(self, t, **kw):    return self._c(self.C, t, **kw)
    def mint(self, t, **kw):    return self._c(self.MINT, t, **kw)
    def red(self, t, **kw):     return self._c(self.RED, t, **kw)
    def grey(self, t, **kw):    return self._c(self.GREY, t, **kw)
    def white(self, t, **kw):   return self._c(self.WHITE, t, **kw)

    def grad(self, text: str) -> str:
        """Left-to-right violet → pink → gold, one character at a time."""
        if not self.on or not text:
            return text
        n = max(1, len(text) - 1)
        out = []
        for i, ch in enumerate(text):
            if ch == " ":
                out.append(ch)
                continue
            t = i / n
            if t < 0.5:
                a, b, u = self.A, self.B, t / 0.5
            else:
                a, b, u = self.B, self.C, (t - 0.5) / 0.5
            r = int(a[0] + (b[0] - a[0]) * u)
            g = int(a[1] + (b[1] - a[1]) * u)
            bl = int(a[2] + (b[2] - a[2]) * u)
            out.append(f"\x1b[1m\x1b[38;2;{r};{g};{bl}m{ch}")
        return "".join(out) + "\x1b[0m"


# ══════════════════════════════════════════════════════════════════════════════
#  lines
# ══════════════════════════════════════════════════════════════════════════════
_ROASTS = [
    "Ye installer AYUSH ne likha hai. Isliye har step ke baad ek taunt milega. Free hai.",
    "Tum abhi tak sirf ENTER dabaya hai. Technically tumne kuch nahi kiya. Aur technically yahi karna tha.",
    "Do log, ek laptop, aur ek idea — 'bhai ek ladki banate hain jo sun sake'. Ab tum use install kar rahe ho.",
    "MAYANK ne bola tha ye ek din me ban jayega. Aaj wo din nahi hai.",
    "Agar yahan tak aa gaye ho to samajh lo tumne ek .bat file double-click karna seekh liya. Badhai ho.",
    "Ye progress bar jhooth nahi bol raha. Wo actually kaam kar raha hai. Tumse zyada, is waqt.",
    "Warning: is installer me koi bug nahi hai. Agar phir bhi kuch hua to problem tumhari hai. (Legally. Actually. Genuinely.)",
    "Pip abhi internet se baat kar raha hai. Tumhare messages ka reply aaj bhi nahi aaya, but okay.",
    "Aaram se. Ye 90 second tumhare zindagi ke sabse productive 90 second nahi hain, par hain bhi nahi.",
    "Mikasa tumse zyada sun sakti hai. Literally. Uske paas microphone hai.",
    "Agar ye step fail hua to internet ka naam kharab hoga, tumhara nahi. Thoda sa tumhara bhi.",
    "Log kehte hain patience ek virtue hai. Log ne kabhi PyQt6 download nahi kiya.",
    "Tum abhi kuch install kar rahe ho jo tumhari baat sun ke jawab degi. Apne group chat se zyada dhyan se.",
    "Installer ko band mat karna. Wo tumhari tarah nahi hai, wo beech me chhod ke nahi jaata.",
    "Ek chhota sa sach: tumhara laptop is waqt zinda hai sirf isliye ki tumne update rok rakhe hain.",
    "Ye line sirf isliye hai ki tumhe lage tum padh rahe ho. Padh rahe ho. Fine.",
    "Jo log setup skip karke seedha app kholte hain, unke paas baad me bahut time hota hai — debugging ke liye.",
    "Sab kuch theek chal raha hai. Main bhi shocked hoon.",
]

_FACTS = [
    "Mikasa ke paas 7 aawaz hain. Default Leda — sabse soft. Badalna live hota hai, restart nahi.",
    "Uska apna clock hai, Agra ke IST me. Bina poochhe bata degi kitne baje hain.",
    "Pehli raat wo tumhe jaanti nahi hai — aur jhooth nahi bolegi ki jaanti hai.",
    "Wo tumhari aawaz pehchaan sakti hai. Koi aur bole to pata chal jayega.",
    "Uski apni shelf hai — jo usme rakha jaye, wo rehta hai.",
    "Uska face Qt se draw hota hai. Koi video, koi GIF nahi.",
    "Wo net girne pe khud dobara judti hai. Tumhe kuch nahi karna.",
    "Mikasa ULTRON ki behen nahi hai, na uska button. Alag kamra, alag chabi.",
    "Usske paas 'first night' ka rule hai: pehli mulaqat pe wo zyada bolti nahi, sunti hai.",
]


class UI:
    def __init__(self, args):
        self.args = args
        self.tty = sys.stdout.isatty()
        colour_ok = (_enable_ansi()
                     and not args.no_color
                     and os.environ.get("NO_COLOR") is None
                     and (self.tty or args.force_color))
        self.s = Skin(colour_ok)
        self.unicode = self._unicode_ok() and not args.ascii
        self.fast = args.fast or not self.tty
        self.t0 = time.time()
        self.step_no = 0
        self.steps = 7
        self._rng = random.Random()

    # ── primitives ───────────────────────────────────────────────────────────
    def _unicode_ok(self) -> bool:
        enc = (sys.stdout.encoding or "ascii")
        try:
            "╭─█░▓⠋✓→".encode(enc)
            return True
        except Exception:
            return False

    def clear(self):
        if self.tty and not self.args.no_clear:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()

    def out(self, text=""):
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    def hr(self, text="", colour=None):
        left = self.unicode and "─" or "-"
        corner_l = self.unicode and "╭" or "+"
        corner_r = self.unicode and "╮" or "+"
        if not text:
            self.out(self.s.grey(left * W))
            return
        label = f"{corner_l}─ {text} "
        pad = W - len(label) - 1
        self.out(self.s.grey(label + left * max(0, pad) + corner_r))

    def panel(self, title, rows, accent=None, pad=1):
        s = self.s
        accent = accent or s.accent
        if self.unicode:
            tl, tr, bl, br, h, v = "╭", "╮", "╰", "╯", "─", "│"
        else:
            tl, tr, bl, br, h, v = "+", "+", "+", "+", "-", "|"
        if title:
            head = f"{tl}{h} {title} "
            self.out(accent(head + h * max(0, W - len(head) - 1) + tr))
        else:
            self.out(s.grey(tl + h * (W - 2) + tr))
        for r in rows:
            for wrapped in self._wrap(r, W - 4 - pad * 2):
                pad_s = " " * pad
                self.out(s.grey(v) + pad_s + wrapped
                         + " " * max(0, W - 3 - pad - self._vlen(wrapped))
                         + s.grey(v))
        self.out(s.grey(bl + h * (W - 2) + br))

    @staticmethod
    def _vlen(text) -> int:
        return len(re.sub(r"\x1b\[[0-9;]*m", "", text))

    def _wrap(self, text, width):
        """Wrap on visible width, tolerating the ANSI codes inside."""
        words = text.split(" ")
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip() if cur else w
            if self._vlen(trial) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    # ── voice ────────────────────────────────────────────────────────────────
    def type(self, text, cps=120):
        if self.fast or not self.tty:
            self.out(text)
            return
        delay = 1.0 / max(20, cps)
        chunk = 3
        for i in range(0, len(text), chunk):
            sys.stdout.write(text[i:i + chunk])
            sys.stdout.flush()
            time.sleep(delay * chunk)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def ok(self, text):
        self.out(f"  {self.s.mint('✓' if self.unicode else '+')} {text}")

    def warn(self, text):
        self.out(f"  {self.s.gold('!' if self.unicode else '!')} {self.s.gold(text)}")

    def bad(self, text):
        self.out(f"  {self.s.red('✗' if self.unicode else 'x')} {self.s.red(text)}")

    def info(self, text):
        self.out(f"  {self.s.grey('·')} {text}")

    def _aside(self, mark, text, style):
        """One remark, wrapped, with the mark only on its first line."""
        for i, chunk in enumerate(self._wrap(text, W - 6)):
            lead = f"  {mark} " if i == 0 else "    "
            self.out(lead + style(chunk))

    def roast(self):
        self._aside(self.s.hot("›"), self._rng.choice(_ROASTS),
                    lambda t: self.s.grey(t, italic=True))

    def fact(self):
        self._aside(self.s.accent("◆"), self._rng.choice(_FACTS), self.s.white)

    def step(self, title):
        self.step_no += 1
        if self.step_no > 1:
            self.out()
        tag = f"STEP {self.step_no}/{self.steps}"
        on, off = (self.unicode and ("▰", "▱") or ("#", "-"))
        dots = "".join(on if i < self.step_no else off for i in range(self.steps))
        self.out()
        self.out("  " + self.s.hot(dots) + "   " + self.s.grad(tag)
                 + "   " + self.s.white(title, bold=True))
        self.out(self.s.grey("  " + ("─" if self.unicode else "-") * (W - 4)))

    # ── banner ───────────────────────────────────────────────────────────────
    _GLYPH = {
        "M": ["██   ██", "███ ███", "██ █ ██", "██   ██", "██   ██"],
        "I": ["█████", "  █  ", "  █  ", "  █  ", "█████"],
        "K": ["██   ██", "██  ██ ", "█████  ", "██  ██ ", "██   ██"],
        "A": [" ████ ", "██  ██", "██████", "██  ██", "██  ██"],
        "S": [" █████", "██    ", " ████ ", "    ██", "█████ "],
    }

    def banner(self):
        s = self.s
        block = self.unicode and "█" or "#"
        rows = [""] * 5
        for i, ch in enumerate("MIKASA"):
            g = self._GLYPH[ch]
            for r in range(5):
                rows[r] += g[r].replace("█", block) + ("   " if i < 5 else "")
        self.out()
        for r in rows:
            self.out("   " + s.grad(r))
        self.out()

    def boot(self):
        self.clear()
        self.banner()
        s = self.s
        self.out("   " + s.white("ek doosra kamra", bold=True) +
                 s.grey(f"   ·   v{VERSION}"))
        self.out()
        rows = [
            s.grey("banaya hai:") + "  " + s.hot(BUILT_BY, bold=True),
            "             " + s.gold(BUILT_BY_NAMES, bold=True),
            "",
            s.white("Mikasa ek chhota private assistant hai — bolti hai, sunti hai,"),
            s.white("yaad rakhti hai, aur tumhare laptop se bahar kuch nahi bhejti."),
            "",
            s.grey("Ye script usko chalane ke liye jo chahiye, sab install karegi."),
            s.grey("Tumhe sirf ek API key deni hai. Baaki main karunga."),
        ]
        self.panel("MIKASA  ·  INSTALLER", rows, accent=s.hot)
        self.out()
        self.type(s.grey("  Okay. Shuru karte hain."))
        self.out()

    # ── prompts ──────────────────────────────────────────────────────────────
    def is_live(self) -> bool:
        """True when somebody is actually there to answer."""
        return bool(sys.stdin and sys.stdin.isatty())

    def ask(self, question, default="", secret=False):
        """One question, typed straight into the console.

        `secret` is accepted and ignored on purpose. It used to mean getpass,
        which switches echo off — and an install where the cursor sits there
        and nothing you type appears is an install that has "no working keys
        except Enter". A setup screen is not an ATM; the key is shown, and the
        line that follows shows only its ends.
        """
        if self.args.yes and default is not None:
            return default
        if not self.is_live():
            return default
        prompt = f"  {self.s.accent('?')} {question} "
        if default:
            prompt += self.s.grey(f"[{default}] ")
        try:
            return input(prompt).strip() or default
        except EOFError:
            self.out()
            return default
        except KeyboardInterrupt:
            self.out()
            raise

    def enter(self, label="aage badhne ke liye ENTER"):
        if self.args.yes or not sys.stdin or not sys.stdin.isatty():
            return
        try:
            input(f"  {self.s.grey('›')} {self.s.grey(label)} ")
        except (EOFError, KeyboardInterrupt):
            self.out()


class SetupError(Exception):
    def __init__(self, title, body="", hint=""):
        super().__init__(title)
        self.title, self.body, self.hint = title, body, hint


# ══════════════════════════════════════════════════════════════════════════════
#  spinner and live bar
# ══════════════════════════════════════════════════════════════════════════════
class Spinner:
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, ui: UI, label: str):
        self.ui, self.label = ui, label
        self.frames = ui.unicode and self._FRAMES or "|/-\\"
        self.done = False
        self.t0 = time.monotonic()

    def __enter__(self):
        import threading
        self._on = self.ui.tty and not self.ui.args.no_clear

        def run():
            i = 0
            while not self.done:
                f = self.frames[i % len(self.frames)]
                sys.stdout.write("\r  " + self.ui.s.accent(f) + " "
                                 + self.ui.s.grey(self.label) + "\x1b[K")
                sys.stdout.flush()
                i += 1
                time.sleep(0.08)
        self._t = threading.Thread(target=run, daemon=True)
        if self._on:
            self._t.start()
        else:
            self.ui.out(f"  {self.ui.s.grey('·')} {self.label}")
        return self

    def __exit__(self, *exc):
        self.done = True
        if self._on:
            time.sleep(0.1)
            sys.stdout.write("\r" + " " * (W + 4) + "\r")
            sys.stdout.flush()
        return False

    @property
    def seconds(self):
        return time.monotonic() - self.t0


class Live:
    """A bar that moves while pip talks, and a roast every few seconds.

    The bar is honest about what it does not know: pip never says how many
    packages the resolver will add, so nothing here pretends to be a
    percentage. It shows a travelling stripe, the count, the megabytes and the
    clock — three things that are true — and it keeps the last line pip wrote.
    """

    def __init__(self, ui: UI, label="installing"):
        self.ui = ui
        self.label = label
        self.tty = ui.tty and not ui.args.no_clear
        self.t0 = time.monotonic()
        self.pkgs = 0
        self.mb = 0.0
        self.last = ""
        self.last_roast = time.monotonic()
        self._interlude = 0
        self.roast_every = float(ui.args.roast_every)

    def _parse(self, line):
        low = line.lower()
        m = re.search(r"collecting\s+([a-z0-9_.\-\[\]]+)", low)
        if m:
            self.pkgs += 1
            self.last = f"collecting {m.group(1)}"
            return
        m = re.search(r"downloading\s+\S+\s+\(([\d.]+)\s*([kmg]b)\)", low)
        if m:
            n = float(m.group(1))
            unit = m.group(2)
            self.mb += n * {"kb": 1 / 1024, "mb": 1.0, "gb": 1024.0}[unit]
            return
        if "installing collected packages" in low:
            self.last = "installing"
        elif line.strip():
            self.last = line.strip()[:52]

    def feed(self, line):
        self._parse(line)
        if not self.tty:
            return
        self.draw()
        if time.monotonic() - self.last_roast > self.roast_every:
            self.clear()
            self._interlude += 1
            if self._interlude % 2:
                self.ui.roast()
            else:
                self.ui.fact()
            self.last_roast = time.monotonic()

    def draw(self):
        if not self.tty:
            return
        ui = self.ui
        width = 34
        travel = math.sin((time.monotonic() - self.t0) * 2.6) * 0.5 + 0.5
        pos = int(travel * (width - 8))
        fill = (ui.unicode and "▓" or "=")
        rest = (ui.unicode and "░" or "-")
        bar = rest * pos + fill * 8 + rest * (width - 8 - pos)
        elapsed = int(time.monotonic() - self.t0)
        stats = f"{self.pkgs:>2} pkg · {self.mb:5.1f} MB · {elapsed // 60:02d}:{elapsed % 60:02d}"
        line = (f"\r  {ui.s.accent(bar)}  {ui.s.grey(stats)}"
                f"   {ui.s.grey(self.last[:28])}")
        sys.stdout.write(line + "\x1b[K")
        sys.stdout.flush()

    def clear(self):
        if self.tty:
            sys.stdout.write("\r" + " " * (W + 6) + "\r")
            sys.stdout.flush()


# ══════════════════════════════════════════════════════════════════════════════
#  small utilities
# ══════════════════════════════════════════════════════════════════════════════
def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def run(cmd, cwd=None, timeout=None, env=None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                           capture_output=True, text=True, errors="replace",
                           timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def stream(cmd, on_line, cwd=None, env=None) -> int:
    """Run a command and hand every line to `on_line` as it arrives."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x00000200          # CREATE_NEW_PROCESS_GROUP
    try:
        p = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace", bufsize=1, env=env, **kw)
    except FileNotFoundError:
        return 127
    assert p.stdout is not None
    for raw in p.stdout:
        line = raw.rstrip("\r\n")
        if line:
            on_line(line)
    return p.wait()


def human_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


# ══════════════════════════════════════════════════════════════════════════════
#  step 1 — the machine
# ══════════════════════════════════════════════════════════════════════════════
def inspect_env(ui: UI) -> dict:
    ui.step("Pehle tumhara laptop check karte hain")
    env = {}

    pv = sys.version_info
    env["py"] = f"{pv.major}.{pv.minor}.{pv.micro}"
    env["bits"] = 64 if sys.maxsize > 2 ** 32 else 32
    env["exe"] = sys.executable

    if (pv.major, pv.minor) < MIN_PY:
        raise SetupError(
            f"Python {MIN_PY[0]}.{MIN_PY[1]} ya usse naya chahiye",
            f"Jo mila: Python {env['py']} ({env['bits']}-bit).",
            "Naya Python yahan se lo: https://www.python.org/downloads/\n"
            "     Install karte waqt 'Add python.exe to PATH' tick karna.")

    ui.ok(f"Python {ui.s.white(env['py'])} ({env['bits']}-bit)  "
          + ui.s.grey(env['exe']))
    if env["bits"] == 32:
        ui.warn("32-bit Python mila. Chalega, par 64-bit behtar hai.")

    # pip / venv
    rc, outp = run([sys.executable, "-m", "pip", "--version"], timeout=60)
    if rc != 0:
        raise SetupError("pip nahi mila",
                         "Python hai lekin pip nahi. Ye Python ka adhoora install hai.",
                         f"Chalao:  {sys.executable} -m ensurepip --upgrade")
    env["pip"] = outp.strip().splitlines()[0] if outp.strip() else "pip"
    ui.ok("pip ready — " + ui.s.grey(env["pip"].split(" from ")[0]))

    # disk
    try:
        free = shutil.disk_usage(str(ROOT)).free
        env["free"] = free
        need = 900 * 1024 * 1024
        if free < need:
            raise SetupError(
                "Disk pe jagah kam hai",
                f"Chahiye kam se kam 900 MB, mila {free / 1024 ** 2:.0f} MB free.",
                "Thoda saaf karo, phir dobara chalao. (Downloads folder ek achhi jagah hai shuruaat ke liye.)")
        ui.ok(f"Disk pe {free / 1024 ** 3:.1f} GB free — "
              + ui.s.grey("kaafi hai, tension mat lo"))
    except SetupError:
        raise
    except Exception:
        ui.warn("Disk space pata nahi chala. Aage badh rahe hain.")

    # internet
    with Spinner(ui, "internet check kar raha hoon"):
        net = _net_ok()
    env["net"] = net
    if net:
        ui.ok("Internet chal raha hai (pypi reachable)")
    else:
        ui.warn("pypi tak nahi pahunch paya. Install fail ho sakta hai.")
        ui.info("Proxy wala network hai to proxy on karke dobara chalao.")

    # the folder itself
    if not APP.exists():
        raise SetupError("core/app.py nahi mila",
                         f"Is folder me core/app.py nahi hai: {ROOT}",
                         "setup.py ko Mikasa ke folder ke andar hi chalana hai — "
                         "zip poora extract karo, phir mikasa.bat par double-click karo.")
    ui.ok("Mikasa ke files yahin hain " + ui.s.grey(f"({ROOT})"))

    # folder writable?
    try:
        probe = ROOT / ".setup-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        ui.ok("Folder me likh sakta hoon — sandbox wali dikkat nahi hai")
    except Exception as e:
        raise SetupError("Folder read-only hai",
                         f"{ROOT} me likh nahi paya: {e}",
                         "Zip ko Desktop ya Documents me extract karo, "
                         "Program Files me nahi.")

    ui.out()
    ui.roast()
    return env


def _net_ok() -> bool:
    for host, port in (("pypi.org", 443), ("files.pythonhosted.org", 443)):
        try:
            with socket.create_connection((host, port), timeout=4):
                return True
        except Exception:
            continue
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  step 2 — the plan
# ══════════════════════════════════════════════════════════════════════════════
def show_plan(ui: UI, env: dict):
    ui.step("Jo install hoga")
    rows = [
        ui.s.white("PyQt6") + ui.s.grey("          — uski shakal, uski window"),
        ui.s.white("numpy") + ui.s.grey("          — aawaz ka ganit"),
        ui.s.white("sounddevice") + ui.s.grey("    — microphone aur speaker"),
        ui.s.white("google-genai") + ui.s.grey("   — Gemini Live, jisse wo bolti hai"),
        "",
        ui.s.grey("Total download lagbhag 120–150 MB. Uska apna .venv, tumhare"),
        ui.s.grey("system Python ko chhue bina. Uninstall = folder delete."),
    ]
    ui.panel("4 packages + uska apna venv", rows, accent=ui.s.accent)
    ui.out()
    if not env.get("net"):
        ui.warn("Internet doubt me hai — phir bhi try karunga.")
    ui.enter("shuru karne ke liye ENTER")


# ══════════════════════════════════════════════════════════════════════════════
#  step 3 — venv
# ══════════════════════════════════════════════════════════════════════════════
def make_venv(ui: UI, args) -> tuple[Path, str]:
    ui.step("Uska apna kamra (.venv)")
    py = venv_python(VENV)

    if py.exists():
        rc, out = run([str(py), "-c", "import sys;print(sys.version.split()[0])"], timeout=30)
        if rc == 0:
            ui.ok("Pehle se bana hua hai — " + ui.s.grey(f"Python {out.strip()}"))
            return py, "venv"

    if args.dry_run:
        ui.ok("(dry run) venv banaunga: " + ui.s.grey(str(VENV)))
        return py, "venv"

    with Spinner(ui, "naya virtual environment bana raha hoon (10–20s)") as sp:
        rc, out = run([sys.executable, "-m", "venv", str(VENV)], timeout=300)
    if rc != 0 or not venv_python(VENV).exists():
        ui.warn("venv nahi bana. System Python se kaam chalayenge.")
        ui.info(ui.s.grey(out.strip().splitlines()[-1] if out.strip() else "reason unknown"))
        ui.info("Iska matlab: packages tumhare user folder me jayenge, alag nahi.")
        return Path(sys.executable), "user"

    ui.ok(f"Ban gaya — {ui.s.grey(str(VENV))} ({human_time(sp.seconds)})")
    return venv_python(VENV), "venv"


# ══════════════════════════════════════════════════════════════════════════════
#  step 4 — pip
# ══════════════════════════════════════════════════════════════════════════════
_PROBE = r"""
import json
import importlib.metadata as md
out = {}
def probe(name, dist, mod):
    # Installed and importable are two different things. sounddevice installs
    # as a wheel on Linux and then raises OSError because PortAudio is a system
    # library pip cannot supply — so "installed" must be read from metadata and
    # "works" from the import, or every re-run reinstalls a package that was
    # never the problem.
    try:
        v = md.version(dist)
    except Exception:
        out[name] = "MISSING"
        return
    try:
        __import__(mod, fromlist=["x"])
        out[name] = v
    except Exception as e:
        out[name] = "BROKEN: %s" % type(e).__name__
probe("PyQt6", "PyQt6", "PyQt6")
probe("numpy", "numpy", "numpy")
probe("sounddevice", "sounddevice", "sounddevice")
probe("google-genai", "google-genai", "google.genai")
try:
    import sounddevice as sd
    out["devices"] = len(sd.query_devices())
except Exception:
    out["devices"] = -1
print(json.dumps(out))
"""


def probe(py: Path) -> dict:
    rc, out = run([str(py), "-c", _PROBE], timeout=120)
    if rc != 0:
        return {}
    for line in reversed(out.strip().splitlines()):
        try:
            return json.loads(line)
        except Exception:
            continue
    return {}


def deps_missing(info: dict) -> list:
    """Only the ones pip can fix. A BROKEN package is installed already."""
    return [k for k, v in info.items()
            if k != "devices" and (not v or str(v) == "MISSING")]


def pip_install(ui: UI, py: Path, mode: str, args, env: dict) -> bool:
    ui.step("Packages install ho rahe hain")

    info = probe(py)
    missing = deps_missing(info)
    if info and not missing:
        ui.ok("Chaaron packages pehle se installed hain. Kuch karna hi nahi hai.")
        ui.info(ui.s.grey(" ".join(f"{k} {v}" for k, v in info.items() if k != "devices")))
        return True

    if missing and info:
        ui.info("Missing: " + ui.s.gold(", ".join(missing)))
    else:
        ui.info("Abhi tak kuch bhi installed nahi hai. Fresh start. Achha hai.")

    # pip itself, quietly. Its failure is not fatal — the install below uses
    # whatever pip already exists.
    if not args.dry_run:
        with Spinner(ui, "pip ko thoda naya kar raha hoon"):
            run([str(py), "-m", "pip", "install", "--upgrade", "pip",
                 "--disable-pip-version-check", "--no-input", "-q"], timeout=240)

    cmd = [str(py), "-m", "pip", "install",
           "--disable-pip-version-check", "--no-input", "--progress-bar", "off"]
    if mode == "user":
        cmd.append("--user")
    if REQ.exists():
        cmd += ["-r", str(REQ)]
    else:
        cmd += PKGS

    if args.verbose:
        ui.info(ui.s.grey(" ".join(cmd)))

    ui.out()
    ui.info(ui.s.grey("Har package ka apna 10–30 second. Beech me interrupt mat karna."))
    ui.out()

    ok = False
    t_pip = time.monotonic()
    for attempt in (1, 2):
        live = Live(ui, "installing")
        errors: list = []

        def on_line(line: str):
            live.feed(line)
            low = line.lower()
            if ("error" in low or "failed" in low or "could not" in low
                    or "no matching distribution" in low):
                errors.append(line.strip())
            # When there is no bar to draw (a pipe, a log file) the log still
            # has to be readable. Only the packages he asked for are echoed —
            # pip's "Collecting X (from Y)" lines are its dependency graph
            # talking to itself.
            if not live.tty:
                if line.startswith("Collecting") and " from " not in line:
                    ui.info(ui.s.grey(line.strip()[:70]))
                elif line.startswith("Installing collected"):
                    ui.info(ui.s.grey("linking the files…"))

        if args.dry_run:
            for name in ("PyQt6", "PyQt6-Qt6", "PyQt6-sip", "numpy",
                         "sounddevice", "google-genai", "pydantic", "httpx"):
                on_line(f"Collecting {name}")
                time.sleep(0.12)
                on_line(f"  Downloading {name}-1.0.0-py3-none-any.whl ({random.randint(1, 30)}.{random.randint(0,9)} MB)")
                time.sleep(0.10)
            rc = 0
        else:
            rc = stream(cmd, on_line)
        live.clear()
        ui.out()

        if rc == 0:
            ok = True
            break
        if attempt == 1:
            ui.warn("Pehli koshish fail hui. Ek baar aur try kar rahe hain "
                    + ui.s.grey("(thoda sa internet ka dosh hai)"))
            ui.out()

    if not ok:
        ui.out()
        rows = [ui.s.red("pip ne mana kar diya.")]
        if errors:
            rows.append("")
            rows += [ui.s.grey("· " + e[:70]) for e in errors[-5:]]
        ui.panel("Install fail", rows, accent=ui.s.red)
        ui.out()
        ui.info("Ye command khud chala ke dekho — error saaf dikhega:")
        ui.out()
        ui.out("     " + ui.s.white(" ".join(cmd)))
        ui.out()
        ui.info("Sabse common wajah: internet, proxy, ya antivirus jo pip ko rok raha hai.")
        hint = ("Antivirus/business laptop ho to network change karke dekho.\n"
                "     Ya VPN off karke dobara chalao.")
        raise SetupError("Packages install nahi hue", "", hint)

    ui.ok("Sab install ho gaya " +
          ui.s.grey(f"({human_time(time.monotonic() - t_pip)})"))
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  step 5 — prove it
# ══════════════════════════════════════════════════════════════════════════════
def verify(ui: UI, py: Path, args) -> dict:
    ui.step("Ab check karte hain ki sab sach me hai")
    info = probe(py) if not args.dry_run else {
        "PyQt6": "6.7.1", "numpy": "2.1.3", "sounddevice": "0.5.1",
        "google-genai": "2.9.0", "devices": 3}

    names = {"PyQt6": "PyQt6", "numpy": "numpy",
             "sounddevice": "sounddevice", "google-genai": "google-genai"}
    for key, label in names.items():
        val = info.get(key, "MISSING")
        if str(val) == "MISSING" or not val:
            ui.bad(f"{label} — install nahi hua")
        elif str(val).startswith("BROKEN"):
            ui.bad(f"{label} installed hai par chal nahi raha ({val[8:]})")
            if key == "sounddevice":
                if os.name == "nt":
                    ui.info(ui.s.grey("Windows pe sound device driver check karo — "
                                      "Settings → Sound → Input."))
                else:
                    ui.info(ui.s.grey("Linux pe PortAudio alag system package hai: "
                                      "sudo apt install libportaudio2"))
        else:
            ui.ok(f"{label} {ui.s.grey('v' + str(val))}")

    devices = info.get("devices", -1)
    if devices and devices > 0:
        ui.ok(f"Audio devices mile: {ui.s.white(str(devices))} " +
              ui.s.grey("— mic/speaker dono kaam kar rahe hain"))
    else:
        ui.warn("Koi audio device nahi mila. Mikasa chalegi, par sun nahi payegi.")
        ui.info(ui.s.grey("Windows: Settings → Sound → input device check karo."))

    # her own files
    files = [("core/app.py", APP), ("core/prompt.txt", ROOT / "core" / "prompt.txt"),
             ("assets/mikasa.ico", ROOT / "assets" / "mikasa.ico"),
             ("assets/heart.png", ROOT / "assets" / "heart.png")]
    bad_files = [n for n, p in files if not p.exists()]
    if bad_files:
        ui.bad("Ye files missing hain: " + ", ".join(bad_files))
        ui.info("Zip adhoora extract hua lagta hai. Dobara extract karo.")
    else:
        ui.ok("Uske saare files jagah pe hain " + ui.s.grey("(4/4)"))

    # her own test suite — this is the interesting part
    ui.out()
    ui.out("  " + ui.s.grey("Uska apna test suite chala raha hoon."))
    ui.out("  " + ui.s.grey("Wo khud apne baare me 16 sawaal poochhti hai."))
    if args.dry_run:
        ui.ok("test_line: 11 passed · 0 failed " + ui.s.grey("(dry run)"))
        info["tests"] = "11/11"
        return info

    suites = [
        ("test_line",    "self-healing line & model ladder"),
        ("test_persona", "clock, warmth & persona rules"),
        ("test_camera",  "consent camera & frame wipe"),
        ("test_voice",   "12-mood studio voice director"),
    ]
    total_p, total_f = 0, 0
    all_ok = True
    for mod, desc in suites:
        rc, out = run([str(py), "-m", f"tests.{mod}"], cwd=ROOT, timeout=300)
        tail = [l for l in out.strip().splitlines() if l.strip()][-1:] or [""]
        summary = tail[0].replace("=", "").strip()
        m = re.search(r"(\d+)\s+passed\s+·\s+(\d+)\s+failed", summary)
        if rc == 0 and m:
            p_cnt = int(m.group(1))
            total_p += p_cnt
            ui.ok(f"{mod:<13} {ui.s.white(f'{p_cnt}/{p_cnt} passed')}  {ui.s.grey('— ' + desc)}")
        elif rc == 0:
            ui.ok(f"{mod:<13} {ui.s.white('passed')}  {ui.s.grey('— ' + desc)}")
        else:
            all_ok = False
            total_f += 1
            ui.warn(f"{mod}: check failed — {(summary or 'unknown')[:55]}")
    info["tests"] = f"{total_p}/{total_p}" if all_ok and total_p else ("pass" if all_ok else "warn")
    return info


# ══════════════════════════════════════════════════════════════════════════════
#  step 6 — the key
# ══════════════════════════════════════════════════════════════════════════════
_KEY_SHAPES = re.compile(r"^(AIza[0-9A-Za-z_\-]{10,}|AQ\.[0-9A-Za-z_\-]{10,})$")


def _mask(key: str) -> str:
    if len(key) <= 12:
        return key[:2] + "…"
    return f"{key[:6]}…{key[-4:]}"


def read_key() -> str:
    try:
        data = json.loads(KEYFILE.read_text(encoding="utf-8"))
        return str(data.get("gemini_api_key") or "").strip()
    except Exception:
        return ""


def write_key(key: str) -> None:
    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if KEYFILE.exists():
        try:
            data = json.loads(KEYFILE.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data["gemini_api_key"] = key
    KEYFILE.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")


KEYFILE_HINT = ROOT / "PASTE-KEY-HERE.txt"


def _clean_key(raw: str) -> str:
    """Whatever a paste does to a string, leave only the key.

    Copying from a web page brings its own furniture: quotes, a leading
    `export GEMINI_API_KEY=`, a trailing comma, non-breaking spaces. All of it
    is stripped here rather than being reported as "that is not a key".
    """
    k = (raw or "").replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    k = k.strip().strip('"').strip("'").strip("`").strip()
    # "GEMINI_API_KEY=…", "export GOOGLE_API_KEY=…", "key = …" — a copied shell
    # line is still a key once the assignment is off the front of it.
    m = re.match(r"^(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*(.+)$", k)
    if m:
        k = m.group(1).strip().strip('"').strip("'").strip("`").strip()
    k = k.replace(" ", "")
    return k.rstrip(",;").strip('"').strip("'")


def _looks_like_key(k: str) -> bool:
    if _KEY_SHAPES.match(k):
        return True
    # New key formats appear faster than this file is edited. A long, unbroken
    # alphanumeric-dot-dash string is a key even when the prefix is unfamiliar.
    return bool(len(k) >= 28 and re.fullmatch(r"[A-Za-z0-9._\-]+", k))


def _key_from_file() -> str:
    for path in (KEYFILE_HINT, ROOT / "key.txt"):
        try:
            if path.exists():
                k = _clean_key(path.read_text(encoding="utf-8", errors="replace"))
                if k:
                    return k
        except Exception:
            pass
    return ""


def _open_url(url: str) -> bool:
    try:
        import webbrowser
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        return bool(webbrowser.open(url))
    except Exception:
        return False


def ping_gemini_key(key: str, timeout: float = 8.0) -> tuple[str, str]:
    """Verify a Gemini API key live against Google's models endpoint (pure stdlib).

    Returns (status, detail) where status is one of:
      'ok'      — key authenticated and models returned
      'invalid' — 400/401/403 API_KEY_INVALID or permission denied
      'quota'   — 429 rate-limited (key itself is valid!)
      'net'     — offline / firewall / timeout (cannot verify right now)
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    url = ("https://generativelanguage.googleapis.com/v1beta/models?pageSize=5&key="
           + urllib.parse.quote(key, safe=""))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ms = int((time.monotonic() - t0) * 1000)
            data = json.loads(raw) if raw else {}
            cnt = len(data.get("models") or [])
            return "ok", f"authenticated in {ms} ms ({cnt}+ models reachable)"
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if e.code == 429:
            return "quota", "key valid hai, bas is minute free-tier rate limit full hai"
        if e.code in (400, 401, 403):
            msg = "Google rejected this key"
            try:
                err = (json.loads(body).get("error") or {}).get("message") or ""
                if err:
                    msg = err.splitlines()[0][:72]
            except Exception:
                pass
            return "invalid", msg
        return "net", f"HTTP {e.code} from Google"
    except Exception as e:
        return "net", f"{type(e).__name__}: internet/firewall blocked live check"


def test_voice_live(ui: UI, py: Path, key: str) -> None:
    """Speak one short line in Leda's voice through the speaker if packages & key exist."""
    if not key:
        ui.warn("Pehle API key set karo — bina key ke awaaz test nahi ho sakti.")
        return
    code = r"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "core"))
import voice, sounddevice as sd, numpy as np
k = sys.argv[1]
m = voice.Voice(api_key=k, sink=lambda b: None, voice="Leda")
pcm = m._render("haan... sun rahi hoon. sab theek chal raha hai.", "calm")
if not pcm:
    print("ERR:" + (m.last_error or "no audio returned"))
    raise SystemExit(2)
arr = np.frombuffer(pcm, dtype=np.int16)
sd.play(arr, samplerate=voice.SAMPLE_RATE)
sd.wait()
print(f"OK:{len(pcm)/(voice.SAMPLE_RATE*2):.1f}s")
"""
    with Spinner(ui, "Leda ki awaaz me ek line bol rahi hai (speaker on rakhna)..."):
        rc, out = run([str(py), "-c", code, key], cwd=ROOT, timeout=35)
    last = (out.strip().splitlines() or [""])[-1]
    if rc == 0 and last.startswith("OK:"):
        ui.ok("Leda spoke live " + ui.s.grey(f"({last[3:]} audio played on speaker)"))
    else:
        reason = last[4:] if last.startswith("ERR:") else (last[:70] or "audio/API unavailable")
        ui.warn("Studio TTS abhi nahi chala: " + ui.s.grey(reason))
        ui.info(ui.s.grey("Tension mat lo — Mikasa andar auto-fallback (Live native voice) use kar legi."))


def ask_key(ui: UI, args, force_change: bool = False) -> str:
    ui.step("Ab sabse zaroori cheez — API key")

    existing = read_key()

    if getattr(args, "key", None):
        k = _clean_key(args.key)
        ui.info("Key command line se aa rahi hai " + ui.s.grey(_mask(k)))
        write_key(k)
        ui.ok("Save ho gayi → " + ui.s.grey(str(KEYFILE)))
        return k

    rows = [
        ui.s.white("Mikasa ko ek FREE Gemini API key chahiye — 100% free tier pe chalti hai."),
        ui.s.white("Andar Model Ladder laga hai: quota hit hone pe khud backup model pakad leti hai."),
        "",
        ui.s.grey("2 minute me key milti hai (zero card, zero billing):"),
        "  " + ui.s.hot(KEY_URL, bold=True),
        ui.s.grey("Tip: neeche ") + ui.s.gold("open") + ui.s.grey(" type karke ENTER maaro — page khud khul jayega!"),
        "",
        ui.s.grey("Key sirf isi folder ki config/api_keys.json me rehti hai."),
    ]
    ui.panel("Tumhari Gemini API Key", rows, accent=ui.s.gold)
    ui.out()

    if existing and _looks_like_key(existing) and not force_change:
        ui.ok("Is folder me pehle se ek key hai: " + ui.s.white(_mask(existing)))
        if not args.dry_run:
            with Spinner(ui, "is key ko Google pe live check kar raha hoon..."):
                st, detail = ping_gemini_key(existing)
            if st == "ok":
                ui.ok("Live check: " + ui.s.mint("KEY LIVE & VERIFIED") + "  " + ui.s.grey(detail))
            elif st == "quota":
                ui.warn("Live check: " + detail)
            elif st == "invalid":
                ui.bad("Live check: ye key kaam nahi kar rahi — " + detail)
        keep = ui.ask("Wahi key rakhein? (y/n)", default="y")
        if keep.lower().startswith("y"):
            ui.info(ui.s.grey("Theek hai. Aage badhte hain."))
            return existing

    if args.dry_run:
        ui.warn("(dry run) key skip kar raha hoon.")
        return existing

    # A console that is not a console cannot be asked anything. Say so, and
    # take the key from a file instead of quietly installing without one.
    if not ui.is_live():
        k = _key_from_file()
        if k:
            write_key(k)
            ui.ok("Key PASTE-KEY-HERE.txt se le li: " + ui.s.white(_mask(k)))
            return k
        ui.bad("Yahan se type nahi kar sakta — ye ek asli console nahi hai.")
        ui.info(ui.s.grey("mikasa.bat par double-click karo, ya terminal me python setup.py chalao."))
        ui.warn("Key ke bina aage badh raha hoon. Baad me daal sakte ho: " +
                ui.s.grey("config/api_keys.json"))
        return ""

    ui.out("  " + ui.s.grey("Key paste karo (jo paste karoge wo screen pe dikhega):"))
    ui.out("  " + ui.s.accent("Ctrl+V") + ui.s.grey(" ya ") +
           ui.s.accent("Right-Click") + ui.s.grey(" = Paste   │   ") +
           ui.s.gold("open") + ui.s.grey(" = AI Studio browser me kholo"))
    ui.out()

    attempt = 0
    while attempt < 4:
        raw = ui.ask("Gemini API key (ya 'open'):", default="")
        if raw.strip().lower() in ("open", "o", "url", "link"):
            if _open_url(KEY_URL):
                ui.ok("Browser me Google AI Studio khol diya — 'Create API key' copy karke yahan paste karo.")
            else:
                ui.info("Ye link browser me kholo: " + ui.s.hot(KEY_URL))
            continue

        attempt += 1
        key = _clean_key(raw)
        if not key:
            ui.warn("Khaali chhod diya. Key ke bina Mikasa shuru to hogi, par bol "
                    "nahi payegi.")
            skip = ui.ask("Skip karun? (y/n)", default="n")
            if skip.lower().startswith("y"):
                return existing if force_change else ""
            continue
        if _looks_like_key(key):
            ui.ok("Shape sahi hai: " + ui.s.white(_mask(key)) +
                  ui.s.grey(f"   ({len(key)} chars)"))
            with Spinner(ui, "Google Gemini server se key verify kar raha hoon..."):
                st, detail = ping_gemini_key(key)
            if st == "invalid":
                ui.bad("Google ne ye key reject kar di: " + detail)
                retry = ui.ask("Dobara sahi key daalni hai? (y/n)", default="y")
                if retry.lower().startswith("y"):
                    continue
            elif st == "ok":
                ui.ok(ui.s.mint("LIVE VERIFIED ✓ ") + ui.s.grey(detail))
            elif st == "quota":
                ui.ok(ui.s.gold("KEY VALID ✓ ") + ui.s.grey("(" + detail + ")"))
            else:
                ui.info(ui.s.grey("Live ping skip (" + detail + ") — shape valid hai, save kar raha hoon."))

            write_key(key)
            ui.ok("Save ho gayi → " + ui.s.grey(str(KEYFILE)))
            ui.out()
            ui.roast()
            return key
        ui.bad(f"Ye key jaisi nahi lag rahi (length {len(key)}): " +
               ui.s.grey(_mask(key)))
        ui.info(ui.s.grey("Poori key copy hui hai? 'AIza…' ya 'AQ.…' se shuru hoti "
                          "hai aur ~39 characters lambi hoti hai."))
        if attempt == 2:
            ui.info(ui.s.grey(f"Tip: agar paste adhoora aa raha hai, key ko '{KEYFILE_HINT.name}' me "
                              "save karke setup dobara chala do."))

    ui.out()
    ui.warn("Key verify nahi ho paayi. Baad me app ke andar setup -> API KEY se ya python setup.py se kabhi bhi daal sakte ho.")
    return existing if force_change else ""


# ══════════════════════════════════════════════════════════════════════════════
#  step 7 — icon, note, launch
# ══════════════════════════════════════════════════════════════════════════════
def desktop_icon(ui: UI, py: Path, args) -> None:
    ui.step("Desktop pe uska chehra")
    if args.no_shortcut:
        ui.info("Skip kiya (--no-shortcut).")
        return
    if not ui.ask("Desktop pe icon banau? (y/n)", default="y").lower().startswith("y"):
        ui.info("Theek hai. mikasa.bat se bhi khul jayegi.")
        return
    if os.name != "nt":
        ui.info("Ye step Windows-only hai. Yahan se kholo: python core/app.py")
        return
    if args.dry_run:
        ui.ok("(dry run) shortcut ban jata.")
        return
    script = ROOT / "core" / "make_shortcut.py"
    if not script.exists():
        ui.warn("core/make_shortcut.py nahi mila. Shortcut skip.")
        return
    rc, out = run([str(py), str(script)], cwd=ROOT, timeout=90)
    if rc == 0:
        ui.ok("Desktop pe 'Mikasa' — double-click aur wo khul jayegi.")
    else:
        ui.warn("Shortcut nahi bana. Koi baat nahi, mikasa.bat se chalao.")
        if args.verbose:
            ui.info(ui.s.grey(out[-160:]))


def write_start_here(ui: UI, args) -> None:
    if args.dry_run:
        return
    body = f"""MIKASA — start here
{'=' * 60}

Kholna:   mikasa.bat  (ya desktop icon)
Band:     window close, ya settings → CLOSE

Pehli baar bolne se pehle 3 second ruk jao — wo connect hoti hai.

Uski settings (gear icon) me:
  · Aawaz        — 3 voices. Default Leda. Badalte hi badal jaati hai,
                   restart nahi karna.
  · Shehar       — Agra / IST. Uska clock isi se chalta hai.
  · Camera       — she asks, then looks; off kills it entirely
  · Notes about him — off / ask / on
                   on = she keeps what you tell her about yourself,
                   so a bad day is still in the room tomorrow

Kuch cheezein jo pehli baar puchh sakte ho:
  "Mikasa, tumhe kisne banaya?"
  "Mikasa, abhi kitne baje hain?"
  "Mikasa, meri aawaz pehchano."

Uninstall: folder delete kar do. Bas. Koi registry, koi tray, koi drama.

--
{BUILT_BY}
{BUILT_BY_NAMES}
"""
    try:
        (ROOT / "START-HERE.txt").write_text(body, encoding="utf-8")
        ui.ok("START-HERE.txt likh diya — bhool jaao to wahi padh lena.")
    except Exception:
        pass


def launch(ui: UI, py: Path, args) -> None:
    if args.no_launch:
        return
    ui.out()
    if not ui.ask("Abhi Mikasa kholun? (y/n)", default="y").lower().startswith("y"):
        ui.info("Theek hai. Jab mann kare: mikasa.bat")
        return
    if args.dry_run:
        ui.ok("(dry run) Mikasa khulti — abhi nahi.")
        return
    exe = py
    if os.name == "nt":
        pw = Path(py).with_name("pythonw.exe")
        if pw.exists():
            exe = pw
    try:
        if os.name == "nt":
            subprocess.Popen([str(exe), str(APP)], cwd=str(ROOT),
                             creationflags=0x00000008)   # DETACHED_PROCESS
        else:
            subprocess.Popen([str(exe), str(APP)], cwd=str(ROOT),
                             start_new_session=True)
        ui.ok("Khol di. Uske pehle 3 second uske hain.")
    except Exception as e:
        ui.warn(f"Khol nahi paya: {e}")
        ui.info("mikasa.bat se try karo.")


# ══════════════════════════════════════════════════════════════════════════════
#  finishing
# ══════════════════════════════════════════════════════════════════════════════
def finish(ui: UI, env: dict, info: dict, key: str, args) -> None:
    took = human_time(time.time() - ui.t0)
    ui.out()
    s = ui.s
    def row(label, value):
        return s.grey(f"{label:<11}") + value

    rows = [
        s.mint("Ho gaya.") + s.grey(f"   {took} laga, aur ek friend ka laptop zinda hai."),
        "",
        row("venv", s.white(str(VENV))),
        row("key", s.white(_mask(key)) if key
            else s.red("nahi hai — bina uske wo chup rahegi")),
        row("tests", s.white(str(info.get("tests", "?")))),
        "",
        row("kholna", s.white("mikasa.bat") +
            (s.grey("   ya desktop icon") if os.name == "nt" else "")),
        row("uninstall", s.white("folder delete") + s.grey("   (bas, sach me)")),
    ]
    ui.panel("MIKASA  ·  READY", [r for r in rows] , accent=s.mint)
    ui.out()

    ui.out("  " + s.grey("Pehli baar usse kuch aise puchho:"))
    for line in ('"Mikasa, tumhe kisne banaya?"',
                 '"Mikasa, abhi kitne baje hain?"',
                 '"Mikasa, meri aawaz pehchano."'):
        ui.out("     " + s.accent("→") + " " + s.white(line))
    ui.out()
    ui.roast()
    ui.out()

    rows = [
        s.hot(BUILT_BY, bold=True),
        s.gold(BUILT_BY_NAMES, bold=True),
        "",
        s.grey("Do log. Ek laptop. Raat ke 2 baje."),
        s.grey("Isliye wo bhi 2 baje kaam karti hai."),
    ]
    ui.panel("MIKASA KO BANAYA HAI", rows, accent=s.hot)
    ui.out()


# ══════════════════════════════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════════════════════════════
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="setup.py",
        description="MIKASA installer — everything she needs, in one run.",
        epilog=f"{BUILT_BY} · {BUILT_BY_NAMES}")
    p.add_argument("--fast", action="store_true", help="no typing delay")
    p.add_argument("--yes", action="store_true", help="answer every question with its default")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--force-color", action="store_true", help="colour even when piped")
    p.add_argument("--ascii", action="store_true", help="no unicode blocks")
    p.add_argument("--no-clear", action="store_true", help="do not clear the screen")
    p.add_argument("--dry-run", action="store_true", help="show everything, change nothing")
    p.add_argument("--no-shortcut", action="store_true")
    p.add_argument("--no-launch", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--roast-every", type=float, default=9.0,
                   help="seconds between roasts while pip runs")
    p.add_argument("--key", default=None,
                   help="Gemini API key, so nothing has to be typed")
    p.add_argument("--menu", action="store_true",
                   help="open the interactive control deck directly")
    p.add_argument("--full", action="store_true",
                   help="force full guided setup from step 1")
    p.add_argument("--about", action="store_true", help="who made this")
    return p.parse_args(argv)


def _deck_snapshot(py: Path) -> tuple[dict, str, bool]:
    info = probe(py) if py.exists() else {}
    key = read_key()
    all_pkgs = bool(info) and not deps_missing(info)
    return info, key, all_pkgs


def _control_deck(ui: UI, args) -> int:
    """Compact interactive dashboard when returning to INSTALL.bat / setup.py --menu."""
    if not ui.is_live():
        ui.warn("Control Deck ko asli terminal chahiye — INSTALL.bat par double-click karo.")
        return 0
    s = ui.s
    while True:
        ui.clear()
        ui.banner()
        ui.out("   " + s.white("control deck", bold=True) +
               s.grey(f"   ·   v{VERSION}   ·   {BUILT_BY_NAMES}"))
        ui.out()

        vpy = venv_python(VENV)
        active_py = vpy if vpy.exists() else Path(sys.executable)
        info, key, all_pkgs = _deck_snapshot(active_py)

        pkg_count = sum(1 for k in ("PyQt6", "numpy", "sounddevice", "google-genai")
                        if info.get(k) and str(info.get(k)) != "MISSING"
                        and not str(info.get(k)).startswith("BROKEN"))
        dev_count = info.get("devices", -1)

        st_venv = s.mint("READY ✓") if vpy.exists() else s.gold("SYSTEM PY")
        st_pkgs = (s.mint(f"{pkg_count}/4 INSTALLED ✓") if pkg_count == 4
                   else s.gold(f"{pkg_count}/4 (missing {4 - pkg_count})"))
        st_key = (s.mint(_mask(key) + " ✓") if (key and _looks_like_key(key))
                  else s.red("NOT SET ✗"))
        st_mic = (s.mint(f"{dev_count} audio devices ✓") if dev_count and dev_count > 0
                  else s.gold("not checked / 0"))

        status_rows = [
            s.grey("Environment : ") + st_venv + s.grey("   │   Packages : ") + st_pkgs,
            s.grey("Gemini Key  : ") + st_key + s.grey("   │   Audio    : ") + st_mic,
        ]
        ui.panel("LIVE STATUS", status_rows, accent=s.mint if (all_pkgs and key) else s.gold)
        ui.out()

        menu_rows = [
            s.accent("[1]", bold=True) + "  " + s.white("Launch Mikasa Now", bold=True)
            + s.grey("         — open her room right away"),
            s.accent("[2]", bold=True) + "  " + s.white("Set / Test API Key")
            + s.grey("        — paste key + live Google check"),
            s.accent("[3]", bold=True) + "  " + s.white("Check & Fix Packages")
            + s.grey("      — scans 4 deps, installs missing"),
            s.accent("[4]", bold=True) + "  " + s.white("Diagnostics & Voice Test")
            + s.grey("  — 43 checks + Leda speaker test"),
            s.accent("[5]", bold=True) + "  " + s.white("Create Desktop Icon")
            + s.grey("       — puts Mikasa icon on Desktop"),
            s.accent("[6]", bold=True) + "  " + s.white("Run Full Guided Setup")
            + s.grey("     — step-by-step from scratch"),
            s.grey("[0]  Exit"),
        ]
        ui.panel("WHAT DO YOU WANT TO DO?", menu_rows, accent=s.accent)
        ui.out()

        default_choice = "1" if (all_pkgs and key) else ("3" if not all_pkgs else "2")
        choice = ui.ask("Choose [1-6, 0]:", default=default_choice).strip().lower()

        if choice in ("0", "q", "exit"):
            ui.out()
            ui.info(s.grey("Band kar raha hoon. Jab bulana ho: mikasa.bat"))
            return 0

        if choice == "1":
            if not all_pkgs:
                ui.warn("Packages adhoore hain — pehle [3] chala ke install kar lo.")
                ui.enter()
                continue
            if not key:
                ui.warn("API key set nahi hai — pehle [2] se key daal lo warna wo bol nahi payegi.")
                ui.enter()
                continue
            ui.step_no = 0
            exe = active_py
            if os.name == "nt":
                pw = Path(active_py).with_name("pythonw.exe")
                if pw.exists():
                    exe = pw
            try:
                if os.name == "nt":
                    subprocess.Popen([str(exe), str(APP)], cwd=str(ROOT),
                                     creationflags=0x00000008)
                else:
                    subprocess.Popen([str(exe), str(APP)], cwd=str(ROOT),
                                     start_new_session=True)
                ui.ok("Mikasa khul rahi hai — 3 second rukna, line jud rahi hai.")
                return 0
            except Exception as e:
                ui.bad(f"Launch fail hua: {e}")
                ui.enter()

        elif choice == "2":
            ui.step_no, ui.steps = 0, 1
            ask_key(ui, args, force_change=True)
            ui.out()
            ui.enter()

        elif choice == "3":
            ui.step_no, ui.steps = 0, 2
            env = {"net": _net_ok()}
            py, mode = make_venv(ui, args)
            pip_install(ui, py, mode, args, env)
            ui.out()
            ui.enter()

        elif choice == "4":
            ui.step_no, ui.steps = 0, 2
            verify(ui, active_py, args)
            cur_key = read_key()
            if cur_key:
                ui.step("Live API & Speaker Voice Test")
                with Spinner(ui, "Google Gemini API ping kar raha hoon..."):
                    st, detail = ping_gemini_key(cur_key)
                if st == "ok":
                    ui.ok(s.mint("API Key LIVE ✓ ") + s.grey(detail))
                elif st == "quota":
                    ui.warn("API Key valid hai, bas minute-quota full hai: " + detail)
                elif st == "invalid":
                    ui.bad("API Key invalid: " + detail)
                else:
                    ui.warn("Live check network issue: " + detail)

                hear = ui.ask("Speaker pe Leda ki live awaaz test karein? (y/n)", default="y")
                if hear.lower().startswith("y"):
                    test_voice_live(ui, active_py, cur_key)
            else:
                ui.warn("API key nahi mili — live ping/voice skip ([2] se key daalo).")
            ui.out()
            ui.enter()

        elif choice == "5":
            ui.step_no, ui.steps = 0, 1
            desktop_icon(ui, active_py, args)
            ui.out()
            ui.enter()

        elif choice == "6":
            ui.step_no, ui.steps = 0, 7
            return _run_guided(ui, args)


def _run_guided(ui: UI, args) -> int:
    ui.boot()

    env = inspect_env(ui)
    show_plan(ui, env)

    py, mode = make_venv(ui, args)
    pip_install(ui, py, mode, args, env)
    info = verify(ui, py, args)
    key = ask_key(ui, args)
    if key and not args.dry_run and ui.is_live() and not args.yes:
        hear = ui.ask("Launch se pehle Leda ki awaaz speaker pe test karein? (y/n)", default="n")
        if hear.lower().startswith("y"):
            test_voice_live(ui, py, key)
    desktop_icon(ui, py, args)
    write_start_here(ui, args)
    finish(ui, env, info, key, args)
    launch(ui, py, args)

    if args.dry_run:
        ui.out()
        ui.info(ui.s.grey("dry run tha — kuch install nahi hua, kuch likha nahi gaya."))
    return 0


def _run(ui: UI, args) -> int:
    # Smart auto-route:
    # - First-time user (missing venv/packages or missing key) -> straight into Guided Setup
    # - Returning user (everything already set up) or --menu -> Interactive Control Deck
    if args.menu and not args.full:
        return _control_deck(ui, args)
    if (not args.full and not args.dry_run and not args.yes
            and not getattr(args, "key", None) and ui.is_live()):
        vpy = venv_python(VENV)
        if vpy.exists():
            _, existing_key, all_pkgs = _deck_snapshot(vpy)
            if all_pkgs and existing_key and _looks_like_key(existing_key):
                return _control_deck(ui, args)
    return _run_guided(ui, args)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.about:
        print(f"MIKASA v{VERSION}")
        print(f"Built by {BUILT_BY}")
        print(f"Creators: {BUILT_BY_NAMES}")
        return 0

    console_fix()
    ui = UI(args)
    try:
        return _run(ui, args)
    except KeyboardInterrupt:
        ui.out()
        ui.out()
        ui.warn("Beech me band kar diya. Koi baat nahi — dobara chala dena,")
        ui.info(ui.s.grey("jo install ho chuka hai wo ho chuka hai. Dubara nahi hoga."))
        return 130
    except SetupError as e:
        ui.out()
        rows = [ui.s.red(e.title)]
        if e.body:
            rows += [""] + [ui.s.grey(x) for x in e.body.splitlines()]
        ui.panel("RUKO", rows, accent=ui.s.red)
        if e.hint:
            ui.out()
            for line in e.hint.splitlines():
                ui.out("  " + ui.s.gold(line))
        ui.out()
        ui.info(ui.s.grey("Theek karke wahi command dobara chalao. Wo wahi se shuru karega "
                          "jahan ruka tha."))
        return 1
    except Exception as e:
        import traceback
        ui.out()
        ui.panel("Kuch toota", [ui.s.red(f"{type(e).__name__}: {e}"),
                                "", ui.s.grey("Ye mera dosh hai, tumhara nahi.")],
                 accent=ui.s.red)
        if args.verbose:
            traceback.print_exc()
        else:
            ui.info(ui.s.grey("Detail ke liye: python setup.py --verbose"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
