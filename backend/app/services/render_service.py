"""Render service: FFmpeg NVENC 9:16 vertical clips with burned ASS captions + template overlay."""
from __future__ import annotations

import json
import math
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from app.models import Clip, Template, Video
from app.services.whisper_service import (
    TranscriptionResult,
    TranscriptSegment,
    WordSegment,
    WhisperService,
    format_ass_timestamp,
)
from app.core.config import (
    RENDERS_DIR,
    FFMPEG_PATH,
    FFMPEG_DEVICE,
    FFMPEG_TIMEOUT_SECONDS,
    OUTPUT_WIDTH,
    OUTPUT_HEIGHT,
    OUTPUT_FPS,
    OUTPUT_CRF,
)
from app.core.processing_utils import (
    ensure_writable_dir,
    clear_gpu_memory,
    run_subprocess,
)


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

    # ------------------------------------------------------------------ public
    def render_clip(self, clip: Clip, video: Video, template: Optional[Template] = None, base_path: Optional[str] = None) -> str:
        """Render a single vertical clip. Returns output path.
        
        All ffmpeg calls are wrapped with a timeout so a hung or failing
        encode cannot stall or crash a long-running batch job. The output
        directory is verified writable before any work begins.
        """
        render_root = Path(base_path) if base_path else RENDERS_DIR
        ensure_writable_dir(render_root)
        
        output_path = render_root / f"clip_{clip.id}_{uuid.uuid4().hex[:8]}.mp4"
        
        config = template.get_config() if template else (
            self.VIBE_PROFILES.get(getattr(clip, "vibe_category", None), self._default_config())
        )
        
        # 1. Build ASS subtitles from transcript if available
        ass_path = self._build_ass(clip, video, config, render_root)
        
        # 2. Build the ffmpeg filter graph
        vf = self._build_filter_graph(video, config, ass_path)
        
        # 3. Run ffmpeg (timeout-protected).
        # When an ASS file is burned in, set cwd to the ASS file's folder so
        # the bare `ass=<name>` filter reference resolves correctly.
        cmd = self._build_ffmpeg_cmd(video.path, clip.start_time, clip.end_time, vf, str(output_path), config, ass_path)
        ffmpeg_cwd = str(Path(ass_path).parent) if ass_path else None
        try:
            subprocess.run([str(x) for x in cmd], check=True, timeout=120, cwd=ffmpeg_cwd)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"FFmpeg render failed: {exc}") from exc
        
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
            thumb_path = None
        
        clip.output_path = str(output_path)
        clip.thumbnail_path = str(thumb_path) if thumb_path else None
        clip.status = "rendered"
        clip.progress = 100.0
        self.db.commit()
        
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

    def _build_ass(self, clip: Clip, video: Video, config: Dict[str, Any], render_root: Path) -> Optional[str]:

        """Create an ASS file containing only the subtitles within the clip window.

        When the transcript has word-level timestamps and the template caption
        config enables kinetic rendering (default: on), words are grouped into
        short phrases (1-3 words) and rendered as karaoke-style Dialogue
        lines: the actively spoken word fills yellow while the rest of the
        phrase stays white — bold, centered, center-bottom of the 9:16 frame.
        Otherwise falls back to one plain line per transcript segment.

        All ASS timestamps are clip-relative (clip start == 0s) so they stay
        in sync with the trimmed output timeline.
        """
        transcript_path = video.transcript_path
        if not transcript_path or not os.path.exists(transcript_path):
            return None

        with open(transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cap = config.get("caption", {})
        kinetic = bool(cap.get("kinetic", cap.get("karaoke", True)))

        def clip_rel(ts: float) -> float:
            return max(0.0, min(clip.end_time - clip.start_time, ts - clip.start_time))

        # Collect segments/words overlapping the clip window, shifted to
        # clip-relative time so they land on the trimmed output timeline.
        clip_segments: List[tuple[float, float, str, List[WordSegment]]] = []
        clip_words: List[WordSegment] = []
        for seg in data.get("segments", []):
            s = float(seg["start"])
            e = float(seg["end"])
            # keep only segments overlapping the clip window
            if e <= clip.start_time or s >= clip.end_time:
                continue
            cs = clip_rel(s)
            ce = clip_rel(e)
            if ce <= cs:
                continue
            seg_words: List[WordSegment] = []
            for w in seg.get("words") or []:
                ws = float(w["start"])
                we = float(w["end"])
                if we <= clip.start_time or ws >= clip.end_time:
                    continue
                seg_words.append(
                    WordSegment(
                        word=str(w.get("word", "")),
                        start=clip_rel(ws),
                        end=clip_rel(we),
                        probability=float(w.get("probability", 0.0)),
                    )
                )
                clip_words.append(seg_words[-1])
            text = str(seg.get("text", "")).strip().replace("\n", " ")
            clip_segments.append((cs, ce, text, seg_words))

        if not clip_segments:
            return None

        ass_path = render_root / f"subs_{clip.id}_{uuid.uuid4().hex[:8]}.ass"
        ensure_writable_dir(render_root)

        try:
            if kinetic and clip_words:
                result = TranscriptionResult(
                    language=str(data.get("language", "en")),
                    duration=clip.end_time - clip.start_time,
                    segments=[
                        TranscriptSegment(id=i, start=cs, end=ce, text=text, words=sw)
                        for i, (cs, ce, text, sw) in enumerate(clip_segments)
                    ],
                )
                ass_content = WhisperService().format_ass(result, cap)
            else:
                # Legacy: one plain Dialogue line per segment.
                lines: List[str] = [
                    "[Script Info]\n"
                    "Title: CreatorDesk Captions\n"
                    "ScriptType: v4.00+\n"
                    "WrapStyle: 0\n"
                    "ScaledBorderAndShadow: yes\n"
                    "PlayResX: 1080\n"
                    "PlayResY: 1920\n"
                    "\n[V4+ Styles]\n"
                    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
                    f"Style: Default,{cap.get('font','Arial')},{int(cap.get('size',48))},{cap.get('primary','white')},"
                    f"{cap.get('primary','white')},{cap.get('outline','&H00000000&')},{cap.get('back','&H4D000000&')},"
                    f"{int(cap.get('bold',1))},0,0,0,100,100,0,0,1,{int(cap.get('outline_w',3))},{int(cap.get('shadow',0))},"
                    f"{int(cap.get('alignment',2))},30,30,{int(cap.get('margin_v',120))},1\n"
                    "\n[Events]\n"
                    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                ]
                for cs, ce, text, _sw in clip_segments:
                    lines.append(
                        f"Dialogue: 0,{format_ass_timestamp(cs)},{format_ass_timestamp(ce)},"
                        f"Default,,0,0,0,,{text}"
                    )
                lines.append("")
                ass_content = "\n".join(lines)

            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
        except OSError as exc:
            raise RuntimeError(f"Failed to write ASS subtitle file: {ass_path} ({exc})") from exc
        return str(ass_path)

    def _build_filter_graph(
        self, video: Video, config: Dict[str, Any], ass_path: Optional[str]
    ) -> str:
        """Build a complex filtergraph: center-crop to 9:16 + subtitles + overlays."""
        W = OUTPUT_WIDTH
        H = OUTPUT_HEIGHT
        vw = video.width or 1920
        vh = video.height or 1080

        # Scale source to fill height H (preserving aspect), then center-crop width W.
        # scale=-2:H makes width = H * vw/vh (even). crop=W:H:(iw-W)/2:0 center-crops.
        scale = f"scale=-2:{H}:flags=bicubic"
        crop = f"crop={W}:{H}:(iw-{W})/2:0"

        parts: List[str] = [scale, crop]

        # Background handling: if source aspect is very wide, blurred sides already covered by crop.
        # We add a subtle letterbox fallback handled by crop; keep simple.

        # Burn subtitles. Use a bare filename resolved via the ffmpeg working
        # directory (set to the ASS file's folder in render_clip) to avoid
        # fragile Windows drive-letter/backslash escaping inside the filtergraph.
        if ass_path:
            ass_name = Path(ass_path).name
            parts.append(f"ass={ass_name}")

        # Title overlay (drawtext)
        title_conf = config.get("title", {})
        title_text = title_conf.get("text", "")
        if title_text:
            t_size = int(title_conf.get("size", 36))
            t_color = title_conf.get("color", "white")
            t_font = title_conf.get("font", "Arial")
            t_bold = int(title_conf.get("bold", 1))
            t_outline = int(title_conf.get("outline_w", 2))
            t_pos = title_conf.get("position", "top")
            t_margin = int(title_conf.get("margin_v", 70))
            if t_pos == "top":
                y = t_margin
            elif t_pos == "bottom":
                y = f"H-{t_margin}-text_h"
            else:
                y = "(H-text_h)/2"
            parts.append(
                f"drawtext=fontfile='{t_font}':fontsize={t_size}:fontcolor=white:"
                f"bold={t_bold}:outline={t_outline}:x=(w-text_w)/2:y={y}:text='{title_text}'"
            )




        return ",".join(parts)

    def _build_ffmpeg_cmd(
        self,
        input_path: str,
        start: float,
        end: float,
        vf: str,
        output_path: str,
        config: Dict[str, Any],
        ass_path: Optional[str] = None,
    ) -> List[str]:
        duration = end - start
        hwaccel = FFMPEG_DEVICE  # cuda | cpu

        if ass_path:
            safe_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
            ass_filter = f",ass='{safe_ass}'"
        else:
            ass_filter = ""

        # Ensure ASS path is properly escaped for Windows
        if ass_path:
            ass_name = Path(ass_path).name
            ass_filter = f",ass='{ass_name}'"
        else:
            ass_filter = ""
        
        # Dynamic zoompan filter with slow center zoom
        zoompan_filter = "zoompan=z='min(zoom+0.0005,1.3)':d=20:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
        
        vf_string = f"scale=-2:1920:flags=bicubic,crop=1080:1920:(iw-1080)/2:0,{zoompan_filter}{ass_filter}"

        cmd = [
            FFMPEG_PATH, "-y",
            "-hide_banner", "-loglevel", "error",
            "-ss", str(start),
            "-i", input_path,
            "-t", str(duration),
            "-vf", vf_string,
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-rc", "vbr",
            "-cq", str(OUTPUT_CRF),
            "-b:v", "5M",
            "-maxrate", "10M",
            "-bufsize", "10M",
            "-c:a", "aac",
            "-b:a", "128k",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            str(output_path)
        ]

        print(f"DEBUG FFMPEG CMD: {cmd}", flush=True)
        return cmd
