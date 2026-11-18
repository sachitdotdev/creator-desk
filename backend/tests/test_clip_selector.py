"""Whole-video clip selection: deterministic stage 2 + mocked LLM stage 1."""
from __future__ import annotations

import asyncio
import itertools
import json
from types import SimpleNamespace

import pytest

from app.services import clip_selector


def segments_for_seconds(total: float, step: float = 30.0) -> list[dict]:
    """Segments with text short enough that many fit in a small test window."""
    out = []
    index = 0
    start = 0.0
    while start < total:
        out.append(
            {
                "start": start,
                "end": start + step,
                "text": f"moment {index} of the story",
            }
        )
        index += 1
        start += step
    return out


def candidate_json(candidates: list[dict]) -> str:
    return json.dumps({"candidates": candidates})


def test_effective_window_chars_respects_llm_context(monkeypatch):
    monkeypatch.setattr(clip_selector, "CLIP_WINDOW_CHARS", 6000)
    monkeypatch.setattr(clip_selector, "LLM_MAX_MODEL_LEN", 4096)
    monkeypatch.setattr(clip_selector, "CLIP_WINDOW_MAX_TOKENS", 800)
    monkeypatch.setattr(clip_selector, "LLM_PROMPT_TOKEN_RESERVE", 400)
    monkeypatch.setattr(clip_selector, "LLM_CHARS_PER_TOKEN", 4)
    assert clip_selector.effective_window_chars() == 6000

    # A smaller context must shrink the window, never overflow it.
    monkeypatch.setattr(clip_selector, "LLM_MAX_MODEL_LEN", 1600)
    budget = clip_selector.effective_window_chars()
    assert budget < 6000
    windows = clip_selector.build_windows(segments_for_seconds(900), window_chars=budget)
    assert windows
    assert all(len(window.text) <= budget for window in windows)


def test_window_count_and_overlap_are_correct():
    segs = segments_for_seconds(300, step=30.0)  # 10 segments
    max_line_len = max(len(clip_selector._segment_line(seg)) for seg in segs)
    windows = clip_selector.build_windows(
        segs, window_chars=4 * (max_line_len + 1), overlap=0.5
    )
    # Each window holds 4 segments and steps by 2 -> 4 windows (no trailing
    # duplicate window once the last one reaches the end of the transcript).
    assert len(windows) == 4
    for first, second in itertools.pairwise(windows):
        shared = [s["start"] for s in first.segments if s in second.segments]
        assert shared == [s["start"] for s in first.segments[-2:]]
        assert second.start < first.end
    # Every segment is seen at least once.
    covered = {s["start"] for w in windows for s in w.segments}
    assert covered == {s["start"] for s in segs}


def test_mocked_llm_picks_are_spread_and_boundaries_are_segment_edges(monkeypatch):
    segs = segments_for_seconds(5400.0)  # 90 minutes, 180 segments
    monkeypatch.setattr(clip_selector, "CLIP_WINDOW_CHARS", 600)
    seg_starts = {s["start"] for s in segs}
    seg_ends = {s["end"] for s in segs}

    async def fake_llm(window, total_windows, client, model, custom_prompt=None, vibe=None):
        # Equal scores everywhere: only the bucket rule can spread the picks.
        candidates = [
            {"start": window.start + 60.0, "end": window.start + 105.0, "score": 5, "hook": "first big moment"},
            {"start": window.start + 300.0, "end": window.start + 345.0, "score": 5, "hook": "second big moment"},
        ]
        return candidate_json(candidates)

    monkeypatch.setattr(clip_selector, "_ask_window_llm", fake_llm)
    picks = asyncio.run(
        clip_selector.generate_clips(segs, num_clips=5, client=object(), model="test")
    )

    assert len(picks) == 5
    starts = [p["start"] for p in picks]
    assert starts == sorted(starts)
    for first, second in itertools.pairwise(picks):
        assert first["end"] <= second["start"]  # no overlap
        assert second["start"] - first["end"] >= clip_selector.CLIP_MIN_GAP_SECONDS
    assert sum(1 for p in picks if p["start"] < 600.0) <= 1  # first 10 minutes
    assert max(starts) > 3600.0  # spans well beyond the first hour-mark
    for pick in picks:
        assert pick["start"] in seg_starts
        assert pick["end"] in seg_ends
        assert clip_selector.CLIP_MIN_SECONDS <= pick["end"] - pick["start"] <= clip_selector.CLIP_MAX_SECONDS


def test_failing_window_is_skipped_without_aborting(monkeypatch, capsys):
    segs = segments_for_seconds(1800.0)
    monkeypatch.setattr(clip_selector, "CLIP_WINDOW_CHARS", 600)

    async def fake_llm(window, total_windows, client, model, custom_prompt=None, vibe=None):
        if window.index == 1:
            raise RuntimeError("vLLM returned garbage for this window")
        return candidate_json(
            [{"start": window.start + 30.0, "end": window.start + 75.0, "score": 8, "hook": "good moment here"}]
        )

    monkeypatch.setattr(clip_selector, "_ask_window_llm", fake_llm)
    picks = asyncio.run(
        clip_selector.generate_clips(segs, num_clips=3, client=object(), model="test")
    )
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "RAW VLLM OUTPUT" in out
    assert picks  # the other windows still produced clips


