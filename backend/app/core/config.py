import os
import re
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
    CUT_CACHE_DIR,
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

# Phase 4.0 - ComfyUI VRAM release. A single POST to /free asks a running
# ComfyUI instance to unload its models; it is a no-op when nothing listens.
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").strip().rstrip("/")
COMFYUI_FREE_TIMEOUT = float(os.getenv("COMFYUI_FREE_TIMEOUT", "1"))

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
# The two-pass post-render normalization re-encodes audio as AAC, which can
# overshoot true peak by ~0.5 dB. Leave headroom there only; the inline
# loudnorm (single encode) keeps the -1.5 dBTP target above.
LOUDNESS_TP_HEADROOM = float(os.getenv("LOUDNESS_TP_HEADROOM", "0.5"))
LOUDNESS_TARGET_LRA = float(os.getenv("LOUDNESS_TARGET_LRA", "11"))

# Batch (drop-folder) processing
BATCH_INPUT_DIR = SOURCES_DIR      # drop raw videos here
BATCH_DONE_DIR = PROCESSED_DIR     # successfully processed videos move here
BATCH_NUM_CLIPS = int(os.getenv("BATCH_NUM_CLIPS", "5"))
BATCH_VIBE = os.getenv("BATCH_VIBE", "Streamer Hype")

# Whole-video clip selection (backend/app/services/clip_selector.py).
# vLLM is launched with --max-model-len 4096 and --max-num-seqs 4; the real
# limits are configurable here so window sizing always leaves room for output.
LLM_MAX_MODEL_LEN = int(os.getenv("LLM_MAX_MODEL_LEN", "4096"))
LLM_MAX_NUM_SEQS = int(os.getenv("LLM_MAX_NUM_SEQS", "4"))
# Tokens reserved for the system prompt, rubric and schema on every request.
LLM_PROMPT_TOKEN_RESERVE = int(os.getenv("LLM_PROMPT_TOKEN_RESERVE", "400"))
LLM_CHARS_PER_TOKEN = int(os.getenv("LLM_CHARS_PER_TOKEN", "4"))

CLIP_WINDOW_CHARS = int(os.getenv("CLIP_WINDOW_CHARS", "6000"))
CLIP_WINDOW_OVERLAP = float(os.getenv("CLIP_WINDOW_OVERLAP", "0.15"))
CLIP_WINDOW_MAX_TOKENS = int(os.getenv("CLIP_WINDOW_MAX_TOKENS", "800"))
CLIP_MAX_CONCURRENT_WINDOWS = int(
    os.getenv("CLIP_MAX_CONCURRENT_WINDOWS", str(LLM_MAX_NUM_SEQS))
)
CLIP_CANDIDATES_PER_WINDOW = int(os.getenv("CLIP_CANDIDATES_PER_WINDOW", "2"))

# Stage 2 is fully deterministic (no LLM calls).
CLIP_EDGE_TRIM_SECONDS = float(os.getenv("CLIP_EDGE_TRIM_SECONDS", "30"))
CLIP_MIN_GAP_SECONDS = float(os.getenv("CLIP_MIN_GAP_SECONDS", "90"))
CLIP_MIN_SECONDS = float(os.getenv("CLIP_MIN_SECONDS", "30"))
CLIP_MAX_SECONDS = float(os.getenv("CLIP_MAX_SECONDS", "61"))

API_TITLE = "CreatorDesk AI"
API_VERSION = "1.0.0"

DATABASE_URL = f"sqlite:///{DB_PATH}"

