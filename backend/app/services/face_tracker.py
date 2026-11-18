"""Face tracker: YOLOv8 face detection -> per-frame crop sendcmd file.

The tracker watches a clip window of a source video and emits one FFmpeg
``sendcmd`` line per frame (``data/renders/crop_<clip_id>.txt``)::

    0.000 overlay x -2333.33;

This moves the full-frame image inside the 1080px vertical output so the
chosen face stays centered. The sendcmd *format* is unchanged from the
original implementation.

A per-frame detection sidecar (``crop_<clip_id>.track.json``) is always
written next to the sendcmd so review tooling can build the missed-frames
sheet and report an exact no-detection rate.

All behavior is driven by config values in :mod:`app.core.config` so it can be
tuned or disabled without touching this file:

* ``FACE_TRACKER_ENABLED``            - master switch (false => center crop)
* ``FACE_MODEL_CONF / FACE_MODEL_IMGSZ`` - YOLO conf / inference size
* ``FACE_MODEL_UPSCALE_SMALL``        - 2x upscale small frames before detect
* ``FACE_DETECTION_STRIDE``           - detect every N frames (1 = every frame)
* ``FACE_CUT_THRESHOLD``              - ffmpeg scene-detection threshold
* ``FACE_TARGET_MIN_DWELL_S``         - hysteresis dwell before switching faces
* ``FACE_SMOOTHING_OMEGA``            - critically damped spring (rad/s)
* ``FACE_MAX_PAN_PX_PER_S``           - max pan speed
* ``FACE_HOLD_SECONDS``               - hold last pos when detection is lost

Phase 6 will replace target selection with diarization-based speaker mapping;
the hook is :func:`_select_target` (largest face + dwell hysteresis).
"""
from __future__ import annotations

import json
import math
import os
import subprocess

from app.core.config import (
    FACE_CUT_CACHE_DIR,
    FACE_CUT_THRESHOLD,
    FACE_DETECTION_STRIDE,
    FACE_HOLD_SECONDS,
    FACE_MAX_PAN_PX_PER_S,
    FACE_MODEL,
    FACE_MODEL_CONF,
    FACE_MODEL_IMGSZ,
    FACE_MODEL_UPSCALE_SMALL,
    FACE_SMOOTHING_OMEGA,
    FACE_TARGET_MIN_DWELL_S,
    FACE_TARGET_PREFER_LARGEST,
    FACE_TRACKER_ENABLED,
)
from app.core.gpu_lock import gpu_lock
from app.core.processing_utils import flush_vram

# A detected face is considered "the same" as the current target when its
# center is within this many source pixels of the target center.
SAME_TARGET_PX = 70.0
# A newly largest face must exceed the current target by this factor (and
# persist MIN_DWELL seconds) before the tracker switches to it. Anti
# wrong-target-flip hysteresis; Phase 6 (diarization) supersedes it.
SWITCH_MARGIN = 1.25


class _CriticallyDampedSpring:
    """Smoothly follows a moving target with a hard max pan speed.

    Critically damped (zeta = 1): no overshoot, no oscillation. ``max_speed``
    caps the pan speed in source px/s so the crop can never whip across the
    frame onto empty space.
    """

    def __init__(self, omega: float, max_speed_px_per_s: float, fps: float) -> None:
        self.omega = float(omega)
        self.max_speed = float(max_speed_px_per_s)
        self.dt = 1.0 / float(fps)
        self.pos: float | None = None
        self.vel = 0.0

    def reset(self) -> None:
        self.pos = None
        self.vel = 0.0

    def update(self, target: float) -> float:
        if self.pos is None:
            self.pos = float(target)
            return self.pos
        accel = -2.0 * self.omega * self.vel - self.omega ** 2 * (self.pos - target)
        self.vel += accel * self.dt
        self.vel = max(-self.max_speed, min(self.max_speed, self.vel))
        self.pos += self.vel * self.dt
        return self.pos


def _ffmpeg() -> str:
    import shutil

    from app.core.config import FFMPEG_PATH
    return FFMPEG_PATH or shutil.which("ffmpeg") or "ffmpeg"


