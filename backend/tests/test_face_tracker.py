"""Unit tests for the stabilized face tracker (no GPU, no torch).

The detector and OpenCV are mocked; only pure logic and the sendcmd output are
exercised. See tools/render_metrics.py for the trajectory metric tests.
"""
import json
import shutil
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

from app.core.gpu_lock import GPULockTimeout, gpu_lock

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class FakeConf:
    def __init__(self, value):
        self._v = value

    def item(self):
        return self._v


class FakeArr:
    def __init__(self, value):
        self._v = list(value)

    def tolist(self):
        return self._v


class FakeBox:
    def __init__(self, x1, y1, x2, y2, conf):
        self.xyxy = [FakeArr([x1, y1, x2, y2])]
        self.conf = [FakeConf(conf)] if conf is not None else None


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeModel:
    def __init__(self, per_frame):
        # per_frame: dict frame_index -> list of (x1,y1,x2,y2,conf)
        self.per_frame = per_frame
        self.calls = 0

    def __call__(self, frame, verbose=False, device="cuda", **kwargs):
        self.calls += 1
        # frame is an opencv image; use its object identity via a tag we set.
        tag = getattr(frame, "_tag", 0)
        boxes = [FakeBox(*b) for b in self.per_frame.get(tag, [])]
        return [FakeResult(boxes)]


class FakeCap:
    def __init__(self, n_frames, fps=30.0, width=1920, height=1080):
        self.n_frames = n_frames
        self.fps = fps
        self.width = width
        self.height = height
        self.i = 0
        self.pos_msec = 0.0

    def isOpened(self):
        return self.i < self.n_frames

    def set(self, prop, val):
        self.pos_msec = float(val)
        self.i = 0

    def get(self, prop):
        if prop == 5:  # CAP_PROP_FPS
            return self.fps
        if prop == 3:  # CAP_PROP_FRAME_WIDTH
            return self.width
        if prop == 4:  # CAP_PROP_FRAME_HEIGHT
            return self.height
        if prop == 0:  # CAP_PROP_POS_MSEC
            return self.pos_msec
        return 0.0

    def read(self):
        if self.i >= self.n_frames:
            return False, None
        frame = types.SimpleNamespace(shape=(self.height, self.width, 3))
        frame._tag = self.i
        self.i += 1
        return True, frame

    def release(self):
        pass


def install_fakes(monkeypatch, n_frames, per_frame, fps=30.0, width=1920, height=1080):
    # Injecting a detector means no YOLO weights file is needed (CI has none).
    monkeypatch.setattr(face_tracker, "_model_file_exists", lambda: True)
    fake_cv2 = types.SimpleNamespace(
        CAP_PROP_POS_MSEC=0, CAP_PROP_FPS=5, CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4, INTER_LINEAR=1,
        VideoCapture=lambda path: FakeCap(n_frames, fps, width, height),
        resize=lambda frame, size, fx=None, fy=None, interpolation=None:
            types.SimpleNamespace(
                _tag=frame._tag,
                shape=(round(frame.shape[0] * fy), round(frame.shape[1] * fx), 3),
            ),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    fake_ultralytics = types.SimpleNamespace(YOLO=lambda path: FakeModel(per_frame))
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultralytics)
    return fake_cv2, fake_ultralytics


def parse_sendcmd(path):
    out = []
    for line in Path(path).read_text().splitlines():
        m = __import__("re").match(r"\s*([\d.]+)\s+overlay\s+x\s+(-?[\d.]+)", line)
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
    return out


def overlay_to_cx(overlay_x, sf=1920 / 1080, target_width=1080):
    return (target_width / 2.0 - overlay_x) / sf


# --------------------------------------------------------------------------- spring
from app.services import face_tracker
from app.services.face_tracker import _CriticallyDampedSpring


def test_spring_inits_to_target():
    s = _CriticallyDampedSpring(omega=6.0, max_speed_px_per_s=500.0, fps=30.0)
    assert s.update(100.0) == 100.0
    assert s.pos == 100.0


def test_spring_no_overshoot_critically_damped():
    s = _CriticallyDampedSpring(omega=6.0, max_speed_px_per_s=5000.0, fps=30.0)
    s.update(0.0)  # init pos = 0
    s.pos = 0.0
    s.vel = 0.0
    target = 100.0
    max_seen = 0.0
    for _ in range(200):
        p = s.update(target)
        max_seen = max(max_seen, p)
    assert max_seen <= target + 1e-6  # critically damped: no overshoot
    assert abs(s.pos - target) < 1.0  # converges


