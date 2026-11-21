"""Her room.

95% of this window is black. Three colours besides it, and no fourth:

    ROSE    #E0A2A8   her — the mouth of the light, her name, her lines
    EMBER   #C98A5E   the hour, the heart, anything warm and low
    BONE    #E7E1DA   what he said, and only that

Nothing glows. Nothing pulses except the heart, and that is barely a pulse —
a breath at most. The whole design brief is one line: it should look like a
room with the lights low, not like a dashboard.

WHY THE CHAT IS PLAIN
    ULTRON's log has badges, tags and colours because it is a report of what
    the machine did. This is a conversation. Two voices, one column, her name
    above her line and nothing at all above his. Anything more and it reads as
    a console, which is exactly what she is not.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QLineF, QPointF
from PyQt6.QtGui import (QFont, QPixmap, QColor, QPainter, QPen, QBrush,
                         QPainterPath)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QLineEdit, QFrame, QDialog, QCheckBox,
                             QComboBox, QPlainTextEdit, QMessageBox)

import settings
import shelf as shelf_mod

ROOT = Path(__file__).resolve().parent

# Qt reads an eight-digit colour as #AARRGGBB, so "#E0A2A866" is olive at 88%
# alpha, not rose at 40%. Anything translucent is written as rgba() instead.
ROSE  = "#E0A2A8"
EMBER = "#C98A5E"
BONE  = "#E7E1DA"
DIM   = "#6E6460"
BLACK = "#07060A"


# ─────────────────────────────────────────────────────────────────────────────
#  the portrait
# ─────────────────────────────────────────────────────────────────────────────
class Portrait(QWidget):
    """Her face — one of twelve, changing with what she is saying.

    The face used to be a photograph, and there was exactly one of it, so the
    only thing it could ever do was sit there. Now it is twelve drawings and a
    mood, and when the mood changes the two are crossfaded over 180 ms: short
    enough that it happens inside her own sentence, long enough that it does
    not flicker.

    Nothing animates on its own. She breathes while she is speaking and is
    still while she is not — a loop running under a face reads as a screensaver,
    and she is supposed to read as somebody in the room.
    """

    MOODS = ("happy", "sad", "angry", "fearful", "disgusted", "surprised",
             "excited", "calm", "bored", "confused", "tired", "love")
    DEFAULT = "calm"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background:transparent;")

        self._faces = {}
        folder = ROOT / "assets" / "faces"
        for m in self.MOODS:
            px = QPixmap(str(folder / f"{m}.png"))
            if not px.isNull():
                self._faces[m] = px
        self._mood = self.DEFAULT if self.DEFAULT in self._faces else \
            (next(iter(self._faces), None))
        self._prev = None
        self._fade = 1.0

        self._speaking = False
        self._listening = False

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(16)
        self._fade_timer.timeout.connect(self._fade_step)

    # ── mood ────────────────────────────────────────────────────────────────
    def set_mood(self, mood: str) -> bool:
        mood = (mood or "").strip().lower()
        if mood not in self._faces or mood == self._mood:
            return False
        self._prev = self._mood
        self._mood = mood
        self._fade = 0.0
        self._fade_timer.start()
        self.update()
        return True

    def _fade_step(self):
        self._fade = min(1.0, self._fade + 16.0 / 180.0)
        if self._fade >= 1.0:
            self._fade_timer.stop()
            self._prev = None
        self.update()

    # ── state ───────────────────────────────────────────────────────────────
    def set_state(self, speaking: bool = None, listening: bool = None):
        """Who is doing what. Nothing here starts any animation.

        There used to be a sine on the circle's size while she spoke, driven
        by a 40 ms timer. It is gone: a face that pulses is a screensaver, and
        it was also the one thing that made the drawing drift out of its own
        circle. Her movement now lives in the Wave row underneath.
        """
        if speaking is not None:
            self._speaking = speaking
        if listening is not None:
            self._listening = listening

    # ── paint ───────────────────────────────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = self.width(), self.height()
        # The circle is the smaller side of the widget, minus a margin, and it
        # is centred in both directions. It used to be min(w-40, h-40) with the
        # drawing scaled by IgnoreAspectRatio into whatever that gave — on a
        # tall window the drawing was stretched, and the faint vignette the
        # PNGs carried was crushed against the rim, which is what read as
        # "leftovers" at the sides. The drawings are square and already
        # centred, so now the maths is one line and nothing is stretched.
        # The circle is the square that fits, capped at 520 px. On a 1080p
        # window the panel is wide enough to draw her at ~980 and at that size
        # she stopped being a face in a room and became a wallpaper. The widget
        # itself is height-capped in the layout (see Window.__init__), so this
        # almost always lands at 520 and only shrinks when the window does.
        side = max(150, min(w - 32, h - 32, 520.0))
        x = (w - side) / 2.0
        y = (h - side) / 2.0

        def face_pixmap(mood):
            px = self._faces.get(mood)
            if px is None:
                return None
            return px.scaled(int(side), int(side),
                             Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

        if self._faces:
            path = QRectF(x, y, side, side)
            clip = QPainterPath()
            clip.addEllipse(path)
            p.save()
            p.setClipPath(clip)

            cur = face_pixmap(self._mood)
            if self._prev and self._fade < 1.0:
                old = face_pixmap(self._prev)
                if old is not None:
                    p.setOpacity(1.0 - self._fade)
                    p.drawPixmap(int(x), int(y), old)
            if cur is not None:
                p.setOpacity(self._fade if self._prev else 1.0)
                p.drawPixmap(int(x), int(y), cur)
            p.setOpacity(1.0)

            # Being listened to is a lamp on her; being spoken through is the
            # lamp off. Never the other way round — a face that brightens when
            # it talks is a puppet.
            alpha = 0 if self._speaking else 74 if not self._listening else 44
            if alpha:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(5, 4, 7, alpha)))
                p.drawRect(path)
            p.restore()

            # The rim — a class attribute, so the design can be swapped
            # without touching the painting around it. See RINGS below.
            paint_rim(p, RIM, path, "speaking" if self._speaking else
                      ("listening" if self._listening else "idle"))
        else:
            p.setPen(QPen(QColor(DIM), 1))
            p.drawEllipse(QRectF(x, y, side, side))
            p.setPen(QColor(DIM))
            p.setFont(QFont("Georgia", 11))
            p.drawText(QRectF(x, y, side, side), Qt.AlignmentFlag.AlignCenter,
                       "her face")
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  the rim around her face
# ─────────────────────────────────────────────────────────────────────────────
# A rim is not decoration here: it is the only thing on screen that says the
# room is awake without moving her face. Each of these is one function, and the
# chosen one is named in RIM. `state` is "idle", "listening" or "speaking".
import math as _math

RIM = "ticks"             # ← his pick: bezel ticks, ring C


def _rim_hairline(p, rect, state):
    """One thin ember line. Quiet, and it lifts while she talks."""
    rim = QColor(EMBER)
    rim.setAlpha(0x88 if state == "speaking" else 0x3A if state == "listening" else 0x22)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(rim, 1.2 if state == "speaking" else 1.0))
    p.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))


def _rim_locket(p, rect, state):
    """Two hairlines with a gap at the top, so it reads as a locket."""
    outer = rect.adjusted(1, 1, -1, -1)
    inner = outer.adjusted(7, 7, -7, -7)
    for rr, a0, a1, w in ((outer, 26, 334, 1.1), (inner, 40, 320, 0.8)):
        c = QColor(ROSE if state == "speaking" else EMBER)
        c.setAlpha((140 if state == "speaking" else
                    70 if state == "listening" else 34))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(c, w))
        p.drawArc(rr, int(a0 * 16), int((a1 - a0) * 16))


def _rim_ticks(p, rect, state):
    """A watch bezel: 48 ticks, brightest at the bottom, brighter when she talks."""
    c = rect.center()
    r = rect.width() / 2.0
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(48):
        a = _math.radians(i * 360 / 48 - 90)
        long_tick = (i % 4 == 0)
        # Outside the rim, never inward: a tick drawn inside lands on her hair
        # and reads as dirt on the drawing.
        r1 = r + (7.0 if long_tick else 4.0)
        x0, y0 = c.x() + (r + 1.0) * _math.cos(a), c.y() + (r + 1.0) * _math.sin(a)
        x1, y1 = c.x() + r1 * _math.cos(a), c.y() + r1 * _math.sin(a)
        low = 0.5 + 0.5 * _math.sin(a - _math.pi / 2)
        col = QColor(ROSE if state == "speaking" else EMBER)
        col.setAlpha(int((22 + 104 * low) *
                        (1.0 if state == "speaking" else
                         0.55 if state == "listening" else 0.28)))
        p.setPen(QPen(col, 1.0 if long_tick else 0.7))
        p.drawLine(QLineF(x0, y0, x1, y1))


def _rim_bloom(p, rect, state):
    """No ring at all — a soft light from under her chin, inside the circle."""
    from PyQt6.QtGui import QRadialGradient
    grad = QRadialGradient(rect.center() + QPointF(0, rect.height() * 0.30),
                           rect.width() * 0.62)
    warm = QColor(ROSE if state == "speaking" else EMBER)
    a = (46 if state == "speaking" else 24 if state == "listening" else 12)
    grad.setColorAt(0.0, QColor(warm.red(), warm.green(), warm.blue(), a))
    grad.setColorAt(0.55, QColor(warm.red(), warm.green(), warm.blue(), a // 3))
    grad.setColorAt(1.0, QColor(warm.red(), warm.green(), warm.blue(), 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(rect)


def _rim_arcs(p, rect, state):
    """Four arcs turning slowly while she speaks. Quiet machinery."""
    outer = rect.adjusted(1.5, 1.5, -1.5, -1.5)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k in range(4):
        a0 = 12 + k * 90
        col = QColor(ROSE if state == "speaking" else EMBER)
        col.setAlpha(130 if state == "speaking" else
                     58 if state == "listening" else 26)
        p.setPen(QPen(col, 1.1))
        p.drawArc(outer, int(a0 * 16), int(56 * 16))


RIM_DESIGNS = {"hairline": _rim_hairline, "locket": _rim_locket,
               "ticks": _rim_ticks, "bloom": _rim_bloom, "arcs": _rim_arcs}


def paint_rim(p, name: str, rect, state: str) -> None:
    RIM_DESIGNS.get(name, _rim_hairline)(p, rect, state)


WAVE = "dots"          # ← his pick: soft dots, trace 3


def _trace_bars(p, w, h, state, t, lv):
    """96 mirrored one-pixel bars. The equaliser."""
    import math
    cy = h / 2.0
    n, span = 96, min(w * 0.78, 460.0)
    step = span / n
    x0 = (w - span) / 2.0
    base = QColor(ROSE if state == "speaking" else EMBER)
    amp = 15.0 * (1.0 + min(1.0, w / 1400.0))
    for i in range(n):
        k = abs(i - (n - 1) / 2.0) / ((n - 1) / 2.0)
        env = (1.0 - k) ** 0.9
        wave = (0.55 + 0.45 * math.sin(t * 2.1 - i * 0.34)
                + 0.18 * math.sin(t * 3.7 + i * 0.19))
        wave = max(0.12, min(1.0, wave))
        bh = 1.2 + amp * lv * env * wave
        col = QColor(base)
        col.setAlpha(int(95 + 145 * env * min(1.0, wave * (0.6 + 0.6 * lv))))
        p.setPen(QPen(col, 1))
        x = x0 + i * step
        p.drawLine(QLineF(x, cy - bh, x, cy + bh))


def _trace_hairline(p, w, h, state, t, lv):
    """One continuous line that breathes — a voice, not an equaliser."""
    import math
    cy = h / 2.0
    span = min(w * 0.80, 470.0)
    x0 = (w - span) / 2.0
    n = 220
    amp = (4.0 + 6.0 * lv)
    pts = []
    for i in range(n):
        u = i / (n - 1)
        env = (1.0 - abs(u - 0.5) * 2) ** 1.6
        v = (math.sin(u * 22 + t * 2.4) * 0.55 +
             math.sin(u * 9.5 - t * 1.3) * 0.45)
        pts.append(QPointF(x0 + u * span, cy + v * amp * env))
    path = QPainterPath(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    col = QColor(ROSE if state == "speaking" else EMBER)
    col.setAlpha(200 if state == "speaking" else 120)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(col, 1.3))
    p.drawPath(path)
    p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 34), 1.0))
    for pt in pts:
        p.drawLine(QLineF(pt.x(), cy, pt.x(), cy + (cy - pt.y()) * 0.55))


def _trace_dots(p, w, h, state, t, lv):
    """Forty soft dots that lift and settle. Softer than bars."""
    import math
    cy = h / 2.0
    n, span = 40, min(w * 0.70, 420.0)
    step = span / (n - 1)
    x0 = (w - span) / 2.0
    base = QColor(ROSE if state == "speaking" else EMBER)
    for i in range(n):
        u = i / (n - 1)
        env = (1.0 - abs(u - 0.5) * 2) ** 1.3
        wv = 0.5 + 0.5 * math.sin(t * 1.8 - i * 0.42)
        y = cy - (wv - 0.5) * 24 * env * (0.4 + lv)
        col = QColor(base)
        col.setAlpha(int(60 + 175 * env * (0.5 + 0.5 * wv)))
        r = 1.4 + 2.0 * env
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(QPointF(x0 + i * step, y), r, r)


def _trace_grain(p, w, h, state, t, lv):
    """Dense hairline with an envelope — ULTRON's trace, softened."""
    import math
    cy = h / 2.0
    n, span = 120, min(w * 0.82, 480.0)
    step = span / n
    x0 = (w - span) / 2.0
    flat = QColor(BONE)
    flat.setAlpha(30)
    p.setPen(QPen(flat, 1))
    p.drawLine(QLineF(x0, cy, x0 + span, cy))
    base = QColor(ROSE if state == "speaking" else EMBER)
    for i in range(n):
        u = i / (n - 1)
        env = math.sin(math.pi * u) ** 0.7
        wv = abs(math.sin(t * 2.6 + i * 0.31) * math.sin(t * 1.1 + i * 0.09))
        bh = 0.8 + 17 * env * wv * (0.35 + lv)
        col = QColor(base)
        col.setAlpha(int(60 + 170 * env))
        p.setPen(QPen(col, 1))
        p.drawLine(QLineF(x0 + i * step, cy - bh, x0 + i * step, cy + bh))


