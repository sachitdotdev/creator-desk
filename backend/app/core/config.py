import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- locate ffmpeg/ffprobe
# ffmpeg is required for media probing, vertical rendering and yt-dlp merges.
# When it is not on PATH (and FFMPEG_PATH is not set explicitly), check common
# installation locations (mirrors backend/batch_cli.py) so the app works out of
# the box on Windows dev machines where ffmpeg was installed via winget.
if not os.environ.get("FFMPEG_PATH") and not shutil.which("ffmpeg"):
    _ffmpeg_candidates = [
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-9.0.2-full_build"
        / "bin"
        / "ffmpeg.exe",
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
    ]
    for _c in _ffmpeg_candidates:
        if _c.exists():
            os.environ["FFMPEG_PATH"] = str(_c)
            os.environ["PATH"] = str(_c.parent) + os.pathsep + os.environ.get("PATH", "")
            break

# Import paths from core.paths
from app.core.paths import (
    DATA_DIR,
    DB_PATH,
    FACE_MODEL,  # noqa: F401 - re-exported for app.services.face_tracker
    MODELS_DIR,
    MUSIC_DIR,
    PROCESSED_DIR,
    RENDERS_DIR,
    SFX_DIR,
    SOURCES_DIR,
    TEMPLATES_DIR,
    TRANSCRIPTS_DIR,
)

# Ensure directories exist
for d in [DATA_DIR, SOURCES_DIR, RENDERS_DIR, TRANSCRIPTS_DIR, TEMPLATES_DIR, MUSIC_DIR, SFX_DIR, MODELS_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Ollama
_ollama_host = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")
if not _ollama_host.startswith(("http://", "https://")):
    _ollama_host = "http://" + _ollama_host
OLLAMA_HOST = _ollama_host.rstrip("/")
OLLAMA_HOST = OLLAMA_HOST.replace("0.0.0.0", "127.0.0.1")
OLLAMA_BASE_URL = OLLAMA_HOST
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen14b-awq")

OLLAMA_ACTIVE_MODEL: str | None = None

# Phase 4.0 - single-tenant GPU guardrails. A VRAM stage waits at most this
# long for the process-wide GPU lock before failing loudly with GPULockTimeout.
GPU_LOCK_TIMEOUT = float(os.getenv("GPU_LOCK_TIMEOUT", "900"))

# Whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")  # cuda | cpu
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")

# FFmpeg
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFMPEG_DEVICE = os.getenv("FFMPEG_DEVICE", "cuda")  # cuda | cpu
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800"))  # 30 min

# Output settings
OUTPUT_WIDTH = int(os.getenv("OUTPUT_WIDTH", "1080"))
OUTPUT_HEIGHT = int(os.getenv("OUTPUT_HEIGHT", "1920"))
OUTPUT_FPS = int(os.getenv("OUTPUT_FPS", "30"))
OUTPUT_CRF = int(os.getenv("OUTPUT_CRF", "24"))

# Phase 3.1/3.2 - Audio mix: SFX layer gain + BGM ducking.
# Ducking uses FFmpeg sidechaincompress keyed by the voice, so the music
# ducks under speech. Ducking only runs when a BGM track is present.
AUDIO_MUSIC_VOLUME = float(os.getenv("AUDIO_MUSIC_VOLUME", "0.25"))
AUDIO_SFX_VOLUME = float(os.getenv("AUDIO_SFX_VOLUME", "0.9"))
AUDIO_DUCK_THRESHOLD = float(os.getenv("AUDIO_DUCK_THRESHOLD", "0.05"))
AUDIO_DUCK_RATIO = float(os.getenv("AUDIO_DUCK_RATIO", "8"))
AUDIO_DUCK_ATTACK = int(os.getenv("AUDIO_DUCK_ATTACK", "20"))    # ms
AUDIO_DUCK_RELEASE = int(os.getenv("AUDIO_DUCK_RELEASE", "400"))  # ms

# Phase 3.6 - BGM library uploads (assets/music).
MUSIC_MAX_UPLOAD_MB = int(os.getenv("MUSIC_MAX_UPLOAD_MB", "25"))
MUSIC_MAX_UPLOAD_BYTES = MUSIC_MAX_UPLOAD_MB * 1024 * 1024

# Phase 3.5 - Loudness normalization (EBU R128 two-pass). Optional final audio step.
LOUDNESS_NORMALIZE = os.getenv("LOUDNESS_NORMALIZE", "false").strip().lower() in ("1", "true", "yes", "on")
LOUDNESS_TARGET_I = float(os.getenv("LOUDNESS_TARGET_I", "-14"))
LOUDNESS_TARGET_TP = float(os.getenv("LOUDNESS_TARGET_TP", "-1.5"))
LOUDNESS_TARGET_LRA = float(os.getenv("LOUDNESS_TARGET_LRA", "11"))

# Batch (drop-folder) processing
BATCH_INPUT_DIR = SOURCES_DIR      # drop raw videos here
BATCH_DONE_DIR = PROCESSED_DIR     # successfully processed videos move here
BATCH_NUM_CLIPS = int(os.getenv("BATCH_NUM_CLIPS", "5"))
BATCH_VIBE = os.getenv("BATCH_VIBE", "Streamer Hype")

API_TITLE = "CreatorDesk AI"
API_VERSION = "1.0.0"

DATABASE_URL = f"sqlite:///{DB_PATH}"

# Debug prints to verify paths
print(f"DEBUG CONFIG: DATA_DIR={DATA_DIR}")
print(f"DEBUG CONFIG: SOURCES_DIR={SOURCES_DIR}")
print(f"DEBUG CONFIG: TRANSCRIPTS_DIR={TRANSCRIPTS_DIR}")
