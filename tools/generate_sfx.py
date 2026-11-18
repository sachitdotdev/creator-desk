"""Regenerate the original, ffmpeg-synthesised audio assets.

Every audio file committed under ``backend/assets/sfx/`` and the one original
BGM placeholder under ``backend/assets/music/`` is produced by the commands
below. No stock, downloaded, or AI-vocal audio is used. Re-running this script
reproduces the committed files byte-for-byte in structure (MP3 encoding is
deterministic for a given FFmpeg build).

Usage (from the repository root)::

    python tools/generate_sfx.py

Requires ``ffmpeg`` on PATH. See ``docs/ASSETS.md`` for the licensing policy.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# tools/generate_sfx.py -> repository root (parents[1] == repo root)
ROOT = Path(__file__).resolve().parents[1]
SFX_DIR = ROOT / "backend" / "assets" / "sfx"
MUSIC_DIR = ROOT / "backend" / "assets" / "music"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


# Each command is the exact argv passed to ffmpeg (no shell quoting involved).
COMMANDS: list[tuple[str, list[str]]] = [
    (
        "backend/assets/sfx/boom.mp3  (~3.1 s low sine, pitch drop + fast decay)",
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=0.55*exp(-1.5*t)*sin(2*PI*(90*t-10*t*t)):d=3.11:s=44100",
            "-af", "lowpass=f=400,volume=0.9",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(SFX_DIR / "boom.mp3"),
        ],
    ),
    (
        "backend/assets/sfx/pop.mp3  (~0.7 s short sine burst, very fast decay)",
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=0.6*exp(-20*t)*sin(2*PI*450*t):d=0.72:s=44100",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(SFX_DIR / "pop.mp3"),
        ],
    ),
    (
        "backend/assets/sfx/whoosh.mp3  (~0.6 s filtered noise + rising chirp)",
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i", "anoisesrc=color=white:duration=0.6:sample_rate=44100:seed=7",
            "-f", "lavfi",
            "-i", "aevalsrc=0.3*sin(2*PI*(200*t+1500*t*t)):d=0.6:s=44100",
            "-filter_complex",
            "[0:a]highpass=f=400,lowpass=f=7000,volume=0.35,"
            "afade=t=in:st=0:d=0.12,afade=t=out:st=0.22:d=0.38[n];"
            "[1:a]afade=t=in:st=0:d=0.12,afade=t=out:st=0.22:d=0.38[c];"
            "[n][c]amix=inputs=2:duration=first:normalize=0[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(SFX_DIR / "whoosh.mp3"),
        ],
    ),
    (
        "backend/assets/music/ambient-pad.mp3  (40 s seamless original pad)",
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi",
            "-i",
            "aevalsrc=0.12*sin(2*PI*110*t)+0.10*sin(2*PI*165*t)+"
            "0.08*sin(2*PI*220*t)+0.06*sin(2*PI*260*t):d=40:s=44100",
            "-af", "tremolo=f=0.1:d=0.2,lowpass=f=2000,volume=1.0",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(MUSIC_DIR / "ambient-pad.mp3"),
        ],
    ),
]


def main() -> None:
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    for description, argv in COMMANDS:
        print(f"\n==> {description}")
        print("    " + " ".join(argv))
        try:
            result = subprocess.run(argv, timeout=120, capture_output=True, text=True)
        except OSError as exc:
            raise SystemExit(f"Could not run ffmpeg for {description}: {exc}") from exc
        if result.returncode != 0:
            print(result.stderr)
            raise SystemExit(f"ffmpeg failed ({result.returncode}) for {description}")
    print("\nAll original audio assets regenerated.")


if __name__ == "__main__":
    main()
