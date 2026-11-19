"""Default caption style is bold/larger/legible; explicit template styles win."""

from __future__ import annotations

import json
import os
import types
from pathlib import Path

import pytest

from app.core.config import CAPTION_FONT_SIZE_PCT, CAPTION_MARGIN_LR, CAPTION_WRAP_CHARS
from app.services.render_service import (
    RenderService,
    resolve_caption_style,
    wrap_caption_text,
)


def _ass_for(template_config: dict | None, tmp_path: Path) -> str:
    transcript = tmp_path / "transcript.json"
    transcript.write_text(json.dumps([
        {"start": 0.0, "end": 2.0, "text": "a fairly long caption line for review"}
    ]), encoding="utf-8")
    clip = types.SimpleNamespace(id=99, start_time=0.0, end_time=2.0)
    video = types.SimpleNamespace(transcript_path=str(transcript))
    template = types.SimpleNamespace(config=template_config or {}) if template_config is not None else None
    service = RenderService(db=None)
    ass_path = service._build_ass(clip, video, template, tmp_path)
    assert ass_path is not None
    return Path(ass_path).read_text(encoding="utf-8")


def test_default_style_values_are_larger_and_bold(tmp_path):
    style = resolve_caption_style({})
    # 6.5% of the 1920 px output height -> 125 px (was 45 px / 2.34%).
    assert style["size"] == pytest.approx(125)
    assert style["size"] / 1920 == pytest.approx(0.065, abs=0.001)
    assert style["bold"] == -1                    # ASS bold
    assert style["primary"] == "&H00FFFFFF"       # white
    assert style["outline"] == "&H00000000"       # dark outline
    assert style["shadow"] >= 2                   # soft shadow
    assert style["max_lines"] == 2
    assert style["alignment"] == 2                # bottom centre

    ass = _ass_for(None, tmp_path)
    assert "WrapStyle: 2" in ass
    style_line = next(line for line in ass.splitlines() if line.startswith("Style:"))
    fields = [f.strip() for f in style_line.split(",", 23)]
    assert fields[1] == "Arial"
    assert int(fields[2]) == 125
    assert fields[3] == "&H00FFFFFF"
    assert fields[7] == "-1"
    assert int(fields[16]) == 5                   # Outline width
    assert int(fields[17]) == 3                   # Shadow
    assert int(fields[18]) == 2                   # Alignment
    # Bottom margin stays inside the 18% safe zone (345.6 px of 1920).
    assert float(fields[21]) == pytest.approx(345.6)


def test_explicit_template_settings_are_unchanged(tmp_path):
    explicit = {
        "caption": {
            "font": "Comic Sans", "size": 90, "bold": 0,
            "primary": "#FF0000", "outline": "&H00000000",
            "back": "&H80000000", "alignment": 1,
            "outline_w": 7, "shadow": 1, "max_lines": 3,
        }
    }
    ass = _ass_for(explicit, tmp_path)
    style_line = next(line for line in ass.splitlines() if line.startswith("Style:"))
    fields = [f.strip() for f in style_line.split(",", 23)]
    assert fields[1] == "Comic Sans"
    assert int(fields[2]) == 90
    assert fields[3] == "&H000000FF"              # #FF0000 -> ASS BGR
    assert fields[7] == "0"
    assert int(fields[16]) == 7
    assert int(fields[17]) == 1
    assert int(fields[18]) == 1


def test_wrapping_is_word_based_and_capped_at_two_lines():
    wrapped = wrap_caption_text(
        "this is a very long caption that must wrap onto more than two lines",
        max_chars=12, max_lines=2,
    )
    lines = wrapped.split("\\N")
    assert len(lines) == 2
    assert all(line and " " in line or len(line) <= 12 for line in lines)
    assert lines[-1].endswith("…")
    # Short captions are untouched.
    assert wrap_caption_text("short hook", max_chars=18) == "short hook"


def test_default_wrap_fits_three_word_hooks_in_two_lines():
    # The old 18-char wrap left lines such as "God hates someone." overflowing
    # the 1080 px frame at the new 125 px bold style (1231 px measured).
    assert CAPTION_WRAP_CHARS <= 15
    for text in ("God hates someone.", "looking down and", "where they would",
                 "like violent ways.", "blasphemous piece of"):
        lines = wrap_caption_text(text).split("\\N")
        assert len(lines) <= 2, (text, lines)
        assert all(len(line) <= CAPTION_WRAP_CHARS for line in lines), (text, lines)
        assert not any(line.endswith("…") for line in lines), (text, lines)


def test_wrapped_lines_fit_frame_width_with_bold_font():
    ImageFont = pytest.importorskip("PIL.ImageFont")
    size = round(CAPTION_FONT_SIZE_PCT * 1920)
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf"
    if not font_path.is_file():
        pytest.skip("bold Arial font file unavailable")
    font = ImageFont.truetype(str(font_path), size)
    available = 1080 - 2 * CAPTION_MARGIN_LR
    for text in ("God hates someone.", "looking down and", "where they would",
                 "like violent ways.", "blasphemous piece of"):
        for line in wrap_caption_text(text).split("\\N"):
            assert font.getlength(line) <= available, (text, line, font.getlength(line))
