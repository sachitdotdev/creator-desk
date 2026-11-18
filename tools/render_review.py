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
    SAFE_ZONE_BOTTOM_PCT,
    TARGET_WIDTH,
    blackdetect_periods,
    caption_metrics,
    compute_crop_metrics,
    first_frame_luma,
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
    """Resolve clip id, source path, start time, operations and crop path."""
    info: dict = {
        "clip_id": clip_id, "source_path": None, "start_time": None,
        "sfx_count": None, "crop_path": None,
    }
    if not DB_PATH.exists():
        return info
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = None
        if clip_id is not None:
            row = conn.execute(
                "SELECT c.id, c.start_time, c.operations, v.path AS source_path "
                "FROM clips c JOIN videos v ON v.id=c.video_id WHERE c.id=?",
                (clip_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT c.id, c.start_time, c.operations, v.path AS source_path "
                "FROM clips c JOIN videos v ON v.id=c.video_id WHERE c.output_path=?",
                (str(render),),
            ).fetchone()
            if row is not None:
                info["clip_id"] = row["id"]
        if row is not None:
            info["source_path"] = row["source_path"]
            info["start_time"] = row["start_time"]
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
        try:
            margin_v = float(parts[7])
        except (ValueError, IndexError):
            margin_v = None
        dialogues.append({
            "start": round(ass_time(parts[1]), 3),
            "text": text,
            "margin_v": margin_v,
        })
    return dialogues


def find_ass(clip_id: int | None, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    if clip_id is not None:
        matches = sorted(RENDERS_DIR.glob(f"subs_{clip_id}_*.ass"))
        if matches:
            return matches[-1]
    return None


def style_margin_v(path: Path) -> float | None:
    """Read the bottom margin (MarginV) from the ASS Default style.

    Per-dialogue MarginV of 0 usually means "inherit from style", so the
    style's MarginV is the effective bottom margin when dialogues don't set it.
    """
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Style: Default,"):
                parts = line.split(",", 23)
                # "Style: Default" is field 0; Alignment(18), MarginL(19), MarginR(20), MarginV(21), Encoding(22)
                if len(parts) > 21:
                    return float(parts[21])
    except (ValueError, IndexError, OSError):
        pass
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
        if not png.exists():
            print(f"[WARN] ffmpeg did not write frame at {t:.2f}s")
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


def black_frame_report(render: Path) -> dict:
    """Run ffmpeg blackdetect on the render and flag a black first frame."""
    periods = blackdetect_periods(_ffmpeg(), str(render))
    black_first_frame = any(p["black_start"] < 0.5 for p in periods)
    luma = first_frame_luma(_ffmpeg(), str(render))
    # YAVG ~16 is an all-black frame; normal content sits well above 20.
    black_frames = [i for i, value in enumerate(luma) if value < 20.0]
    return {
        "periods": periods,
        "black_first_frame": black_first_frame,
        "first_5_luma": [round(v, 2) for v in luma],
        "black_frame_count": len(black_frames),
        "black_frame_indices": black_frames,
    }


def caption_safe_zone(
    dialogues: list[dict], frame_height: int | None, style_margin_v: float | None = None
) -> dict:
    """Report the closest caption bottom margin as % of frame height.

    ASS alignment 2 is bottom-center; ``margin_v`` is the distance from the
    bottom edge. The safe-zone threshold is ``SAFE_ZONE_BOTTOM_PCT`` (default
    0.18 => 18% of frame height); text inside the bottom ``SAFE_ZONE_BOTTOM_PCT``
    of the frame is flagged as a safe-zone violation. A per-dialogue margin of 0 is
    treated as "inherit from style", so ``style_margin_v`` is used as fallback.
    """
    result = {
        "bottom_margin_px": None,
        "bottom_margin_pct": None,
        "frame_height": frame_height,
        "safe_zone_violation": None,
        "style_margin_v": style_margin_v,
    }
    if frame_height is None or frame_height <= 0:
        return result
    margins = [d["margin_v"] for d in dialogues if d.get("margin_v") not in (None, 0)]
    source = "dialogue"
    if not margins and style_margin_v is not None:
        margins = [style_margin_v]
        source = "style"
    if not margins:
        return result
    closest = min(margins)
    pct = closest / float(frame_height) * 100.0
    result["bottom_margin_px"] = round(closest, 1)
    result["bottom_margin_pct"] = round(pct, 2)
    result["margin_source"] = source
    result["safe_zone_violation"] = pct < SAFE_ZONE_BOTTOM_PCT * 100.0
    return result


def build_missed_frames_sheet(
    source_path: str | None,
    start_time: float | None,
    detection_records: list[dict] | None,
    render: Path,
    out_path: Path,
) -> dict:
    """Contact sheet of up to 16 frames where the tracker found no face.

    Frames are taken from the source video at absolute time
    (clip.start_time + tracker time) so the reviewer can check whether a face
    was really visible; falls back to the render when the source is unavailable.
    Returns {"sheet": path|None, "count": int, "timestamps": [abs times]}.
    """
    result = {"sheet": None, "count": 0, "timestamps": []}
    if not detection_records:
        return result
    missed = [r for r in detection_records if not r.get("detected", False)]
    if not missed:
        return result
    result["count"] = len(missed)
    times = [round(float(r.get("time", 0.0)), 3) for r in missed[:16]]
    if source_path and Path(source_path).exists() and start_time is not None:
        abs_times = [round(start_time + t, 3) for t in times]
        video = Path(source_path)
        label_times = abs_times
    else:
        video = render
        abs_times = times
        label_times = times
    result["timestamps"] = [round(t, 3) for t in label_times]
    try:
        build_contact_sheet(video, abs_times, out_path)
        result["sheet"] = str(out_path)
    except RuntimeError as exc:
        print(f"[WARN] could not build missed frames sheet: {exc}")
    return result


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
    ass_dialogues = parse_ass(ass_path) if ass_path and ass_path.exists() else []
    captions = caption_metrics(ass_dialogues) if ass_dialogues else {
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
    detection_records = None
    track_path = Path(crop_path).with_suffix(".track.json") if crop_path else None
    if track_path and track_path.exists():
        try:
            detection_records = json.loads(track_path.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError) as exc:
            print(f"[WARN] could not read tracker sidecar {track_path}: {exc}")
            detection_records = None

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
            detection_records=detection_records,
        )
        crop["crop_path"] = str(crop_path)
        crop["track_path"] = str(track_path) if track_path else None
    else:
        crop = {"available": False, "reason": "no crop sendcmd file found for this render"}

    times = sample_times(probe["duration"], captions["caption_change_times"])
    sheet_path = out / "contact_sheet.png"
    build_contact_sheet(render, times, sheet_path)

    black = black_frame_report(render)
    render_height = probe["resolution"][1] if probe["resolution"] and len(probe["resolution"]) > 1 else None
    style_mv = style_margin_v(ass_path) if ass_path and ass_path.exists() else None
    safe_zone = caption_safe_zone(ass_dialogues, render_height, style_mv)
    missed_sheet_path = out / "missed_frames.png"
    missed = build_missed_frames_sheet(
        source_path, info["start_time"], detection_records, render, missed_sheet_path,
    )

    crop_violation = crop.get("crop_violation") or {
        "available": False, "source": "none", "margin_px": None,
        "half_window_px": None, "violations": 0, "samples": 0,
        "violation_fraction": 0.0, "longest_violation": {"start": None, "end": None, "duration_s": 0.0, "count": 0},
    }

    metrics = {
        "render": str(render),
        "clip_id": info["clip_id"],
        "source_path": source_path,
        "start_time": info["start_time"],
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
        "crop_violation": crop_violation,
        "glitch_formula": (
            "glitch_score = 1.0*jumps_per_min + 5.0*target_switches "
            "+ 100.0*no_detection_fraction + 0.5*(travel_per_1s_window_px/1000) "
            "+ 2.0*direction_reversals + 3.0*fast_sweeps + "
            "10.0*crop_violation_fraction (see tools/render_metrics.py)"
        ),
        "black_detect": black,
        "caption_safe_zone": safe_zone,
        "missed_frames": missed,
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
        print(f"no detection  : {ft['no_detection_frames']} frames ({ft['no_detection_seconds']}s), fraction {ft['no_detection_fraction']} ({ft['no_detection_source']})")
        print(f"1s travel     : {ft['travel_per_1s_window_px']} px   reversals: {ft['direction_reversals']}   fast sweeps: {ft['fast_sweeps']}")
        print(f"GLITCH SCORE  : {ft['glitch_score']}")
        print(f"face-in-crop  : violation fraction {crop_violation.get('violation_fraction')} over {crop_violation.get('samples')} samples ({crop_violation.get('violations')} violating), margin {crop_violation.get('margin_px')}px, longest violation {crop_violation.get('longest_violation')}")
    else:
        print(f"face tracking : unavailable ({ft.get('reason')})")
    bd = metrics["black_detect"]
    print(f"black detect  : {len(bd['periods'])} period(s), black first frame: {bd['black_first_frame']}, "
          f"black frames in first 5: {bd['black_frame_count']} {bd['black_frame_indices']} (YAVG {bd['first_5_luma']})")
    sz = metrics["caption_safe_zone"]
    print(f"caption safe zone: bottom margin {sz['bottom_margin_pct']}% of height ({sz.get('margin_source')}), violation: {sz['safe_zone_violation']}")
    mf = metrics["missed_frames"]
    print(f"missed frames : {mf['count']} no-detection frames, sheet: {mf['sheet']}")


if __name__ == "__main__":
    main()