# --------------------------------------------------------------------------- Face tracking (Phase 6 prep)
# All face-tracker behavior below is gated by config so it can be tuned or
# disabled without changing the sendcmd file format that render_service consumes.
# FACE_MODEL is re-exported from core.paths: repo-relative by default, with an
# optional FACE_MODEL_PATH environment override (never a hardcoded local path).
FACE_TRACKER_ENABLED = os.getenv("FACE_TRACKER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
FACE_MODEL_CONF = float(os.getenv("FACE_DETECTION_CONF", "0.25"))       # YOLO confidence threshold
FACE_MODEL_IMGSZ = int(os.getenv("FACE_DETECTION_IMGSZ", "640"))        # YOLO inference size
FACE_MODEL_UPSCALE_SMALL = os.getenv("FACE_DETECTION_UPSCALE_SMALL", "false").strip().lower() in ("1", "true", "yes", "on")
# Detection stride: 1 = every frame (most reliable, slower), N = every N frames
# with gaps filled by interpolation. Larger strides increase lost-tracking risk.
FACE_DETECTION_STRIDE = int(os.getenv("FACE_DETECTION_STRIDE", "1"))

# Shot-cut detection. Multi-camera podcasts cut hard between wide/single shots;
# the tracker must reset its target at every cut so it never carries one shot's
# x position into the next. Cuts are detected with ffmpeg scene detection and
# cached so re-renders don't re-scan the source.
FACE_CUT_THRESHOLD = float(os.getenv("FACE_CUT_THRESHOLD", "0.3"))      # ffmpeg scene detection threshold
FACE_CUT_CACHE_DIR = CUT_CACHE_DIR                                      # cached cut times per source/clip

# Target selection: with several faces and no speaker info yet, prefer the
# largest face and require it to persist MIN_DWELL seconds before switching
# (hysteresis against wrong-target flipping). Phase 6 will replace this with
# diarization-based speaker mapping; the hook is select_target() in face_tracker.
FACE_TARGET_MIN_DWELL_S = float(os.getenv("FACE_TARGET_MIN_DWELL_S", "1.5"))
FACE_TARGET_PREFER_LARGEST = os.getenv("FACE_TARGET_PREFER_LARGEST", "true").strip().lower() in ("1", "true", "yes", "on")

# Smoothing + loss handling. A critically damped spring follows the target with
# a max pan speed; when detection is lost the last position is held for
# HOLD_SECONDS then eased toward the shot's face center (or shot center).
FACE_SMOOTHING_OMEGA = float(os.getenv("FACE_SMOOTHING_OMEGA", "6.0"))   # critically damped spring (rad/s)
FACE_MAX_PAN_PX_PER_S = float(os.getenv("FACE_MAX_PAN_PX_PER_S", "500.0"))
FACE_HOLD_SECONDS = float(os.getenv("FACE_HOLD_SECONDS", "1.0"))

# Debug prints to verify paths
print(f"DEBUG CONFIG: DATA_DIR={DATA_DIR}")
print(f"DEBUG CONFIG: SOURCES_DIR={SOURCES_DIR}")
print(f"DEBUG CONFIG: TRANSCRIPTS_DIR={TRANSCRIPTS_DIR}")

# Caption safe zone (bottom margin clamp). The caption bottom margin (ASS
# MarginV) is expressed as a fraction of the frame height; when a template's
# margin is below CAPTION_SAFE_BOTTOM_PCT the render-time clamp raises it to
# that safe value (toggle with CAPTION_SAFE_ZONE_ENFORCE, default on).
CAPTION_SAFE_BOTTOM_PCT = float(os.getenv("CAPTION_SAFE_BOTTOM_PCT", "0.18"))
CAPTION_SAFE_ZONE_ENFORCE = os.getenv("CAPTION_SAFE_ZONE_ENFORCE", "true").strip().lower() in ("1", "true", "yes", "on")

# --------------------------------------------------------------------------- Default burned-in caption style
# Only templates that do not override these keys use these values. Saved
# templates with explicit caption settings keep their own styling. The font
# size is a fraction of the 1920 px output height (6.5% -> 124.8 px), which is
# legible over light backgrounds without swallowing the frame.
CAPTION_FONT = os.getenv("CAPTION_FONT", "Arial")
# Font family names are interpolated into an FFmpeg filtergraph option. Only
# plain family names may pass; anything else is rejected at the API boundary
# and again in the render fallback (see edit_compiler.compile_plan).
CAPTION_FONT_NAME_RE = re.compile(r"^[A-Za-z0-9 ._-]{1,64}$")


def is_valid_caption_font(value: object) -> bool:
    """Whether ``value`` is a safe plain font-family name."""
    return isinstance(value, str) and bool(CAPTION_FONT_NAME_RE.fullmatch(value))


CAPTION_BOLD = os.getenv("CAPTION_BOLD", "true").strip().lower() in ("1", "true", "yes", "on")
CAPTION_FONT_SIZE_PCT = float(os.getenv("CAPTION_FONT_SIZE_PCT", "0.065"))
CAPTION_PRIMARY_COLOR = os.getenv("CAPTION_PRIMARY_COLOR", "&H00FFFFFF")       # white
CAPTION_OUTLINE_COLOR = os.getenv("CAPTION_OUTLINE_COLOR", "&H00000000")       # black
CAPTION_OUTLINE_W = int(os.getenv("CAPTION_OUTLINE_W", "5"))
CAPTION_SHADOW = int(os.getenv("CAPTION_SHADOW", "3"))
CAPTION_BACK_COLOR = os.getenv("CAPTION_BACK_COLOR", "&H00000000")
CAPTION_ALIGNMENT = int(os.getenv("CAPTION_ALIGNMENT", "2"))                   # bottom centre
CAPTION_MARGIN_LR = int(os.getenv("CAPTION_MARGIN_LR", "40"))
CAPTION_MAX_LINES = int(os.getenv("CAPTION_MAX_LINES", "2"))
CAPTION_WORD_WRAP = os.getenv("CAPTION_WORD_WRAP", "true").strip().lower() in ("1", "true", "yes", "on")
CAPTION_WRAP_CHARS = int(os.getenv("CAPTION_WRAP_CHARS", "15"))                # chars per line at default size

# --------------------------------------------------------------------------- Per-shot wide-shot face zoom
# Constant within a shot, changes only at detected cuts. The base full-height
# crop already upscales a 1920x1080 source by 1920/1080 = 1.778x, so a total
# upscale ceiling of 3.0x allows at most ~1.69x extra zoom on 1080p sources
# before the picture gets unduly soft.
FACE_ZOOM_ENABLED = os.getenv("FACE_ZOOM_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
FACE_ZOOM_TARGET_PCT = float(os.getenv("FACE_ZOOM_TARGET_PCT", "0.18"))        # face height / output height
FACE_ZOOM_MAX_ZOOM = float(os.getenv("FACE_ZOOM_MAX_ZOOM", "2.0"))             # relative to full-height crop
FACE_ZOOM_MAX_UPSCALE = float(os.getenv("FACE_ZOOM_MAX_UPSCALE", "3.0"))       # source px -> output px
FACE_ZOOM_HEADROOM_PCT = float(os.getenv("FACE_ZOOM_HEADROOM_PCT", "0.12"))    # space above face


