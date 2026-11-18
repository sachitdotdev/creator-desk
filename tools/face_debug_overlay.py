"""Render a short debug video of the face tracker's decisions.

Draws every detected face (yellow), the chosen target (green, with index and
confidence) and the computed crop window (cyan), so mid-frame tracking glitches
can be watched frame by frame. Mirrors ``face_tracker.generate_sendcmd_file``:
YOLOv8, largest-area face wins, alpha=0.15 smoothing, detection every 5 frames.

Run with the backend venv (needs ultralytics + cv2 + torch)::

    backend\\venv\\Scripts\\python.exe tools/face_debug_overlay.py --clip-id 1 \
        --out data/reviews/face_debug_clip1.mp4

Or pass an explicit source and start time::

    backend\\venv\\Scripts\\python.exe tools/face_debug_overlay.py --source VIDEO \
        --start 36.8 --duration 20 --out data/reviews/debug.mp4

Output is written under data/reviews/ (gitignored).
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
DB_PATH = ROOT / "data" / "creatordesk.db"
FACE_MODEL = BACKEND_DIR / "yolov8n-face.pt"

FRAME_SKIP = 5
ALPHA = 0.15
TARGET_WIDTH = 1080
MAX_WIDTH = 640  # downscale for a light, watchable debug clip


def clip_lookup(clip_id: int) -> dict:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT c.start_time, v.path AS source_path FROM clips c "
            "JOIN videos v ON v.id=c.video_id WHERE c.id=?",
            (clip_id,),
        ).fetchone()
        return {"source_path": row["source_path"], "start": float(row["start_time"])} if row else {}
    finally:
        conn.close()


def ffmpeg_cmd() -> str:
    from app.core.config import FFMPEG_PATH

    return FFMPEG_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="source video path")
    parser.add_argument("--clip-id", type=int, help="look up source + start time from the DB")
    parser.add_argument("--start", type=float, default=0.0, help="start seconds in the source")
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--out", default=str(ROOT / "data" / "reviews" / "face_debug.mp4"))
    parser.add_argument("--cpu", action="store_true", help="force CPU inference")
    args = parser.parse_args()

    if args.clip_id is not None:
        info = clip_lookup(args.clip_id)
        source = args.source or info.get("source_path")
        start = args.start if args.start else info.get("start", 0.0)
    else:
        source, start = args.source, args.start
    if not source or not Path(source).exists():
        parser.error(f"source video not found: {source}")

    import cv2
    from ultralytics import YOLO

    from app.core.gpu_lock import gpu_lock
    from app.core.processing_utils import flush_vram

    if not FACE_MODEL.exists():
        parser.error(f"YOLO model not found: {FACE_MODEL}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        parser.error(f"cannot open source: {source}")
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, MAX_WIDTH / src_w)
    out_w, out_h = int(src_w * scale), int(src_h * scale)
    scale_factor = 1920.0 / src_h

    device = "cpu" if args.cpu or not _cuda_available() else "cuda"
    print(f"[FACE-OVERLAY] source={source} start={start:.1f}s fps={fps:.2f} "
          f"src={src_w}x{src_h} out={out_w}x{out_h} device={device}")

    writer_cmd = [
        ffmpeg_cmd(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}", "-r", f"{fps:.3f}",
        "-i", "-", "-an", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", str(out_path),
    ]
    proc = subprocess.Popen(writer_cmd, stdin=subprocess.PIPE)

    faces_seen = 0
    no_detection_frames = 0
    chosen_switches = 0
    smoothed_x = None
    last_chosen_index = -1
    total_frames = int(args.duration * fps)
    detections: list[tuple[float, float, float, float, float]] = []  # x1,y1,x2,y2,conf

    try:
        with gpu_lock("face-debug:yolo"):
            model = YOLO(str(FACE_MODEL))
            for frame_idx in range(total_frames):
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % FRAME_SKIP == 0:
                    results = model(frame, verbose=False, device=device)
                    detections = []
                    for r in results:
                        if r.boxes is None:
                            continue
                        for box in r.boxes:
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            conf = float(box.conf[0].item()) if box.conf is not None else 0.0
                            detections.append((x1, y1, x2, y2, conf))
                    if detections:
                        best = max(detections, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
                        chosen = (best[0] + best[2]) / 2.0
                        best_index = detections.index(best)
                        smoothed_x = chosen if smoothed_x is None else ALPHA * chosen + (1 - ALPHA) * smoothed_x
                        if best_index != last_chosen_index and last_chosen_index != -1:
                            chosen_switches += 1
                        last_chosen_index = best_index
                    else:
                        no_detection_frames += 1
                    faces_seen += len(detections)

                draw = cv2.resize(frame, (out_w, out_h))
                for i, (x1, y1, x2, y2, conf) in enumerate(detections):
                    chosen = i == last_chosen_index
                    color = (0, 255, 0) if chosen else (0, 255, 255)
                    thickness = 3 if chosen else 1
                    cv2.rectangle(draw, (int(x1 * scale), int(y1 * scale)),
                                  (int(x2 * scale), int(y2 * scale)), color, thickness)
                    cv2.putText(draw, f"#{i} {conf:.2f}", (int(x1 * scale), max(12, int(y1 * scale) - 4)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                if smoothed_x is not None:
                    half = (TARGET_WIDTH / scale_factor) / 2.0
                    left, right = int((smoothed_x - half) * scale), int((smoothed_x + half) * scale)
                    cv2.rectangle(draw, (left, 0), (right, out_h), (255, 0, 0), 2)
                    cv2.putText(draw, "CROP", (max(0, left) + 4, out_h - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                proc.stdin.write(draw.tobytes())
        flush_vram("face-debug:yolo")
    finally:
        cap.release()
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=120)

    print(f"[FACE-OVERLAY] done: {frame_idx + 1} frames, detections={faces_seen}, "
          f"no-detection samples={no_detection_frames}, target switches={chosen_switches}")
    print(f"[FACE-OVERLAY] overlay video: {out_path}")


def _cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:  # noqa: BLE001 - CPU fallback when torch is unavailable
        return False


if __name__ == "__main__":
    main()
