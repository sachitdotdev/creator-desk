r"""Command-line batch (drop-folder) processor.

Usage:
    cd backend && .\venv\Scripts\python.exe batch_cli.py

Drops raw videos into ``data/sources/``, transcribes them with faster-whisper,
selects clip windows, and renders fully captioned 9:16 vertical MP4s with
burned kinetic ASS captions. A sidecar ``.json`` metadata file is written next
to every rendered MP4. Processed sources are moved to
``data/sources/processed/``.

This reuses RenderService / WhisperService / LLMService so caption styling,
encoding and template configuration are shared with the interactive pipeline.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

# --------------------------------------------------------------------------- locate ffmpeg
# The backend is designed to run with ffmpeg on PATH (FFMPEG_PATH). In dev
# environments where winget installed ffmpeg to a user AppData location, point
# FFMPEG_PATH there so both ffmpeg and ffprobe are discovered.
import shutil  # noqa: E402

if not os.environ.get("FFMPEG_PATH") and not shutil.which("ffmpeg"):
    _candidates = [
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
    for _c in _candidates:
        if _c.exists():
            os.environ["FFMPEG_PATH"] = str(_c)
            os.environ["PATH"] = str(_c.parent) + os.pathsep + os.environ.get("PATH", "")
            break

os.environ.setdefault("FFMPEG_DEVICE", "cpu")
os.environ.setdefault("WHISPER_DEVICE", "cpu")
os.environ.setdefault("WHISPER_MODEL", "tiny")

from app.database import Base  # noqa: E402
from app.core.config import DATABASE_URL  # noqa: E402
from app.services.batch_service import BatchService  # noqa: E402
import app.models  # noqa: E402  register models
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def main() -> int:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        batch = BatchService(db)
        pending = batch.scan_pending()
        print(f"[batch] {len(pending)} pending video(s) in {batch.input_dir}")
        if not pending:
            print("[batch] nothing to do")
            return 0

        result = batch.run_batch()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

        failed = [r for r in result["results"] if r.get("status") == "error"]
        if failed:
            print(f"[batch] {len(failed)} video(s) failed", file=sys.stderr)
            return 1
        print("[batch] done")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
