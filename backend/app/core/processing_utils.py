"""Shared helpers for robust, crash-tolerant batch media processing.

These utilities are used by the faster-whisper transcription pipeline and the
FFmpeg render pipeline so that a single corrupted/invalid media file, a hung
encode, or a permission problem cannot crash the Uvicorn server or leak GPU
memory across a long-running batch job.
"""
from __future__ import annotations

import gc
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

# Default timeout (seconds) for a single ffmpeg/ffprobe invocation. A long
# batch should never let one hung encode block the whole server.
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800"))


def ensure_writable_dir(path) -> Path:
    """Create a directory (parents included) and verify it is writable.

    Raises OSError with a clear message if the directory cannot be created
    or written to, so callers can surface a friendly error instead of a
    cryptic permission failure mid-batch.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    # Verify write permission by creating and removing a probe file.
    probe = path / ".creatordesk_write_probe"
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        probe.unlink()
    except OSError as exc:
        raise OSError(f"Directory is not writable: {path} ({exc})") from exc
    return path


def validate_media_file(path, ffmpeg_path: str = "ffmpeg") -> dict:
    """Probe a media file with ffprobe and return the first video stream info.

    Raises ValueError if the file is missing, unreadable, or not a valid
    decodable media file. This lets the pipeline fail fast on corrupted
    uploads instead of crashing inside faster-whisper/ffmpeg.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Media file not found: {path}")
    if not p.is_file():
        raise ValueError(f"Path is not a regular file: {path}")
    try:
        p.stat().st_size  # raises PermissionError if unreadable
    except OSError as exc:
        raise ValueError(f"Cannot read media file: {path} ({exc})") from exc

    probe_cmd = [
        ffmpeg_path.replace("ffmpeg", "ffprobe"),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,codec_name",
        "-of", "json",
        str(p),
    ]
    try:
        proc = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"ffprobe timed out probing {path}") from exc
    except FileNotFoundError as exc:
        raise ValueError(f"ffprobe not found (is ffmpeg installed?): {exc}") from exc

    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise ValueError(f"Invalid or corrupted media file: {path} — {detail}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ValueError(f"ffprobe returned unparseable output for {path}")

    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No video streams found in {path}; file may be corrupted")
    return streams[0]


def run_subprocess(
    cmd,
    timeout: Optional[int] = None,
    check: bool = True,
    cwd: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess (ffmpeg/ffprobe) with a timeout and clear error reporting.

    Used so a hung or failing encode cannot stall or crash a long-running
    batch job. TimeoutExpired and CalledProcessError are converted into
    plain RuntimeError with the offending command and stderr included.

    ``cwd`` sets the working directory for the child process. This is used by
    the FFmpeg render pipeline so the ASS subtitle filter can reference its
    file by a bare name (avoiding fragile Windows drive-letter escaping in the
    filtergraph).
    """
    timeout = timeout or FFMPEG_TIMEOUT_SECONDS
    try:
        return subprocess.run(
            cmd,
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Command timed out after {timeout}s: {' '.join(map(str, cmd))}"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executable not found: {cmd[0]} (is it on PATH?)") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        raise RuntimeError(
            f"Command failed (exit {exc.returncode}): {' '.join(map(str, cmd))}\n{stderr}"
        ) from exc


def clear_gpu_memory() -> None:
    """Best-effort release of GPU/accelerator memory between batch jobs.

    Runs Python garbage collection and, if PyTorch is imported with a CUDA
    device present, calls torch.cuda.empty_cache() plus synchronize() to
    return cached CUDA memory to the allocator.

    faster-whisper/ctranslate2 holds CUDA memory in the loaded model; call
    WhisperService.unload_model() to actually release the model itself.
    """
    gc.collect()
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        # torch not installed, or no CUDA — nothing to do.
        pass
