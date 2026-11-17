import os
from pathlib import Path


def _detect_root() -> Path:
    override = os.environ.get("CREATOR_DESK_ROOT")
    if override:
        return Path(override)
    container_root = Path("/workspace/Active/Creator Desk")
    if container_root.exists():
        return container_root
    return Path(r"C:\Projects Openhands\Active\Creator Desk")

ROOT = _detect_root()
DATA_DIR      = ROOT / "data"
BACKEND_DIR   = ROOT / "backend"
ASSETS_DIR    = BACKEND_DIR / "assets"
MUSIC_DIR     = ASSETS_DIR / "music"
SFX_DIR       = ASSETS_DIR / "sfx"
SOURCES_DIR   = DATA_DIR / "sources"
PROCESSED_DIR = SOURCES_DIR / "processed"
RENDERS_DIR   = DATA_DIR / "renders"
MODELS_DIR    = ASSETS_DIR / "models"
FACE_MODEL    = BACKEND_DIR / "yolov8n-face.pt"

TRANSCRIPTS_DIR = DATA_DIR / "creators"
TEMPLATES_DIR   = DATA_DIR / "templates"
DB_PATH          = DATA_DIR / "creatordesk.db"
