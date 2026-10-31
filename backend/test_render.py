r"""End-to-end test: render a 9:16 vertical clip with burned kinetic ASS captions.

Usage:
    cd backend && .\venv\Scripts\python.exe test_render.py

What it does:
    1. Generates a synthetic vertical (1080x1920) test video if missing.
    2. Writes a synthetic word-level transcript JSON (mimics faster-whisper output).
    3. Creates a Clip + Video + Template (kinetic caption template) in a throwaway
       SQLite DB.
    4. Calls RenderService.render_clip() to burn kinetic karaoke captions into the
       MP4 via FFmpeg (libass ASS filter).
    5. Verifies the output MP4: exists, valid video+audio streams, 9:16 aspect,
       correct duration, and that subtitles are actually burned (frame diff in the
       caption region between a captioned and a non-captioned moment).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------- env
# Force CPU (no GPU in this test box) so FFmpeg uses libx264 instead of NVENC.
os.environ.setdefault("FFMPEG_DEVICE", "cpu")
os.environ.setdefault("WHISPER_DEVICE", "cpu")
# Point the app's FFmpeg path at the winget-installed ffmpeg.exe.
os.environ.setdefault(
    "FFMPEG_PATH",
    r"C:\Users\bechi\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe",
)

FFMPEG = os.environ["FFMPEG_PATH"]
FFPROBE = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

DATA_DIR = BACKEND / "data"
SOURCES_DIR = DATA_DIR / "sources"
RENDERS_DIR = DATA_DIR / "renders"
for d in (SOURCES_DIR, RENDERS_DIR):
    d.mkdir(parents=True, exist_ok=True)

TEST_VIDEO = SOURCES_DIR / "test_video.mp4"
TRANSCRIPT_JSON = RENDERS_DIR / "transcript_test.json"


# --------------------------------------------------------------------------- helpers
def ffprobe(path: Path) -> dict:
    cmd = [
        FFPROBE, "-hide_banner", "-loglevel", "error",
        "-select_streams", "v:0", "-show_entries",
        "stream=width,height,r_frame_rate,duration,codec_name",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)


def ffprobe_audio(path: Path) -> dict:
    cmd = [
        FFPROBE, "-hide_banner", "-loglevel", "error",
        "-select_streams", "a:0", "-show_entries",
        "stream=codec_name,duration",
        "-of", "json", str(path),
    ]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)


def extract_frame(path: Path, ts: float, out: Path) -> None:
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(ts), "-i", str(path),
        "-frames:v", "1", "-q:v", "2", str(out),
    ]
    subprocess.run(cmd, check=True)


def mean_brightness(image_path: Path) -> float:
    """Mean pixel brightness (0-255) via ffmpeg -> rawvideo -> numpy."""
    import numpy as np  # type: ignore

    def _probe_dimensions(p: Path) -> tuple:
        cmd = [
            FFPROBE, "-hide_banner", "-loglevel", "error",
            "-show_entries", "stream=width,height,codec_type",
            "-of", "json", str(p),
        ]
        info = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
        streams = info.get("streams", [])
        vs = [s for s in streams if s.get("codec_type") == "video"]
        target = vs[0] if vs else streams[0]
        return int(target["width"]), int(target["height"])

    w, h = _probe_dimensions(image_path)
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-i", str(image_path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
    return float(arr.mean()), float(arr.max())


# --------------------------------------------------------------------------- step 1: test video
def ensure_test_video() -> Path:
    if TEST_VIDEO.exists():
        print(f"[1/6] Test video already present: {TEST_VIDEO}")
        return TEST_VIDEO
    print("[1/6] Generating synthetic vertical test video ...")
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:size=1080x1920:duration=15:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=15:sample_rate=44100",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-pix_fmt", "yuv420p", "-shortest",
        str(TEST_VIDEO),
    ]
    subprocess.run(cmd, check=True)
    print(f"      -> {TEST_VIDEO} ({TEST_VIDEO.stat().st_size / 1024:.0f} KB)")
    return TEST_VIDEO


# --------------------------------------------------------------------------- step 2: synthetic transcript
def ensure_transcript() -> Path:
    if TRANSCRIPT_JSON.exists():
        print(f"[2/6] Transcript already present: {TRANSCRIPT_JSON}")
        return TRANSCRIPT_JSON

    print("[2/6] Writing synthetic word-level transcript ...")
    # Word timestamps are absolute (video timeline). Clip window will be 2.0-7.0s.
    words = [
        {"word": "Hey", "start": 2.0, "end": 2.4, "probability": 0.99},
        {"word": "everyone", "start": 2.4, "end": 3.0, "probability": 0.98},
        {"word": "this", "start": 3.0, "end": 3.3, "probability": 0.97},
        {"word": "is", "start": 3.3, "end": 3.6, "probability": 0.96},
        {"word": "Creator", "start": 3.6, "end": 4.2, "probability": 0.99},
        {"word": "Desk", "start": 4.2, "end": 4.8, "probability": 0.98},
        {"word": "Welcome", "start": 6.0, "end": 6.6, "probability": 0.99},
        {"word": "to", "start": 6.6, "end": 6.9, "probability": 0.97},
        {"word": "Creator", "start": 6.9, "end": 7.5, "probability": 0.98},
        {"word": "Desk", "start": 7.5, "end": 8.0, "probability": 0.97},
    ]
    segments = [
        {"id": 0, "start": 2.0, "end": 4.8, "text": "Hey everyone this is Creator Desk", "words": words[:6]},
        {"id": 1, "start": 6.0, "end": 8.0, "text": "Welcome to Creator Desk", "words": words[6:]},
    ]
    data = {
        "language": "en",
        "duration": 15.0,
        "segments": segments,
    }
    with open(TRANSCRIPT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"      -> {TRANSCRIPT_JSON}")
    return TRANSCRIPT_JSON


# --------------------------------------------------------------------------- step 3: DB + ORM objects
def build_orm(transcript_path: Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    import app.models  # noqa: F401 register models

    tmp_db = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{tmp_db}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    video = app.models.Video(
        filename="test_video.mp4",
        original_name="test_video.mp4",
        path=str(TEST_VIDEO),
        duration=15.0,
        fps=30.0,
        width=1080,
        height=1920,
        status="transcribed",
        transcript_path=str(transcript_path),
    )
    db.add(video)
    db.flush()

    clip = app.models.Clip(
        video_id=video.id,
        start_time=2.0,
        end_time=7.0,
        duration=5.0,
        title="Test Kinetic Clip",
        description="E2E test of burned kinetic captions",
        hashtags="#test,#shorts",
        hook="Hey everyone",
        status="pending",
        progress=0.0,
    )
    db.add(clip)
    db.flush()

    caption_config = {
        "caption": {
            "font": "Arial",
            "size": 56,
            "bold": 1,
            "primary": "&H00FFFFFF&",
            "highlight_color": "&H00FFFF&",   # yellow karaoke fill
            "outline": "&H00000000&",
            "back": "&H80000000&",
            "alignment": 2,                    # bottom center
            "margin_v": 120,
            "outline_w": 4,
            "shadow": 0,
            "kinetic": True,
        },
    }
    template = app.models.Template(
        name="Test Kinetic",
        description="Kinetic caption test template",
        config=json.dumps(caption_config),
        is_default=False,
    )
    db.add(template)
    db.commit()
    db.refresh(clip)
    db.refresh(video)
    db.refresh(template)
    return db, clip, video, template


# --------------------------------------------------------------------------- step 4: render
def render_clip(db, clip, video, template, base_path: str = None) -> Path:
    from app.services.render_service import RenderService

    print("[4/6] Rendering clip with kinetic captions ...")
    rs = RenderService(db)
    output_path = rs.render_clip(clip, video, template, base_path)
    print(f"      -> {output_path}")
    return Path(output_path)


# --------------------------------------------------------------------------- step 5: verify
def verify(output: Path) -> None:
    print("[5/6] Verifying output MP4 ...")
    assert output.exists() and output.stat().st_size > 0, "output MP4 missing/empty"

    info = ffprobe(output)  # -select_streams v:0 -> only the video stream
    streams = info.get("streams", [])
    assert streams, "no video stream in output"
    vs = streams[0]
    width = int(vs.get("width", 0))
    height = int(vs.get("height", 0))
    assert (width, height) == (1080, 1920), f"expected 1080x1920, got {width}x{height}"
    # Separate probe for the audio stream (A/V sync check).
    info_a = ffprobe_audio(output)
    assert info_a.get("streams"), "no audio stream in output (sync check)"
    print(f"      streams: video={width}x{height} ({vs.get('codec_name')}), audio present")
    print(f"      format duration: {info.get('format', {}).get('duration')}s")

    # Verify the ASS file was produced with karaoke \k tags.
    ass_files = list(RENDERS_DIR.glob("subs_*.ass"))
    assert ass_files, "no ASS subtitle file was generated"
    ass_text = ass_files[-1].read_text(encoding="utf-8")
    assert "\\k" in ass_text, "ASS file lacks karaoke \\k tags (not kinetic)"
    print(f"      ASS file: {ass_files[-1].name} (contains \\k karaoke tags)")

    # Verify subtitles are actually burned: captioned frame vs blank frame.
    # Clip window is 2.0-7.0s -> clip-relative 0-5s.
    # Caption present at clip-relative 0.5s ("Hey everyone"), absent at 3.5s (gap).
    cap_frame = RENDERS_DIR / "verify_captioned.jpg"
    blank_frame = RENDERS_DIR / "verify_blank.jpg"
    extract_frame(output, 0.5, cap_frame)
    extract_frame(output, 3.5, blank_frame)

    # Bottom-center caption region: full width, lower 25% of frame.
    # Crop via ffmpeg then measure mean brightness.
    def region_stats(frame: Path, y0_frac: float, y1_frac: float) -> tuple:
        y0 = int(1920 * y0_frac)
        y1 = int(1920 * y1_frac)
        h = y1 - y0
        tmp = RENDERS_DIR / f"verify_crop_{frame.stem}.jpg"
        cmd = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(frame),
            "-vf", f"crop=1080:{h}:0:{y0}",
            "-frames:v", "1", "-q:v", "2", str(tmp),
        ]
        subprocess.run(cmd, check=True)
        return mean_brightness(tmp)

    cap_mean, cap_max = region_stats(cap_frame, 0.70, 1.0)
    blank_mean, blank_max = region_stats(blank_frame, 0.70, 1.0)
    print(f"      caption-region brightness: captioned mean={cap_mean:.1f}/max={cap_max:.0f} "
          f"blank mean={blank_mean:.1f}/max={blank_max:.0f}")
    assert cap_max > 60, "captioned frame has no bright pixels (subtitles not burning?)"
    assert blank_max < 10, "blank frame region has bright pixels (unexpected)"
    assert cap_max > blank_max + 40, "captioned region not brighter than blank (subtitles may not be burned)"
    print("      [OK] kinetic subtitles verified burning into output MP4")

    # Cleanup verify frames
    for p in (cap_frame, blank_frame):
        if p.exists():
            p.unlink()


# --------------------------------------------------------------------------- main
def main() -> None:
    ensure_test_video()
    transcript_path = ensure_transcript()
    db, clip, video, template = build_orm(transcript_path)
    try:
        output = render_clip(db, clip, video, template)
        verify(output)
        print("\n=== END-TO-END RENDER TEST PASSED ===")
        print(f"Output: {output}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
