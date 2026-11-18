"""Unit tests for the render-review metrics using synthetic crop trajectories."""
import subprocess
import sys
import types
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import render_metrics
from render_metrics import (
    CROP_MARGIN_PX,
    CropSample,
    caption_metrics,
    compute_crop_metrics,
    crop_violation_metrics,
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


def test_face_in_crop_clean_when_target_inside_window():
    # Face centre dead-on the crop centre, bbox fully inside the window:
    # no violation.
    records = [
        {"time": i / 30.0, "detected": True, "bbox": [x1, y1, x2, y2], "crop_center_x": cc, "target_x": cc}
        for i, (x1, y1, x2, y2, cc) in enumerate([
            (100.0, 200.0, 300.0, 400.0, 200.0),
            (150.0, 180.0, 250.0, 380.0, 200.0),
        ])
    ]
    v = crop_violation_metrics(records, scale_factor=1.0, target_width=1080.0, margin_px=25.0)
    assert v["available"] is True
    assert v["violations"] == 0
    assert v["violation_fraction"] == 0.0
    assert v["longest_violation"]["count"] == 0


def test_face_in_crop_flags_bbox_outside_window():
    # bbox centre (200, ...) with crop window half-width 540/1.0 = 540 ->
    # window is [cc-540, cc+540]; cc=100 -> window [-440, 640]; bbox at 200 is
    # inside, so instead push the bbox outside: cc=0, bbox centre 700 -> outside.
    records = [
        {"time": 0.0, "detected": True, "bbox": [650.0, 100.0, 750.0, 300.0], "crop_center_x": 0.0, "target_x": 0.0},
    ]
    v = crop_violation_metrics(records, scale_factor=1.0, target_width=1080.0, margin_px=25.0)
    assert v["violations"] == 1
    assert v["violation_fraction"] == 1.0
    assert v["longest_violation"]["count"] == 1


def test_face_in_crop_margin_touches_edge_is_violation():
    # Window half-width = 540 source px (scale 1.0, target 1080). With margin 25,
    # the centre must stay within 540-25 = 515 px of the window centre; a centre
    # exactly at the window edge (540) is "touching" -> violation.
    records = [
        {"time": 1.0, "detected": True, "bbox": [40.0, 100.0, 60.0, 300.0], "crop_center_x": 500.0, "target_x": 500.0},
    ]
    # bbox centre = 50, |50-500| = 450 <= 515 -> inside, no violation.
    v = crop_violation_metrics(records, scale_factor=1.0, target_width=1080.0, margin_px=25.0)
    assert v["violations"] == 0
    records[0]["bbox"] = [0.0, 100.0, 20.0, 300.0]  # centre = 10, |10-500|=490 <= 515 -> still inside
    v = crop_violation_metrics(records, scale_factor=1.0, target_width=1080.0, margin_px=25.0)
    assert v["violations"] == 0
    records[0]["bbox"] = [0.0, 100.0, 1080.0, 300.0]  # centre = 540 -> touching right edge -> violation
    v = crop_violation_metrics(records, scale_factor=1.0, target_width=1080.0, margin_px=25.0)
    assert v["violations"] == 1


def test_face_in_crop_undetected_is_violation():
    records = [
        {"time": 0.0, "detected": False, "bbox": None, "crop_center_x": None, "target_x": None},
        {"time": 0.033, "detected": True, "bbox": [100.0, 100.0, 200.0, 300.0], "crop_center_x": 150.0, "target_x": 150.0},
    ]
    v = crop_violation_metrics(records, scale_factor=1.0, target_width=1080.0)
    assert v["violations"] == 1
    assert v["violation_fraction"] == 0.5


def test_face_in_crop_no_records_no_violations():
    v = crop_violation_metrics(None, scale_factor=1.0, target_width=1080.0)
    assert v["available"] is False
    assert v["violations"] == 0
    assert v["violation_fraction"] == 0.0


def test_glitch_score_includes_crop_violation_term():
    samples = trajectory([0.0] * 30)
    records = [
        {"time": i / 30.0, "detected": True, "bbox": [700.0, 100.0, 900.0, 300.0], "crop_center_x": 0.0, "target_x": 0.0}
        for i in range(30)
    ]
    m = compute_crop_metrics(samples, detection_records=records, crop_margin_px=25.0)
    assert m["crop_violation_fraction"] > 0
    assert m["crop_violation"]["violations"] > 0
    # The crop term must be part of the glitch score.
    base = (
        1.0 * m["jumps_per_min"]
        + 5.0 * m["target_switches"]
        + 100.0 * m["no_detection_fraction"]
        + 0.5 * (m["travel_per_1s_window_px"] / 1000.0)
        + 2.0 * m["direction_reversals"]
        + 3.0 * m["fast_sweeps"]
    )
    assert m["glitch_score"] > base


def test_crop_violation_default_margin_from_config_constant():
    assert CROP_MARGIN_PX > 0


def test_reversals_resume_after_pause_outside_window():
    # Two excursions separated by a 2.8 s pause. The extremum at t=3.0 s is
    # outside the 2 s reversal window, but it must still become the reference
    # for the next excursion so the second reversal is counted.
    values = [0.0, 200.0, 0.0, 0.0, 200.0, 0.0]
    times = [0.0, 0.1, 0.2, 3.0, 3.1, 3.2]
    samples = [CropSample(t, 540.0 - x) for t, x in zip(times, values)]
    m = compute_crop_metrics(
        samples, reversal_threshold_px=100.0, reversal_window_seconds=2.0
    )
    assert m["direction_reversals"] == 2, m


def test_no_detection_uses_only_sampled_frames():
    samples = trajectory([100.0 + i * 5.0 for i in range(60)])
    # FACE_DETECTION_STRIDE=3: only every third frame ran detection; ten of
    # those twenty sampled frames found no face.
    records = [
        {"sampled": i % 3 == 0, "detected": not (i % 3 == 0 and i >= 30)}
        for i in range(60)
    ]
    m = compute_crop_metrics(samples, detection_records=records)
    assert m["no_detection_source"] == "tracker_sidecar"
    assert m["no_detection_population"] == 20
    assert m["no_detection_frames"] == 10
    assert m["no_detection_fraction"] == 0.5


def test_margin_equality_boundary_is_a_violation():
    # half window = 540, margin 25 -> tol = 515. A bbox centre exactly 515 px
    # from the crop centre touches the margin and must be a violation.
    records = [{
        "time": 0.0, "detected": True,
        "bbox": [1010.0, 100.0, 1020.0, 300.0],  # centre 1015 = 500 + 515
        "crop_center_x": 500.0, "target_x": 500.0,
    }]
    v = crop_violation_metrics(
        records, scale_factor=1.0, target_width=1080.0, margin_px=25.0
    )
    assert v["violations"] == 1
    assert v["violation_fraction"] == 1.0


def test_first_frame_luma_stops_after_requested_frames(monkeypatch):
    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        return types.SimpleNamespace(
            returncode=0,
            stdout="lavfi.signalstats.YAVG=16.10\nlavfi.signalstats.YAVG=78.50\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    values = render_metrics.first_frame_luma("ffmpeg", "render.mp4", n_frames=5)
    assert values == [16.1, 78.5]
    assert commands[0][commands[0].index("-frames:v") + 1] == "5"


def test_ffmpeg_analysis_reports_unavailable_on_failure(monkeypatch):
    def timed_out(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr(subprocess, "run", timed_out)
    assert render_metrics.first_frame_luma("ffmpeg", "render.mp4") == render_metrics.UNAVAILABLE
    assert render_metrics.blackdetect_periods("ffmpeg", "render.mp4") == render_metrics.UNAVAILABLE

    def failed(cmd, **kwargs):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="ffmpeg failed")

    monkeypatch.setattr(subprocess, "run", failed)
    assert render_metrics.first_frame_luma("ffmpeg", "render.mp4") == render_metrics.UNAVAILABLE
    assert render_metrics.blackdetect_periods("ffmpeg", "render.mp4") == render_metrics.UNAVAILABLE


def test_ffmpeg_analysis_success_with_no_findings_is_empty_list(monkeypatch):
    def ok(cmd, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", ok)
    assert render_metrics.first_frame_luma("ffmpeg", "render.mp4") == []
    assert render_metrics.blackdetect_periods("ffmpeg", "render.mp4") == []
