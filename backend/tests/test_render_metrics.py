"""Unit tests for the render-review metrics using synthetic crop trajectories."""
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from render_metrics import (
    CropSample,
    caption_metrics,
    compute_crop_metrics,
    parse_sendcmd,
)


def trajectory(values: list[float], fps: float = 30.0) -> list[CropSample]:
    """Build (time, overlay_x) samples; crop_center_x = 540 - overlay_x."""
    return [CropSample(i / fps, 540.0 - x) for i, x in enumerate(values)]


def test_smooth_path_is_clean():
    # crop_center_x rises a steady 5 px/frame - a fast but bounded pan.
    values = [i * 5.0 for i in range(100)]
    m = compute_crop_metrics(trajectory(values))
    assert m["jumps"] == 0
    assert m["target_switches"] == 0
    assert m["no_detection_frames"] == 0
    assert m["longest_hold_frames"] == 0
    assert m["direction_reversals"] == 0
    assert m["fast_sweeps"] == 0
    assert abs(m["travel_per_1s_window_px"] - 150.0) < 1.0  # 30 deltas * 5 px per 1 s
    # Only the travel term contributes now; a bounded pan is still "clean".
    assert m["glitch_score"] < 0.1


def test_sudden_jump_is_counted():
    values = [0.0] * 50 + [300.0] * 50  # one exact 300 px discontinuity
    m = compute_crop_metrics(trajectory(values))
    assert m["jumps"] == 1
    assert m["target_switches"] == 1
    assert m["max_abs_delta_px"] == 300.0
    assert m["glitch_score"] > 5.0


def test_no_detection_gap_and_longest_hold():
    values = [i * 4.0 for i in range(100)]
    for i in range(20, 41):  # 21 identical frames = 20 flat deltas
        values[i] = values[20]
    m = compute_crop_metrics(trajectory(values))
    assert m["longest_hold_frames"] == 21
    assert m["no_detection_frames"] == 21
    assert m["no_detection_seconds"] > 0
    assert m["glitch_score"] > 0
    assert m["no_detection_fraction"] > 0


def test_empty_trajectory():
    m = compute_crop_metrics([])
    assert m["glitch_score"] == 0.0
    assert m["n_samples"] == 0


def test_parse_sendcmd_and_caption_metrics():
    samples = parse_sendcmd("0.000 overlay x -2333.33;\n0.033 overlay x -2330.00;\n\n")
    assert samples == [CropSample(0.0, -2333.33), CropSample(0.033, -2330.0)]
    caps = caption_metrics([
        {"start": 1.0, "text": "the truth about cheese"},
        {"start": 5.0, "text": "stop making bad decisions"},
    ])
    assert caps["num_captions"] == 2
    assert caps["avg_words_per_caption"] == 4.0
    assert caps["caption_change_times"] == [1.0, 5.0]


def test_new_fields_present():
    m = compute_crop_metrics(trajectory([0.0] * 30))
    for key in (
        "travel_per_1s_window_px", "direction_reversals", "fast_sweeps",
        "no_detection_source",
    ):
        assert key in m, key
    assert m["no_detection_source"] in ("tracker_sidecar", "flat_run_heuristic")


def test_smooth_pan_low_travel_no_reversals():
    # 5 px/frame = 150 px/s: a bounded pan, not a fast sweep (< 400 px/s).
    values = [i * 5.0 for i in range(100)]
    m = compute_crop_metrics(trajectory(values))
    assert m["jumps"] == 0
    assert m["target_switches"] == 0
    assert m["direction_reversals"] == 0
    assert m["fast_sweeps"] == 0
    assert abs(m["travel_per_1s_window_px"] - 150.0) < 1.0


def test_fast_sweep_and_return():
    # 0 -> 1200 px over 1 s, hold, then back to 0 over 1 s.
    values = ([i * 40.0 for i in range(31)]
              + [1200.0] * 31
              + [1200.0 - (i - 61) * 40.0 for i in range(61, 92)])
    m = compute_crop_metrics(trajectory(values))
    assert m["fast_sweeps"] == 2, m
    assert m["direction_reversals"] == 1, m
    assert abs(m["travel_per_1s_window_px"] - 1200.0) < 1.0, m
    assert m["jumps"] == 0  # 40 px/frame < 50 px jump threshold


def test_ping_pong_reversals():
    # Rapid 120 px oscillation: reversals count, but each swing is too brief
    # to be a sustained fast sweep (speed never holds in one direction).
    values = [0.0, 120.0] * 50
    m = compute_crop_metrics(trajectory(values))
    assert m["direction_reversals"] > 0, m
    assert m["fast_sweeps"] == 0, m


def test_flat_hold_is_no_detection():
    values = [i * 4.0 for i in range(100)]
    for i in range(20, 41):  # 22 identical samples = 20 flat deltas
        values[i] = values[20]
    m = compute_crop_metrics(trajectory(values))
    assert m["longest_hold_frames"] == 21
    assert m["no_detection_frames"] == 21
    assert m["no_detection_seconds"] > 0
    assert m["glitch_score"] > 0
    assert m["no_detection_fraction"] > 0


def test_exact_no_detection_from_sidecar():
    values = [100.0 + i * 5.0 for i in range(60)]  # never flat (5 px > 2 px eps), so heuristic = 0
    samples = trajectory(values)
    records = [
        {"detected": True} if i < 30 else {"detected": False}
        for i in range(60)
    ]
    m = compute_crop_metrics(samples, detection_records=records)
    assert m["no_detection_frames"] == 30, m
    assert m["no_detection_fraction"] == 0.5, m
    assert m["no_detection_source"] == "tracker_sidecar"
    # The flat-run heuristic would report 0 (no flat deltas), proving the
    # sidecar is authoritative when provided.
    m_heuristic = compute_crop_metrics(samples)
    assert m_heuristic["no_detection_frames"] == 0, m_heuristic
