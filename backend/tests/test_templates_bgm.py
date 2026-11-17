"""Phase 3.6 - template config keeps optional bgm_track/bgm_volume fields."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'templates.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_template_roundtrip_with_bgm_fields(client):
    response = client.post(
        "/api/templates",
        json={
            "name": "With BGM",
            "config": {"caption": {"size": 48}, "bgm_track": "lofi.mp3", "bgm_volume": 0.4},
        },
    )
    assert response.status_code == 200
    template_id = response.json()["id"]

    listed = client.get("/api/templates").json()
    stored = next(t for t in listed if t["id"] == template_id)
    assert stored["config"]["bgm_track"] == "lofi.mp3"
    assert stored["config"]["bgm_volume"] == pytest.approx(0.4)


def test_template_without_bgm_fields_is_unchanged(client):
    response = client.post(
        "/api/templates",
        json={"name": "No BGM", "config": {"caption": {"size": 48}}},
    )
    assert response.status_code == 200
    template_id = response.json()["id"]

    stored = next(t for t in client.get("/api/templates").json() if t["id"] == template_id)
    assert "bgm_track" not in stored["config"]
    assert "bgm_volume" not in stored["config"]


def test_template_update_can_add_bgm_fields(client):
    created = client.post(
        "/api/templates",
        json={"name": "Update Me", "config": {"caption": {"size": 48}}},
    ).json()

    response = client.put(
        f"/api/templates/{created['id']}",
        json={"config": {"caption": {"size": 48}, "bgm_track": "beat.wav", "bgm_volume": 0.2}},
    )

    assert response.status_code == 200
    assert response.json()["config"]["bgm_track"] == "beat.wav"
    assert response.json()["config"]["bgm_volume"] == pytest.approx(0.2)
