"""Per-shot wide-shot zoom: pure math + graph strings + one CI-safe FFmpeg render."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app.core.config import FFMPEG_PATH
from app.services import edit_compiler, face_tracker
from app.services.edit_compiler import compile_plan, first_sendcmd_overlay_x
from app.services.face_tracker import (
    compute_zoom_window,
    generate_zoom_sendcmd_file,
    plan_shot_zooms,
)

SRC_W, SRC_H = 1920, 1080
OUT_W, OUT_H = 1080, 1920


# --------------------------------------------------------------------------- pure math

def test_wide_shot_zoom_is_capped_by_upscale_limit():
    # 90px face in a 1080p source = 8.3% of output height. Reaching 18% would
    # need 2.16x, but 3.0x total upscale / 1.778x base = 1.69x max extra zoom.
    w = compute_zoom_window(90.0, 960.0, 500.0, SRC_W, SRC_H)
    assert w.zoom == pytest.approx(3.0 / (OUT_H / SRC_H), abs=1e-3)
    assert w.effective_upscale == pytest.approx(3.0, abs=0.01)
    assert w.capped_by == "max_upscale"
    assert 600 <= w.crop_w <= 700                 # 1080 / 1.6875 ~ 640
    assert w.crop_h < OUT_H


def test_no_cap_label_when_required_zoom_is_below_both_caps():
    # 90px face needs 2.16x; with generous caps nothing binds.
    w = compute_zoom_window(90.0, 960.0, 500.0, SRC_W, SRC_H,
                            max_zoom=3.0, max_upscale=10.0)
    assert w.zoom == pytest.approx(2.16, abs=1e-3)
    assert w.capped_by is None


def test_close_up_is_unchanged():
    # 250px / 1080 = 23% > 18% target -> no zoom at all.
    w = compute_zoom_window(250.0, 1200.0, 600.0, SRC_W, SRC_H)
    assert w.zoom == 1.0
    assert (w.crop_w, w.crop_h, w.crop_x, w.crop_y) == (OUT_W, OUT_H, 0, 0)
    assert w.capped_by is None
    assert w.effective_upscale == pytest.approx(OUT_H / SRC_H, abs=1e-3)


def test_max_zoom_cap_applies_for_very_generous_upscale_budget():
    w = compute_zoom_window(30.0, 960.0, 500.0, SRC_W, SRC_H,
                            max_zoom=2.0, max_upscale=100.0)
    assert w.zoom == pytest.approx(2.0)
    assert w.capped_by == "max_zoom"


def test_headroom_and_clamping_keep_window_inside_frame():
    # Face at the top-left corner: window must not go negative.
    w = compute_zoom_window(90.0, 10.0, 10.0, SRC_W, SRC_H)
    assert w.crop_x >= 0 and w.crop_y >= 0
    assert w.crop_x <= OUT_W - w.crop_w
    assert w.crop_y <= OUT_H - w.crop_h
    assert w.crop_w % 2 == 0 and w.crop_h % 2 == 0
    assert abs(w.crop_w / w.crop_h - OUT_W / OUT_H) < 0.01


def test_smaller_source_has_tighter_upscale_cap():
    w = compute_zoom_window(80.0, 640.0, 300.0, 1280, 720)
    # base upscale 1920/720 = 2.667 -> extra zoom capped at 3.0/2.667 = 1.125.
    assert w.zoom == pytest.approx(1.125, abs=1e-3)
    assert w.capped_by == "max_upscale"


def test_centered_face_lands_at_window_center_after_overlay_pan():
    # 3840x2160 source, 180px face, zoom capped at 2.0. The base crop pans the
    # centered face to x=540 of the vertical frame; the zoom window must follow.
    src_w, src_h = 3840, 2160
    face_h, face_cx = 180.0, src_w / 2.0
    base_scale = OUT_H / float(src_h)
    pan = OUT_W / 2.0 - face_cx * base_scale
    w = compute_zoom_window(face_h, face_cx, src_h / 2.0, src_w, src_h, pan_x=pan)
    assert w.zoom == pytest.approx(2.0)
    face_x_in_frame = face_cx * base_scale + pan
    assert face_x_in_frame == pytest.approx(OUT_W / 2.0, abs=1)
    assert w.crop_x + w.crop_w / 2.0 == pytest.approx(face_x_in_frame, abs=1)


def test_edge_clamped_face_keeps_window_inside_frame():
    # A face near the left edge cannot be centred by the overlay: the base
    # crop clamps its pan to 0. The zoom window must clamp inside 0..1080 too.
    src_w, src_h = 3840, 2160
    face_cx = 100.0
    base_scale = OUT_H / float(src_h)
    pan = max(OUT_W - src_w * base_scale, min(0.0, OUT_W / 2.0 - face_cx * base_scale))
    assert pan == 0.0
    w = compute_zoom_window(180.0, face_cx, src_h / 2.0, src_w, src_h, pan_x=pan)
    assert w.crop_x == 0
    assert 0 <= w.crop_x <= OUT_W - w.crop_w


def test_plan_shot_zooms_uses_one_window_per_shot():
    records = [
        {"time": 0.0, "sampled": True, "detected": True,
         "bbox": [910.0, 460.0, 1010.0, 540.0]},
        {"time": 2.0, "sampled": True, "detected": True,
         "bbox": [910.0, 460.0, 1010.0, 540.0]},
    ]
    windows = plan_shot_zooms(records, [1.0], 3.0, SRC_W, SRC_H)
    assert len(windows) == 2
    assert all(w.zoom > 1.0 for w in windows)


# --------------------------------------------------------------------------- graph strings

def test_filtergraph_zoom_stage_is_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(edit_compiler, "RENDERS_DIR", tmp_path)
    (tmp_path / "crop.txt").write_text("0.000 overlay x -1166.67;\n", encoding="utf-8")
    plain = compile_plan([], "center_crop", "subs.ass", sendcmd_path="crop.txt")[0]
    assert "crop@zc" not in plain and "concat=n=" not in plain

    shots = [
        {"start": 0.0, "end": 1.0, "crop": [640, 1138, 220, 300]},
        {"start": 1.0, "end": 2.0, "crop": [1080, 1920, 0, 0]},
    ]
    zoomed = compile_plan(
        [], "center_crop", "subs.ass", sendcmd_path="crop.txt",
        zoom_shots=shots,
    )[0]
    assert "crop@zc" not in zoomed and "sendcmd=f='zoom.txt'" not in zoomed
    assert "crop=1080:1920:0:0[vbase];[vbase]split=2[zsrc0][zsrc1]" in zoomed
    assert "[zsrc0]trim=start=0.000:end=1.000,setpts=PTS-STARTPTS,crop=640:1138:220:300,scale=1080:1920,setsar=1[zseg0]" in zoomed
    assert "[zsrc1]trim=start=1.000,setpts=PTS-STARTPTS,crop=1080:1920:0:0,scale=1080:1920,setsar=1[zseg1]" in zoomed
    assert "[zseg0][zseg1]concat=n=2:v=1:a=0[out_v]" in zoomed
    assert zoomed.count("sendcmd=f=") == 1          # pan only; no zoom sendcmd
    assert "color" not in zoomed


def test_zoom_plan_shots_become_fixed_crops(monkeypatch, tmp_path):
    """Each plan shot must contribute one fixed crop, never a runtime resize."""
    monkeypatch.setattr(face_tracker, "detect_cuts", lambda *a, **k: [1.0])
    monkeypatch.setattr(face_tracker, "_source_dimensions", lambda p: (SRC_W, SRC_H))
    records = [
        {"time": t, "sampled": True, "detected": True,
         "bbox": [910.0, 460.0, 1010.0, 540.0]}
        for t in (0.2, 0.8, 1.2, 1.8)
    ]
    crop = tmp_path / "crop.txt"
    crop.write_text("0.000 overlay x -100.00;\n1.000 overlay x -100.00;\n", encoding="utf-8")
    (tmp_path / "crop.track.json").write_text(json.dumps(records), encoding="utf-8")
    zoom = tmp_path / "zoom.txt"
    plan = generate_zoom_sendcmd_file(
        str(crop), "src.mp4", 0.0, 2.0, str(zoom),
    )
    assert plan.active and len(plan.shots) == 2
    vf = compile_plan(
        [], "center_crop", "subs.ass", sendcmd_path="crop.txt",
        zoom_shots=plan.shots,
    )[0]
    for shot in plan.shots:
        w, h, x, y = shot["crop"]
        assert f"crop={w}:{h}:{x}:{y},scale=1080:1920,setsar=1" in vf
    assert "crop@zc" not in vf


# --------------------------------------------------------------------------- real FFmpeg

def _tool(name: str):
    found = shutil.which(name)
    if found:
        return found
    ffmpeg = Path(str(FFMPEG_PATH))
    sibling = ffmpeg.with_name(name + ffmpeg.suffix)
    return str(sibling) if sibling.exists() else None


HAVE_TOOLS = _tool("ffmpeg") is not None and _tool("ffprobe") is not None


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, cwd=str(cwd), capture_output=True,
                          text=True, timeout=120)


def _install_fake_detector(monkeypatch):
    """Small face (80px) so the zoom path actually engages; no model/GPU."""
    monkeypatch.setattr(face_tracker, "_model_file_exists", lambda: True)
    monkeypatch.setattr(face_tracker, "detect_cuts", lambda *a, **k: [1.5])

    class Arr:
        def __init__(self, value):
            self.value = list(value)

        def tolist(self):
            return self.value

    class Box:
        def __init__(self):
            self.xyxy = [Arr([600.0, 400.0, 760.0, 480.0])]
            self.conf = [types.SimpleNamespace(item=lambda: 0.9)]

    class Result:
        def __init__(self):
            self.boxes = [Box()]

    class Model:
        def __call__(self, *a, **k):
            return [Result()]

    class Cap:
        def __init__(self, *a, **k):
            self.i = 0

        def isOpened(self):
            return self.i < 90

        def set(self, *a, **k):
            pass

        def get(self, prop):
            return {5: 30.0, 3: 1920, 4: 1080, 0: 0.0}.get(prop, 0.0)

        def read(self):
            self.i += 1
            return True, types.SimpleNamespace()

        def release(self):
            pass

    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace(
        CAP_PROP_POS_MSEC=0, CAP_PROP_FPS=5, CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4, VideoCapture=Cap,
    ))
    monkeypatch.setitem(sys.modules, "ultralytics",
                        types.SimpleNamespace(YOLO=lambda path: Model()))


@pytest.mark.skipif(not HAVE_TOOLS, reason="ffmpeg/ffprobe are required")
def test_zoom_render_stays_vertical_with_audio(monkeypatch, tmp_path):
    src = tmp_path / "src.mp4"
    made = _run([
        _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "3", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src),
    ], tmp_path)
    assert made.returncode == 0, made.stderr

    _install_fake_detector(monkeypatch)
    crop = tmp_path / "crop.txt"
    assert face_tracker.generate_sendcmd_file(str(src), 0.0, 3.0, str(crop)) is True

    zoom = tmp_path / "zoom.txt"
    plan = generate_zoom_sendcmd_file(
        crop_sendcmd_path=str(crop), video_path=str(src),
        start_time=0.0, duration=3.0, sendcmd_path=str(zoom),
        report_path=str(tmp_path / "zoom.json"),
    )
    assert plan.active and len(plan.shots) == 2
    assert "crop@zc w" in zoom.read_text(encoding="utf-8")

    (tmp_path / "subs.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,125\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
        encoding="utf-8",
    )
    vf = compile_plan(
        [], "center_crop", "subs.ass", sendcmd_path="crop.txt",
        zoom_shots=plan.shots,
    )[0]
    assert "crop@zc" not in vf and "concat=n=2:v=1:a=0" in vf
    out = tmp_path / "out.mp4"
    rendered = _run([
        _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-t", "3", "-filter_complex", vf,
        "-map", "[out_final]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ], tmp_path)
    assert rendered.returncode == 0, rendered.stderr

    dims = _run([
        _tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out),
    ], tmp_path)
    assert dims.stdout.strip().split(",")[:2] == [str(OUT_W), str(OUT_H)]
    audio = _run([
        _tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(out),
    ], tmp_path)
    assert audio.stdout.strip(), "no audio stream"
    decoded = _run([_tool("ffmpeg"), "-v", "error", "-i", str(out), "-f", "null", "-"], tmp_path)
    assert decoded.returncode == 0 and decoded.stderr.strip() == "", decoded.stderr
    report = json.loads((tmp_path / "zoom.json").read_text(encoding="utf-8"))
    assert report["shots"][0]["zoom"] == pytest.approx(1.125, abs=1e-3)


def _install_multishot_detector(monkeypatch):
    """Fake detector: wide (80px) / close-up (250px) / wide, no model or GPU."""
    monkeypatch.setattr(face_tracker, "_model_file_exists", lambda: True)
    monkeypatch.setattr(face_tracker, "detect_cuts", lambda *a, **k: [1.5, 3.0])

    class Arr:
        def __init__(self, value):
            self.value = list(value)

        def tolist(self):
            return self.value

    class Box:
        def __init__(self, half_h):
            self.xyxy = [Arr([960.0 - 40.0, 540.0 - half_h,
                              960.0 + 40.0, 540.0 + half_h])]
            self.conf = [types.SimpleNamespace(item=lambda: 0.9)]

    class Result:
        def __init__(self, half_h):
            self.boxes = [Box(half_h)]

    class Model:
        def __init__(self):
            self.i = 0

        def __call__(self, *a, **k):
            frame = self.i
            self.i += 1
            half_h = 125.0 if 45 <= frame < 90 else 40.0
            return [Result(half_h)]

    class Cap:
        def __init__(self, *a, **k):
            self.i = 0

        def isOpened(self):
            return self.i < 135

        def set(self, *a, **k):
            pass

        def get(self, prop):
            return {5: 30.0, 3: 1920, 4: 1080, 0: 0.0}.get(prop, 0.0)

        def read(self):
            self.i += 1
            return True, types.SimpleNamespace()

        def release(self):
            pass

    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace(
        CAP_PROP_POS_MSEC=0, CAP_PROP_FPS=5, CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4, VideoCapture=Cap,
    ))
    monkeypatch.setitem(sys.modules, "ultralytics",
                        types.SimpleNamespace(YOLO=lambda path: Model()))


def _raw_frame_at(ffmpeg: str, video: Path, seconds: float, cwd: Path) -> bytes:
    proc = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(video), "-ss", f"{seconds:.3f}",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, timeout=120, cwd=str(cwd), check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _probe_video(ffprobe: str, path: Path, cwd: Path) -> tuple[int, float]:
    """Return (decoded frame count, duration) of a video stream."""
    proc = _run([
        ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=nb_read_frames,duration", "-of", "json", str(path),
    ], cwd)
    assert proc.returncode == 0, proc.stderr
    stream = json.loads(proc.stdout)["streams"][0]
    return int(stream["nb_read_frames"]), float(stream["duration"])


# Spatial markers: a coloured block at a known source position in each shot.
# "green" in FFmpeg is 0x008000, so use "lime" for pure 0x00ff00.
MARKER_CX, MARKER_CY = 960.0, 470.0
SHOT_COLORS = ("red", "lime", "blue")
SHOT_TIMES = (0.75, 2.25, 3.75)


def _marker_centroid(frame: bytes, color: str) -> tuple[float, float] | None:
    """Locate a marker block in an rgb24 frame; sample every other pixel."""
    xs: list[int] = []
    ys: list[int] = []
    for y in range(0, OUT_H, 2):
        row = y * OUT_W * 3
        for x in range(0, OUT_W, 2):
            i = row + x * 3
            r, g, b = frame[i], frame[i + 1], frame[i + 2]
            hit = (
                (color == "red" and r > 150 and g < 100 and b < 100)
                or (color == "lime" and g > 150 and r < 100 and b < 100)
                or (color == "blue" and b > 150 and r < 100 and g < 100)
            )
            if hit:
                xs.append(x); ys.append(y)
    if not xs:
        return None
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _expected_marker_position(shot: dict, pan: float) -> tuple[float, float]:
    """Where the marker must land after the base pan and this shot's crop."""
    w, h, x, y = shot["crop"]
    base_scale = OUT_H / float(SRC_H)
    vx = MARKER_CX * base_scale + pan
    vy = MARKER_CY * base_scale
    return (vx - x) * OUT_W / float(w), (vy - y) * OUT_H / float(h)


