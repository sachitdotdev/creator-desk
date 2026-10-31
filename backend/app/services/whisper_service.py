from __future__ import annotations
import os
import site

# Inject NVIDIA DLLs into PATH before importing ctranslate2/faster_whisper
if os.name == 'nt':
    site_packages = site.getsitepackages()[0]
    nvidia_bin_paths = [
        os.path.join(site_packages, "nvidia", "cublas", "bin"),
        os.path.join(site_packages, "nvidia", "cudnn", "bin")
    ]
    for path in nvidia_bin_paths:
        if os.path.exists(path):
            os.environ["PATH"] = path + os.pathsep + os.environ["PATH"]

# Now import the rest normally
import logging
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

"""Transcription service using faster-whisper with word/timestamp segments."""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Sequence

from app.core.config import (
    SOURCES_DIR,
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
)
from app.core.processing_utils import clear_gpu_memory


# --------------------------------------------------------------------------- PyAV compatibility
# faster-whisper decodes audio via ``av.open(input, mode="r", metadata_errors="ignore")``.
# Some PyAV wheels/builds ship an ``av.open()`` that does not accept the
# ``metadata_errors`` keyword, which would break transcription on otherwise
# healthy machines. Wrap it so we transparently fall back when the kwarg is
# unsupported.
_orig_av_open = None


def _ensure_av_open_compat() -> None:
    """Patch ``av.open`` to tolerate a missing ``metadata_errors`` parameter."""
    global _orig_av_open
    if _orig_av_open is not None:
        return
    try:
        import av as _av_mod  # type: ignore
    except Exception:
        return  # av unavailable; faster-whisper will raise its own clear error
    _orig_av_open = _av_mod.open

    def _open_compat(*args, **kwargs):
        try:
            return _orig_av_open(*args, **kwargs)
        except TypeError as exc:
            if "metadata_errors" in str(exc):
                kwargs.pop("metadata_errors", None)
                return _orig_av_open(*args, **kwargs)
            raise

    _av_mod.open = _open_compat


@dataclass
class WordSegment:
    word: str
    start: float
    end: float
    probability: float


@dataclass
class TranscriptSegment:
    id: int
    start: float
    end: float
    text: str
    words: List[WordSegment]


@dataclass
class TranscriptionResult:
    language: str
    duration: float
    segments: List[TranscriptSegment]

    def to_dict(self):
        return asdict(self)


_HEX_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")
_ASS_COLOR_RE = re.compile(r"^&H([0-9A-Fa-f]{6,8})&$")


def to_ass_color(value: Optional[str], default: str = "&H00FFFFFF&") -> str:
    """Normalize a color to ASS &HBBGGRR& (optionally &HAABBGGRR&) form.

    Accepts "#RRGGBB" hex or an existing "&H...&" ASS color; anything else
    falls back to ``default``.
    """
    if not value:
        return default
    v = str(value).strip()
    if _ASS_COLOR_RE.match(v):
        return v
    m = _HEX_COLOR_RE.match(v)
    if m:
        hexrgb = m.group(1)
        return f"&H00{hexrgb[4:6]}{hexrgb[2:4]}{hexrgb[0:2]}&"
    return default


