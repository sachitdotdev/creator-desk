"""Pure, dependency-free calculations used by ``tools/render_review.py``.

This module has no side effects and no third-party imports so it can be unit
tested (see ``backend/tests/test_render_metrics.py``) with synthetic crop
trajectories without FFmpeg, a GPU, or the app stack installed.

Input data
----------
The renderer's face tracker writes one FFmpeg ``sendcmd`` line per video frame
to ``data/renders/crop_<clip_id>.txt``::

    0.000 overlay x -2333.33;

``overlay_x`` is the horizontal offset of the full-frame image inside the 1080px
output: ``overlay_x = target_width/2 - crop_x * scale_factor``. Given the source
video height, ``scale_factor = 1920 / source_height`` and ``crop_center_x`` (in
original source pixels) is recovered with::

    crop_center_x = (target_width / 2 - overlay_x) / scale_factor

If the source height is unknown, ``scale_factor`` defaults to 1.0 and
``crop_center_x`` is reported in raw overlay pixels (documented in metrics.json).

The tracker also writes a sidecar per-frame detection record to
``crop_<clip_id>.track.json`` (one JSON object per frame, see
``app.services.face_tracker``)::

    {"time": 0.033, "frame": 1, "detected": true, "conf": 0.82,
     "bbox": [900.0, 400.0, 1080.0, 580.0], "crop_center_x": 990.0}

Metrics definitions
-------------------
* ``jumps``            - consecutive samples whose |delta crop_center_x| exceeds
  ``jump_threshold_px`` (default 50 px). A fast but bounded pan is *not* a jump.
* ``target_switches``  - consecutive samples whose |delta| exceeds
  ``switch_threshold_px`` (default 150 px); a large reposition consistent with
  the tracker jumping to a different face. Counted as a subset of jumps.
* ``longest_hold``     - longest run of consecutive samples with |delta| <=
  ``hold_epsilon_px`` (default 2 px), reported in frames and seconds.
* ``no_detection``     - frames where the tracker found no face. When the
  tracker sidecar is available this is exact (sampled frames with
  ``detected == false``); otherwise it is the HEURISTIC approximation used
  before: a flat run of at least ``min_flat_run`` consecutive samples
  (default 10 ~= 0.33 s at 30 fps). A held last-known position is exactly what
  the tracker emits when no face is found.
* ``travel_per_1s_window_px`` - the greatest sum of |delta crop_center_x|
  observed inside any rolling 1-second window. Captures fast, sustained pans
  that stay under the per-frame jump threshold but still swing the crop across
  the frame.
* ``direction_reversals`` - count of direction reversals (a pan one way then
  back the other) whose amplitude exceeds ``reversal_threshold_px`` (default
  100 px) and which unfold inside ``reversal_window_seconds`` (default 2 s).
  Measures "ping-pong" / wrong-target flipping between faces.
* ``fast_sweeps`` - count of sustained, unidirectional sweeps where the crop
  speed stays above ``fast_sweep_px_per_s`` (default 400 px/s) for at least
  ``fast_sweep_min_seconds`` (default 0.5 s). Measures uncontrolled rapid pans
  onto empty space; a direction change ends a sweep.
* ``glitch_score``     - dimensionless, higher is worse::

      jumps_per_min = jumps / (n_samples / fps / 60)
      no_detection_fraction = no_detection_frames / n_samples
      travel_score = travel_per_1s_window_px / 1000.0   # per 1000 px of 1 s travel
      glitch_score = 1.0 * jumps_per_min
                   + 5.0 * target_switches
                   + 100.0 * no_detection_fraction
                   + 0.5 * travel_score
                   + 2.0 * direction_reversals
                   + 3.0 * fast_sweeps

  Weighting rationale: a single target switch is 5x a jump per minute, and a
  tracker that is blind for half a clip scores ~50 from that term alone. A
  1000 px/s one-second travel adds 0.5, each reversal adds 2, and each fast
  sweep adds 3 -- so a clip that swings wildly but never formally "jumps"
  still surfaces in the score.

  The glitch score also carries a face-in-crop term: ``CROP_VIOLATION_WEIGHT *
  crop_violation_fraction`` where the fraction is the per-sample share of
  timeline where the chosen target bbox centre is outside (or within the
  safety margin of) the crop window.
"""
from __future__ import annotations

