"""Phase 3.6 - render_service resolves template bgm_track defensively."""

import logging

import pytest

from app.core.config import AUDIO_MUSIC_VOLUME
from app.services import music_service
from app.services.render_service import resolve_bgm_settings


@pytest.fixture
def music_dir(tmp_path, monkeypatch):
    target = tmp_path / "music"
    target.mkdir()
    monkeypatch.setattr(music_service, "MUSIC_DIR", target)
    return target


def test_existing_track_resolves_through_music_dir(music_dir):
    (music_dir / "lofi.mp3").write_bytes(b"audio")

    path, volume, duck = resolve_bgm_settings(
        {"bgm_track": "lofi.mp3", "bgm_volume": 0.33}
    )

    assert path == str((music_dir / "lofi.mp3").resolve())
    assert volume == pytest.approx(0.33)
    assert duck is True


def test_missing_track_degrades_to_no_music(music_dir, caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.render_service"):
        path, volume, duck = resolve_bgm_settings(
            {"bgm_track": "missing.mp3", "bgm_volume": 0.5}
        )

    assert path is None
    assert volume == pytest.approx(0.5)
    assert duck is True
    assert "BGM skipped" in caplog.text


def test_traversal_attempt_degrades_to_no_music(music_dir, caplog):
    (music_dir.parent / "secret.mp3").write_bytes(b"secret")

    with caplog.at_level(logging.WARNING, logger="app.services.render_service"):
        path, _, _ = resolve_bgm_settings({"bgm_track": "../secret.mp3"})

    assert path is None
    assert "BGM skipped" in caplog.text


def test_templates_without_bgm_keep_legacy_behavior(music_dir):
    path, volume, duck = resolve_bgm_settings({})

    assert path is None
    assert volume == pytest.approx(AUDIO_MUSIC_VOLUME)
    assert duck is True


def test_volume_is_clamped_and_invalid_values_fall_back(music_dir):
    (music_dir / "lofi.mp3").write_bytes(b"audio")

    _, loud, _ = resolve_bgm_settings({"bgm_track": "lofi.mp3", "bgm_volume": 5})
    _, invalid, _ = resolve_bgm_settings({"bgm_track": "lofi.mp3", "bgm_volume": "loud"})

    assert loud == pytest.approx(1.0)
    assert invalid == pytest.approx(AUDIO_MUSIC_VOLUME)
