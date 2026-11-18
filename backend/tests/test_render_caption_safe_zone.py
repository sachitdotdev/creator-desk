"""Caption safe-zone: render-time bottom margin clamp (never edits templates)."""

import pytest

from app.core.config import CAPTION_SAFE_BOTTOM_PCT
from app.services import render_service
from app.services.render_service import effective_caption_margin_v


def test_default_template_margin_is_raised_to_safe_zone():
    # Default template stores margin_v=120 (6.25%); 0.18*1920 = 345.6 px.
    assert CAPTION_SAFE_BOTTOM_PCT == 0.18
    assert effective_caption_margin_v({"caption": {"margin_v": 120}}) == pytest.approx(345.6)


def test_margin_above_safe_zone_is_left_unchanged():
    assert effective_caption_margin_v({"caption": {"margin_v": 400}}) == 400.0


def test_missing_or_invalid_margin_uses_default_then_clamps():
    assert effective_caption_margin_v({}) == pytest.approx(345.6)
    assert effective_caption_margin_v({"caption": {"margin_v": "bad"}}) == pytest.approx(345.6)


def test_enforce_toggle_off_keeps_template_value(monkeypatch):
    monkeypatch.setattr(render_service, "CAPTION_SAFE_ZONE_ENFORCE", False)
    assert effective_caption_margin_v({"caption": {"margin_v": 120}}) == 120.0


def test_custom_safe_pct(monkeypatch):
    monkeypatch.setattr(render_service, "CAPTION_SAFE_BOTTOM_PCT", 0.25)
    assert effective_caption_margin_v({"caption": {"margin_v": 120}}) == pytest.approx(480.0)
