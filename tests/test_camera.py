"""The camera: consent is hers, the machinery is ours.

Run:  python -m tests.test_camera      (from the mikasa/ folder)

No Qt, no webcam, no window. Qt is replaced with four stub classes that behave
the way the real ones do at the only level this module depends on: a signal
that fires, a frame that arrives, a device that can refuse. What is proved here
is the part that would otherwise be untestable until somebody's laptop:

  1. no camera           -> one honest sentence, and it returns immediately
  2. a frame arrives     -> exactly one JPEG, and the device is released after
  3. a frame never comes -> it gives up instead of waiting forever
  4. device busy         -> says *busy*, not "camera failed"
  5. black/empty frames  -> ignored, so the photo is a photo of a person
  6. the file is deleted after it has been sent

The real Qt objects are exercised on the machine that has a camera. This file
is what makes sure that when they are not there, nothing hangs.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import camera  # noqa: E402


# ── a Qt small enough to keep in one screen ─────────────────────────────────
class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, fn, *_a):
        self._slots.append(fn)

    def disconnect(self, *_a):
        self._slots.clear()

    def emit(self, *a):
        for fn in list(self._slots):
            fn(*a)


class _Proxy:
    """A piece of a QObject that is only ever a signal."""

    def __init__(self, name):
        setattr(self, name, _Signal())


class _QObject:
    def __init__(self, *a, **k):
        pass


class _Qt:
    class ConnectionType:
        QueuedConnection = 0


class _QTimer:
    def __init__(self):
        self.calls = []

    @staticmethod
    def singleShot(ms, fn):
        # The real one fires later on the event loop; the stub keeps the
        # callback so a test can decide when the clock runs out.
        _Qt.last_timeout = fn


_Qt.last_timeout = None


class _Frame:
    def __init__(self, image):
        self._img = image

    def toImage(self):
        return self._img


class _Image:
    def __init__(self, w=640, h=480, null=False, save_ok=True, sink=None):
        self._w, self._h, self._null = w, h, null
        self._save_ok, self._sink = save_ok, sink

    def width(self):
        return self._w

    def height(self):
        return self._h

    def isNull(self):
        return self._null

    def save(self, path, fmt=None, quality=None):
        if not self._save_ok:
            return False
        Path(path).write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
        if self._sink is not None:
            self._sink.append(path)
        return True


class _Camera:
    def __init__(self, dev):
        self.dev = dev
        self.started = False
        self.stopped = False
        self.errorOccurred = getattr(self, "errorOccurred", None) or _Signal()

    def start(self):
        self.started = True
        _Qt.last_camera = self

    def stop(self):
        self.stopped = True


class _Sink:
    def __init__(self):
        self.videoFrameChanged = _Signal()
        _Qt.last_sink = self


class _CaptureSession:
    def setCamera(self, cam):
        pass

    def setVideoSink(self, sink):
        pass


class _Devices:
    list: list = []

    @staticmethod
    def videoInputs():
        return list(_Devices.list)


class _Queue:
    """What a QueuedConnection looks like from the emitting thread: nothing
    happens yet. The GUI thread picks the job up later. Without this the stub
    ran the capture inside the worker thread and the test hung — which is
    exactly the bug the real signal exists to avoid."""

    def connect(self, *_a):
        pass

    def emit(self, job):
        _Qt.pending.append(job)


def _install_stub(devices=("fake-webcam",)):
    _Devices.list = list(devices)
    _Qt.last_camera = None
    _Qt.last_sink = None
    _Qt.last_timeout = None
    camera._qt = {
        "QObject": _QObject, "QTimer": _QTimer, "Qt": _Qt,
        "pyqtSignal": lambda *a: _Signal(),
        "pyqtSlot": lambda *a: (lambda fn: fn),
        "QCamera": _Camera, "QMediaCaptureSession": _CaptureSession,
        "QMediaDevices": _Devices, "QVideoSink": _Sink,
    }
    _Qt.pending = []
    camera._lane = camera._make_lane()
    camera._lane.go = _Queue()      # deferred, the way Qt defers it


def _lane_grab(job):
    """What the GUI thread would do, run right here."""
    camera._lane._run(job)


# ══════════════════════════════════════════════════════════════════════════════
#  checks
# ══════════════════════════════════════════════════════════════════════════════
_checks: list[tuple[str, callable]] = []


def check(name):
    def deco(fn):
        _checks.append((name, fn))
        return fn
    return deco


@check("no camera: one sentence, no waiting")
def _none():
    real = camera.FRAMES
    camera.FRAMES = Path(tempfile.mkdtemp())
    try:
        _install_stub(devices=())
        ok, why = camera.available()
        assert not ok and "no camera" in why, why
        t0 = time.monotonic()
        path, reason = camera.grab()
        assert path is None and "no camera" in reason, reason
        assert time.monotonic() - t0 < 1.5, "it waited for a camera that is not there"
        return why
    finally:
        camera.FRAMES = real


@check("a frame arrives: one jpeg saved, and the device is let go")
def _frame():
    real = camera.FRAMES
    camera.FRAMES = Path(tempfile.mkdtemp())
    try:
        _install_stub()
        job = camera._Job()
        _lane_grab(job)                        # starts the camera
        assert _Qt.last_camera and _Qt.last_camera.started, "camera never started"
        assert _Qt.last_sink is not None, "no sink attached"

        camera.WARMUP_S = 0.0
        saved: list = []
        _Qt.last_sink.videoFrameChanged.emit(_Frame(_Image(sink=saved)))
        assert job.done.is_set(), "the job never finished"
        assert job.path and Path(job.path).exists(), "no picture was written"
        assert saved == [str(job.path)], "not exactly one picture was taken"
        assert _Qt.last_camera.stopped, "the camera was left running — LED stays on"
        return f"one frame at {Path(job.path).name}, device stopped"
    finally:
        camera.FRAMES = real


@check("nothing arrives: it gives up instead of waiting forever")
def _timeout():
    real = camera.FRAMES
    camera.FRAMES = Path(tempfile.mkdtemp())
    try:
        _install_stub()
        job = camera._Job()
        _lane_grab(job)
        _Qt.last_timeout()                     # what the real timer would call
        assert job.done.is_set(), "the timeout did not finish the job"
        assert job.path is None and "never sent a picture" in job.reason, job.reason
        assert _Qt.last_camera.stopped, "a timeout left the camera on"
        return job.reason
    finally:
        camera.FRAMES = real


@check("device busy: it says busy, not 'camera failed'")
def _busy():
    real = camera.FRAMES
    camera.FRAMES = Path(tempfile.mkdtemp())
    try:
        _install_stub()
        job = camera._Job()
        _lane_grab(job)
        _Qt.last_camera.errorOccurred.emit(0, "camera is in use by another application")
        assert job.done.is_set(), "an error did not finish the job"
        assert "another app" in job.reason, job.reason
        return job.reason
    finally:
        camera.FRAMES = real


@check("a blank frame is not a picture of him")
def _blank():
    real = camera.FRAMES
    camera.FRAMES = Path(tempfile.mkdtemp())
    try:
        _install_stub()
        job = camera._Job()
        _lane_grab(job)
        camera.WARMUP_S = 0.0
        sink = _Qt.last_sink
        sink.videoFrameChanged.emit(_Frame(_Image(null=True)))      # dropped
        sink.videoFrameChanged.emit(_Frame(_Image(w=8, h=8)))       # dropped
        assert not job.done.is_set(), "a null frame was accepted as a photo"
        sink.videoFrameChanged.emit(_Frame(_Image(w=1280, h=720)))
        assert job.done.is_set() and job.path, "the good frame was refused too"
        return "null and 8x8 frames ignored, 1280x720 taken"
    finally:
        camera.FRAMES = real


@check("the picture is deleted once it has been sent")
def _discard():
    d = Path(tempfile.mkdtemp())
    p = d / "last.jpg"
    p.write_bytes(b"jpeg")
    camera.discard(str(p))
    assert not p.exists(), "the frame was left on disk"
    camera.discard(None)          # must not raise
    camera.discard(str(d / "nope.jpg"))
    return "file gone, and discarding nothing is safe"


@check("grab() hands the job to the GUI thread and returns")
def _threaded():
    real = camera.FRAMES
    camera.FRAMES = Path(tempfile.mkdtemp())
    try:
        _install_stub()
        out = {}

        def worker():
            out["res"] = camera.grab()       # blocks on the Event, not the GUI

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # the GUI thread would get here on its event loop
        deadline = time.monotonic() + 2.0
        while not _Qt.pending and time.monotonic() < deadline:
            time.sleep(0.01)
        assert _Qt.pending, "the job never reached the GUI thread"
        job = _Qt.pending.pop()
        camera.WARMUP_S = 0.0
        camera._lane._run(job)
        _Qt.last_sink.videoFrameChanged.emit(_Frame(_Image()))

        t.join(timeout=3.0)
        assert not t.is_alive(), "the worker thread never came back"
        path, reason = out["res"]
        assert path and not reason, (path, reason)
        return "job crossed to the GUI thread, worker returned with the picture"
    finally:
        camera.FRAMES = real
        camera.WARMUP_S = 0.35


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
