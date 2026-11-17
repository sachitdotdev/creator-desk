"""Phase 3.3 - Short hooks: unit tests for hook/caption text post-processing."""

from app.services.edit_compiler import compile_plan, truncate_hook_text


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