def _marker_in_frame(centroid: tuple[float, float] | None,
                     expected: tuple[float, float], tol: float = 8.0) -> bool:
    return bool(centroid) and abs(centroid[0] - expected[0]) <= tol \
        and abs(centroid[1] - expected[1]) <= tol


def _make_marker_multishot(ffmpeg: str, cwd: Path) -> Path:
    """3 x 1.5 s 1920x1080 shots (wide/close-up/wide) with distinct markers."""
    shots: list[Path] = []
    for i, color in enumerate(SHOT_COLORS):
        shot = cwd / f"shot_{i}.mp4"
        made = _run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30:d=1.5",
            "-vf", f"drawbox=x=900:y=430:w=120:h=80:color={color}:t=fill",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(shot),
        ], cwd)
        assert made.returncode == 0, made.stderr
        shots.append(shot)
    src = cwd / "multishot.mp4"
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for shot in shots:
        cmd += ["-i", str(shot)]
    cmd += [
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:d=4.5",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(src),
    ]
    made = _run(cmd, cwd)
    assert made.returncode == 0, made.stderr
    return src


def _render_zoom(ffmpeg: str, vf: str, cwd: Path, out: Path, duration: float):
    return _run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(cwd / "multishot.mp4"), "-t", f"{duration:.3f}",
        "-filter_complex", vf, "-map", "[out_final]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ], cwd)