def detect_cuts(video_path: str, start: float, duration: float,
                threshold: float) -> list[float]:
    """Return cut times (clip-relative seconds) via ffmpeg scene detection.

    Runs ffmpeg scene detection only over the clip window (``-ss`` + ``-t``)
    so it is fast and never scans the whole source. Results are cached under
    ``FACE_CUT_CACHE_DIR`` keyed by source + window + threshold so re-renders
    do not re-scan.
    """
    FACE_CUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{os.path.basename(video_path)}@{start:.3f}-{duration:.3f}@{threshold:.2f}"
    cache = FACE_CUT_CACHE_DIR / (key.replace(os.sep, "_") + ".json")
    if cache.exists():
        try:
            return [float(x) for x in json.loads(cache.read_text())]
        except (ValueError, OSError):
            pass

    cuts: list[float] = []
    cmd = [
        _ffmpeg(), "-hide_banner", "-loglevel", "error", "-an",
        "-ss", f"{max(0.0, start):.3f}", "-i", str(video_path), "-t", f"{duration:.3f}",
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None:
        for line in proc.stderr.splitlines():
            if "pts_time" in line and "n:" in line:
                for part in line.split():
                    if part.startswith("pts_time:"):
                        try:
                            cut = float(part.split(":", 1)[1])
                        except ValueError:
                            continue
                        # ffmpeg input seeking on some containers does not
                        # rebase pts to the clip start; clamp to the clip
                        # window so a cut never falls outside the render.
                        if 0.0 <= cut <= duration:
                            cuts.append(cut)
                        break
    try:
        cache.write_text(json.dumps(cuts))
    except OSError:
        pass
    return sorted(cuts)


def _upscale_if_small(frame, min_side: int = 640):
    """Optionally upscale a frame so small faces reach imgsz scale."""
    if not FACE_MODEL_UPSCALE_SMALL:
        return frame
    try:
        import cv2  # heavy, optional; only imported when upscaling is on
    except Exception:  # noqa: BLE001 - degrade gracefully when cv2 is missing
        return frame
    h, w = frame.shape[:2]
    if min(h, w) >= min_side:
        return frame
    scale = min_side / float(min(h, w))
    return cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)


def _center(face: dict) -> tuple[float, float]:
    return ((face["x1"] + face["x2"]) / 2.0, (face["y1"] + face["y2"]) / 2.0)


def _select_target(faces: list[dict], now: float, state: dict) -> dict | None:
    """Pick the target face with largest-face preference + dwell hysteresis.

    ``state`` is ``{"target": face|None, "since": float}`` and is mutated in
    place. Returns the chosen face dict or None.

    Hook for Phase 6: replace this body with diarization-based speaker mapping
    (pick the face matching the active speaker). The signature and the
    ``state`` contract (chosen face + dwell time) stay the same.
    """
    if not faces:
        state["target"] = None
        state["since"] = now
        return None

    best = max(faces, key=lambda f: f["area"])
    cur = state.get("target")

    if cur is None:
        state["target"] = best
        state["since"] = now
        return best

    # Same face as the current target? (center within SAME_TARGET_PX).
    # Return the CURRENT detection so the crop follows the face, but keep the
    # dwell clock running (we are not switching identity).
    if math.dist(_center(best), _center(cur)) <= SAME_TARGET_PX:
        return best

    # Different face is largest: switch only if clearly better AND persisted.
    if (FACE_TARGET_PREFER_LARGEST
            and best["area"] > cur["area"] * SWITCH_MARGIN
            and (now - state["since"]) >= FACE_TARGET_MIN_DWELL_S):
        state["target"] = best
        state["since"] = now
        return best
    return cur  # hysteresis: keep the current target


