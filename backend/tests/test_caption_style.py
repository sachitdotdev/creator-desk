"""Default caption style is bold/larger/legible; explicit template styles win."""

from __future__ import annotations

import itertools
import json
import os
import types
from pathlib import Path

import pytest

from app.core.config import (
    CAPTION_FONT_SIZE_PCT,
    CAPTION_MARGIN_LR,
    CAPTION_WRAP_CHARS,
)
from app.core.paths import TRANSCRIPTS_DIR
from app.services.render_service import (
    RenderService,
    estimate_caption_width,
    resolve_caption_style,
    wrap_caption_text,
)


def _dialogues(ass: str) -> list[tuple[str, str, str]]:
    return [tuple(line.split(",", 9)[i] for i in (1, 2, 9))
            for line in ass.splitlines() if line.startswith("Dialogue:")]


def _seconds(ts: str) -> float:
    hours, minutes, secs = ts.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(secs)


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


def test_wrapping_is_word_based_and_never_truncates():
    text = "this is a very long caption that must wrap onto more than two lines"
    wrapped = wrap_caption_text(text, max_chars=12, max_lines=2)
    lines = wrapped.split("\\N")
    assert len(lines) > 2                       # no ellipsis truncation
    assert "…" not in wrapped
    assert " ".join(lines).split() == text.split()  # every word survives, in order
    assert all(len(line) <= 12 for line in lines)
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
                 "like violent ways.", "blasphemous piece of",
                 "WOW WOW WOW WOW"):
        for line in wrap_caption_text(text).split("\\N"):
            assert font.getlength(line) <= available, (text, line, font.getlength(line))


def test_uppercase_hook_wraps_by_estimated_width():
    size = round(CAPTION_FONT_SIZE_PCT * 1920)
    assert estimate_caption_width("WOW WOW WOW WOW", size) > 1080 - 2 * CAPTION_MARGIN_LR
    lines = wrap_caption_text("WOW WOW WOW WOW").split("\\N")
    assert len(lines) == 2
    assert " ".join(lines).split() == ["WOW"] * 4
    max_width = (1080 - 2 * CAPTION_MARGIN_LR) * 0.95
    assert all(estimate_caption_width(line, size) <= max_width for line in lines)


def test_long_words_split_into_dialogues_without_losing_time(tmp_path):
    transcript = tmp_path / "t.json"
    transcript.write_text(json.dumps(
        [{"start": 0.0, "end": 3.0, "text": "extraordinary communication responsibilities"}]
    ), encoding="utf-8")
    clip = types.SimpleNamespace(id=7, start_time=0.0, end_time=3.0)
    video = types.SimpleNamespace(transcript_path=str(transcript))
    service = RenderService(db=None)
    ass = Path(service._build_ass(clip, video, None, tmp_path)).read_text(encoding="utf-8")
    assert "…" not in ass

    dialogues = _dialogues(ass)
    assert len(dialogues) >= 2
    text = " ".join(" ".join(d.split("\\N")) for _, _, d in dialogues)
    assert text.split() == ["extraordinary", "communication", "responsibilities"]
    spans = sorted((_seconds(start), _seconds(end)) for start, end, _ in dialogues)
    assert spans[0][0] == pytest.approx(0.0)
    assert spans[-1][1] == pytest.approx(3.0)
    assert all(a[1] <= b[0] + 0.01 for a, b in itertools.pairwise(spans))  # no overlap


@pytest.mark.parametrize("clip_name,start,end", [
    ("clip_2", 1630.957, 1662.934),
    ("clip_4", 4387.657, 4421.996),
])
def test_real_clip_transcript_words_all_reach_ass(tmp_path, clip_name, start, end):
    source = Path(TRANSCRIPTS_DIR) / "video_1_transcript.json"
    if not source.is_file():
        pytest.skip("local clip transcripts are not available")
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("segments", [])
    segments = sorted(
        (s for s in data if s["end"] >= start and s["start"] <= end),
        key=lambda s: s["start"],
    )
    if not segments:
        pytest.skip("no overlapping transcript segments")

    local = tmp_path / "t.json"
    local.write_text(json.dumps(segments), encoding="utf-8")
    clip_id = 2 if clip_name == "clip_2" else 4
    clip = types.SimpleNamespace(id=clip_id, start_time=start, end_time=end)
    video = types.SimpleNamespace(transcript_path=str(local))
    ass = Path(RenderService(db=None)._build_ass(clip, video, None, tmp_path)).read_text(
        encoding="utf-8"
    )
    assert "…" not in ass
    rendered = " ".join(d.replace("\\N", " ") for _, _, d in _dialogues(ass)).split()
    expected = [w for s in segments for w in s["text"].split()]
    it = iter(rendered)
    assert all(any(word == token for token in it) for word in expected), clip_name
