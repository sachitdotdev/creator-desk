"""Render service: FFmpeg libx264 9:16 vertical clips with burned ASS captions + template overlay."""
from __future__ import annotations

import gc
import json
import os
import subprocess
import torch
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from app.models import Clip, Template, Video
from app.services.whisper_service import (
    TranscriptSegment,
    WhisperService,
)
from app.services.edit_compiler import compile_plan
from app.services.face_tracker import generate_sendcmd_file
from app.core.config import (
    RENDERS_DIR,
    FFMPEG_PATH,
    FFMPEG_TIMEOUT_SECONDS,
    OUTPUT_HEIGHT,
    OUTPUT_FPS,
    OUTPUT_CRF,
)
from app.core.processing_utils import (
    ensure_writable_dir,
    clear_gpu_memory,
)


def _hex_to_ass(hex_color: str, default: str = "&H00FFFFFF") -> str:
    if not hex_color or not hex_color.startswith("#") or len(hex_color) < 7:
        return default
    try:
        r = hex_color[1:3]
        g = hex_color[3:5]
        b = hex_color[5:7]
        return f"&H00{b}{g}{r}&"
    except Exception:
        return default


class RenderService:
    VIBE_PROFILES = {
    "Streamer Hype": {
        "layout": "Split Stack",
        "zoom_intensity": "fast",
        "caption_style": {"font": "Arial", "size": 48, "bold": 1, "primary": "white", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 120, "outline_w": 3, "shadow": 0, "highlight_color": "&H0068EE7B&", "karaoke": True, "kinetic": True},
        "pacing": "fast",
    },
    "Rapper Energy": {
        "layout": "PiP B-roll",
        "zoom_intensity": "high",
        "caption_style": {"font": "Arial", "size": 48, "bold": 1, "primary": "white", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 120, "outline_w": 3, "shadow": 0, "highlight_color": "&H0068EE7B&", "karaoke": True, "kinetic": True},
        "pacing": "beat-synced",
    },
    "Technical": {
        "layout": "Focus Frame",
        "zoom_intensity": "none",
        "caption_style": {"font": "Arial", "size": 48, "bold": 1, "primary": "white", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 120, "outline_w": 3, "shadow": 0, "highlight_color": "&H0068EE7B&", "karaoke": False, "kinetic": False},
        "pacing": "strict",
    },
    "Horror": {
        "layout": "Letterbox",
        "zoom_intensity": "slow",
        "caption_style": {"font": "Arial", "size": 48, "bold": 1, "primary": "white", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 120, "outline_w": 3, "shadow": 0, "highlight_color": "&H0068EE7B&", "karaoke": True, "kinetic": True},
        "pacing": "slow",
    },
    "Narrative": {
        "layout": "Cinema Bar",
        "zoom_intensity": "soft",
        "caption_style": {"font": "Arial", "size": 48, "bold": 1, "primary": "white", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 120, "outline_w": 3, "shadow": 0, "highlight_color": "&H0068EE7B&", "karaoke": True, "kinetic": True},
        "pacing": "documentary",
    },
}

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _format_time(s: float) -> str:
        """Convert seconds to H:MM:SS.cs format."""
        if s < 0:
            s = 0.0
        total_cs = int(round(s * 100))
        h = total_cs // 360000
        m = (total_cs % 360000) // 6000
        ssec = (total_cs % 6000) // 100
        cs = total_cs % 100
        return f"{h}:{m:02d}:{ssec:02d}.{cs:02d}"

    # ------------------------------------------------------------------ public
    def render_clip(self, clip: Clip, video: Video, template: Optional[Template] = None, base_path: Optional[str] = None) -> str:
        """Render a single vertical clip. Returns output path.
        
        All ffmpeg calls are wrapped with a timeout so a hung or failing
        encode cannot stall or crash a long-running batch job. The output
        directory is verified writable before any work begins.
        """

        # Clear VRAM from previous stages (Whisper/vLLM) before rendering
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Clamp start_time to >= 0 and ensure end_time > start_time
        if clip.start_time < 0:
            clip.start_time = 0.0
        if clip.end_time <= clip.start_time:
            clip.end_time = clip.start_time + 5.0
        
        render_root = Path(base_path) if base_path else RENDERS_DIR
        ensure_writable_dir(render_root)
        print(f"DEBUG render_clip: clip_id={clip.id}", flush=True)
        
        output_path = render_root / f"clip_{clip.id}_{uuid.uuid4().hex[:8]}.mp4"
        
        # 1. Build ASS subtitles from transcript if available
        print("DEBUG render_clip: Starting _build_ass", flush=True)
        
        # Debug: Check if transcript exists
        transcript_path = video.transcript_path
        print(f"DEBUG render_clip: video.transcript_path = {transcript_path}", flush=True)
        print(f"DEBUG render_clip: transcript exists = {Path(transcript_path).exists() if transcript_path else 'NOT SET'}", flush=True)
        
        ass_path = self._build_ass(clip, video, template, render_root)
        print(f"DEBUG render_clip: ass_path (returned from _build_ass) = {ass_path}", flush=True)
        
        # 2. Build the ffmpeg filter graph using the edit plan from the clip
        print("DEBUG render_clip: Starting _build_filter_graph", flush=True)
        print(f"DEBUG render_clip: clip.layout = {clip.layout}, clip.operations = {clip.operations}", flush=True)

        sendcmd_path = f"C:/Sachit/Creator Desk/data/renders/crop_{clip.id}.txt"
        sendcmd_filename = f"crop_{clip.id}.txt"
        generate_sendcmd_file(video.path, clip.start_time, clip.end_time - clip.start_time, sendcmd_path)

        vf, sfx_files = self._build_filter_graph(
            video, clip, ass_path, template, clip.layout, clip.operations, clip.start_time, sendcmd_filename, template_config=template.config if template else {}
        )
        print(f"DEBUG render_clip: vf={vf}", flush=True)
        
        # 3. Run ffmpeg (timeout-protected).
        # When an ASS file is burned in, set cwd to the ASS file's folder so
        # the bare `ass=<name>` filter reference resolves correctly.
        print("DEBUG render_clip: Starting _build_ffmpeg_cmd", flush=True)
        cmd = self._build_ffmpeg_cmd(video.path, clip.start_time, clip.end_time, vf, str(output_path), ass_path, sfx_files)
        ffmpeg_cwd = str(Path(ass_path).parent) if ass_path else None
        print(f"DEBUG render_clip: running ffmpeg, cwd={ffmpeg_cwd}", flush=True)
        print(f"DEBUG render_clip: ffmpeg command (space-separated): {' '.join(str(x) for x in cmd)}", flush=True)
        try:
            subprocess.run([str(x) for x in cmd], check=True, timeout=120, cwd=ffmpeg_cwd)
        except subprocess.CalledProcessError as exc:
            print(f"DEBUG render_clip: ffmpeg failed: {exc}", flush=True)
            print(f"DEBUG render_clip: stderr={exc.stderr}", flush=True)
            print(f"DEBUG render_clip: stdout={exc.stdout}", flush=True)
            raise RuntimeError(f"FFmpeg render failed: {exc.stderr or 'no stderr output'}") from exc
        
        # Generate a thumbnail (best-effort; failure does not fail the render)
        thumb_path = render_root / f"clip_{clip.id}_{uuid.uuid4().hex[:8]}.jpg"
        try:
            run_subprocess(
                [
                    FFMPEG_PATH, "-y",
                    "-hide_banner", "-loglevel", "error",
                    "-ss", str(clip.start_time + 1),
                    "-i", str(output_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(thumb_path),
                ],
                timeout=FFMPEG_TIMEOUT_SECONDS,
                check=True,
            )
        except Exception:
            print(f"DEBUG render_clip: thumbnail generation failed", flush=True)
            thumb_path = None
        
        clip.output_path = str(output_path)
        clip.thumbnail_path = str(thumb_path) if thumb_path else None
        clip.status = "rendered"
        clip.progress = 100.0
        self.db.commit()
        print(f"DEBUG render_clip: done, output={output_path}", flush=True)
        
        # Release GPU/accelerator memory after each render so long batch
        # sessions do not leak NVENC/CUDA buffers.
        clear_gpu_memory()
        return str(output_path)

    # ---------------------------------------------------------------- internals
    def _default_config(self) -> Dict[str, Any]:
        return {
            "caption": {
                "font": "Arial",
                "size": 48,
                "bold": 1,
                "primary": "white",
                "outline": "&H00000000&",
                "back": "&H4D000000&",
                "alignment": 2,
                "margin_v": 120,
                "outline_w": 3,
                "shadow": 0,
                "highlight_color": "&H0068EE7B&",
                "karaoke": False,
                "kinetic": True,
            },
            "title": {
                "font": "Arial",
                "size": 36,
                "bold": 1,
                "color": "white",
                "position": "top",
                "margin_v": 70,
                "outline_w": 2,
                "glow": False,
            },
            "watermark": {
                "text": "CREATOR DESK",
                "font": "Arial",
                "size": 22,
                "color": "white",
                "opacity": 0.3,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "blur",
                "blur_amount": 25,
                "color": "#000000",
            },
        }
    def _build_ass(self, clip, video, template, render_root):
        """Create an ASS file containing only the subtitles within the clip window."""
        print(f"DEBUG _build_ass: clip.start_time={clip.start_time}, clip.end_time={clip.end_time}", flush=True)
        
        transcript_path = video.transcript_path
        if not transcript_path or not os.path.exists(transcript_path):
            print(f"DEBUG: _build_ass transcript not found at {transcript_path}", flush=True)
            return None
        
        transcript = json.loads(Path(transcript_path).read_text())
        if isinstance(transcript, dict):
            transcript = transcript.get("segments", [])
        
        data = transcript
        if not data:
            return None

        # Strict overlap filtering
        overlapping_segments = [s for s in data if s["end"] >= clip.start_time and s["start"] <= clip.end_time]
        
        # Sort to prevent out-of-order captions
        overlapping_segments = sorted(overlapping_segments, key=lambda x: x.get("start", 0))
        
        if not overlapping_segments:
            return None

        ass_path = render_root / f"subs_{clip.id}_{uuid.uuid4().hex[:8]}.ass"

        ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,45,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        ass_lines: List[str] = []
        last_end_time = 0.0
        for seg in overlapping_segments:
            words = seg.get("text", "").strip().replace("\n", " ").split()
            if not words:
                continue
            
            chunks = [words[i:i + 3] for i in range(0, len(words), 3)]
            total_words = len(words)
            
            raw_start = max(0.0, float(seg.get("start", 0)) - float(clip.start_time))
            raw_end = min(float(clip.end_time) - float(clip.start_time), float(seg.get("end", 0)) - float(clip.start_time))
            
            # Strictly use the original timestamps to prevent any lag
            seg_start = raw_start
            seg_end = raw_end
            
            if seg_start >= seg_end:
                continue
                
            total_duration = seg_end - seg_start
            current_time = seg_start
            
            for chunk in chunks:
                chunk_text = " ".join(chunk)
                
                # Calculate exact proportional time for this chunk
                chunk_duration = total_duration * (len(chunk) / total_words)
                
                # Force the chunk to end exactly at the segment end
                chunk_end = min(seg_end, current_time + chunk_duration)
                
                start_str = self._format_time(current_time)
                end_str = self._format_time(chunk_end)
                ass_lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{chunk_text}")
                current_time = chunk_end

        ass_content = ass_header + "\n".join(ass_lines)

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        print(f"DEBUG: _build_ass wrote {len(ass_lines)} lines to {ass_path}", flush=True)
        return str(ass_path)

    def _build_filter_graph(self, video: Video, clip: Clip, ass_path: Optional[str], template: Optional[Template] = None, layout: str = "split_screen", operations: List = [], start_time: float = 0.0, sendcmd_path: str = "", template_config: dict = None) -> tuple:
        """Build a complex filtergraph: compile the LLM-provided edit plan via edit_compiler.
        
        start_time normalizes absolute timestamps to relative clip timestamps
        so burn-in text and SFX appear at the correct time within the clip.
        """
        clip_start_time = clip.start_time
        ass_filename = os.path.basename(ass_path) if ass_path else ""

        print(f"DEBUG _build_filter_graph: received layout={layout}, operations={operations}, clip_start_time={start_time}", flush=True)

        # If operations is empty from the LLM, use a sensible default.
        if not operations:
            operations = [
                {
                    "type": "zoom",
                    "start": clip.start_time,
                    "end": clip.end_time,
                    "zoom": 1.0,
                },
            ]

        vf_str, sfx_files = compile_plan(
            operations=operations,
            layout=layout,
            ass_filename=ass_filename,
            clip_start_time=clip_start_time,
            sendcmd_path=sendcmd_path,
            template_config=template_config
        )
        return vf_str, sfx_files

    def _build_ffmpeg_cmd(
        self,
        input_path: str,
        start: float,
        end: float,
        vf: str,
        output_path: str,
        ass_path: Optional[str] = None,
        sfx_files: Optional[List[str]] = None,
    ) -> List[str]:
        """Build the ffmpeg command list for rendering a vertical clip."""
        cmd = [
            FFMPEG_PATH, "-y",
            "-hide_banner", "-loglevel", "warning",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(end - start),
            "-filter_complex", vf,
            "-map", "[out_final]",
            "-map", "0:a",
            "-c:v", "h264_nvenc", "-preset", "p4",
            "-b:v", "5M",
            "-maxrate", "10M",
            "-bufsize", "10M",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            str(output_path),
        ]
        return cmd

    