def escape_ass_text(text: str) -> str:
    """Escape backslash/braces so transcript text cannot break ASS tags."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def format_ass_timestamp(ts: float) -> str:
    """Format seconds as an ASS time stamp: H:MM:SS.cc (centiseconds)."""
    cs = int(round(ts * 100))
    h = cs // 360_000
    cs %= 360_000
    m = cs // 6_000
    cs %= 6_000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def group_kinetic_phrases(
    words: Sequence[WordSegment],
    max_words_per_phrase: int = 3,
    max_phrase_secs: float = 2.5,
    max_gap_secs: float = 0.6,
) -> List[List[WordSegment]]:
    """Split a chronologically ordered word list into short kinetic phrases.

    A new phrase starts when the gap between words exceeds ``max_gap_secs``,
    the phrase would exceed ``max_words_per_phrase`` words, or the phrase
    span exceeds ``max_phrase_secs``. Phrases stay within a single segment
    (caller passes per-segment word lists).
    """
    phrases: List[List[WordSegment]] = []
    current: List[WordSegment] = []
    for w in words:
        if current:
            gap = w.start - current[-1].end
            span = w.end - current[0].start
            if len(current) >= max_words_per_phrase or gap > max_gap_secs or span > max_phrase_secs:
                phrases.append(current)
                current = [w]
            else:
                current.append(w)
        else:
            current = [w]
    if current:
        phrases.append(current)
    return phrases


class WhisperService:
    def __init__(self):
        self._model = None
        self._model_size = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(f"Failed to import faster_whisper: {exc}") from exc

        self._model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

        self._model_size = WHISPER_MODEL
        return self._model


    def unload_model(self) -> None:
        """Release the loaded faster-whisper model and free GPU memory.

        Called between batch jobs to prevent CUDA memory from accumulating
        during long-running sessions. Safe to call when no model is loaded.
        """
        self._model = None
        self._model_size = None
        clear_gpu_memory()

    def reset(self) -> None:
        """Alias for unload_model() for readability at call sites."""
        self.unload_model()

    def transcribe(self, video_path: str, output_json_path: Optional[str] = None) -> TranscriptionResult:
        model = self._load_model()
        # Ensure faster-whisper's av.open() call works on PyAV builds that lack
        # the ``metadata_errors`` keyword.
        _ensure_av_open_compat()

        try:
            segments_iter, info = model.transcribe(
                video_path,
                beam_size=5,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
        except Exception as exc:
            # Surface a clear, catchable error so the pipeline can mark the
            # job as failed instead of crashing Uvicorn on a corrupt file.
            raise RuntimeError(f"faster-whisper transcription failed for {video_path}: {exc}") from exc

        segments: List[TranscriptSegment] = []
        for i, seg in enumerate(segments_iter):
            words = [
                WordSegment(
                    word=w.word,
                    start=w.start,
                    end=w.end,
                    probability=w.probability,
                )
                for w in (seg.words or [])
            ]
            segments.append(
                TranscriptSegment(
                    id=i,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    words=words,
                )
            )

        result = TranscriptionResult(
            language=info.language,
            duration=info.duration,
            segments=segments,
        )

        if output_json_path:
            Path(output_json_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

        return result

    def format_srt(self, result: TranscriptionResult) -> str:
        def fmt(ts: float) -> str:
            ms = int(round(ts * 1000))
            h = ms // 3_600_000
            ms %= 3_600_000
            m = ms // 60_000
            ms %= 60_000
            s = ms // 1000
            ms %= 1000
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines = []
        for i, seg in enumerate(result.segments, start=1):
            lines.append(str(i))
            lines.append(f"{fmt(seg.start)} --> {fmt(seg.end)}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)

    def format_ass(self, result: TranscriptionResult, style: str = "Default") -> str:
        """Generate an ASS subtitle file with a single style block."""
        header = (
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
            "Style: Default,Arial,24,&H0000FFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,30,30,60,1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        lines = [header]
        for seg in result.segments:
            words = list(seg.words or [])
            if not words:
                text = seg.text.strip().replace("\n", " ")
                lines.append(f"Dialogue: 0,{format_ass_timestamp(seg.start)},{format_ass_timestamp(seg.end)},Default,,0,0,0,,{text}")
                continue

            phrases = group_kinetic_phrases(words, max_words_per_phrase=3)
            for phrase in phrases:
                start = phrase[0].start
                end = phrase[-1].end
                parts = []
                for w in phrase:
                    cs = max(1, int(round((w.end - w.start) * 100)))
                    parts.append(f"{{\\k{cs}}}{escape_ass_text(w.word)}")
                text = "".join(parts)
                lines.append(f"Dialogue: 0,{format_ass_timestamp(start)},{format_ass_timestamp(end)},Default,,0,0,0,,{text}")

        lines.append("")
        return "\n".join(lines)

    def format_ass_styled(self, result: TranscriptionResult, caption_style: dict) -> str:
        """Generate ASS with template-driven styling."""
        font = caption_style.get("font", "Arial")
        size = int(caption_style.get("size", 48))
        primary = caption_style.get("primary", "&H00FFFFFF&")
        outline = caption_style.get("outline", "&H00000000&")
        back = caption_style.get("back", "&H80000000&")
        bold = -1 if int(caption_style.get("bold", 1)) else 0  # ASS: -1 = bold
        alignment = int(caption_style.get("alignment", 2))  # 2 = bottom center
        margin_v = int(caption_style.get("margin_v", 60))
        outline_w = int(caption_style.get("outline_w", 3))
        shadow = int(caption_style.get("shadow", 0))

        header = (
            "[Script Info]\n"
            "Title: CreatorDesk Kinetic Captions\n"
            "ScriptType: v4.00+\n"
            "WrapStyle: 0\n"
            "ScaledBorderAndShadow: yes\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font},{size},{primary},{primary},{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_w},{shadow},{alignment},30,30,{margin_v},1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        lines = [header]
        for seg in result.segments:
            words = list(seg.words or [])
            if not words:
                # Segment without word-level data: plain full-text line.
                text = escape_ass_text(seg.text.strip().replace("\n", " "))
                lines.append(
                    f"Dialogue: 0,{format_ass_timestamp(seg.start)},{format_ass_timestamp(seg.end)},"
                    f"Default,,0,0,0,,{text}"
                )
                continue
            has_words = True
            for phrase in group_kinetic_phrases(
                words,
                max_words_per_phrase=max_words_per_phrase,
                max_phrase_secs=max_phrase_secs,
                max_gap_secs=max_gap_secs,
            ):
                start = phrase[0].start
                end = phrase[-1].end
                # Karaoke \k tags (centiseconds): each word fills yellow while
                # spoken, the rest of the phrase stays primary (white) color.
                parts: List[str] = []
                first = phrase[0]
                parts.append(f"{{\\k{max(1, int(round((first.end - first.start) * 100)))}}}{escape_ass_text(first.word)}")
                for w in phrase[1:]:
                    cs = max(1, int(round((w.end - w.start) * 100)))
                    parts.append(f" {{\\k{cs}}}{escape_ass_text(w.word)}")
                text = "".join(parts)
                lines.append(
                    f"Dialogue: 0,{format_ass_timestamp(start)},{format_ass_timestamp(end)},"
                    f"Default,,0,0,0,,{text}"
                )
        lines.append("")
        return "\n".join(lines)
