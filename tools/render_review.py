"""Inspect a rendered clip: contact sheet + caption/SFX/tracking metrics.

Usage (from repo root)::

    python tools/render_review.py data/renders/e2e_test.mp4
    python tools/render_review.py data/renders/clip_13_f2485b5e.mp4 --clip-id 13

Outputs go to ``data/reviews/<name>/`` (gitignored):

* ``contact_sheet.png`` - 12 frames evenly spaced across the render plus up
  to 4 frames sampled at caption-change times, in a labeled 4-column grid.
* ``metrics.json`` - duration, resolution, caption/SFX counts and the
  face-tracking metrics computed by ``render_metrics.py``.

Requires only FFmpeg/FFprobe and Pillow (already installed). The renderer keeps
its per-frame crop data at ``data/renders/crop_<clip_id>.txt``; pass ``--clip-id``
so the tool can find it. ``--crop`` overrides the path explicitly.

Face-tracking metrics and the glitch-score formula are documented in
``tools/render_metrics.py`` and echoed into metrics.json.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from render_metrics import (
    TARGET_WIDTH,
    caption_metrics,
    compute_crop_metrics,
    parse_sendcmd,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RENDERS_DIR = DATA_DIR / "renders"
REVIEWS_DIR = DATA_DIR / "reviews"
DB_PATH = DATA_DIR / "creatordesk.db"
TILE_W, TILE_H = 270, 480
COLS = 4
TIMEOUT = 120


def _ffmpeg() -> str:
    return os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe() -> str:
    exe = _ffmpeg()
    if exe.endswith("ffmpeg.exe"):
        return exe[:-10] + "ffprobe.exe"
    if exe.endswith("ffmpeg"):
        return exe[:-6] + "ffprobe"
    return shutil.which("ffprobe") or "ffprobe"


def _run(cmd: list[str]) -> str:
    result = subprocess.run(
        [str(c) for c in cmd], capture_output=True, text=True, timeout=TIMEOUT, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(map(str, cmd))}\n{result.stderr[-2000:]}")
    return result.stdout


def probe_media(path: Path) -> dict:
    out = _run([
        _ffprobe(), "-v", "error",
        "-show_entries", "format=duration",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration",
        "-of", "json", str(path),
    ])
    data = json.loads(out)
    stream = (data.get("streams") or [{}])[0]
    duration = stream.get("duration") or data.get("format", {}).get("duration") or 0.0
    return {
        "duration": round(float(duration), 3),
        "resolution": [stream.get("width"), stream.get("height")],
        "fps": stream.get("r_frame_rate", "0/0"),
    }


def db_lookup(clip_id: int | None, render: Path) -> dict:
    """Resolve clip id, source path, operations and crop path from the DB."""
    info: dict = {"clip_id": clip_id, "source_path": None, "sfx_count": None, "crop_path": None}
    if not DB_PATH.exists():
        return info
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = None
        if clip_id is not None:
            row = conn.execute(
                "SELECT c.id, c.operations, v.path AS source_path "
                "FROM clips c JOIN videos v ON v.id=c.video_id WHERE c.id=?",
                (clip_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT c.id, c.operations, v.path AS source_path "
                "FROM clips c JOIN videos v ON v.id=c.video_id WHERE c.output_path=?",
                (str(render),),
            ).fetchone()
            if row is not None:
                info["clip_id"] = row["id"]
        if row is not None:
            info["source_path"] = row["source_path"]
            try:
                ops = json.loads(row["operations"]) if row["operations"] else []
            except (ValueError, TypeError):
                ops = []
            info["sfx_count"] = sum(1 for op in ops if isinstance(op, dict) and op.get("type") == "sfx")
    finally:
        conn.close()
    if info["clip_id"] is not None:
        candidate = RENDERS_DIR / f"crop_{info['clip_id']}.txt"
        if candidate.exists():
            info["crop_path"] = str(candidate)
    return info


def parse_ass(path: Path) -> list[dict]:
    """Return ASS Dialogue entries as {start, text} with override tags stripped."""
    import re

    dialogues: list[dict] = []
    tag_re = re.compile(r"\{[^}]*\}")

    def ass_time(value: str) -> float:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        text = tag_re.sub("", parts[9]).replace("\\N", " ").strip()
        dialogues.append({"start": round(ass_time(parts[1]), 3), "text": text})
    return dialogues


def find_ass(clip_id: int | None, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    if clip_id is not None:
        matches = sorted(RENDERS_DIR.glob(f"subs_{clip_id}_*.ass"))
        if matches:
            return matches[-1]
    return None


def extract_frame(render: Path, t: float, dest: Path) -> None:
    _run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, t):.3f}", "-i", str(render),
        "-frames:v", "1", "-vf", f"scale={TILE_W}:{TILE_H}",
        "-q:v", "2", str(dest),
    ])


def build_contact_sheet(render: Path, times: list[float], out_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    times = sorted({round(max(0.0, t), 3) for t in times})
    temp_dir = out_path.parent / "_frames"
    temp_dir.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[float, Path]] = []
    for i, t in enumerate(times):
        png = temp_dir / f"frame_{i:02d}.png"
        try:
            extract_frame(render, t, png)
        except RuntimeError as exc:
            print(f"[WARN] could not extract frame at {t:.2f}s: {exc}")
            continue
        frames.append((t, png))
    if not frames:
        raise RuntimeError("no frames could be extracted for the contact sheet")

    label_h = 26
    rows = (len(frames) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * TILE_W, rows * (TILE_H + label_h)), (20, 20, 20))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()

    for i, (t, png) in enumerate(frames):
        col, row = i % COLS, i // COLS
        x, y = col * TILE_W, row * (TILE_H + label_h)
        with Image.open(png) as img:
            sheet.paste(img.convert("RGB"), (x, y))
        mm, ss = divmod(t, 60.0)
        draw.text((x + 6, y + TILE_H + 3), f"{int(mm):02d}:{ss:05.2f}", fill=(255, 255, 255), font=font)
    sheet.save(out_path)
    for _, png in frames:
        png.unlink(missing_ok=True)
    try:
        temp_dir.rmdir()
    except OSError:
        pass


def sample_times(duration: float, caption_times: list[float]) -> list[float]:
    times = [(i + 0.5) * duration / 12.0 for i in range(12)]
    if caption_times:
        m = len(caption_times)
        for i in range(min(4, m)):
            times.append(caption_times[round(i * (m - 1) / max(1, min(4, m) - 1))])
    # Drop samples that are effectively duplicates of an even sample.
    unique: list[float] = []
    for t in sorted(times):
        if not unique or t - unique[-1] >= 0.2:
            unique.append(t)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render", help="path to the rendered MP4")
    parser.add_argument("--clip-id", type=int, help="clip id (finds crop + caption data)")
    parser.add_argument("--crop", help="explicit path to a crop sendcmd file")
    parser.add_argument("--ass", help="explicit path to an ASS caption file")
    parser.add_argument("--source", help="explicit path to the source video (for scale factor)")
    parser.add_argument("--name", help="review subfolder name (default: render stem)")
    parser.add_argument("--out-dir", default=str(REVIEWS_DIR))
    parser.add_argument("--jump-threshold", type=float, default=50.0)
    parser.add_argument("--switch-threshold", type=float, default=150.0)
    args = parser.parse_args()

    render = Path(args.render).resolve()
    if not render.exists():
        parser.error(f"render not found: {render}")
    name = args.name or render.stem
    out = Path(args.out_dir) / name
    out.mkdir(parents=True, exist_ok=True)

    info = db_lookup(args.clip_id, render)
    probe = probe_media(render)

    ass_path = find_ass(info["clip_id"], args.ass)
    captions = caption_metrics(parse_ass(ass_path)) if ass_path and ass_path.exists() else {
        "num_captions": None, "avg_words_per_caption": None, "caption_change_times": [],
    }
    captions["ass_path"] = str(ass_path) if ass_path else None

    source_path = args.source or info["source_path"]
    scale_factor = None
    if source_path and Path(source_path).exists():
        src_probe = probe_media(Path(source_path))
        height = src_probe["resolution"][1]
        if height:
            scale_factor = 1920.0 / float(height)

    crop_path = args.crop or info["crop_path"]
    crop = None
    if crop_path and Path(crop_path).exists():
        samples = parse_sendcmd(Path(crop_path).read_text(encoding="utf-8", errors="replace"))
        crop = compute_crop_metrics(
            samples,
            fps=30.0,
            scale_factor=scale_factor,
            target_width=TARGET_WIDTH,
            jump_threshold_px=args.jump_threshold,
            switch_threshold_px=args.switch_threshold,
        )
        crop["crop_path"] = str(crop_path)
    else:
        crop = {"available": False, "reason": "no crop sendcmd file found for this render"}

    times = sample_times(probe["duration"], captions["caption_change_times"])
    sheet_path = out / "contact_sheet.png"
    build_contact_sheet(render, times, sheet_path)

    metrics = {
        "render": str(render),
        "clip_id": info["clip_id"],
        "source_path": source_path,
        "duration_seconds": probe["duration"],
        "resolution": probe["resolution"],
        "fps": probe["fps"],
        "num_captions": captions["num_captions"],
        "avg_words_per_caption": captions["avg_words_per_caption"],
        "sfx_count": info["sfx_count"],
        "caption_change_times": captions["caption_change_times"],
        "ass_path": captions["ass_path"],
        "contact_sheet": str(sheet_path),
        "contact_sheet_frames": len(times),
        "face_tracking": crop,
        "glitch_formula": (
            "glitch_score = 1.0*jumps_per_min + 5.0*target_switches "
            "+ 100.0*no_detection_fraction (see tools/render_metrics.py)"
        ),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    ft = crop
    print(f"=== REVIEW: {render.name} ===")
    print(f"contact sheet : {sheet_path}")
    print(f"metrics json  : {out / 'metrics.json'}")
    print(f"duration      : {probe['duration']}s   resolution: {probe['resolution']}")
    print(f"captions      : {captions['num_captions']}  avg words: {captions['avg_words_per_caption']}  SFX: {info['sfx_count']}")
    if ft.get("available", True):
        print(f"crop samples  : {ft['n_samples']}  scale_factor: {ft['scale_factor']:.3f} ({ft['scale_factor_source']})")
        print(f"jumps         : {ft['jumps']}  (> {ft['jump_threshold_px']} px/frame)   jumps/min: {ft['jumps_per_min']}")
        print(f"target switches: {ft['target_switches']}  (> {ft['switch_threshold_px']} px/frame)")
        print(f"longest hold  : {ft['longest_hold_frames']} frames ({ft['longest_hold_seconds']}s)")
        print(f"no detection  : {ft['no_detection_frames']} frames ({ft['no_detection_seconds']}s), fraction {ft['no_detection_fraction']}")
        print(f"GLITCH SCORE  : {ft['glitch_score']}")
    else:
        print(f"face tracking : unavailable ({ft.get('reason')})")


if __name__ == "__main__":
    main()