TRACES = {"bars": _trace_bars, "hairline": _trace_hairline,
          "dots": _trace_dots, "grain": _trace_grain}


class Wave(QWidget):
    """The line under her face: the only thing in the window that moves.

    There used to be a heart-beat on the circle itself; that is gone. Movement
    lives here, it is one row, and it says exactly one thing — she is listening,
    or she is speaking, or she is neither and the row is a flat faint line. A
    meter that moves when nothing is happening is worse than no meter, because
    you stop believing the words under it.

    Which trace is drawn is `WAVE` — see TRACES above.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setMinimumWidth(180)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._state = "idle"
        self._muted = True          # start quiet: nothing has happened yet
        self._t = 0.0
        self._lv = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: str, muted: bool):
        state = state if state in ("listening", "speaking", "thinking") else "idle"
        if state != self._state or muted != self._muted:
            self._state = state
            self._muted = muted or state == "idle"
            if self._muted:
                self._timer.stop()
                self._lv = 0.0
            else:
                # start at the level, not at zero: the first frame of a new
                # state must not look like the flat one it just left
                self._lv = 1.0 if state == "speaking" else 0.55
                self._t = 0.0
                self._timer.start()
            self.update()

    def _tick(self):
        self._t += 0.055
        target = 1.0 if self._state == "speaking" else 0.55 \
            if self._state == "listening" else 0.3
        self._lv += (target - self._lv) * 0.15
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 40 or h < 12:
            return
        if self._muted:
            # nothing is happening: one flat faint line, and nothing else
            flat = QColor(BONE)
            flat.setAlpha(26)
            p.setPen(QPen(flat, 1))
            span = min(w * 0.55, 420.0)
            p.drawLine(QLineF((w - span) / 2.0, h / 2.0,
                              (w + span) / 2.0, h / 2.0))
            p.end()
            return
        TRACES.get(WAVE, _trace_bars)(p, w, h, self._state, self._t, self._lv)
        p.end()


class Heart(QWidget):
    """The heart, small, beside her name at the top.

    It used to sit under her face, in the gap between the circle and the
    window's bottom edge. That gap is a different size at every window size, so
    the heart was never quite centred under anything, and against a circle it
    looked like a mistake rather than a mark. Here the row has its own height
    and the heart is optically centred in it by the layout, at any size.

    It does not beat. It used to swell 6% on a sine while she was talking,
    which was the second thing on screen pretending to be alive — and the
    waveform under her face already says the same sentence, better. A mark
    that only ever looks like a mark is worth more than a small animation that
    is always slightly out of time with her voice.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._px = QPixmap(str(ROOT / "assets" / "heart.png"))

    def paintEvent(self, _e):
        if self._px.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Added, not laid over. The heart is a warm object on a black field,
        # so adding it puts the object on the header and adds nothing where
        # the field is black — no square edge around it, at any size.
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        px = self._px.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(int((self.width() - px.width()) / 2),
                     int((self.height() - px.height()) / 2), px)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  chat