@pytest.mark.skipif(not HAVE_TOOLS, reason="ffmpeg/ffprobe are required")
def test_zoom_render_fixed_crops_geometric_and_temporal(monkeypatch, tmp_path):
    """Real render of wide / close-up / wide shots with DIFFERENT crop sizes.

    Checks 1080x1920 output, frame count + duration against the source, a clean
    FFmpeg log and the spatial position of a known marker in every shot. A
    negative control re-renders with the crop updates disabled and verifies the
    geometric check actually fails in that case.
    """
    ffmpeg, ffprobe = _tool("ffmpeg"), _tool("ffprobe")
    src = _make_marker_multishot(ffmpeg, tmp_path)

    _install_multishot_detector(monkeypatch)
    crop = tmp_path / "crop.txt"
    assert face_tracker.generate_sendcmd_file(str(src), 0.0, 4.5, str(crop)) is True
    zoom = tmp_path / "zoom.txt"
    plan = generate_zoom_sendcmd_file(
        crop_sendcmd_path=str(crop), video_path=str(src),
        start_time=0.0, duration=4.5, sendcmd_path=str(zoom),
        report_path=str(tmp_path / "zoom.json"),
    )
    assert plan.active and len(plan.shots) == 3
    assert [s["zoom"] > 1.0 for s in plan.shots] == [True, False, True]
    crops = [s["crop"] for s in plan.shots]
    assert crops[0] != crops[1] and crops[1] != crops[2]

    (tmp_path / "subs.ass").write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,125\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
        encoding="utf-8",
    )
    vf = compile_plan(
        [], "center_crop", "subs.ass", sendcmd_path="crop.txt",
        zoom_shots=plan.shots,
    )[0]
    assert "crop@zc" not in vf and "sendcmd=f='zoom.txt'" not in vf
    assert vf.count("concat=n=3:v=1:a=0") == 1
    for w, h, x, y in crops:
        assert f"crop={w}:{h}:{x}:{y},scale=1080:1920,setsar=1" in vf

    out = tmp_path / "out.mp4"
    rendered = _render_zoom(ffmpeg, vf, tmp_path, out, 4.5)
    assert rendered.returncode == 0, rendered.stderr
    low = rendered.stderr.lower()
    for bad in ("no such filter", "no option name", "error parsing a filter",
                "error initializing filters", "error reinitializing filters",
                "failed to configure", "could not find command target",
                "unable to parse option value", "error"):
        assert bad not in low, (bad, rendered.stderr[-1500:])

    dims = _run([
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out),
    ], tmp_path)
    assert dims.stdout.strip().split(",")[:2] == [str(OUT_W), str(OUT_H)]
    audio = _run([
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(out),
    ], tmp_path)
    assert audio.stdout.strip(), "no audio stream"
    src_frames, src_duration = _probe_video(ffprobe, src, tmp_path)
    out_frames, out_duration = _probe_video(ffprobe, out, tmp_path)
    assert out_frames == src_frames, (out_frames, src_frames)
    assert abs(out_duration - src_duration) <= 0.1, (out_duration, src_duration)

    pan = float(first_sendcmd_overlay_x(str(crop)))
    for shot, t, color in zip(plan.shots, SHOT_TIMES, SHOT_COLORS):
        centroid = _marker_centroid(_raw_frame_at(ffmpeg, out, t, tmp_path), color)
        expected = _expected_marker_position(shot, pan)
        assert _marker_in_frame(centroid, expected), (color, centroid, expected)

    # Negative control: with crop updates disabled every shot keeps the first
    # full-frame window, so the zoomed shots' markers land in the wrong place.
    plain_vf = compile_plan(
        [], "center_crop", "subs.ass", sendcmd_path="crop.txt",
    )[0]
    plain_out = tmp_path / "plain.mp4"
    plain_render = _render_zoom(ffmpeg, plain_vf, tmp_path, plain_out, 4.5)
    assert plain_render.returncode == 0, plain_render.stderr
    failed: list[tuple[int, tuple[float, float] | None, tuple[float, float]]] = []
    for i, (shot, t, color) in enumerate(zip(plan.shots, SHOT_TIMES, SHOT_COLORS)):
        centroid = _marker_centroid(_raw_frame_at(ffmpeg, plain_out, t, tmp_path), color)
        expected = _expected_marker_position(shot, pan)
        if not _marker_in_frame(centroid, expected):
            failed.append((i, centroid, expected))
    print(f"[negative control] shots failing geometric check with crop updates "
          f"disabled: {len(failed)}/3 -> {failed}")
    assert failed, "disabling the crop updates did not fail the geometric check"
