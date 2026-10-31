import os
import shutil
from pathlib import Path
from typing import Optional

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

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SOURCES_DIR = DATA_DIR / "sources"
RENDERS_DIR = DATA_DIR / "renders"
TEMPLATES_DIR = DATA_DIR / "templates"
DB_PATH = DATA_DIR / "creatordesk.db"

# Ensure directories exist
for d in [DATA_DIR, SOURCES_DIR, RENDERS_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Ollama
_ollama_host = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")
# Always normalize to an explicit base URL with a scheme
# (http://localhost:11434; use .../11434/v1 for OpenAI-compatible clients).
if not _ollama_host.startswith(("http://", "https://")):
    _ollama_host = "http://" + _ollama_host
OLLAMA_HOST = _ollama_host.rstrip("/")
OLLAMA_HOST = OLLAMA_HOST.replace("0.0.0.0", "127.0.0.1")
OLLAMA_BASE_URL = OLLAMA_HOST
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")

# Runtime-resolved active model. Auto-detected at startup from GET /api/tags;
# falls back to OLLAMA_MODEL when Ollama is unreachable or has no models.
OLLAMA_ACTIVE_MODEL: Optional[str] = None

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

# Batch (drop-folder) processing
BATCH_INPUT_DIR = DATA_DIR / "sources"      # drop raw videos here
BATCH_DONE_DIR = DATA_DIR / "sources" / "processed"  # successfully processed videos move here
BATCH_NUM_CLIPS = int(os.getenv("BATCH_NUM_CLIPS", "5"))
BATCH_VIBE = os.getenv("BATCH_VIBE", "Streamer Hype")

API_TITLE = "CreatorDesk AI"
API_VERSION = "1.0.0"

DATABASE_URL = f"sqlite:///{DB_PATH}"