def test_spring_speed_capped():
    s = _CriticallyDampedSpring(omega=6.0, max_speed_px_per_s=300.0, fps=30.0)
    s.update(0.0)
    s.pos = 0.0
    s.vel = 0.0
    # target steps to +1000 and stays: speed must stay <= max_speed px/s
    per_frame = []
    for _ in range(30):
        p = s.update(1000.0)
        per_frame.append(p)
    diffs = [abs(per_frame[i] - per_frame[i - 1]) for i in range(1, len(per_frame))]
    assert max(diffs) <= 300.0 / 30.0 + 1e-6  # max_speed * dt


# --------------------------------------------------------------------------- target selection
from app.services.face_tracker import _select_target


def face(x1, y1, x2, y2, conf=0.8):
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "area": (x2 - x1) * (y2 - y1), "conf": conf,
            "cx": x1 + (x2 - x1) / 2.0}


def test_select_target_prefers_largest():
    state = {"target": None, "since": 0.0}
    chosen = _select_target([face(0, 0, 100, 100), face(400, 0, 600, 200)], 0.0, state)
    assert chosen["cx"] == 500.0  # larger face (area 40000 vs 10000)


def test_select_target_hysteresis_dwells():
    state = {"target": None, "since": 0.0}
    cur = face(0, 0, 200, 200, conf=0.8)  # cx 100, area 40000
    state["target"] = cur
    state["since"] = 0.0
    # New clearly-larger face (cx 900, area 90000) but not yet dwelled 1.5s
    new_big = face(800, 0, 1000, 300, conf=0.9)  # cx 900, area 90000
    chosen = _select_target([cur, new_big], 0.5, state)
    assert chosen is cur  # not yet switched (dwell)
    # After MIN_DWELL seconds it switches
    chosen = _select_target([cur, new_big], 2.0, state)
    assert chosen is new_big


def test_select_target_same_face_returns_current_detection():
    state = {"target": None, "since": 0.0}
    cur = face(0, 0, 200, 200)  # cx 100
    _ = _select_target([cur], 0.0, state)
    # Face drifts slightly but stays within SAME_TARGET_PX -> same identity,
    # but must return the CURRENT position (not the stale object).
    drifted = face(30, 0, 230, 200)  # cx 130, within 70 of cur
    chosen2 = _select_target([drifted], 0.5, state)
    assert chosen2["cx"] == 130.0  # follows current detection
    assert state["target"] is drifted  # the last matched position is stored
    assert state["since"] == 0.0  # matching does not restart the dwell clock


def test_select_target_follows_face_drifting_5px_per_frame():
    state = {"target": None, "since": 0.0}
    _ = _select_target([face(0, 0, 200, 200)], 0.0, state)  # cx 100
    current = None
    for i in range(1, 41):
        x = i * 5.0
        current = face(x, 0, x + 200, 200)
        chosen = _select_target([current], i / 30.0, state)
        assert chosen is current
        assert chosen["cx"] == 100.0 + x
    assert state["target"] is current
    assert state["since"] == 0.0


def test_select_target_other_face_slightly_larger_returns_current_detection():
    state = {"target": None, "since": 0.0}
    _ = _select_target([face(0, 0, 200, 200)], 0.0, state)  # cx 100, area 40000
    moved = face(5, 0, 205, 200)  # current target detection: cx 105
    other = face(800, 0, 1000, 220)  # cx 900, area 44000 (< 1.25 * 40000)
    chosen = _select_target([moved, other], 0.5, state)
    assert chosen is moved  # current detection of the target, not a stale bbox
    assert chosen["cx"] == 105.0
    assert state["target"] is moved
    assert state["since"] == 0.0


# --------------------------------------------------------------------------- cut detection
from app.services.face_tracker import detect_cuts


def _fake_subprocess(monkeypatch, stderr_text, commands=None, returncode=0):
    class Proc:
        pass

    def run(cmd, capture_output=True, text=True, timeout=120, check=False):
        if commands is not None:
            commands.append(cmd)
        proc = Proc()
        proc.returncode = returncode
        proc.stderr = stderr_text
        return proc
    monkeypatch.setattr(subprocess, "run", run)