def generate_sendcmd_file(video_path: str, start_time: float, duration: float, sendcmd_path: str, target_width: int = 1080, debug: bool = False) -> bool:
    # DIAGNOSTIC ONLY: opt in with debug=True or FACE_TRACKER_DEBUG=1. When off
    # (the default) this function's output and control flow are unchanged.
    debug_enabled = debug or os.environ.get("FACE_TRACKER_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    if not FACE_TRACKER_ENABLED:
        _write_center_sendcmd(sendcmd_path, start_time, duration, target_width)
        return True

    try:
        import cv2  # heavy, optional dependency: keep the module importable without it

        os.makedirs(os.path.dirname(sendcmd_path), exist_ok=True)

        if not os.path.exists(FACE_MODEL):
            print(f"DEBUG: YOLO model not found at {FACE_MODEL}!")
            return False

        from ultralytics import YOLO
        # Model load + YOLO inference are the only VRAM-touching steps here.
        # Hold the lock for that span, then flush once when it is done.
        with gpu_lock("face-tracker:yolo"):
            try:
                model = YOLO(FACE_MODEL)

                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    return False

                cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps == 0:
                    fps = 30
                original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                scale_factor = 1920.0 / original_height
                shot_center_x = original_width / 2.0
                crop_window_half = (target_width / scale_factor) / 2.0
                # Valid crop-center range in source pixels (window must stay in
                # frame); beyond it the overlay clamps to the frame edge.
                cx_min = crop_window_half
                cx_max = original_width - crop_window_half

                cuts = detect_cuts(video_path, start_time, duration, FACE_CUT_THRESHOLD)
                cut_idx = 0

                # Per-shot face-center history (loss-handling ease target).
                shot_centers: list[float] = []

                smoothed = _CriticallyDampedSpring(FACE_SMOOTHING_OMEGA,
                                                   FACE_MAX_PAN_PX_PER_S, fps)
                target_state: dict = {"target": None, "since": 0.0}
                last_good_x: float | None = None
                last_good_t: float = -1e9

                frame_count = 0
                sampled_positions = []  # (frame, smoothed_x) for interpolation
                stride = max(1, int(FACE_DETECTION_STRIDE))
                records = []  # per-frame detection sidecar

                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret or frame_count > (duration * fps):
                        break
                    t = frame_count / fps

                    # Shot-cut boundary: reset ALL tracker state so one shot's
                    # x position is never carried into the next shot.
                    while cut_idx < len(cuts) and t >= cuts[cut_idx]:
                        smoothed.reset()
                        target_state = {"target": None, "since": t}
                        shot_centers = []
                        last_good_x = None
                        cut_idx += 1

                    detected_this_frame = False
                    chosen: dict | None = None
                    faces: list[dict] = []
                    if frame_count % stride == 0:
                        inf_frame = _upscale_if_small(frame)
                        results = model(inf_frame, verbose=False, device="cuda",
                                        imgsz=FACE_MODEL_IMGSZ, conf=FACE_MODEL_CONF)
                        for r in results:
                            for box in r.boxes:
                                x1, y1, x2, y2 = box.xyxy[0].tolist()
                                area = (x2 - x1) * (y2 - y1)
                                conf = float(box.conf[0].item()) if box.conf is not None else 0.0
                                faces.append({
                                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                    "area": area, "conf": conf,
                                    "cx": x1 + (x2 - x1) / 2.0,
                                })
                        if faces:
                            shot_centers.extend(f["cx"] for f in faces)
                        chosen = _select_target(faces, t, target_state)
                        # _select_target mutates target_state in place (chosen +
                        # dwell time) and returns the chosen face or None.

                    if chosen is not None:
                        detected_this_frame = True
                        cx = chosen["cx"]
                        shot_centers.append(cx)
                        if smoothed.pos is None:
                            smoothed.pos = cx
                        smoothed_x = smoothed.update(cx)
                        last_good_x = cx
                        last_good_t = t
                    else:
                        # Detection lost: hold last good pos for HOLD_SECONDS,
                        # then ease toward the shot's face center / shot center.
                        if last_good_x is not None and (t - last_good_t) <= FACE_HOLD_SECONDS:
                            if smoothed.pos is None:
                                smoothed.pos = last_good_x
                            smoothed_x = smoothed.pos  # hold steady
                        else:
                            ease_x = (sum(shot_centers) / len(shot_centers)) if shot_centers else shot_center_x
                            if smoothed.pos is None:
                                smoothed.pos = ease_x
                            smoothed_x = smoothed.update(ease_x)

                    clamped_x = max(cx_min, min(cx_max, smoothed_x))
                    scaled_x = clamped_x * scale_factor
                    overlay_x = (target_width / 2.0) - scaled_x
                    min_overlay_x = target_width - original_width * scale_factor
                    max_overlay_x = 0.0
                    overlay_x = max(min_overlay_x, min(max_overlay_x, overlay_x))

                    records.append({
                        "frame": frame_count,
                        "time": round(t, 4),
                        "detected": detected_this_frame,
                        "sampled": frame_count % stride == 0,
                        "bbox": ([round(v, 1) for v in (chosen["x1"], chosen["y1"], chosen["x2"], chosen["y2"])]
                               if chosen is not None else None),
                        "conf": (round(chosen["conf"], 4) if chosen is not None else None),
                        "crop_center_x": round(clamped_x, 2),
                        "target_x": round(chosen["cx"], 2) if chosen is not None else None,
                    })

                    if smoothed_x is not None:
                        sampled_positions.append((frame_count, smoothed_x))

                    if debug_enabled and frame_count % stride == 0:
                        prefix = f"[FACE-DEBUG] frame={frame_count} t={t:.2f}s "
                        if chosen is None:
                            print(f"{prefix}faces={len(faces)} chosen=NONE crop_center_x={smoothed_x}", flush=True)
                        else:
                            f = chosen
                            idx = faces.index(f)
                            print(f"{prefix}chosen={idx} "
                                  f"bbox=({f['x1']:.1f},{f['y1']:.1f},{f['x2']:.1f},{f['y2']:.1f}) "
                                  f"conf={f['conf']:.3f} crop_center_x={smoothed_x}", flush=True)

                    frame_count += 1

                cap.release()
            finally:
                flush_vram("face-tracker:yolo")

            # Sidecar with per-frame detection record (instrumentation;
            # the sendcmd format is unchanged).
            track_path = None
            try:
                track_path = os.path.splitext(sendcmd_path)[0] + ".track.json"
                with open(track_path, "w", encoding="utf-8") as f:
                    json.dump(records, f)
            except OSError as exc:  # sidecar is best effort
                print(f"DEBUG: could not write tracker sidecar {track_path}: {exc}")

            final_commands = []
            if sampled_positions:
                for i in range(frame_count):
                    prev_pos = sampled_positions[0]
                    next_pos = sampled_positions[-1]
                    for pos in sampled_positions:
                        if pos[0] <= i:
                            prev_pos = pos
                        if pos[0] >= i:
                            next_pos = pos
                            break

                    if prev_pos[0] == next_pos[0]:
                        crop_x = prev_pos[1]
                    else:
                        tt = (i - prev_pos[0]) / (next_pos[0] - prev_pos[0])
                        crop_x = prev_pos[1] + tt * (next_pos[1] - prev_pos[1])

                    scaled_x = crop_x * scale_factor
                    overlay_x = (target_width / 2.0) - scaled_x
                    min_overlay_x = target_width - original_width * scale_factor
                    max_overlay_x = 0.0
                    overlay_x = max(min_overlay_x, min(max_overlay_x, overlay_x))

                    time_sec = i / fps
                    final_commands.append(f"{time_sec:.3f} overlay x {overlay_x:.2f};")

            with open(sendcmd_path, "w") as f:
                f.write("\n".join(final_commands))

            return True
    except Exception as e:  # noqa: BLE001 - face-tracking failure falls back to a safe overlay
        import traceback
        print(f"DEBUG: Face tracking failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            with open(sendcmd_path, "w") as f:
                f.write("0.000 overlay x -420.0;\n")
        except Exception:  # noqa: BLE001,S110 - best-effort fallback overlay
            pass
        return False


def _write_center_sendcmd(sendcmd_path: str, start_time: float, duration: float,
                          target_width: int) -> None:
    """Best-effort center crop when face tracking is disabled."""
    os.makedirs(os.path.dirname(sendcmd_path), exist_ok=True)
    # Center of source frame: overlay_x = target_width/2 - (orig_width/2)*scale_factor.
    # For a 1920x1080 source this is 540 - 960*1.777 = -1166.7.
    overlay_x = (target_width / 2.0) - 960.0 * (1920.0 / 1080.0)
    fps = 30.0
    n = max(1, round(duration * fps))
    lines = [f"{i / fps:.3f} overlay x {overlay_x:.2f};" for i in range(n)]
    try:
        with open(sendcmd_path, "w") as f:
            f.write("\n".join(lines))
    except OSError:
        pass
