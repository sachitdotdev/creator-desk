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
    assert m["glitch_score"] == 0.0


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
