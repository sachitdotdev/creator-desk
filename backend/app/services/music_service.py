"""Phase 3.6 - BGM library backed by the filesystem.

Tracks live directly in ``MUSIC_DIR`` (``backend/assets/music``). Each track may
have a sidecar ``<filename>.json`` with optional metadata:

    {"title": "...", "artist": "...", "license": "...", "mood": "...", "bpm": 92}

No database table is involved: the directory is the source of truth. Files with
unsupported extensions are ignored. Uploads are sanitized so a client can never
write outside ``MUSIC_DIR``.
"""
from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

from app.core.config import MUSIC_MAX_UPLOAD_BYTES
from app.core.paths import MUSIC_DIR

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".ogg"})
METADATA_FIELDS = ("title", "artist", "license", "mood", "bpm")
# Bounded retry budget for exclusive-create name collisions on upload.
_MAX_UPLOAD_NAME_ATTEMPTS = 1000


class MusicError(ValueError):
    """Raised when an uploaded track is invalid (name, extension or size)."""


def _music_dir() -> Path:
    """Return MUSIC_DIR, creating it on demand.

    Read at call time (not import time) so tests can point it at a temp folder.
    """
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    return MUSIC_DIR


def _sidecar_path(track: Path) -> Path:
    return track.with_name(f"{track.name}.json")


def sanitize_filename(raw: str | None) -> str:
    """Reduce an uploaded filename to a safe basename inside MUSIC_DIR.

    Strips every path component, replaces unsafe characters and rejects
    unsupported extensions. Raises ``MusicError`` for unusable input.
    """
    candidate = (raw or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    candidate = re.sub(r"[^A-Za-z0-9._ -]+", "_", candidate).strip(" .")
    if not candidate or candidate in {".", ".."}:
        raise MusicError("Invalid filename")

    suffix = Path(candidate).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise MusicError(f"Unsupported audio format. Allowed: {allowed}")

    stem = Path(candidate).stem.strip(" .") or "track"
    return f"{stem}{suffix}"


def _coerce_bpm(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        bpm = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(bpm):
        return None
    return int(bpm) if bpm.is_integer() else bpm


def read_metadata(track: Path) -> dict[str, Any]:
    """Read a track's sidecar JSON. Unreadable/invalid sidecars are ignored."""
    sidecar = _sidecar_path(track)
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # ValueError covers both JSONDecodeError and UnicodeDecodeError, so one
        # malformed sidecar can never break GET /api/music.
        log.warning("[MUSIC] Ignoring unreadable sidecar %s: %s", sidecar.name, exc)
        return {}
    if not isinstance(data, dict):
        log.warning("[MUSIC] Ignoring non-object sidecar %s", sidecar.name)
        return {}

    metadata: dict[str, Any] = {}
    for field in METADATA_FIELDS:
        value = data.get(field)
        if field == "bpm":
            metadata[field] = _coerce_bpm(value)
        elif value is not None:
            metadata[field] = str(value)
    return metadata


def describe_track(track: Path) -> dict[str, Any]:
    metadata = read_metadata(track)
    return {
        "name": track.name,
        "filename": track.name,
        "title": metadata.get("title") or track.stem,
        "artist": metadata.get("artist") or "",
        "license": metadata.get("license") or "",
        "mood": metadata.get("mood") or "",
        "bpm": metadata.get("bpm"),
        "size_bytes": track.stat().st_size,
        "preview_url": f"/api/music/{quote(track.name)}/preview",
    }


def list_tracks() -> list[dict[str, Any]]:
    """List supported audio files in MUSIC_DIR with their metadata."""
    tracks: list[dict[str, Any]] = []
    for path in sorted(_music_dir().iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        tracks.append(describe_track(path))
    return tracks


def resolve_track(name: str | None) -> Path | None:
    """Resolve a template/API track name to a file inside MUSIC_DIR.

    Returns ``None`` for empty names, unsupported extensions, missing files and
    any attempt to escape the music directory.
    """
    raw = (name or "").strip()
    if not raw or raw in {".", ".."}:
        return None
    if "/" in raw or "\\" in raw or Path(raw).name != raw:
        log.warning("[MUSIC] Rejected track name with path components: %r", name)
        return None
    if Path(raw).suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None

    music_dir = _music_dir().resolve()
    try:
        resolved = (music_dir / raw).resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file() or resolved.parent != music_dir:
        return None
    return resolved


def _numbered_name(safe_name: str, attempt: int) -> str:
    """Return the candidate filename for the ``attempt``-th create try."""
    if attempt <= 1:
        return safe_name
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    return f"{stem} ({attempt}){suffix}"


def save_upload(filename: str | None, stream: BinaryIO) -> dict[str, Any]:
    """Persist an uploaded track into MUSIC_DIR and return its description.

    The target file is created exclusively (``"xb"``) so two concurrent uploads
    can never write into the same file. A name collision regenerates a unique
    name and retries; only a file this call actually created is ever removed.
    """
    safe_name = sanitize_filename(filename)
    music_dir = _music_dir()

    created: Path | None = None
    target: Path | None = None
    out = None
    try:
        for attempt in range(1, _MAX_UPLOAD_NAME_ATTEMPTS + 1):
            candidate = music_dir / _numbered_name(safe_name, attempt)
            try:
                # Created exclusively; the handle is closed by the with-block below.
                out = open(candidate, "xb")  # noqa: SIM115
            except FileExistsError:
                continue
            created = target = candidate
            break
        else:
            raise MusicError("Too many tracks with that name")

        written = 0
        with out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MUSIC_MAX_UPLOAD_BYTES:
                    raise MusicError(
                        "File too large. Limit is "
                        f"{MUSIC_MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
                    )
                out.write(chunk)
        if written == 0:
            raise MusicError("Uploaded file is empty")
    except BaseException:
        # Only the file this call created may be removed (never a peer's file).
        if created is not None:
            created.unlink(missing_ok=True)
        raise

    log.info("[MUSIC] Uploaded %s (%d bytes)", target.name, written)
    return describe_track(target)