# ─────────────────────────────────────────────────────────────────────────────
class Bubble(QWidget):
    """One line of the conversation. Her name above hers; nothing above his."""

    def __init__(self, who: str, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 4)
        lay.setSpacing(3)

        if who == "her":
            name = QLabel("m i k a s a")
            name.setStyleSheet(f"color:{ROSE}; font-size:9px; letter-spacing:2px;")
            lay.addWidget(name)
            colour, weight = ROSE, QFont.Weight.Normal
        else:
            colour, weight = BONE, QFont.Weight.Light

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f = QFont("Georgia", 11)
        f.setWeight(weight)
        body.setFont(f)
        body.setStyleSheet(f"color:{colour}; line-height:150%;")
        if who != "her":
            body.setStyleSheet(f"color:{colour};")
        lay.addWidget(body)


class Note(QWidget):
    """One line about the room, in the room's own voice.

    There has to be something here when the line drops, because otherwise the
    window looks exactly like a window that is working and she looks exactly
    like a person ignoring him. But it must not read as her saying it, or as
    the machine talking over her: no badge, no name, no colour of its own —
    dim, small, centred, gone in the scroll.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 9, 0, 9)
        lay.setSpacing(0)
        lab = QLabel(f"·  {text}  ·")
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont("Georgia", 8)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        lab.setFont(f)
        lab.setStyleSheet(f"color:{DIM}; background:transparent;")
        lay.addWidget(lab)


class Chat(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                           "QScrollBar:vertical{background:transparent;width:4px;}"
                           f"QScrollBar::handle:vertical{{background:{DIM};"
                           "border-radius:2px;min-height:24px;}"
                           "QScrollBar::add-line,::sub-line{height:0;}")
        self._holder = QWidget()
        self._holder.setStyleSheet("background:transparent;")
        self._box = QVBoxLayout(self._holder)
        self._box.setContentsMargins(18, 8, 12, 8)
        self._box.setSpacing(2)
        self._box.addStretch(1)
        self.setWidget(self._holder)

    def add(self, who: str, text: str):
        text = (text or "").strip()
        if not text:
            return
        if who == "note":
            self._box.addWidget(Note(text))
        else:
            self._box.addWidget(Bubble(who, text))
        QTimer.singleShot(30, self._bottom)

    def _bottom(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear(self):
        while self._box.count() > 1:
            item = self._box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
#  the gear — everything she must never see
# ─────────────────────────────────────────────────────────────────────────────
class NetLogDialog(QDialog):
    """What the line actually did, newest first.

    Small on purpose: this is not a telemetry screen, it is the answer to one
    question — "is it the network or is it her side?" — and the answer is
    usually one glance. Copyable, because the next step for anything odd is to
    send three lines to somebody.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("the line")
        self.setMinimumSize(560, 420)
        self.setStyleSheet(
            f"QDialog{{background:{BLACK};color:{BONE};}}"
            f"QPlainTextEdit{{background:#0d0b11;color:{BONE};"
            f"border:1px solid #241f28;font-family:monospace;font-size:11px;}}"
            f"QPushButton{{background:#121016;color:{BONE};"
            f"border:1px solid #241f28;padding:7px 14px;border-radius:3px;}}"
            f"QPushButton:hover{{border-color:{ROSE};color:{ROSE};}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        line = _line_log()
        head = QLabel(line.summary())
        head.setStyleSheet(f"color:{ROSE}; font-size:11px;")
        lay.addWidget(head)

        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(line.as_text(120))
        lay.addWidget(box, 1)

        hint = QLabel("drop = the line went · back = it returned · rotate = "
                      "moved on purpose · model = a different rung · "
                      "stall = silent socket · route = the path itself")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{DIM}; font-size:10px;")
        lay.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        copy = QPushButton("copy")
        copy.clicked.connect(
            lambda: QApplication.clipboard().setText(box.toPlainText()))
        row.addWidget(copy)
        close = QPushButton("close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)


def _line_log():
    """One reader for the file the session writes. Never creates it."""
    import netwatch
    return netwatch.Line(ROOT / "config" / "netlog.json")


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.cfg = settings.load()
        self.setWindowTitle("mikasa — controls")
        self.setMinimumWidth(460)
        self.setStyleSheet(
            f"QDialog{{background:{BLACK};color:{BONE};}}"
            f"QLabel{{color:{BONE};}}"
            f"QPushButton{{background:#121016;color:{BONE};border:1px solid #241f28;"
            f"padding:7px 14px;border-radius:3px;}}"
            f"QPushButton:hover{{border-color:{ROSE};color:{ROSE};}}"
            f"QLineEdit,QComboBox{{background:#0d0b11;color:{BONE};"
            f"border:1px solid #241f28;padding:6px;border-radius:3px;}}"
            f"QCheckBox{{color:{BONE};}}")

        # The whole body scrolls; the way back does not. On a laptop screen
        # this list is taller than the window, and the one control that must
        # never be off-screen is the one that gets him out of here.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{background:transparent;width:6px;margin:6px 2px;}"
            "QScrollBar::handle:vertical{background:rgba(110,100,96,0.75);"
            "border-radius:3px;min-height:30px;}"
            "QScrollBar::add-line,::sub-line{height:0;}")
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        body.setMinimumWidth(430)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(22, 20, 18, 14)
        lay.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        foot = QWidget()
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(22, 10, 22, 16)
        fl.setSpacing(10)
        outer.addWidget(foot)

        # 85% of the screen, never taller. Anything more and the title bar sits
        # under the panel edge on a small laptop.
        avail = self.screen().availableGeometry() if self.screen() else None
        if avail is not None:
            self.resize(520, max(420, int(avail.height() * 0.85)))

        title = QLabel("c o n t r o l s")
        title.setStyleSheet(f"color:{DIM}; letter-spacing:4px; font-size:10px;")
        lay.addWidget(title)

        # ── voice ────────────────────────────────────────────────────────────
        # Voice recognition used to live here: a record button, a strictness
        # slider, a "only answer his voice" switch and 120 lines of enrolment
        # dialog. None of it worked well enough to keep and all of it made her
        # look like a security product, so it is gone rather than hidden. The
        # whole feature comes back as its own thing, or not at all.
        # ── code ────────────────────────────────────────────────────────────
        lay.addWidget(self._head("CODE"))
        crow = QHBoxLayout()
        self.lbl_code = QLabel("none set" if not settings.has_code() else "set")
        self.lbl_code.setStyleSheet(
            f"color:{DIM if not settings.has_code() else ROSE};")
        crow.addWidget(self.lbl_code)
        crow.addStretch(1)
        b_code = QPushButton("set" if not settings.has_code() else "change")
        b_code.clicked.connect(self._set_code)
        crow.addWidget(b_code)
        lay.addLayout(crow)
        note = QLabel("typed once to open the chat. stored as a hash — "
                      "it cannot be read back, and she never sees it.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{DIM}; font-size:10px;")
        lay.addWidget(note)

        # ── voice / language ────────────────────────────────────────────────
        lay.addWidget(self._head("VOICE"))
        vrow = QHBoxLayout()
        self.cmb_voice = QComboBox()
        # The seven he kept, one flat list — there is nothing left to group.
        # Every item carries its real name as data, not as its label: a label
        # saved as a voice name fails at session setup and looks like a network
        # problem.
        for name in settings.VOICES:
            self.cmb_voice.addItem(name, name)
        cur = str(self.cfg.get("voice") or settings.DEFAULTS["voice"])
        if cur not in settings.VOICES:
            # A config written by hand, or by a build that had more voices.
            # Show it rather than silently switching her to something else.
            self.cmb_voice.addItem(cur, cur)
        for i in range(self.cmb_voice.count()):
            if self.cmb_voice.itemData(i) == cur:
                self.cmb_voice.setCurrentIndex(i)
                break
        vrow.addWidget(QLabel("voice"))
        vrow.addWidget(self.cmb_voice, 1)
        lay.addLayout(vrow)

        vnote = QLabel("takes effect on save — she reconnects for a second, "
                       "it is not a restart")
        vnote.setStyleSheet(f"color:{DIM}; font-size:10px;")
        lay.addWidget(vnote)

        mrow = QHBoxLayout()
        self.cmb_mouth = QComboBox()
        self.cmb_mouth.addItem("studio — acted, ~1s slower", "studio")
        self.cmb_mouth.addItem("live — her own live voice, instant", "live")
        cur_m = str(self.cfg.get("voice_mode") or "studio")
        for i in range(self.cmb_mouth.count()):
            if self.cmb_mouth.itemData(i) == cur_m:
                self.cmb_mouth.setCurrentIndex(i)
                break
        mrow.addWidget(QLabel("mouth"))
        mrow.addWidget(self.cmb_mouth, 1)
        lay.addLayout(mrow)

        mnote = QLabel("studio reads each line before saying it, so a whisper "
                       "is a whisper. if the free voice is out of quota she "
                       "falls back to live by herself.")
        mnote.setWordWrap(True)
        mnote.setStyleSheet(f"color:{DIM}; font-size:10px;")
        lay.addWidget(mnote)

        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems([
            "Hindi and English mixed, the way people here actually talk",
            "Hindi, mostly",
            "English, mostly",
        ])
        cur = self.cfg.get("language", "")
        idx = self.cmb_lang.findText(cur)
        self.cmb_lang.setCurrentIndex(idx if idx >= 0 else 0)
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("language"))
        lrow.addWidget(self.cmb_lang, 1)
        lay.addLayout(lrow)

        # ── where she is ────────────────────────────────────────────────────
        # A city and a zone, never an address. Without it her clock is a number;
        # with it, "subah ke 7" means something and she can tell that it is
        # late because it is dark where he is.
        lay.addWidget(self._head("WHERE SHE IS"))
        crow = QHBoxLayout()
        self.ed_city = QLineEdit(str(self.cfg.get("city", "Agra")))
        self.ed_city.setPlaceholderText("Agra")
        crow.addWidget(QLabel("city"))
        crow.addWidget(self.ed_city, 2)
        self.ed_tz = QLineEdit(str(self.cfg.get("tz", "Asia/Kolkata")))
        self.ed_tz.setPlaceholderText("Asia/Kolkata")
        crow.addWidget(QLabel("zone"))
        crow.addWidget(self.ed_tz, 2)
        lay.addLayout(crow)

        # ── the room ────────────────────────────────────────────────────────
        lay.addWidget(self._head("THE ROOM"))
        self.chk_alarm = QCheckBox("she may offer to set an alarm at night")
        self.chk_alarm.setChecked(bool(self.cfg.get("alarm", True)))
        lay.addWidget(self.chk_alarm)

        # The label used to promise something the code did not do: there was no
        # camera at all, and this checkbox only wrote a word into a JSON file
        # that nothing read. It now says what actually happens — and if there is
        # no camera on the machine, it says that instead of lying about it.
        try:
            import camera
            _cam_ok, _cam_why = camera.available()
        except Exception as e:
            _cam_ok, _cam_why = False, type(e).__name__
        self.chk_cam = QCheckBox(
            "camera — she asks first, and looks only if you say yes"
            if _cam_ok else f"camera — none found ({_cam_why})")
        self.chk_cam.setChecked(_cam_ok and self.cfg.get("camera", "ask") != "off")
        self.chk_cam.setEnabled(_cam_ok)
        lay.addWidget(self.chk_cam)

        hrow = QHBoxLayout()
        hrow.addWidget(QLabel("notes about him"))
        self.cmb_w = QComboBox()
        self.cmb_w.addItems(["on", "off"])
        # "ask" is gone on purpose. She is not an assistant asking permission
        # before it takes a note — she decides what is worth keeping, the way a
        # person does. An old config that still says "ask" lands on "on".
        _w = str(self.cfg.get("her_writing", "on")).lower()
        self.cmb_w.setCurrentText("off" if _w == "off" else "on")
        self.cmb_w.setToolTip("she keeps what you tell her about yourself, on "
                              "her own — off shuts the notebook entirely")
        hrow.addWidget(self.cmb_w, 1)
        lay.addLayout(hrow)

        srow = QHBoxLayout()
        self.lbl_shelf = QLabel(f"shelf — {shelf_mod.count()} pieces")
        self.lbl_shelf.setStyleSheet(f"color:{DIM};")
        srow.addWidget(self.lbl_shelf)
        srow.addStretch(1)
        b_shelf = QPushButton("open folder")
        b_shelf.clicked.connect(self._open_shelf)
        srow.addWidget(b_shelf)
        lay.addLayout(srow)

        # ── the line ────────────────────────────────────────────────────────
        # Not a network speed test: the question this answers is "was that my
        # WiFi or her side", and the only honest answer is a record of what
        # actually happened, in the kinds the supervisor uses internally.
        lay.addWidget(self._head("THE LINE"))
        lrow = QHBoxLayout()
        self.lbl_line = QLabel(_line_log().summary())
        self.lbl_line.setStyleSheet(f"color:{DIM};")
        self.lbl_line.setWordWrap(True)
        lrow.addWidget(self.lbl_line, 1)
        b_line = QPushButton("log")
        b_line.clicked.connect(lambda: NetLogDialog(self).exec())
        lrow.addWidget(b_line)
        lay.addLayout(lrow)

        # ── memory ──────────────────────────────────────────────────────────
        lay.addWidget(self._head("MEMORY"))
        mrow = QHBoxLayout()
        self.lbl_mem = QLabel(self._memory_line())
        self.lbl_mem.setStyleSheet(f"color:{DIM};")
        mrow.addWidget(self.lbl_mem)
        mrow.addStretch(1)
        b_forget = QPushButton("forget everything")
        b_forget.clicked.connect(self._forget)
        mrow.addWidget(b_forget)
        lay.addLayout(mrow)

        # ── the door back ───────────────────────────────────────────────────
        lay.addSpacing(8)
        back = QPushButton("CLOSE")
        back.setStyleSheet(
            f"QPushButton{{background:transparent;color:{EMBER};"
            f"border:1px solid rgba(201,138,94,0.33);padding:11px;letter-spacing:2px;}}"
            f"QPushButton:hover{{border-color:{EMBER};background:rgba(201,138,94,0.07);}}")
        back.clicked.connect(self.win.close_room)
        fl.addWidget(back)

        bot = QHBoxLayout()
        bot.addStretch(1)
        cancel = QPushButton("cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("save")
        save.setStyleSheet(
            f"QPushButton{{background:{ROSE};color:#120a0c;border:none;"
            f"padding:7px 22px;border-radius:3px;font-weight:600;}}")
        save.clicked.connect(self._save)
        bot.addWidget(cancel)
        bot.addWidget(save)
        fl.addLayout(bot)

    # ── helpers ─────────────────────────────────────────────────────────────
    def _head(self, text):
        w = QLabel(text)
        w.setStyleSheet(f"color:{DIM}; letter-spacing:2px; font-size:9px; "
                        f"margin-top:10px;")
        return w

    def _memory_line(self):
        import memory
        n = len(memory.all_facts())
        t = len(memory.threads())
        nights = len(memory.nights(999))
        return f"{n} things remembered · {t} threads open · {nights} nights"

    def _save(self):
        cfg = settings.load()
        # itemData, not currentText: the two group headers are selectable in
        # appearance only, and a header saved as a voice name would fail at
        # session setup and look like a network problem.
        picked = self.cmb_voice.currentData()
        cfg["voice"]       = picked or self.cfg.get("voice", settings.DEFAULTS["voice"])
        cfg["voice_picked"] = True      # from here on it is his choice, not a default
        cfg["voice_mode"]   = self.cmb_mouth.currentData() or "studio"
        cfg["city"]        = (self.ed_city.text() or "Agra").strip()[:40]
        cfg["tz"]          = (self.ed_tz.text() or "Asia/Kolkata").strip()[:40]
        cfg["language"]    = self.cmb_lang.currentText()
        cfg["camera"]      = "ask" if self.chk_cam.isChecked() else "off"
        cfg["alarm"]       = bool(self.chk_alarm.isChecked())
        cfg["her_writing"] = self.cmb_w.currentText()
        settings.save(cfg)
        self.win.reload_settings()
        self.accept()

    def _set_code(self):
        from PyQt6.QtWidgets import QInputDialog
        old_required = settings.has_code()
        if old_required:
            old, ok = QInputDialog.getText(self, "code", "current code:",
                                           QLineEdit.EchoMode.Password)
            if not ok:
                return
            if not settings.check_code(old):
                QMessageBox.warning(self, "code", "that is not it.")
                return
        new, ok = QInputDialog.getText(self, "code", "new code:",
                                       QLineEdit.EchoMode.Password)
        if not ok:
            return
        if len(new.strip()) < 3:
            QMessageBox.warning(self, "code", "at least three characters.")
            return
        settings.set_code(new)
        self.lbl_code.setText("set")
        self.lbl_code.setStyleSheet(f"color:{ROSE};")
        self.win.reload_settings()

    def _open_shelf(self):
        shelf_mod._ensure()
        path = str(shelf_mod.SHELF)
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}" &')
        except Exception:
            pass

    def _forget(self):
        if QMessageBox.question(
                self, "forget everything",
                "This deletes everything she remembers — every night, every "
                "fact, every open thread. It cannot be undone.\n\nForget it all?"
        ) != QMessageBox.StandardButton.Yes:
            return
        if QMessageBox.question(self, "are you sure",
                                "The last chance. Delete all of it?") \
                != QMessageBox.StandardButton.Yes:
            return
        import memory
        memory.forget_everything()
        self.lbl_mem.setText(self._memory_line())


