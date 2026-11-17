"""Phase 3.6 - filesystem BGM library: listing, sidecars and upload safety."""

import io
import json
import logging

import pytest

from app.services import music_service


@pytest.fixture
def music_dir(tmp_path, monkeypatch):
    target = tmp_path / "music"
    target.mkdir()
    monkeypatch.setattr(music_service, "MUSIC_DIR", target)
    return target


def _track(path, payload=b"audio"):
    path.write_bytes(payload)
    return path


def test_list_tracks_reads_sidecar_and_skips_unsupported(music_dir):
    _track(music_dir / "lofi.mp3")
    (music_dir / "lofi.mp3.json").write_text(
        json.dumps(
            {
                "title": "Late Night",
                "artist": "Test Artist",
                "license": "CC0",
                "mood": "chill",
                "bpm": 92,
            }
        ),
        encoding="utf-8",
    )
    _track(music_dir / "beat.wav")
    (music_dir / "notes.txt").write_text("not audio", encoding="utf-8")
    (music_dir / "orphan.json").write_text("{}", encoding="utf-8")

    tracks = music_service.list_tracks()

    assert [t["filename"] for t in tracks] == ["beat.wav", "lofi.mp3"]
    lofi = tracks[1]
    assert lofi["title"] == "Late Night"
    assert lofi["artist"] == "Test Artist"
    assert lofi["license"] == "CC0"
    assert lofi["mood"] == "chill"
    assert lofi["bpm"] == 92
    assert lofi["preview_url"] == "/api/music/lofi.mp3/preview"
    # Missing sidecar falls back to the filename stem.
    assert tracks[0]["title"] == "beat"


def test_invalid_sidecar_is_ignored_with_warning(music_dir, caplog):
    _track(music_dir / "lofi.mp3")
    (music_dir / "lofi.mp3.json").write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="app.services.music_service"):
        tracks = music_service.list_tracks()

    assert tracks[0]["title"] == "lofi"
    assert "Ignoring unreadable sidecar" in caplog.text


def test_sanitize_filename_strips_paths_and_rejects_bad_extension():
    assert music_service.sanitize_filename("../../evil.mp3") == "evil.mp3"
    assert music_service.sanitize_filename(r"..\..\evil.mp3") == "evil.mp3"
    assert music_service.sanitize_filename("My Track!.MP3") == "My Track_.mp3"

    with pytest.raises(music_service.MusicError):
        music_service.sanitize_filename("track.txt")
    with pytest.raises(music_service.MusicError):
        music_service.sanitize_filename("..")


def test_resolve_track_rejects_traversal_and_missing_files(music_dir):
    _track(music_dir / "lofi.mp3")
    secret = music_dir.parent / "secret.mp3"
    _track(secret)

    assert music_service.resolve_track("lofi.mp3") == (music_dir / "lofi.mp3").resolve()
    assert music_service.resolve_track("../secret.mp3") is None
    assert music_service.resolve_track("..\\secret.mp3") is None
    assert music_service.resolve_track("nested/lofi.mp3") is None
    assert music_service.resolve_track("missing.mp3") is None
    assert music_service.resolve_track("notes.txt") is None
    assert music_service.resolve_track("") is None


def test_save_upload_stays_inside_music_dir(music_dir):
    description = music_service.save_upload("../../evil.mp3", io.BytesIO(b"audio-bytes"))

    assert description["filename"] == "evil.mp3"
    assert (music_dir / "evil.mp3").read_bytes() == b"audio-bytes"
    assert not (music_dir.parent / "evil.mp3").exists()


def test_save_upload_deduplicates_names(music_dir):
    first = music_service.save_upload("lofi.mp3", io.BytesIO(b"one"))
    second = music_service.save_upload("lofi.mp3", io.BytesIO(b"two"))

    assert first["filename"] == "lofi.mp3"
    assert second["filename"] == "lofi (2).mp3"


def test_save_upload_enforces_size_limit(music_dir, monkeypatch):
    monkeypatch.setattr(music_service, "MUSIC_MAX_UPLOAD_BYTES", 4)

    with pytest.raises(music_service.MusicError):
        music_service.save_upload("big.mp3", io.BytesIO(b"12345"))

    assert not (music_dir / "big.mp3").exists()


def test_save_upload_rejects_bad_extension(music_dir):
    with pytest.raises(music_service.MusicError):
        music_service.save_upload("notes.txt", io.BytesIO(b"nope"))
