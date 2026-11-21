"""Looking at him — once, because he said yes.

WHAT THIS IS FOR
    He says he is wrecked. She cannot see that in text, and the whole point of
    her is that she is in the room. So she says "ruko, zara dekh lu" and then
    this file takes one photograph and the model reacts to his face.

WHY IT IS BUILT THIS WAY
    * Nothing here decides to look. It is called, and only after he has said
      yes in the conversation. There is no timer, no motion trigger, no
      "she noticed you came back".
    * One frame. Not a stream, not a video, not a second capture to "get a
      better one" unless the first one is genuinely black.
    * The file is deleted the moment it has been sent to the model. What is
      left on his disk afterwards is nothing.
    * No new dependency. PyQt6 is already here and it ships QtMultimedia, so
      the camera costs a module, not a 60 MB download.

HOW THE THREADING WORKS, AND WHY IT IS LIKE THIS
    A camera must live on the thread that owns the GUI event loop. Tools run
    on a worker thread. So `grab()` builds a job, hands it to a lane object
    that was created on the GUI thread, and waits on an Event. The GUI thread
    runs the whole capture sequence through its own timers — warm up, take the
    first real frame, stop the device — and sets the Event when it is done.
    Nothing blocks the window, and nothing touches a Qt object off its thread.

WHAT IT SAYS WHEN IT CANNOT
    Every failure has its own sentence, because "camera failed" is useless on
    the one evening it matters: no device, camera held by another app, no
    permission, and a device that opened but never delivered a frame are four
    different problems with four different fixes.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "config" / "frames"

WARMUP_S  = 0.35     # let the sensor settle before anything is saved
TIMEOUT_S = 7.0      # no frame by now and it is not going to come
QUALITY   = 82

_qt = None           # cached Qt imports
_lane = None         # the object that lives on the GUI thread
_lane_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════════════════════
#  Qt, imported once and only when somebody actually needs a camera
# ══════════════════════════════════════════════════════════════════════════════
def _q():
    global _qt
    if _qt is not None:
        return _qt
    from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal, pyqtSlot
    from PyQt6.QtMultimedia import (QCamera, QMediaCaptureSession, QMediaDevices,
                                    QVideoSink)
    _qt = {
        "QObject": QObject, "QTimer": QTimer, "Qt": Qt,
        "pyqtSignal": pyqtSignal, "pyqtSlot": pyqtSlot,
        "QCamera": QCamera, "QMediaCaptureSession": QMediaCaptureSession,
        "QMediaDevices": QMediaDevices, "QVideoSink": QVideoSink,
    }
    return _qt


class _Job:
    """One request to look, and the place its answer is written."""

    __slots__ = ("done", "path", "reason", "t0")

    def __init__(self):
        self.done = threading.Event()
        self.path = None
        self.reason = ""
        self.t0 = time.monotonic()


def _make_lane():
    """The object that does the work, created where Qt wants it: the GUI thread."""
    q = _q()

    class _Lane(q["QObject"]):
        go = q["pyqtSignal"](object)

        def __init__(self):
            super().__init__()
            self.go.connect(self._run, q["Qt"].ConnectionType.QueuedConnection)
            self._cam = None
            self._sess = None
            self._sink = None
            self._job = None
            self._started = 0.0
            self._stop_timer = None

        # ── the sequence ─────────────────────────────────────────────────────
        @q["pyqtSlot"](object)
        def _run(self, job: _Job):
            self._job = job
            self._started = time.monotonic()
            try:
                cams = q["QMediaDevices"].videoInputs()
            except Exception as e:
                return self._finish(None, f"could not list cameras ({type(e).__name__})")
            if not cams:
                return self._finish(None, "no camera is connected")

            try:
                self._cam = q["QCamera"](cams[0])
                self._sink = q["QVideoSink"]()
                self._sess = q["QMediaCaptureSession"]()
                self._sess.setCamera(self._cam)
                self._sess.setVideoSink(self._sink)
                self._sink.videoFrameChanged.connect(self._on_frame)
                self._cam.errorOccurred.connect(self._on_camera_error)
            except Exception as e:
                return self._finish(None, f"the camera would not open "
                                          f"({type(e).__name__}: {e})")

            self._stop_timer = q["QTimer"].singleShot(
                int(TIMEOUT_S * 1000), self._on_timeout)
            try:
                self._cam.start()
            except Exception as e:
                return self._finish(None, f"the camera would not start "
                                          f"({type(e).__name__})")

        def _on_frame(self, frame):
            """Called for every frame. Saves exactly one, after the warm-up."""
            if self._job is None or self._job.done.is_set():
                return
            if time.monotonic() - self._started < WARMUP_S:
                return
            try:
                img = frame.toImage()
            except Exception:
                return
            if img is None or img.isNull():
                return
            # A camera that has only ever sent black is not a picture of him.
            if img.width() < 32 or img.height() < 24:
                return
            try:
                FRAMES.mkdir(parents=True, exist_ok=True)
                path = FRAMES / "last.jpg"
                if not img.save(str(path), "JPG", QUALITY):
                    return self._finish(None, "the picture could not be saved")
            except Exception as e:
                return self._finish(None, f"the picture could not be saved "
                                          f"({type(e).__name__})")
            self._finish(path, "")

        def _on_camera_error(self, err, text=""):
            if self._job is None or self._job.done.is_set():
                return
            # Busy and denied are the two that actually happen, and they are
            # the two worth naming.
            s = f"{text or ''} {err}".lower()
            if "in use" in s or "busy" in s or "occupied" in s:
                why = "another app is using the camera"
            elif "permission" in s or "denied" in s or "access" in s:
                why = "Windows has not given this app permission to use the camera"
            else:
                why = f"the camera reported a problem ({text or err})"
            self._finish(None, why)

        def _on_timeout(self):
            if self._job is None or self._job.done.is_set():
                return
            self._finish(None, "the camera opened but never sent a picture")

        def _finish(self, path, reason: str):
            job = self._job
            self._job = None
            self._teardown()
            if job is not None:
                job.path, job.reason = path, reason
                job.done.set()

        def _teardown(self):
            """Let go of the device. An LED left on is a broken promise."""
            try:
                if self._cam is not None:
                    self._cam.stop()
            except Exception:
                pass
            try:
                if self._sink is not None:
                    self._sink.videoFrameChanged.disconnect()
            except Exception:
                pass
            self._cam = self._sess = self._sink = None

    return _Lane()


def warm_up() -> bool:
    """Create the lane. Call this once, from the GUI thread, at startup.

    It is optional: `grab()` calls it lazily from whichever thread is asking,
    which is enough for a working camera but not for a perfect one — Qt would
    rather the objects be born on the thread that owns the event loop, and at
    startup we are exactly there.
    """
    global _lane
    try:
        _q()
    except Exception:
        return False
    with _lane_lock:
        if _lane is None:
            _lane = _make_lane()
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  what the rest of her asks
# ══════════════════════════════════════════════════════════════════════════════
def available() -> tuple[bool, str]:
    """(is there something to look with, and the reason when there is not)"""
    try:
        q = _q()
    except Exception as e:
        return False, f"the camera part of Qt is not installed ({type(e).__name__})"
    try:
        cams = q["QMediaDevices"].videoInputs()
    except Exception as e:
        return False, f"could not list cameras ({type(e).__name__})"
    if not cams:
        return False, "no camera is connected"
    return True, ""


def grab() -> tuple[str | None, str]:
    """One photograph. (path, "") on success, (None, why) on failure.

    The caller is expected to have already been given a yes. Nothing in this
    file asks; asking is hers and it happens in the conversation, in words.
    """
    if not available()[0]:
        return None, available()[1]
    if not warm_up() or _lane is None:
        return None, "the camera could not be set up"

    job = _Job()
    try:
        _lane.go.emit(job)          # queued: it runs on the GUI thread
    except Exception as e:
        return None, f"the camera would not take the request ({type(e).__name__})"

    if not job.done.wait(TIMEOUT_S + 3.0):
        return None, "the camera did not answer in time"
    return job.path, job.reason


def discard(path: str | None) -> None:
    """Forget the picture. Called once it has been sent, always."""
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