def test_detect_cuts_uses_info_loglevel_with_nostats(monkeypatch, tmp_path):
    monkeypatch.setattr(face_tracker, "FACE_CUT_CACHE_DIR", tmp_path / "cuts")
    commands: list[list[str]] = []
    # Line shape copied from real ffmpeg showinfo output (see the real-FFmpeg
    # test below): the parser needs both "n:" and "pts_time:".
    stderr = (
        '[Parsed_showinfo_1 @ 0] n:   0 pts: 15360 pts_time:3.500 duration: 512\n'
        '[Parsed_showinfo_1 @ 0] n:   1 pts: 20480 pts_time:6.750 duration: 512\n'
    )
    _fake_subprocess(monkeypatch, stderr, commands=commands)
    cuts = detect_cuts("src.webm", 0.0, 10.0, 0.3)
    assert cuts == [3.5, 6.75]
    assert commands[0][commands[0].index("-loglevel") + 1] == "info"
    assert "-nostats" in commands[0]


def _make_cut_video(tmp_path: Path) -> Path:
    """Build a 2 s source with one hard cut at t=1.0 s using real ffmpeg."""
    ffmpeg = face_tracker._ffmpeg()
    if shutil.which(ffmpeg) is None and not Path(ffmpeg).exists():
        pytest.skip("ffmpeg is required for the real scene-detection test")
    video = tmp_path / "cut_source.mp4"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=320x240:r=30:d=1",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=30:d=1",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    return video


def test_detect_cuts_real_ffmpeg_hard_cut(monkeypatch, tmp_path):
    """No hand-written stderr: parse the real showinfo output of a hard cut."""
    monkeypatch.setattr(face_tracker, "FACE_CUT_CACHE_DIR", tmp_path / "cuts")
    video = _make_cut_video(tmp_path)
    cuts = detect_cuts(str(video), 0.0, 2.0, 0.3)
    assert cuts, "real ffmpeg scene detection found no cuts"
    assert any(abs(c - 1.0) <= 0.2 for c in cuts), cuts


