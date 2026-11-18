"""Phase 3.5 - EBU R128 loudness normalization via FFmpeg loudnorm (two-pass).

Runs FFmpeg's ``loudnorm`` filter as an explicit two-pass pipeline:

1. Pass 1 measures integrated loudness (I), true peak (TP) and loudness range
   (LRA) of the source with ``print_format=json``.
2. Pass 2 re-encodes applying the measured values to hit the target.

Targets: EBU R128 / ITU-R BS.1770 - I=-14, TP=-1.5, LRA=11 (short-form loudness).

FFmpeg only - no new runtime dependencies. Graceful degradation: check
``is_ffmpeg_available()`` before running; callers should treat failures softly.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.core.processing_utils import run_subprocess

# EBU R128 / ITU-R BS.1770 loudness targets for short-form vertical clips.
LOUDNESS_TARGET_I = -14.0
LOUDNESS_TARGET_TP = -1.5
LOUDNESS_TARGET_LRA = 11.0


def is_ffmpeg_available(ffmpeg_path: str | None = None) -> bool:
    """Best-effort check that the ffmpeg binary can be resolved."""
    exe = str(ffmpeg_path or os.environ.get("FFMPEG_PATH") or "ffmpeg")
    if Path(exe).exists():
        return True
    if shutil.which(exe):
        return True
    return bool(
        Path(exe).exists()
        or shutil.which(exe)
        or (os.name == "nt" and not exe.lower().endswith(".exe") and Path(exe + ".exe").exists())
    )


def measure_loudness(
    input_path: str,
    ffmpeg_path: str | None = None,
    target_i: float = LOUDNESS_TARGET_I,
    target_tp: float = LOUDNESS_TARGET_TP,
    target_lra: float = LOUDNESS_TARGET_LRA,
) -> dict:
    """Pass 1: measure loudness (I / TP / LRA) via loudnorm with print_format=json.

    Returns a dict of measured (input_*) and predicted (output_*) loudness stats.
    Raises RuntimeError if ffmpeg fails or the JSON output cannot be parsed.
    """
    ffmpeg = str(ffmpeg_path or os.environ.get("FFMPEG_PATH") or "ffmpeg")
    cmd = [
        ffmpeg,
        "-nostats",
        "-i", str(input_path),
        "-af", (
            f"loudnorm=I={float(target_i):g}:TP={float(target_tp):g}:"
            f"LRA={float(target_lra):g}:print_format=json"
        ),
        "-f", "null", "-",
    ]
    proc = run_subprocess(cmd, timeout=120)
    raw = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        tail = raw[-400:]
        raise RuntimeError(f"loudnorm pass 1 returned unparseable output for {input_path}: {tail}")
    data = json.loads(raw[start:end + 1])
    return {
        "input_i": float(data.get("input_i") or 0.0),
        "input_tp": float(data.get("input_tp") or 0.0),
        "input_lra": float(data.get("input_lra") or 0.0),
        "input_thresh": float(data.get("input_thresh") or 0.0),
        "output_i": float(data.get("output_i") or 0.0),
        "output_tp": float(data.get("output_tp") or 0.0),
        "output_lra": float(data.get("output_lra") or 0.0),
        "normalization_type": data.get("normalization_type") or "dynamic",
        "target_offset": float(data.get("target_offset") or 0.0),
    }


def apply_loudness_normalization(
    input_path: str,
    output_path: str | None = None,
    ffmpeg_path: str | None = None,
    target_i: float = LOUDNESS_TARGET_I,
    target_tp: float = LOUDNESS_TARGET_TP,
    target_lra: float = LOUDNESS_TARGET_LRA,
) -> dict | None:
    """Two-pass EBU R128 loudness normalization.

    Pass 1 measures the input, pass 2 re-encodes applying the measured values to
    the requested targets. Returns the measured stats dict, or None when FFmpeg
    is unavailable (caller should degrade gracefully).
    """
    if not is_ffmpeg_available(ffmpeg_path):
        return None
    ffmpeg = str(ffmpeg_path or os.environ.get("FFMPEG_PATH") or "ffmpeg")
    stats = measure_loudness(
        input_path, ffmpeg_path=ffmpeg,
        target_i=target_i, target_tp=target_tp, target_lra=target_lra,
    )
    out = Path(output_path) if output_path else Path(f"{input_path!s}_loudnorm.mp4")
    flt = (
        f"loudnorm=I={float(target_i):g}:TP={float(target_tp):g}:LRA={float(target_lra):g}"
        f":measured_I={stats['input_i']:.2f}:measured_TP={stats['input_tp']:.2f}:measured_LRA={stats['input_lra']:.2f}"
        f":measured_thresh={stats.get('input_thresh') or 0.0:.2f}:offset={stats.get('target_offset') or 0.0}"
        f":linear=true"
    )
    cmd = [
        ffmpeg,
        "-nostats",
        "-y",
        "-i", str(input_path),
        "-af", flt,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    run_subprocess(cmd, timeout=120)
    return stats
