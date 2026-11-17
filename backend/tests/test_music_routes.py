"""Phase 3.6 - /api/music list, upload and preview routes."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import music_service


@pytest.fixture
def music_dir(tmp_path, monkeypatch):
    target = tmp_path / "music"
    target.mkdir()
    monkeypatch.setattr(music_service, "MUSIC_DIR", target)
    return target


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_list_music_returns_tracks(client, music_dir):
    (music_dir / "lofi.mp3").write_bytes(b"audio")
    (music_dir / "lofi.mp3.json").write_text('{"title": "Lo Fi"}', encoding="utf-8")
    (music_dir / "skip.txt").write_text("no", encoding="utf-8")

    response = client.get("/api/music")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "lofi.mp3",
            "filename": "lofi.mp3",
            "title": "Lo Fi",
            "artist": "",
            "license": "",
            "mood": "",
            "bpm": None,
            "size_bytes": 5,
            "preview_url": "/api/music/lofi.mp3/preview",
        }
    ]


def test_upload_music_sanitizes_filename(client, music_dir):
    response = client.post(
        "/api/music",
        files={"file": ("../../evil.mp3", b"audio-bytes", "audio/mpeg")},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "evil.mp3"
    assert (music_dir / "evil.mp3").read_bytes() == b"audio-bytes"
    assert not (music_dir.parent / "evil.mp3").exists()


def test_upload_music_rejects_bad_extension(client, music_dir):
    response = client.post(
        "/api/music",
        files={"file": ("notes.txt", b"nope", "text/plain")},
    )

    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]
    assert list(music_dir.iterdir()) == []


def test_upload_music_enforces_size_limit(client, music_dir, monkeypatch):
    monkeypatch.setattr(music_service, "MUSIC_MAX_UPLOAD_BYTES", 4)

    response = client.post(
        "/api/music",
        files={"file": ("big.mp3", b"12345", "audio/mpeg")},
    )

    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()
    assert list(music_dir.iterdir()) == []


def test_preview_streams_track(client, music_dir):
    (music_dir / "lofi.mp3").write_bytes(b"audio-bytes")

    response = client.get("/api/music/lofi.mp3/preview")

    assert response.status_code == 200
    assert response.content == b"audio-bytes"


def test_preview_rejects_path_traversal(client, music_dir):
    (music_dir.parent / "secret.mp3").write_bytes(b"secret")

    for name in ("..%2Fsecret.mp3", "..%5Csecret.mp3", "%2E%2E%2Fsecret.mp3"):
        response = client.get(f"/api/music/{name}/preview")
        assert response.status_code == 404, name
        assert b"secret" not in response.content


def test_preview_missing_track_is_404(client, music_dir):
    response = client.get("/api/music/missing.mp3/preview")
    assert response.status_code == 404