import re
from typing import NamedTuple

JUMP_THRESHOLD_PX = 50.0
SWITCH_THRESHOLD_PX = 150.0
HOLD_EPSILON_PX = 2.0
MIN_FLAT_RUN = 10
TARGET_WIDTH = 1080.0

# --- New stability knobs (all configurable via compute_crop_metrics kwargs) ---
# Rolling 1 s window: report the maximum |delta| travel seen inside any 1 s.
TRAVEL_WINDOW_SECONDS = 1.0
# Direction reversal: amplitude must exceed this many px and complete within
# this many seconds to count as a reversal (ping-pong / wrong-target flip).
REVERSAL_THRESHOLD_PX = 100.0
REVERSAL_WINDOW_SECONDS = 2.0
# Fast sweep: speed must stay above this many px/s for at least this many
# seconds to count as a sweep (pan onto empty space).
FAST_SWEEP_PX_PER_S = 400.0
FAST_SWEEP_MIN_SECONDS = 0.5
# Caption safe-zone threshold: caption bottom margin must stay above this
# fraction of frame height to be considered safe.
SAFE_ZONE_BOTTOM_PCT = 0.18
# Face-in-crop: how much slack (source px) the chosen target's bbox center may
# sit inside the crop window before it is flagged. Violations are samples whose
# chosen bbox center lies outside the crop window or touches/within the margin
# of an edge.
CROP_MARGIN_PX = 25.0
# Glitch-score weight for face-in-crop violations (fraction of timeline).
CROP_VIOLATION_WEIGHT = 10.0

_SENDCMD_RE = re.compile(r"^\s*([\d.]+)\s+overlay\s+x\s+(-?[\d.]+)")

# Explicit status returned by the ffmpeg analysis helpers when the scan fails
# or times out. A successful scan with no findings still returns an empty list.
UNAVAILABLE = "unavailable"

# When crop generation falls back (model missing, capture failure, exception),
# the tracker replaces its sidecar with explicit metadata instead of per-frame
# detections. Tools must report that tracking metrics are unavailable rather
# than silently reading detections left by an earlier render of the same clip.
TRACKER_FALLBACK_MESSAGE = "tracker fallback used, tracking metrics unavailable"


def tracker_fallback_reason(detection_records) -> str | None:
    """Return the reason when a sidecar is an explicit fallback marker."""
    if isinstance(detection_records, dict) and detection_records.get("fallback") is True:
        return str(detection_records.get("reason") or "unknown")
    return None


class CropSample(NamedTuple):
    time: float
    overlay_x: float


def parse_sendcmd(text: str) -> list[CropSample]:
    """Parse the ``sendcmd`` crop file body into (time, overlay_x) samples."""
    samples: list[CropSample] = []
    for line in text.splitlines():
        match = _SENDCMD_RE.match(line)
        if match:
            samples.append(CropSample(float(match.group(1)), float(match.group(2))))
    return samples


def _rolling_max_travel(crop_x: list[float], times: list[float], window_s: float) -> float:
    """Greatest sum of |delta| inside any contiguous window of ``window_s`` s."""
    best = 0.0
    n = len(crop_x)
    j = 0
    for i in range(n):
        if j < i:
            j = i
        while j + 1 < n and times[j + 1] - times[i] <= window_s:
            j += 1
        travel = sum(abs(crop_x[k] - crop_x[k - 1]) for k in range(i + 1, j + 1))
        if travel > best:
            best = travel
    return best


