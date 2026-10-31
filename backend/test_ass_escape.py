"""Test ffmpeg 'ass' filter using cwd + bare filename (no drive letter escaping)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

FFMPEG = r"C:\Users\bechi\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"

ASS_CONTENT = (
    "[Script Info]\nTitle: t\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Arial,48,&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,60,1\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{\\k50}Hey\n"
)


def main() -> None:
    workdir = Path(tempfile.mkdtemp())
    ass = workdir / "subs_test.ass"
    ass.write_text(ASS_CONTENT, encoding="utf-8")

    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:size=1080x1920:duration=1:rate=30",
        "-vf", "ass=subs_test.ass",  # bare filename, resolved via cwd
        "-frames:v", "1", "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(workdir))
    err = r.stderr.strip()
    print("rc=", r.returncode, "::", err.splitlines()[0] if err else "OK")
    if r.returncode == 0:
        print("WORKING: cwd + bare filename ass=subs_test.ass")
    ass.unlink()


if __name__ == "__main__":
    main()
