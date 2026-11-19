"""Layout render checks: filtergraph string invariants + real FFmpeg smoke tests.

The renderer builds two filtergraphs in ``compile_plan``:

* ``center_crop`` - video-as-overlay-main + sendcmd pan, cropped to the
  vertical target (this is the graph the black-frame fix rewrote).
* ``split_screen`` - the fallback branch used by every other layout name:
  two stacked halves joined with ``vstack``.

Each layout gets a string-level assertion of the generated graph (no colour
source as the overlay main, explicit target geometry, and - where an overlay
exists - a numeric initial x seed) plus one real FFmpeg render of a short
synthetic 16:9 clip with a tone, asserted to be 1080x1920, to decode cleanly,
to have a non-black first frame and to carry an audio stream. The detector is
injected as a fake for the layout that uses it, so no torch/GPU/model file is
needed - these tests run in the lightweight CI job.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from app.core.config import FFMPEG_PATH
from app.services import edit_compiler, face_tracker
from app.services.edit_compiler import compile_plan

LAYOUTS = ("center_crop", "split_screen")
TARGET_W, TARGET_H = 1080, 1920

_MINIMAL_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,45,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,345,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,HELLO
"""


def _ffmpeg_bin() -> str:
    configured = str(FFMPEG_PATH)
    if configured and configured != "ffmpeg" and Path(configured).exists():
        return configured
    return shutil.which("ffmpeg") or "ffmpeg"


def _tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    ffmpeg = Path(_ffmpeg_bin())
    sibling = ffmpeg.with_name(name + ffmpeg.suffix)
    return str(sibling) if sibling.exists() else None


HAVE_TOOLS = _tool("ffmpeg") is not None and _tool("ffprobe") is not None


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, check=False, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, timeout=120,
    )


def _make_source(tmp_path: Path) -> Path:
    """3 s 1280x720 testsrc2 with a 440 Hz tone (16:9 + audio)."""
    src = tmp_path / "src.mp4"
    proc = _run([
        _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
        "-t", "3", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src),
    ])
    assert proc.returncode == 0, proc.stderr
    return src


def _install_fake_detector(monkeypatch, n_frames: int = 90, cx: float = 960.0) -> None:
    """Inject cv2/ultralytics fakes so generate_sendcmd_file needs no model."""
    monkeypatch.setattr(face_tracker, "_model_file_exists", lambda: True)

    class FakeArr:
        def __init__(self, value) -> None:
            self.value = list(value)

        def tolist(self):
            return self.value

    class FakeBox:
        def __init__(self) -> None:
            self.xyxy = [FakeArr([cx - 100, 400, cx + 100, 600])]
            self.conf = [types.SimpleNamespace(item=lambda: 0.9)]

    class FakeResult:
        def __init__(self) -> None:
            self.boxes = [FakeBox()]

    class FakeModel:
        def __call__(self, *args, **kwargs):
            return [FakeResult()]

    class FakeCap:
        def __init__(self, *args, **kwargs) -> None:
            self.i = 0

        def isOpened(self) -> bool:
            return self.i < n_frames

        def set(self, *args, **kwargs) -> None:
            pass

        def get(self, prop):
            return {5: 30.0, 3: 1920, 4: 1080, 0: 0.0}.get(prop, 0.0)

        def read(self):
            self.i += 1
            return True, types.SimpleNamespace()

        def release(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace(
        CAP_PROP_POS_MSEC=0, CAP_PROP_FPS=5, CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4, VideoCapture=FakeCap,
    ))
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(
        YOLO=lambda path: FakeModel(),
    ))


def _build_vf(monkeypatch, tmp_path: Path, layout: str, src: Path | None = None) -> str:
    """Compile a layout's filtergraph with bare file names (as render_service does)."""
    monkeypatch.setattr(edit_compiler, "RENDERS_DIR", tmp_path)
    (tmp_path / "subs.ass").write_text(_MINIMAL_ASS, encoding="utf-8")
    crop = tmp_path / "crop.txt"
    if layout == "center_crop":
        if src is None:
            crop.write_text("0.000 overlay x -1166.67;\n", encoding="utf-8")
        else:
            _install_fake_detector(monkeypatch)
            monkeypatch.setattr(face_tracker, "detect_cuts", lambda *a, **k: [])
            assert face_tracker.generate_sendcmd_file(str(src), 0.0, 3.0, str(crop)) is True
    else:
        crop.write_text("", encoding="utf-8")
    return compile_plan([], layout, "subs.ass", sendcmd_path="crop.txt")[0]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_filtergraph_string_invariants(monkeypatch, tmp_path, layout):
    vf = _build_vf(monkeypatch, tmp_path, layout)
    # A colour source as overlay main produced a black frame 0 - never one here.
    assert "color" not in vf
    assert "ass='subs.ass'" in vf
    assert TARGET_W % 2 == 0 and TARGET_H % 2 == 0
    if layout == "center_crop":
        # Video is the overlay main; the initial x is seeded numerically from
        # the first sendcmd command (sendcmd cannot reliably set frame 0).
        assert "[a]scale=-1:1920[main];[b]scale=-1:1920[ov];[main][ov]overlay=" in vf
        seed = re.search(r"overlay=x=(-?\d+(?:\.\d+)?):y=0", vf)
        assert seed is not None, vf
        assert float(seed.group(1)) == pytest.approx(-1166.67)
        assert "sendcmd=f='crop.txt'" in vf
        assert f"crop={TARGET_W}:{TARGET_H}:0:0[out_v]" in vf
        assert "[out_v]ass=" in vf
    else:
        # split_screen has no overlay: its geometry is fixed by two explicit
        # 1080x960 halves stacked to exactly the even 1080x1920 target.
        assert vf.count(f"crop={TARGET_W}:{TARGET_H // 2}") == 2
        assert "vstack=inputs=2[vstack]" in vf
        assert "[vstack]ass=" in vf
        assert "overlay=" not in vf


@pytest.mark.skipif(not HAVE_TOOLS, reason="ffmpeg/ffprobe are required")
@pytest.mark.parametrize("layout", LAYOUTS)
def test_layout_renders_vertical_clip_with_audio(monkeypatch, tmp_path, layout):
    src = _make_source(tmp_path)
    vf = _build_vf(monkeypatch, tmp_path, layout, src=src)
    out = tmp_path / "out.mp4"
    proc = _run([
        _tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-t", "3", "-filter_complex", vf,
        "-map", "[out_final]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert out.exists() and out.stat().st_size > 0

    dims = _run([
        _tool("ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out),
    ])
    assert dims.returncode == 0, dims.stderr
    assert dims.stdout.strip().split(",")[:2] == [str(TARGET_W), str(TARGET_H)]

    audio = _run([
        _tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(out),
    ])
    assert audio.returncode == 0, audio.stderr
    assert audio.stdout.strip(), "rendered clip has no audio stream"

    decode = _run([_tool("ffmpeg"), "-v", "error", "-i", str(out), "-f", "null", "-"])
    assert decode.returncode == 0, decode.stderr
    assert decode.stderr.strip() == "", decode.stderr

    raw = subprocess.run([
        _tool("ffmpeg"), "-v", "error", "-i", str(out), "-frames:v", "1",
        "-vf", "format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ], check=False, capture_output=True, timeout=120)
    assert raw.returncode == 0, raw.stderr.decode(errors="replace")
    assert len(raw.stdout) == TARGET_W * TARGET_H, len(raw.stdout)
    mean_luma = float(np.frombuffer(raw.stdout, dtype=np.uint8).mean())
    assert mean_luma > 10.0, f"first frame is black/near-black (mean luma {mean_luma})"