def _count_reversals(
    crop_x: list[float], times: list[float], threshold_px: float, window_s: float
) -> int:
    """Count direction reversals of amplitude > threshold_px within window_s s.

    A reversal is a local extremum (peak or trough) in the trajectory whose
    |amplitude| vs the previous extremum exceeds ``threshold_px`` and which
    occurs within ``window_s`` of that previous extremum. Each qualifying
    extremum after the first counts as one reversal.
    """
    if len(crop_x) < 3:
        return 0
    deltas = [crop_x[i] - crop_x[i - 1] for i in range(1, len(crop_x))]
    # Sign of movement; zero deltas keep the previous sign so flat stretches
    # don't manufacture reversals.
    signs = []
    prev = 0
    for d in deltas:
        s = 1 if d > 0 else (-1 if d < 0 else prev)
        signs.append(s)
        if d != 0:
            prev = s
    reversals = 0
    last_extremum_idx = None  # index into deltas of last counted extremum
    for i in range(1, len(deltas)):
        if signs[i] != 0 and signs[i - 1] != 0 and signs[i] != signs[i - 1]:
            # Reversal point between sample i-1 and i (delta index i-1).
            amp = abs(crop_x[i] - crop_x[i - 1])
            # Amplitude of the swing that just reversed: compare current sample
            # to the sample at the previous reversal (or start).
            if last_extremum_idx is None:
                swing = abs(crop_x[i] - crop_x[0])
            else:
                swing = abs(crop_x[i] - crop_x[last_extremum_idx])
            within_time = True
            if last_extremum_idx is not None:
                within_time = (times[i] - times[last_extremum_idx]) <= window_s
            if swing > threshold_px and within_time:
                reversals += 1
            # The reference extremum advances even when the swing does not
            # qualify (e.g. it followed a long pause), so counting can resume
            # on the next excursion instead of being stuck on an old sample.
            last_extremum_idx = i
    return reversals


def _count_fast_sweeps(
    crop_x: list[float], times: list[float], fps: float, px_per_s: float, min_s: float
) -> int:
    """Count maximal unidirectional runs where speed stays above px_per_s
    for at least min_s s.

    A sweep must move in one direction; a direction change ends the sweep.
    This separates a sustained pan onto empty space (one sweep) from ping-pong
    between two faces (no sustained sweep) and from a sweep-and-return (two
    sweeps when a pause separates them).
    """
    if len(crop_x) < 2:
        return 0
    dt = 1.0 / fps
    count = 0
    i = 1
    n = len(crop_x)
    while i < n:
        d = crop_x[i] - crop_x[i - 1]
        if abs(d) / dt <= px_per_s:
            i += 1
            continue
        start = i - 1
        direction = 1 if d > 0 else -1
        i += 1
        while i < n:
            d = crop_x[i] - crop_x[i - 1]
            sp = abs(d) / dt
            sgn = 1 if d > 0 else (-1 if d < 0 else direction)
            if sp > px_per_s and sgn == direction:
                i += 1
            else:
                break
        duration = times[i - 1] - times[start]
        if duration >= min_s:
            count += 1
    return count