# ─────────────────────────────────────────────────────────────────────────────
#  the window
# ─────────────────────────────────────────────────────────────────────────────
class Window(QMainWindow):
    heard      = pyqtSignal(str)     # what reached her, as text
    she_said   = pyqtSignal(str)     # her words, as text
    state      = pyqtSignal(str)     # idle | listening | speaking | thinking
    mood       = pyqtSignal(str)     # her face, from her own tool call
    note       = pyqtSignal(str)     # the room: connection, and nothing else
    connection = pyqtSignal(dict)    # what the line is doing, from the session

    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.cfg = settings.load()

        self.setWindowTitle("mikasa")
        self.setMinimumSize(760, 560)
        self.resize(1080, 760)
        self.setStyleSheet(f"QMainWindow{{background:{BLACK};}}")

        root = QWidget()
        root.setStyleSheet(f"background:{BLACK};")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── the name, at the top, spaced out ────────────────────────────────
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(26, 16, 26, 10)
        title = QLabel("M I K A S A")
        tf = QFont("Georgia", 13)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 7)
        title.setFont(tf)
        title.setStyleSheet(f"color:{ROSE}; background:transparent;")
        tl.addWidget(title)

        self.heart = Heart()
        hl = QHBoxLayout()
        hl.setContentsMargins(10, 2, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self.heart)
        tl.addLayout(hl)
        tl.addStretch(1)

        self.btn_gear = self._flat("setup")
        self.btn_gear.clicked.connect(self.open_settings)
        tl.addWidget(self.btn_gear)
        self.btn_full = self._flat("full")
        self.btn_full.clicked.connect(self.toggle_fullscreen)
        tl.addWidget(self.btn_full)
        self.btn_min = self._flat("hide")
        self.btn_min.clicked.connect(self.showMinimized)
        tl.addWidget(self.btn_min)
        outer.addWidget(top)

        # ── body: her on the left, the conversation on the right ────────────
        body = QWidget()
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 0, 10, 0)
        ll.setSpacing(0)

        # Her face, the trace and the state word are one object, so they are
        # laid out as one: stretches above and below, nothing between them. A
        # portrait that eats all the height puts the waveform in the corner of
        # the window and leaves a metre of empty black between them.
        ll.addStretch(1)

        self.portrait = Portrait()
        self.portrait.setMinimumHeight(300)
        self.portrait.setMaximumHeight(560)
        # Stretch 4 against the two 1s above and below: without it Qt hands the
        # portrait its bare minimum height (300) and the circle comes out 284 px
        # wide on a 1600 px window, which reads as a thumbnail.
        ll.addWidget(self.portrait, 4)

        # Just under the circle, the way ULTRON puts his trace under the ring:
        # the movement sits in a strip of its own so the face never has to move.
        self.wave = Wave()
        ll.addWidget(self.wave, 0)
        ll.addSpacing(6)

        self.lbl_state = QLabel("")
        self.lbl_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_state.setStyleSheet(
            f"color:{DIM}; font-size:9px; letter-spacing:3px; "
            f"background:transparent;")
        ll.addWidget(self.lbl_state)
        ll.addStretch(1)
        bl.addWidget(left, 3)

        right = QFrame()
        right.setFixedWidth(390)
        # Named, because QLabel *is* a QFrame in Qt: a bare QFrame rule put a
        # one-pixel left border on every line of the conversation.
        right.setObjectName("chatpanel")
        right.setStyleSheet(
            "QFrame#chatpanel{background:#0A0810;"
            " border-left:1px solid #17131c;}")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 12, 0, 0)
        rl.setSpacing(0)
        self.chat = Chat()
        rl.addWidget(self.chat, 1)
        bl.addWidget(right)

        outer.addWidget(body, 1)

        # ── the way in ──────────────────────────────────────────────────────
        bar = QWidget()
        bl2 = QHBoxLayout(bar)
        bl2.setContentsMargins(20, 10, 20, 16)
        bl2.setSpacing(10)

        self.btn_mic = QPushButton("mic")
        self.btn_mic.setFont(QFont("Georgia", 8))
        self.btn_mic.setFixedSize(42, 42)
        self.btn_mic.setStyleSheet(self._mic_style(False))
        self.btn_mic.clicked.connect(self.toggle_mic)
        bl2.addWidget(self.btn_mic)

        self.input = QLineEdit()
        self.input.setPlaceholderText("type…")
        self.input.setFont(QFont("Georgia", 11))
        self.input.setStyleSheet(
            f"QLineEdit{{background:#0d0b11; color:{BONE}; border:none;"
            f" border-bottom:1px solid #241f28; padding:9px 4px;}}"
            f"QLineEdit:focus{{border-bottom:1px solid rgba(224,162,168,0.40);}}")
        self.input.returnPressed.connect(self._send_typed)
        bl2.addWidget(self.input, 1)

        self.btn_send = QPushButton("→")
        self.btn_send.setFixedSize(42, 42)
        self.btn_send.setStyleSheet(self._send_style())
        self.btn_send.clicked.connect(self._send_typed)
        bl2.addWidget(self.btn_send)

        outer.addWidget(bar)

        # ── signals → UI ────────────────────────────────────────────────────
        self.heard.connect(lambda t: self.chat.add("him", t))
        self.she_said.connect(lambda t: self.chat.add("her", t))
        self.state.connect(self._on_state)
        self.connection.connect(self._on_connection)
        self.note.connect(lambda t: self.chat.add("note", t))
        self.mood.connect(self.portrait.set_mood)

        self._listening = True
        self._locked = settings.has_code()
        self._awaiting_code = self._locked
        self._typing_line = None
        # Nobody is listening yet — the socket is still being opened. Saying
        # "listening" here was the first lie of every session, and it lasted
        # until the handshake finished.
        self._mark_state("idle")

        # Full screen by default — Esc, F11 or the "full" button all give the
        # window back, and whichever he picked last is what she opens with.
        if self.cfg.get("fullscreen", True):
            QTimer.singleShot(0, self.showFullScreen)

        # Before the code is typed there is nothing to show: she has not
        # spoken, and a placeholder line would be the first thing she ever
        # "said", which is exactly the wrong first impression.
        if self._locked:
            self.chat.add("her", "…")

    # ── style helpers ───────────────────────────────────────────────────────
    def _flat(self, glyph):
        """Words, not symbols.

        A gear glyph, a fullscreen glyph and a bar chart all looked like empty
        squares on the first render — the fonts this ships to are not
        guaranteed to carry them, and a row of tofu boxes in the corner is a
        worse look than three quiet words.
        """
        b = QPushButton(glyph)
        b.setFixedHeight(24)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton{{background:transparent;color:{DIM};border:none;"
            f"font-size:9px; letter-spacing:2px; padding:0 8px;}}"
            f"QPushButton:hover{{color:{ROSE};}}")
        return b

    def _mic_style(self, live):
        col = ROSE if live else DIM
        return (f"QPushButton{{background:transparent;color:{col};"
                f"border:1px solid {col}66;border-radius:21px;"
                f"font-size:8px; letter-spacing:1px;}}"
                f"QPushButton:hover{{border-color:{ROSE};color:{ROSE};}}")

    def _send_style(self):
        return (f"QPushButton{{background:transparent;color:{BONE};"
                f"border:1px solid #2a2430;border-radius:21px;font-size:15px;}}"
                f"QPushButton:hover{{border-color:{ROSE};color:{ROSE};}}")

    # ── state ───────────────────────────────────────────────────────────────
    def _on_state(self, s):
        self._mark_state(s)

    def _mark_state(self, s):
        """The one place her state becomes words, and the one place it is
        allowed to be wrong.

        The bug this fixes: app.py emits "listening" from about seven different
        corners — after every turn, after every reconnect, on the opening line —
        and the window printed it every time. With the mic shut, she sat there
        saying "l i s t e n i n g" at a closed microphone. An app has no idea
        whether the window's mic is open, so the window decides: if it is not
        listening, nothing downstream may claim it is.
        """
        if s == "listening" and not self._listening:
            s = "idle"                       # mic is shut; it cannot be true
        words = {"listening": "l i s t e n i n g",
                 "speaking":  "s p e a k i n g",
                 "thinking":  "t h i n k i n g",
                 "reconnecting": "r e c o n n e c t i n g",
                 "idle":      "" if self._listening else "m i c   o f f"}
        self.lbl_state.setText(words.get(s, ""))
        self.portrait.set_state(speaking=(s == "speaking"),
                                listening=(s == "listening"))
        self.wave.set_state(s, muted=not self._listening and s != "speaking")

    def _on_connection(self, info: dict):
        """The truth about the line, in the line under her face.

        "reconnecting" was a word that answered nothing: not whether the
        network was involved, not whether it was try one or try nine, not
        whether waiting was worth it. This says which, how many, and how long —
        and it goes back to her state the moment the socket is live again.
        """
        kind = (info or {}).get("kind")
        route = (info or {}).get("route", True)
        if kind == "reconnecting" and not route:
            kind = "offline"      # the two are one state told two ways
        attempt = int((info or {}).get("attempt") or 0)
        delay = float((info or {}).get("delay") or 0)
        backup = bool((info or {}).get("backup"))

        if kind == "offline":
            txt = "o f f l i n e"
            if delay:
                txt += f" · next {delay:.0f}s"
        elif kind == "reconnecting":
            txt = "r e c o n n e c t i n g"
            if attempt:
                txt += f" · try {attempt}"
            if delay:
                txt += f" · {delay:.0f}s"
        elif kind == "live":
            self._mark_state("listening" if self._listening else "idle")
            return
        else:
            return
        if backup:
            txt += " · backup"
        self.lbl_state.setText(txt)
        self.portrait.set_state(speaking=False, listening=False)
        self.wave.set_state("idle", muted=True)

    def toggle_mic(self):
        self._listening = not self._listening
        self.btn_mic.setStyleSheet(self._mic_style(self._listening))
        self._mark_state("listening" if self._listening else "idle")
        if self.controller:
            self.controller.set_listening(self._listening)

    def is_listening(self):
        return self._listening

    # ── the door ────────────────────────────────────────────────────────────
    def _send_typed(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()

        # The code is checked HERE, before anything reaches her. She never
        # sees it, never answers it, and has no idea a door exists.
        if self._awaiting_code and settings.has_code():
            if settings.check_code(text):
                self._locked = False
                self._awaiting_code = False
                return
            self.chat.add("her", "…")
            return

        self.chat.add("him", text)
        self._mark_state("thinking")
        if self.controller:
            self.controller.say_typed(text)

    # ── window ──────────────────────────────────────────────────────────────
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self._remember_fullscreen()

    def _remember_fullscreen(self):
        """So she opens the way he left her, not the way she shipped.

        Saved with settings.save() under the same lock as everything else; a
        failure here is not worth a dialog, because it only costs him one press
        of F11 next time.
        """
        try:
            cfg = settings.load()
            if bool(cfg.get("fullscreen")) != self.isFullScreen() or \
                    not cfg.get("fullscreen_picked"):
                cfg["fullscreen"] = bool(self.isFullScreen())
                cfg["fullscreen_picked"] = True
                settings.save(cfg)
        except Exception as e:
            print(f"[Mikasa] fullscreen not saved: {type(e).__name__}: {e}")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            return
        if e.key() == Qt.Key.Key_Escape and self.isFullScreen():
            # Esc leaves full screen, and only full screen: it is not a close
            # button and it must never end the conversation.
            self.showNormal()
            self._remember_fullscreen()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        if self.controller:
            self.controller.shutdown()
        super().closeEvent(e)

    # ── settings actions ────────────────────────────────────────────────────
    def open_settings(self):
        SettingsDialog(self).exec()

    def reload_settings(self):
        self.cfg = settings.load()
        if self.controller:
            self.controller.reload_settings()

    def close_room(self):
        if self.controller:
            self.controller.close_room()
