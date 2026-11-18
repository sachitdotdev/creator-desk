"""Unit tests for render-review diagnostics (no GPU, no real renders)."""
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import render_review


def test_caption_safe_zone_resolves_inherited_style_margin():
    # Dialogue margin 0 means "inherit from style"; the explicit 400 override
    # must not hide the unsafe 60 px style margin on a 1920 px frame.
    zone = render_review.caption_safe_zone(
        [{"margin_v": 0}, {"margin_v": 400}], 1920, 60
    )
    assert zone["bottom_margin_px"] == 60
    assert zone["bottom_margin_pct"] == 3.12
    assert zone["safe_zone_violation"] is True
    assert zone["margin_source"] == "mixed"


def test_caption_safe_zone_keeps_explicit_override():
    zone = render_review.caption_safe_zone([{"margin_v": 400}], 1920, 60)
    assert zone["bottom_margin_px"] == 400
    assert zone["safe_zone_violation"] is False
    assert zone["margin_source"] == "dialogue"


def test_missed_frames_uses_only_sampled_records(monkeypatch, tmp_path):
    records = [
        {"time": 0.0, "sampled": True, "detected": False},
        {"time": 0.033, "sampled": False, "detected": False},
        {"time": 0.066, "sampled": True, "detected": True},
    ]
    seen: dict = {}

    def fake_sheet(video, times, out_path):
        seen["times"] = times

    monkeypatch.setattr(render_review, "build_contact_sheet", fake_sheet)
    result = render_review.build_missed_frames_sheet(
        None, None, records, Path("render.mp4"), tmp_path / "missed.png"
    )
    assert result["count"] == 1
    assert result["timestamps"] == [0.0]
    assert seen["times"] == [0.0]


def test_black_first_frame_comes_from_frame_zero_luma(monkeypatch):
    periods = [{"black_start": 0.2, "black_end": 0.3, "black_duration": 0.1}]
    monkeypatch.setattr(render_review, "blackdetect_periods", lambda *a, **k: periods)
    monkeypatch.setattr(render_review, "first_frame_luma", lambda *a, **k: [80.0, 16.0])
    report = render_review.black_frame_report(Path("render.mp4"))
    assert report["status"] == "ok"
    assert report["black_first_frame"] is False  # frame zero was not black
    assert report["first_5_luma"] == [80.0, 16.0]
    assert report["black_frame_indices"] == [1]  # later frame is a diagnostic
    assert report["periods"] == periods


def test_black_first_frame_uses_luma_when_no_period_reported(monkeypatch):
    monkeypatch.setattr(render_review, "blackdetect_periods", lambda *a, **k: [])
    monkeypatch.setattr(render_review, "first_frame_luma", lambda *a, **k: [16.1, 80.0])
    report = render_review.black_frame_report(Path("render.mp4"))
    assert report["black_first_frame"] is True
    assert report["periods"] == []


def test_black_frame_report_marks_failed_scan_unavailable(monkeypatch):
    monkeypatch.setattr(
        render_review, "blackdetect_periods", lambda *a, **k: render_review.UNAVAILABLE
    )
    monkeypatch.setattr(
        render_review, "first_frame_luma", lambda *a, **k: render_review.UNAVAILABLE
    )
    report = render_review.black_frame_report(Path("render.mp4"))
    assert report["status"] == render_review.UNAVAILABLE
    assert report["black_first_frame"] == render_review.UNAVAILABLE


def test_main_shows_unavailable_in_json_and_console(monkeypatch, tmp_path, capsys):
    render = tmp_path / "render.mp4"
    render.write_bytes(b"")
    monkeypatch.setattr(
        sys, "argv",
        ["render_review.py", str(render), "--out-dir", str(tmp_path / "reviews")],
    )
    monkeypatch.setattr(render_review, "db_lookup", lambda *a: {
        "clip_id": None, "source_path": None, "start_time": None,
        "sfx_count": None, "crop_path": None,
    })
    monkeypatch.setattr(render_review, "probe_media", lambda *a: {
        "duration": 1.0, "resolution": [1080, 1920], "fps": "30/1",
    })
    monkeypatch.setattr(render_review, "find_ass", lambda *a: None)
    monkeypatch.setattr(render_review, "build_contact_sheet", lambda *a, **k: None)
    monkeypatch.setattr(render_review, "black_frame_report", lambda *a: {
        "status": "unavailable", "periods": "unavailable",
        "black_first_frame": "unavailable", "first_5_luma": "unavailable",
        "black_frame_count": "unavailable", "black_frame_indices": "unavailable",
    })
    monkeypatch.setattr(render_review, "caption_safe_zone", lambda *a, **k: {
        "bottom_margin_pct": None, "margin_source": None,
        "safe_zone_violation": None,
    })
    monkeypatch.setattr(render_review, "build_missed_frames_sheet", lambda *a, **k: {
        "count": 0, "sheet": None, "timestamps": [],
    })

    render_review.main()
    out = capsys.readouterr().out
    assert "black detect  : unavailable" in out
    metrics = json.loads((tmp_path / "reviews" / "render" / "metrics.json").read_text())
    assert metrics["black_detect"]["status"] == "unavailable"