def compute_crop_metrics(
    samples: list[CropSample],
    *,
    fps: float = 30.0,
    scale_factor: float | None = None,
    target_width: float = TARGET_WIDTH,
    jump_threshold_px: float = JUMP_THRESHOLD_PX,
    switch_threshold_px: float = SWITCH_THRESHOLD_PX,
    hold_epsilon_px: float = HOLD_EPSILON_PX,
    min_flat_run: int = MIN_FLAT_RUN,
    travel_window_seconds: float = TRAVEL_WINDOW_SECONDS,
    reversal_threshold_px: float = REVERSAL_THRESHOLD_PX,
    reversal_window_seconds: float = REVERSAL_WINDOW_SECONDS,
    fast_sweep_px_per_s: float = FAST_SWEEP_PX_PER_S,
    fast_sweep_min_seconds: float = FAST_SWEEP_MIN_SECONDS,
    detection_records: list[dict] | None = None,
    crop_margin_px: float = CROP_MARGIN_PX,
) -> dict:
    """Compute face-tracking stability metrics from a crop trajectory.

    ``samples`` are consecutive per-frame ``(time, overlay_x)`` values in the
    order emitted by the renderer. ``fps`` converts frame counts to seconds.

    ``detection_records`` (optional) is the tracker's per-frame sidecar, a list
    of dicts with at least a ``detected`` bool; when provided it is used for
    the exact ``no_detection`` count instead of the flat-run heuristic. A
    fallback marker sidecar yields an explicit "unavailable" result instead.
    """
    fallback_reason = tracker_fallback_reason(detection_records)
    if fallback_reason is not None:
        sf = scale_factor if scale_factor and scale_factor > 0 else 1.0
        return {
            "available": False,
            "fallback": True,
            "reason": TRACKER_FALLBACK_MESSAGE,
            "fallback_reason": fallback_reason,
            "n_samples": len(samples),
            "crop_violation": {
                "available": False,
                "source": "tracker_fallback",
                "reason": TRACKER_FALLBACK_MESSAGE,
                "margin_px": float(crop_margin_px),
                "half_window_px": (float(target_width) / 2.0) / sf,
                "violations": 0,
                "samples": 0,
                "violation_fraction": 0.0,
                "longest_violation": {
                    "start": None, "end": None, "duration_s": 0.0, "count": 0,
                },
            },
        }

    sf = scale_factor if scale_factor and scale_factor > 0 else 1.0
    crop_x = [round((target_width / 2.0 - s.overlay_x) / sf, 2) for s in samples]
    times = [s.time for s in samples]
    n = len(samples)

    result: dict = {
        "n_samples": n,
        "scale_factor": sf,
        "scale_factor_source": "source_height" if scale_factor else "raw_overlay_px",
        "crop_center_x": crop_x,
        "jump_threshold_px": jump_threshold_px,
        "switch_threshold_px": switch_threshold_px,
        "hold_epsilon_px": hold_epsilon_px,
        "min_flat_run": min_flat_run,
        "travel_window_seconds": travel_window_seconds,
        "reversal_threshold_px": reversal_threshold_px,
        "reversal_window_seconds": reversal_window_seconds,
        "fast_sweep_px_per_s": fast_sweep_px_per_s,
        "fast_sweep_min_seconds": fast_sweep_min_seconds,
    }
    if n == 0:
        result.update(
            jumps=0, target_switches=0,
            longest_hold_frames=0, longest_hold_seconds=0.0,
            no_detection_frames=0, no_detection_seconds=0.0,
            jumps_per_min=0.0, no_detection_fraction=0.0, glitch_score=0.0,
            max_abs_delta_px=0.0,
            travel_per_1s_window_px=0.0,
            direction_reversals=0,
            fast_sweeps=0,
            no_detection_source="none",
            no_detection_population=0,
        )
        return result

    deltas = [abs(crop_x[i] - crop_x[i - 1]) for i in range(1, n)]
    jumps = sum(1 for d in deltas if d > jump_threshold_px)
    switches = sum(1 for d in deltas if d > switch_threshold_px)

    # Consecutive flat deltas (|delta| <= epsilon) form a hold / no-detection
    # run. A run of L flat deltas covers L + 1 samples held at one position.
    runs: list[tuple[int, int]] = []  # (start_delta_index, length_in_deltas)
    i = 0
    while i < len(deltas):
        if deltas[i] <= hold_epsilon_px:
            j = i
            while j < len(deltas) and deltas[j] <= hold_epsilon_px:
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    longest = max((length + 1 for _, length in runs), default=0)

    # Exact no-detection count from the tracker sidecar when available. With
    # FACE_DETECTION_STRIDE > 1 only sampled frames actually ran detection, so
    # they are the population (numerator AND denominator) for this metric.
    if detection_records:
        sampled = [r for r in detection_records if r.get("sampled", True)]
        no_detection_frames = sum(1 for r in sampled if not r.get("detected", False))
        no_detection_population = len(sampled)
        no_detection_source = "tracker_sidecar"
    else:
        no_detection_frames = min(
            sum(length + 1 for _, length in runs if length >= min_flat_run), n
        )
        no_detection_population = n
        no_detection_source = "flat_run_heuristic"

    duration_seconds = (samples[-1].time - samples[0].time) or (n / fps)
    minutes = max(duration_seconds, 1.0) / 60.0
    jumps_per_min = jumps / minutes
    no_detection_fraction = (no_detection_frames / no_detection_population
                             if no_detection_population else 0.0)
    longest_seconds = longest / fps

    travel_per_1s_window_px = _rolling_max_travel(crop_x, times, travel_window_seconds)
    direction_reversals = _count_reversals(
        crop_x, times, reversal_threshold_px, reversal_window_seconds
    )
    fast_sweeps = _count_fast_sweeps(
        crop_x, times, fps, fast_sweep_px_per_s, fast_sweep_min_seconds
    )

    crop_violation = crop_violation_metrics(
        detection_records,
        scale_factor=scale_factor,
        target_width=target_width,
        margin_px=crop_margin_px,
    )
    crop_violation_fraction = float(crop_violation.get("violation_fraction") or 0.0)

    glitch_score = (
        1.0 * jumps_per_min
        + 5.0 * switches
        + 100.0 * no_detection_fraction
        + 0.5 * (travel_per_1s_window_px / 1000.0)
        + 2.0 * direction_reversals
        + 3.0 * fast_sweeps
        + CROP_VIOLATION_WEIGHT * crop_violation_fraction
    )

    result.update(
        jumps=jumps,
        target_switches=switches,
        longest_hold_frames=longest,
        longest_hold_seconds=round(longest_seconds, 3),
        no_detection_frames=no_detection_frames,
        no_detection_seconds=round(no_detection_frames / fps, 3),
        jumps_per_min=round(jumps_per_min, 3),
        no_detection_fraction=round(no_detection_fraction, 4),
        glitch_score=round(glitch_score, 3),
        max_abs_delta_px=round(max(deltas, default=0.0), 2),
        travel_per_1s_window_px=round(travel_per_1s_window_px, 2),
        direction_reversals=direction_reversals,
        fast_sweeps=fast_sweeps,
        no_detection_source=no_detection_source,
        no_detection_population=no_detection_population,
        crop_violation=crop_violation,
        crop_violation_fraction=round(crop_violation_fraction, 4),
    )
    return result