def test_detect_cuts_cached(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cuts"
    monkeypatch.setattr(face_tracker, "FACE_CUT_CACHE_DIR", cache_dir)
    calls = {"n": 0}

    def run(cmd, capture_output=True, text=True, timeout=120, check=False):
        calls["n"] += 1
        class Proc:
            returncode = 0
            stderr = '[Parsed_showinfo_1 @ 0] n:   0 pts: 15360 pts_time:2.000 duration: 512\n'
        return Proc()
    monkeypatch.setattr(subprocess, "run", run)
    assert detect_cuts("src.webm", 0.0, 10.0, 0.3) == [2.0]
    assert detect_cuts("src.webm", 0.0, 10.0, 0.3) == [2.0]  # cached
    assert calls["n"] == 1


def test_detect_cuts_failed_scan_is_not_cached(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cuts"
    monkeypatch.setattr(face_tracker, "FACE_CUT_CACHE_DIR", cache_dir)
    calls = {"n": 0}

    def run(cmd, capture_output=True, text=True, timeout=120, check=False):
        calls["n"] += 1
        class Proc:
            returncode = 1
            stderr = '[Parsed_showinfo_1 @ 0] n:   0 pts_time:2.000\n'
        return Proc()
    monkeypatch.setattr(subprocess, "run", run)
    assert detect_cuts("src.webm", 0.0, 10.0, 0.3) == []
    assert not list(cache_dir.glob("*.json"))
    assert detect_cuts("src.webm", 0.0, 10.0, 0.3) == []
    assert calls["n"] == 2


# --------------------------------------------------------------------------- end-to-end: cut reset in generate_sendcmd_file
def test_sendcmd_resets_at_shot_cut(monkeypatch, tmp_path):
    # Two shots: face at cx=500 (shot 1), cut at 1.0s, face at cx=1500 (shot 2).
    # (cx must stay within [cx_min, cx_max] = [303.75, 1616.25] for 1920x1080.)
    n_frames = 60  # 2 s @ 30 fps
    cut_frame = 30
    per_frame = {}
    for i in range(n_frames):
        cx = 500.0 if i < cut_frame else 1500.0
        per_frame[i] = [(cx - 100, 400, cx + 100, 600, 0.9)]
    install_fakes(monkeypatch, n_frames, per_frame, fps=30.0)
    # Force a cut at 1.0 s (frame 30).
    monkeypatch.setattr(face_tracker, "detect_cuts",
                        lambda vp, s, d, th: [1.0])

    sendcmd = tmp_path / "cut_test.txt"
    ok = face_tracker.generate_sendcmd_file(
        "src.webm", 0.0, 2.0, str(sendcmd), target_width=1080, debug=False)
    assert ok is True
    samples = parse_sendcmd(sendcmd)
    assert len(samples) == n_frames

    def cx_at(frame_index):
        _t, ov = samples[frame_index]
        return overlay_to_cx(ov)

    # Just before the cut the crop follows shot 1 (cx ~500).
    assert abs(cx_at(cut_frame - 1) - 500.0) < 60.0
    # Just after the cut the crop re-acquires shot 2's face (cx ~1500), it does
    # NOT hold shot 1's position across the cut.
    assert abs(cx_at(cut_frame + 1) - 1500.0) < 100.0, samples[cut_frame:cut_frame + 6]
    # The crop moves (not flat across the cut).
    assert abs(cx_at(cut_frame + 1) - cx_at(cut_frame - 1)) > 100.0


# --------------------------------------------------------------------------- fallback files
def _assert_center_fallback(sendcmd: Path) -> None:
    samples = parse_sendcmd(sendcmd)
    assert samples
    assert samples[0] == (0.0, -1166.67)
    assert len(samples) == 30  # 1 s @ 30 fps


def test_model_missing_writes_center_fallback(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    monkeypatch.setattr(face_tracker, "_model_file_exists", lambda: False)
    sendcmd = tmp_path / "fallback_model.txt"
    sendcmd.write_text("0.000 overlay x -9999.00;\n")  # stale from an earlier render
    assert face_tracker.generate_sendcmd_file(
        "src.webm", 0.0, 1.0, str(sendcmd)) is False
    _assert_center_fallback(sendcmd)


def test_capture_not_opened_writes_center_fallback(monkeypatch, tmp_path):
    install_fakes(monkeypatch, 0, {}, fps=30.0)  # FakeCap.isOpened() is False
    monkeypatch.setattr(face_tracker, "detect_cuts", lambda *a, **k: [])
    sendcmd = tmp_path / "fallback_cap.txt"
    sendcmd.write_text("0.000 overlay x -9999.00;\n")
    assert face_tracker.generate_sendcmd_file(
        "src.webm", 0.0, 1.0, str(sendcmd)) is False
    _assert_center_fallback(sendcmd)


def test_detect_cuts_runs_without_holding_gpu_lock(monkeypatch, tmp_path):
    """A different thread must be able to take the GPU lock during the scan."""
    install_fakes(monkeypatch, 30, {}, fps=30.0)
    lock_free: list[bool] = []

    def fake_detect_cuts(*args, **kwargs):
        def probe():
            try:
                with gpu_lock("test:probe-during-cut-scan", timeout=0.3):
                    lock_free.append(True)
            except GPULockTimeout:
                lock_free.append(False)

        thread = threading.Thread(target=probe, daemon=True)
        thread.start()
        thread.join(timeout=2)
        return []

    monkeypatch.setattr(face_tracker, "detect_cuts", fake_detect_cuts)
    sendcmd = tmp_path / "lock_probe.txt"
    assert face_tracker.generate_sendcmd_file(
        "src.webm", 0.0, 1.0, str(sendcmd)) is True
    assert lock_free == [True]


def test_upscaled_detections_are_mapped_back_to_source_pixels(monkeypatch, tmp_path):
    width, height = 854, 480
    scale = 640.0 / 480.0
    # Detector sees the upscaled frame; these boxes are in inference pixels.
    per_frame = {0: [(640, 320, 960, 640, 0.9)]}
    install_fakes(monkeypatch, 30, per_frame, width=width, height=height)
    monkeypatch.setattr(face_tracker, "FACE_MODEL_UPSCALE_SMALL", True)
    monkeypatch.setattr(face_tracker, "detect_cuts", lambda *a, **k: [])

    sendcmd = tmp_path / "upscale.txt"
    assert face_tracker.generate_sendcmd_file(
        "src.webm", 0.0, 1.0, str(sendcmd)) is True
    records = json.loads(sendcmd.with_suffix(".track.json").read_text())
    expected_bbox = [round(v / scale, 1) for v in (640, 320, 960, 640)]
    assert records[0]["bbox"] == expected_bbox
    assert abs(records[0]["crop_center_x"] - 600.0) < 2.0
    overlay_x = parse_sendcmd(sendcmd)[0][1]
    assert abs(overlay_to_cx(overlay_x, sf=1920.0 / height) - 600.0) < 2.0

