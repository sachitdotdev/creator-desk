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
FONT_DIR      = ASSETS_DIR / "fonts"
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
CUT_CACHE_DIR = TEMP_DIR / "cut_cache"      # cached ffmpeg cut times per source/clip

TRANSCRIPTS_DIR = DATA_DIR / "creators"
TEMPLATES_DIR   = DATA_DIR / "templates"
DB_PATH          = DATA_DIR / "creatordesk.db"

# Font resolution for burned-in drawtext. Never hard-code a developer's font
# path: prefer the bundled assets, then well-known system directories, then
# let FFmpeg fall back to the fontconfig family name.
_FONT_FILE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "impact": ("impact.ttf",),
    "arial": ("arial.ttf", "arialbd.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"),
    "montserrat": ("Montserrat-Regular.ttf", "Montserrat-Bold.ttf", "DejaVuSans.ttf"),
}


def resolve_font_file(font_name: str) -> str | None:
    """Return an FFmpeg-safe path to a font file, or None for fontconfig use.

    Resolution order: bundled ``backend/assets/fonts`` files matching the
    requested family (Impact/Arial/Montserrat), the bundled Impact font as a
    universal fallback, then common system font directories. No absolute
    developer path is ever returned.
    """
    key = (font_name or "").strip().lower()
    names = _FONT_FILE_CANDIDATES.get(key, ()) + ("impact.ttf", "DejaVuSans.ttf")
    for name in names:
        candidate = FONT_DIR / name
        if candidate.is_file():
            return escape_fontfile_option(candidate.as_posix())

    system_roots = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
        Path("/usr/share/fonts/truetype"),
        Path("/Library/Fonts"),
    ]
    for root in system_roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return escape_fontfile_option(candidate.as_posix())
    return None


def escape_fontfile_option(path: str) -> str:
    """Escape a font path for an unquoted drawtext ``fontfile`` option.

    The value is embedded directly in a filtergraph, so it must survive two
    FFmpeg parsing layers: the filtergraph tokenizer and the AVOption parser.
    Characters special at both layers (``'``) need three backslashes; a
    character special only at the option layer (the Windows drive ``:``)
    needs two. Using the unquoted form avoids FFmpeg's single-quote rules,
    which cannot represent an apostrophe inside a quoted region.
    """
    escaped: list[str] = []
    for ch in str(path).replace("\\", "/"):
        if ch == "'":
            escaped.append("\\\\\\'")
        elif ch == ":":
            escaped.append("\\\\:")
        elif ch in ";,[]":
            escaped.append("\\\\\\" + ch)
        else:
            escaped.append(ch)
    return "".join(escaped)


# Backwards-compatible name for callers that used the old private helper.
_ffmpeg_escape = escape_fontfile_option

