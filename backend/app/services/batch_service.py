"""Batch (drop-folder) processing service.

Drop raw video files into ``BATCH_INPUT_DIR`` and this service automatically
transcribes them with faster-whisper, selects clip windows, renders fully
captioned 9:16 vertical MP4s with burned kinetic ASS captions, and writes a
sidecar JSON metadata file for every rendered clip.

Designed to run on a schedule (cron / systemd timer) or as a long-running
folder watcher. All heavy work reuses the existing WhisperService,
RenderService and LLMService so caption styling, NVENC/CPU encoding and
template configuration are shared with the interactive pipeline.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.core.config import (
    BATCH_DONE_DIR,
    BATCH_INPUT_DIR,
    BATCH_NUM_CLIPS,
    BATCH_VIBE,
    RENDERS_DIR,
)
from app.core.processing_utils import (
    ensure_writable_dir,
    validate_media_file,
)
from app.services import clip_selector, llm_service, render_service, whisper_service

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class BatchService:
    def __init__(
        self,
        db: Session,
        input_dir: Path | None = None,
        done_dir: Path | None = None,
        renders_dir: Path | None = None,
    ):
        self.db = db
        self.input_dir = Path(input_dir) if input_dir else BATCH_INPUT_DIR
        self.done_dir = Path(done_dir) if done_dir else BATCH_DONE_DIR
        self.renders_dir = Path(renders_dir) if renders_dir else RENDERS_DIR
        self.whisper = whisper_service.WhisperService()
        self.llm = llm_service.LLMService()
        ensure_writable_dir(self.input_dir)
        ensure_writable_dir(self.done_dir)
        ensure_writable_dir(self.renders_dir)

    # ------------------------------------------------------------------ public
    def scan_pending(self) -> list[Path]:
        """Return video files in the input folder that have not been processed."""
        pending: list[Path] = []
        if not self.input_dir.exists():
            return pending
        for path in sorted(self.input_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            # Skip anything already tracked as processed in the DB.
            already = (
                self.db.query(models.Video)
                .filter(models.Video.path == str(path))
                .first()
            )
            if already and already.status == "done":
                continue
            pending.append(path)
        return pending

    def process_video(
        self,
        video_path: Path,
        num_clips: int | None = None,
        vibe: str | None = None,
        template: models.Template | None = None,
    ) -> dict[str, Any]:
        """Run the full transcribe → clip-select → render pipeline for one video.

        Returns a dict with the video info and a list of rendered clip metadata.
        """
        num_clips = num_clips or BATCH_NUM_CLIPS
        vibe = vibe or BATCH_VIBE
        video_path = Path(video_path)

        # Validate + (re)create the video record.
        validate_media_file(str(video_path))
        video = (
            self.db.query(models.Video)
            .filter(models.Video.path == str(video_path))
            .first()
        )
        if video is None:
            video = models.Video(
                filename=video_path.name,
                original_name=video_path.name,
                path=str(video_path),
                status="uploaded",
            )
            self.db.add(video)
            self.db.commit()
            self.db.refresh(video)

        # Probe dimensions/fps if missing.
        if video.width is None or video.height is None or video.duration is None:
            try:
                ffmpeg_path = os.environ.get("FFMPEG_PATH", "ffmpeg")
                probe = subprocess.run(
                    [
                        ffmpeg_path.replace("ffmpeg", "ffprobe"),
                        "-v", "error",
                        "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate,duration",
                        "-of", "json", str(video_path),
                    ],
                    capture_output=True, text=True, timeout=30,
                    check=False,
                )
                data = json.loads(probe.stdout)
                s = (data.get("streams") or [{}])[0]
                if video.width is None:
                    video.width = s.get("width")
                if video.height is None:
                    video.height = s.get("height")
                if video.duration is None and s.get("duration"):
                    video.duration = float(s["duration"])
            except Exception:  # noqa: BLE001,S110 - best-effort metadata probe
                pass
        self.db.commit()

        # --- 1. Transcribe --------------------------------------------------
        video.status = "transcribing"
        self.db.commit()
        transcript_path = self.renders_dir / f"batch_transcript_{video.id}.json"
        try:
            result = self.whisper.transcribe(str(video_path), str(transcript_path))
        except Exception as exc:
            video.status = "error"
            video.error_message = f"transcription failed: {exc}"
            self.db.commit()
            raise
        video.transcript_path = str(transcript_path)
        video.status = "transcribed"
        self.db.commit()

        # Release the Whisper model + GPU memory after each transcription.
        self.whisper.reset()

        # --- 2. Clip selection (same whole-video selector as the API route) ---
        # clip_selector owns the windowed search, deterministic picking and the
        # whole-video fallback; there is no second fallback implementation here.
        segments = result.to_dict().get("segments", [])
        clips_data: list[dict[str, Any]] = asyncio.run(
            clip_selector.generate_clips(
                segments,
                num_clips=num_clips,
                vibe=vibe,
                client=self.llm.client,
                model=self.llm.model,
            )
        )

        # --- 3. Render each clip -------------------------------------------
        rendered: list[dict[str, Any]] = []
        for idx, item in enumerate(clips_data):
            start_time = max(0.0, float(item.get("start", 0)))
            end_time = max(start_time + 1.0, float(item.get("end", 0)))
            if end_time - start_time < 5.0:
                continue  # skip too-short clips
            clip = models.Clip(
                video_id=video.id,
                template_id=template.id if template else None,
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                title=item.get("title", f"Clip {idx+1}"),
                description=item.get("description", ""),
                hashtags=",".join(item.get("hashtags", [])),
                hook=item.get("hook", ""),
                status="pending",
                progress=0.0,
            )
            self.db.add(clip)
            self.db.commit()
            self.db.refresh(clip)

            try:
                rs = render_service.RenderService(self.db)
                tmpl = template
                if tmpl is None:
                    tmpl = (
                        self.db.query(models.Template)
                        .filter(models.Template.is_default.is_(True))
                        .first()
                    )
                out = rs.render_clip(clip, video, tmpl)
                clip.status = "rendered"
                clip.progress = 100.0
                self.db.commit()

                meta = self._clip_metadata(clip, video, tmpl, item, out, transcript_path)
                rendered.append(meta)
                # Sidecar JSON next to the MP4 so the clip is ready to post.
                self.write_sidecar_metadata(out, meta)
            except Exception as exc:  # noqa: BLE001 - render failure recorded on clip
                clip.status = "error"
                clip.error_message = f"render failed: {exc}"
                self.db.commit()
                rendered.append({
                    "clip_id": clip.id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "title": clip.title,
                    "status": "error",
                    "error": str(exc),
                })

        # --- 4. Mark video done + move source to done folder ---------------
        video.status = "done"
        self.db.commit()
        self._move_to_done(video_path)

        return {
            "video_id": video.id,
            "video_file": video_path.name,
            "video_path": str(video_path),
            "transcript_path": transcript_path,
            "clips": rendered,
        }

    def run_batch(
        self,
        num_clips: int | None = None,
        vibe: str | None = None,
        template: models.Template | None = None,
    ) -> dict[str, Any]:
        """Process every pending video in the input folder."""
        pending = self.scan_pending()
        results: list[dict[str, Any]] = []
        for path in pending:
            try:
                results.append(self.process_video(path, num_clips, vibe, template))
            except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch
                results.append({
                    "video_file": path.name,
                    "video_path": str(path),
                    "status": "error",
                    "error": str(exc),
                })
        return {
            "processed": len(pending),
            "results": results,
            "completed_at": _utc_now(),
        }

    # ------------------------------------------------------------------ private
    @staticmethod
    def _clip_metadata(
        clip: models.Clip,
        video: models.Video,
        template: models.Template | None,
        clip_data: dict[str, Any],
        output_path: str,
        transcript_path: Path,
    ) -> dict[str, Any]:
        tmpl_name = template.name if template else "default"
        tmpl_id = template.id if template else None
        return {
            "clip_id": clip.id,
            "video_id": video.id,
            "video_file": Path(video.path).name,
            "start_time": clip.start_time,
            "end_time": clip.end_time,
            "duration": clip.duration,
            "title": clip.title,
            "description": clip.description,
            "hashtags": clip.hashtags,
            "hook": clip.hook,
            "vibe": clip_data.get("vibe"),
            "confidence": clip_data.get("confidence"),
            "template_id": tmpl_id,
            "template_name": tmpl_name,
            "output_path": output_path,
            "transcript_path": str(transcript_path),
            "dimensions": [video.width, video.height],
            "fps": video.fps,
            "status": clip.status,
            "rendered_at": _utc_now(),
        }

    def _move_to_done(self, video_path: Path) -> None:
        """Move a fully processed source video into the done folder."""
        try:
            ensure_writable_dir(self.done_dir)
            dest = self.done_dir / video_path.name
            if dest.exists():
                dest = self.done_dir / f"{video_path.stem}_{uuid.uuid4().hex[:8]}{video_path.suffix}"
            shutil.move(str(video_path), str(dest))
        except Exception:  # noqa: BLE001,S110 - moving is best-effort
            # Moving is best-effort; a failed move must not fail the batch.
            pass

    def write_sidecar_metadata(self, output_path: str, metadata: dict[str, Any]) -> Path:
        """Write a sidecar .json next to a rendered MP4. Returns the json path."""
        out = Path(output_path)
        meta_path = out.with_suffix(".json")
        ensure_writable_dir(out.parent)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        return meta_path