def test_all_windows_failing_uses_whole_video_fallback(monkeypatch, capsys):
    segs = segments_for_seconds(5400.0)
    monkeypatch.setattr(clip_selector, "CLIP_WINDOW_CHARS", 600)

    async def fake_llm(window, total_windows, client, model, custom_prompt=None, vibe=None):
        raise RuntimeError("vLLM down")

    monkeypatch.setattr(clip_selector, "_ask_window_llm", fake_llm)
    picks = asyncio.run(
        clip_selector.generate_clips(segs, num_clips=5, client=object(), model="test")
    )
    out = capsys.readouterr().out
    assert "ALL WINDOWS FAILED" in out
    assert "evenly-spaced" in out
    assert len(picks) == 5
    assert max(p["start"] for p in picks) > 3600.0
    for first, second in itertools.pairwise(picks):
        assert first["end"] <= second["start"]


def test_fenced_and_malformed_json():
    fenced = "```json\n" + candidate_json(
        [{"start": 10, "end": 70, "score": 9, "hook": "a great hook"}]
    ) + "\n```"
    assert clip_selector.parse_candidate_response(fenced)[0]["start"] == 10
    assert clip_selector.parse_candidate_response(
        '{"clips": [{"start": "12s", "end": "70s", "score": 7, "hook": "wow"}]}'
    )[0]["start"] == 12
    with pytest.raises(json.JSONDecodeError):
        clip_selector.parse_candidate_response("```json\n{not json}\n```")


def test_effective_window_chars_rejects_non_positive_budget(monkeypatch):
    original = clip_selector.LLM_MAX_MODEL_LEN
    monkeypatch.setattr(clip_selector, "LLM_MAX_MODEL_LEN", 800)
    with pytest.raises(ValueError, match="budget|positive"):
        clip_selector.effective_window_chars()

    # The default configuration still yields a usable input window.
    monkeypatch.setattr(clip_selector, "LLM_MAX_MODEL_LEN", original)
    assert clip_selector.effective_window_chars() > 0


def test_snapped_pick_stays_inside_usable_range():
    segs = segments_for_seconds(300, step=20.0)  # 20-second segments over 300 s
    lo, hi = clip_selector._usable_range(segs)
    assert hi == 270.0

    pick = clip_selector._make_pick(240.0, 265.0, 8.0, "great hook", segs)
    assert pick is not None
    assert lo <= pick["start"] < pick["end"] <= hi
    assert pick["end"] <= 270.0
    assert pick["start"] in {s["start"] for s in segs}
    assert pick["end"] in {s["end"] for s in segs}
    assert (
        clip_selector.CLIP_MIN_SECONDS
        <= pick["end"] - pick["start"]
        <= clip_selector.CLIP_MAX_SECONDS
    )


def test_fallback_retries_respect_gap_and_return_fewer_clips(capsys):
    segs = segments_for_seconds(300, step=30.0)  # 30-second segments over 300 s
    picks = clip_selector.even_spaced_picks(segs, num_clips=5)

    # The timeline cannot fit 5 clips with the configured gap.
    assert len(picks) < 5
    for first, second in itertools.pairwise(picks):
        assert first["end"] <= second["start"]  # never overlap
        assert second["start"] - first["end"] >= clip_selector.CLIP_MIN_GAP_SECONDS
    assert "gap" in capsys.readouterr().out


def test_vibe_shapes_the_window_prompt(monkeypatch):
    captured: list[dict] = []

    class _Completions:
        async def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=candidate_json([]))
                    )
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    segs = segments_for_seconds(120)  # a single transcript window

    asyncio.run(
        clip_selector.generate_clips(
            segs, num_clips=2, vibe="Chill Lo-fi", client=client, model="test"
        )
    )
    assert captured
    first_messages = json.dumps(captured[0]["messages"])
    assert "Chill Lo-fi" in first_messages
    assert "Prefer moments that fit this style" in first_messages

    captured.clear()
    asyncio.run(
        clip_selector.generate_clips(
            segs, num_clips=2, vibe="Hype Rant", client=client, model="test"
        )
    )
    assert captured
    second_messages = json.dumps(captured[0]["messages"])
    assert "Hype Rant" in second_messages
    assert first_messages != second_messages

    # The default vibe keeps working with the unchanged public signature.
    captured.clear()
    asyncio.run(
        clip_selector.generate_clips(segs, num_clips=2, client=client, model="test")
    )
    assert captured
    assert "Streamer Hype" in json.dumps(captured[0]["messages"])
