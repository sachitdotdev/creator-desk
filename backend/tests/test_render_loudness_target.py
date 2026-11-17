"""Unit tests for the effective loudnorm true-peak target clamp."""
from __future__ import annotations

import logging

import pytest

from app.services import render_service


@pytest.mark.parametrize(
    "target, headroom, expected",
    [
        (-1.5, 0.5, -2.0),   # normal case: in range, no warning
        (-8.8, 0.5, -9.0),   # below -9.0: clamped up
        (0.25, -0.5, 0.0),   # above 0.0: clamped down
    ],
)
def test_effective_loudness_target_tp_is_clamped(
    monkeypatch, caplog, target, headroom, expected
):
    monkeypatch.setattr(render_service, "LOUDNESS_TARGET_TP", target)
    monkeypatch.setattr(render_service, "LOUDNESS_TP_HEADROOM", headroom)

    with caplog.at_level(logging.WARNING):
        result = render_service._effective_loudness_target_tp()

    assert result == pytest.approx(expected)
    warnings = [r for r in caplog.records if "clamping" in r.message]
    if target - headroom != expected:
        assert len(warnings) == 1
    else:
        assert warnings == []