def crop_violation_metrics(
    detection_records: list[dict] | None,
    *,
    scale_factor: float | None = None,
    target_width: float = TARGET_WIDTH,
    margin_px: float = CROP_MARGIN_PX,
) -> dict:
    """Per-sample check that the chosen target's bbox centre is inside the crop.

    The face crop is a square of side ``target_width / scale_factor`` source
    pixels centred on the chosen target's centre (``crop_center_x`` /
    ``target_x``). A sample is a *violation* when the chosen bbox centre lies
    outside that window or within ``margin_px`` of an edge (touching counts as
    a violation). Samples with no chosen bbox (no detection / lost target) are
    violations too - the crop cannot be on a face that was never chosen.

    Returns a dict with the violation fraction, the violating sample count and
    the longest consecutive violation run (timestamps + duration). A fallback
    marker sidecar is reported as unavailable, never as a clean trajectory.
    """
    fallback_reason = tracker_fallback_reason(detection_records)
    if fallback_reason is not None:
        sf = scale_factor if scale_factor and scale_factor > 0 else 1.0
        return {
            "available": False,
            "source": "tracker_fallback",
            "reason": TRACKER_FALLBACK_MESSAGE,
            "fallback_reason": fallback_reason,
            "margin_px": float(margin_px),
            "half_window_px": (float(target_width) / 2.0) / sf,
            "violations": 0,
            "samples": 0,
            "violation_fraction": 0.0,
            "longest_violation": {
                "start": None, "end": None, "duration_s": 0.0, "count": 0,
            },
        }

    sf = scale_factor if scale_factor and scale_factor > 0 else 1.0
    half = (float(target_width) / 2.0) / sf  # crop window half-size, source px
    tol = max(half - float(margin_px), 0.0)

    result = {
        "available": bool(detection_records),
        "source": "tracker_sidecar" if detection_records else "none",
        "margin_px": float(margin_px),
        "half_window_px": half,
        "violations": 0,
        "samples": 0,
        "violation_fraction": 0.0,
    }
    if not detection_records:
        return result

    n = len(detection_records)
    violating_flags: list[bool] = []
    for r in detection_records:
        bbox = r.get("bbox") if isinstance(r.get("bbox"), (list, tuple)) else None
        if not bbox or len(bbox) < 4:
            violating_flags.append(True)
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox[:4])
        fcx = (x1 + x2) / 2.0
        fcy = (y1 + y2) / 2.0
        w = max(x2 - x1, 0.0)
        h = max(y2 - y1, 0.0)
        cx = float(r.get("crop_center_x") or r.get("target_x") or 0.0)
        inside = (fcx - w / 2.0) >= (cx - half) and (fcx + w / 2.0) <= (cx + half)
        if abs(fcx - cx) >= tol or not inside:
            violating_flags.append(True)
        else:
            violating_flags.append(False)

    violating_flags = violating_flags[:n]
    n_viol = sum(1 for v in violating_flags if v)
    result["violations"] = n_viol
    result["samples"] = n
    result["violation_fraction"] = (n_viol / n) if n else 0.0

    # Longest consecutive run of violations (timestamps + duration).
    best: dict = {"start": None, "end": None, "duration_s": 0.0, "count": 0}
    run_start: float | None = None
    run_end: float | None = None
    run_count = 0
    for i, flag in enumerate(violating_flags):
        t = float(detection_records[i].get("time") or 0.0)
        if flag:
            if run_start is None:
                run_start = t
            run_end = t
            run_count += 1
        else:
            if run_start is not None and run_end is not None:
                dur = run_end - run_start
                if dur > best["duration_s"] or best["count"] == 0:
                    best = {"start": round(run_start, 3), "end": round(run_end, 3), "duration_s": dur, "count": run_count}
            run_start = None
            run_end = None
            run_count = 0
    if run_start is not None and run_end is not None:
        dur = run_end - run_start
        if dur > best["duration_s"] or best["count"] == 0:
            best = {"start": round(run_start, 3), "end": round(run_end, 3), "duration_s": dur, "count": run_count}

    result["longest_violation"] = best
    return result


