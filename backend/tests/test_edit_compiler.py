"""Phase 3.3 - Short hooks: unit tests for hook/caption text post-processing."""

import logging

from app.services import edit_compiler
from app.services.edit_compiler import (
    MAX_SFX_START_SECONDS,
    compile_plan,
    first_sendcmd_overlay_x,
    truncate_hook_text,
)


def _sfx_plan(operations, monkeypatch, tmp_path, clip_start_time):
    monkeypatch.setattr(edit_compiler, "SFX_DIR", tmp_path)
    (tmp_path / "boom.mp3").write_bytes(b"\x00")
    return compile_plan(
        operations=operations,
        layout="center_crop",
        ass_filename="subs.ass",
        clip_start_time=clip_start_time,
        sendcmd_path="crop.txt",
    )


def test_truncate_hook_short_text_unchanged():
    assert truncate_hook_text("THE TRUTH ABOUT CHEESE") == "THE TRUTH ABOUT CHEESE"


def test_truncate_hook_caps_long_text_to_max_words():
    long_text = "This is an extremely long caption that goes on and on forever"
    # Keeps the first (most meaningful) words, capped at HOOK_MAX_WORDS (5).
    assert truncate_hook_text(long_text) == "This is an extremely long"


def test_truncate_hook_drops_filler_words():
    # "just" is a filler and must not eat into the hook word budget.
    assert truncate_hook_text("Honestly I just think the cheese was fake") == "Honestly I think the cheese"


def test_truncate_hook_preserves_casing_and_punctuation():
    assert truncate_hook_text("THE TRUTH ABOUT CHEESE!!!") == "THE TRUTH ABOUT CHEESE!!!"


def test_truncate_hook_strips_markdown_and_whitespace():
    assert truncate_hook_text("  **THE TRUTH**  ") == "THE TRUTH"


def test_truncate_hook_handles_empty_and_whitespace():
    assert truncate_hook_text("") == ""
    assert truncate_hook_text("    ") == ""


def test_truncate_hook_respects_custom_max_words():
    assert truncate_hook_text("one two three four", max_words=2) == "one two"


def test_first_sendcmd_overlay_x_resolves_bare_name_in_renders_dir(monkeypatch, tmp_path):
    # render_service passes a bare "crop_N.txt" (FFmpeg's cwd is the ASS folder),
    # so the seed must resolve it against RENDERS_DIR rather than Python's cwd.
    monkeypatch.setattr(edit_compiler, "RENDERS_DIR", tmp_path)
    (tmp_path / "crop_2.txt").write_text(
        "0.000 overlay x -981.32;\n0.033 overlay x -980.00;\n", encoding="utf-8"
    )
    assert first_sendcmd_overlay_x("crop_2.txt") == "-981.32"
    vf, _ = compile_plan(
        operations=[],
        layout="center_crop",
        ass_filename="subs.ass",
        clip_start_time=0.0,
        sendcmd_path="crop_2.txt",
    )
    assert "overlay=x=-981.32:y=0" in vf


def test_compile_plan_truncates_llm_hook_text_before_filter_build():
    operations = [
        {
            "type": "text",
            "start": 0.0,
            "end": 5.0,
            "text": "This is a ridiculously long caption that should be shortened",
        }
    ]
    vf, sfx_files = compile_plan(
        operations=operations,
        layout="center_crop",
        ass_filename="subs.ass",
        clip_start_time=0.0,
        sendcmd_path="/tmp/crop.txt",
    )
    # Post-processor truncated the LLM output to a 3-5 word hook.
    assert "This is a" in vf
    assert "ridiculously long caption" not in vf
    assert "should be shortened" not in vf
    assert sfx_files == []


def test_compile_plan_keeps_short_hook_text():
    operations = [
        {
            "type": "text",
            "start": 0.0,
            "end": 5.0,
            "text": "THE TRUTH",
        }
    ]
    vf, _ = compile_plan(
        operations=operations,
        layout="center_crop",
        ass_filename="subs.ass",
        clip_start_time=0.0,
        sendcmd_path="/tmp/crop.txt",
    )
    assert "THE TRUTH" in vf


def test_sfx_late_source_timestamp_uses_clip_relative_delay(monkeypatch, tmp_path):
    # Clip cut from hour 2 of a stream: SFX at 7202s must play 2s into the clip.
    _, sfx_files = _sfx_plan(
        [{"type": "sfx", "name": "boom", "time_sec": 7202}],
        monkeypatch, tmp_path, clip_start_time=7200.0,
    )

    assert len(sfx_files) == 1
    assert sfx_files[0]["start"] == 2.0


def test_sfx_relative_delay_above_ceiling_is_skipped(monkeypatch, tmp_path, caplog):
    relative = MAX_SFX_START_SECONDS + 10
    with caplog.at_level(logging.WARNING, logger="app.services.edit_compiler"):
        _, sfx_files = _sfx_plan(
            [{"type": "sfx", "name": "boom", "time_sec": relative}],
            monkeypatch, tmp_path, clip_start_time=0.0,
        )

    assert sfx_files == []
    assert "skipped" in caplog.text
