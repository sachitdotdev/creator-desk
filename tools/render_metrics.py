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

Metrics definitions
-------------------
* ``jumps``            - consecutive samples whose |delta crop_center_x| exceeds
  ``jump_threshold_px`` (default 50 px). A fast but bounded pan is *not* a jump.
* ``target_switches``  - consecutive samples whose |delta| exceeds
  ``switch_threshold_px`` (default 150 px); a large reposition consistent with
  the tracker jumping to a different face. Counted as a subset of jumps.
* ``longest_hold``     - longest run of consecutive samples with |delta| <=
  ``hold_epsilon_px`` (default 2 px), reported in frames and seconds.
* ``no_detection``     - HEURISTIC: sendcmd data has no detection flag, so a
  "no detection" frame is approximated as one inside a flat run of at least
  ``min_flat_run`` consecutive samples (default 10 ~= 0.33 s at 30 fps). A held
  last-known position is exactly what the tracker emits when no face is found.
* ``glitch_score``     - dimensionless, higher is worse::

      jumps_per_min = jumps / (n_samples / fps / 60)
      no_detection_fraction = no_detection_frames / n_samples
      glitch_score = 1.0 * jumps_per_min
                   + 5.0 * target_switches
                   + 100.0 * no_detection_fraction

  Weighting rationale: a single target switch is 5x a jump per minute, and a
  tracker that is blind for half a clip scores ~50 from that term alone.
"""
from __future__ import annotations

import re
from typing import NamedTuple

JUMP_THRESHOLD_PX = 50.0
SWITCH_THRESHOLD_PX = 150.0
HOLD_EPSILON_PX = 2.0
MIN_FLAT_RUN = 10
TARGET_WIDTH = 1080.0

_SENDCMD_RE = re.compile(r"^\s*([\d.]+)\s+overlay\s+x\s+(-?[\d.]+)")


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
) -> dict:
    """Compute face-tracking stability metrics from a crop trajectory.

    ``samples`` are consecutive per-frame ``(time, overlay_x)`` values in the
    order emitted by the renderer. ``fps`` converts frame counts to seconds.
    """
    sf = scale_factor if scale_factor and scale_factor > 0 else 1.0
    crop_x = [round((target_width / 2.0 - s.overlay_x) / sf, 2) for s in samples]
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
    }
    if n == 0:
        result.update(
            jumps=0, target_switches=0,
            longest_hold_frames=0, longest_hold_seconds=0.0,
            no_detection_frames=0, no_detection_seconds=0.0,
            jumps_per_min=0.0, no_detection_fraction=0.0, glitch_score=0.0,
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

    no_detection_frames = min(
        sum(length + 1 for _, length in runs if length >= min_flat_run), n
    )

    duration_seconds = (samples[-1].time - samples[0].time) or (n / fps)
    minutes = max(duration_seconds, 1.0) / 60.0
    jumps_per_min = jumps / minutes
    no_detection_fraction = no_detection_frames / n
    longest_seconds = longest / fps

    glitch_score = (
        1.0 * jumps_per_min
        + 5.0 * switches
        + 100.0 * no_detection_fraction
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
    )
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