def caption_metrics(dialogues: list[dict]) -> dict:
    """Summarize ASS Dialogue entries.

    Each dict needs ``start`` (seconds) and ``text`` (already stripped of ASS
    override tags). Returns caption count, average words per caption and the
    sorted caption-change (start) times.
    """
    n = len(dialogues)
    total_words = sum(len(d["text"].split()) for d in dialogues)
    return {
        "num_captions": n,
        "avg_words_per_caption": round(total_words / n, 2) if n else 0.0,
        "caption_change_times": sorted(d["start"] for d in dialogues),
    }


def first_frame_luma(ffmpeg: str, render_path: str, *, n_frames: int = 5, timeout: int = 120) -> list[float] | str:
    """Mean luma (YAVG) of the first ``n_frames`` via ffmpeg signalstats.

    Complements blackdetect: a single black frame at t=0 can hide behind
    blackdetect's minimum-duration threshold, but shows up here as YAVG ~16
    while the following frames sit around ~80.

    Returns ``UNAVAILABLE`` on a failed/timed-out scan; an empty list means a
    successful scan that found no luma samples.
    """
    import subprocess

    n = max(1, n_frames)
    select = f"select='lt(n\\,{n})',signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "info", "-i", str(render_path),
           "-frames:v", str(n), "-vf", select, "-an", "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return UNAVAILABLE
    if proc.returncode != 0:
        return UNAVAILABLE
    return [float(line.split("=", 1)[1]) for line in (proc.stdout or "").splitlines()
            if line.startswith("lavfi.signalstats.YAVG=")]


def blackdetect_periods(ffmpeg: str, render_path: str, *, timeout: int = 120, min_duration: float = 0.04, pix_th: float = 0.10) -> list[dict] | str:
    """Run ffmpeg blackdetect on ``render_path`` and return black periods.

    ``min_duration`` defaults to 0.04 s (one frame at 25 fps) so short black
    starts are caught; the historical 0.2 s default silently hid them.

    Each dict: ``black_start``, ``black_end``, ``black_duration`` (seconds).
    Returns [] only for a successful scan with no findings; a failed or
    timed-out scan returns ``UNAVAILABLE``.
    """
    import subprocess

    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "info", "-an",
        "-i", str(render_path),
        "-vf", f"blackdetect=d={min_duration}:pix_th={pix_th}",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return UNAVAILABLE
    if proc.returncode != 0:
        return UNAVAILABLE
    periods: list[dict] = []
    for line in (proc.stderr or "").splitlines():
        if "black_start" not in line:
            continue
        fields: dict[str, float] = {}
        for token in line.split():
            if "black_start" in token:
                fields["black_start"] = float(token.split(":", 1)[1])
            elif "black_end" in token:
                fields["black_end"] = float(token.split(":", 1)[1])
            elif "black_duration" in token:
                fields["black_duration"] = float(token.split(":", 1)[1])
        if len(fields) == 3:
            periods.append({k: round(v, 3) for k, v in fields.items()})
    return periods
