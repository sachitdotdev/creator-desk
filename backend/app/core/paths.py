import os
from pathlib import Path

# Repo-relative anchor: this module lives at <repo>/backend/app/core/paths.py.
# Deriving paths from __file__ keeps them machine-independent - never bake an
# absolute developer path into tracked code.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ANCHOR = Path(__file__).resolve().parents[2]


def _detect_root() -> Path:
    override = os.environ.get("CREATOR_DESK_ROOT")
    if override:
        return Path(override)
    container_root = Path("/workspace/Active/Creator Desk")
    if container_root.exists():
        return container_root
    # Repo-relative fallback (same location as before on a normal checkout).
    return _REPO_ROOT

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
# YOLO face weights. Default is repo-relative to backend/ (where the file
# lives today); FACE_MODEL_PATH overrides it for other deployments. Kept
# independent of ROOT so a machine-specific root fallback can never leak into
# the path printed by the face tracker.
FACE_MODEL    = Path(os.environ.get("FACE_MODEL_PATH") or str(_BACKEND_ANCHOR / "yolov8n-face.pt"))

# Central scratch root for CPU-only work (e.g. Whisper's FFmpeg audio chunks).
# Created on demand by the caller; overridable without changing the data root.
TEMP_DIR      = Path(os.environ.get("CREATOR_DESK_TEMP_DIR", str(DATA_DIR / "tmp")))

TRANSCRIPTS_DIR = DATA_DIR / "creators"
TEMPLATES_DIR   = DATA_DIR / "templates"
DB_PATH          = DATA_DIR / "creatordesk.db"
