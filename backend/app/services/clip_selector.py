"""Whole-video clip selection (single implementation for all callers).

Stage 1 splits the *full* transcript into overlapping windows that fit the
vLLM context and asks the LLM for a few candidate moments per window.
Stage 2 is deterministic: it filters, snaps boundaries to transcript segment
edges, enforces gaps and timeline spread, and picks ``num_clips`` clips.

Both the interactive pipeline (``routes._run_pipeline`` via
``LLMService.generate_clips``) and ``batch_service`` use this module; there is
no second copy of the selection/fallback logic.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any

from app.core.config import (
    CLIP_CANDIDATES_PER_WINDOW,
    CLIP_EDGE_TRIM_SECONDS,
    CLIP_MAX_CONCURRENT_WINDOWS,
    CLIP_MAX_SECONDS,
    CLIP_MIN_GAP_SECONDS,
    CLIP_MIN_SECONDS,
    CLIP_WINDOW_CHARS,
    CLIP_WINDOW_MAX_TOKENS,
    CLIP_WINDOW_OVERLAP,
    LLM_CHARS_PER_TOKEN,
    LLM_MAX_MODEL_LEN,
    LLM_PROMPT_TOKEN_RESERVE,
)

# "format": "json" is kept as the contract of this service. vLLM's
# OpenAI-compatible equivalent is a structured JSON response format; no
# Ollama-only fields (``format``/``keep_alive``) are put on the wire.
JSON_FORMAT = "json"

CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": CLIP_CANDIDATES_PER_WINDOW,
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "score": {"type": "number", "minimum": 1, "maximum": 10},
                    "hook": {"type": "string"},
                },
                "required": ["start", "end", "score", "hook"],
            },
        }
    },
    "required": ["candidates"],
}

SYSTEM_PROMPT = f"""You are a ruthless short-form video editor. Find scroll-stopping moments in the transcript window you are given.

Return ONLY valid JSON (format: {JSON_FORMAT}) matching the requested schema, with at most {CLIP_CANDIDATES_PER_WINDOW} candidates.

Score each candidate from 1 to 10 using this rubric:
- strong first-3-second hook (the opening line grabs attention immediately),
- self-contained without prior context (makes sense on its own),
- emotion, controversy or surprise (not a flat statement),
- clear payoff (something lands or resolves inside the clip).

The "hook" must be exactly 3 to 5 words. Do not copy random nouns; invent a compelling emotional hook.
"start" and "end" are ABSOLUTE timestamps in seconds taken from the bracketed transcript lines and must lie inside the window you were given."""


@dataclass(frozen=True)
class Window:
    index: int
    segments: list[dict[str, Any]]
    text: str
    start: float
    end: float


def _as_float(value: Any) -> float:
    """Parse a numeric (or '12.3s') timestamp from an LLM response."""
    if isinstance(value, bool):
        raise TypeError("boolean is not a timestamp")
    if isinstance(value, str):
        value = value.strip().lower().replace("s", "").strip()
    return float(value)


def _segment_line(seg: dict[str, Any]) -> str:
    return f"[{float(seg['start']):.1f}s - {float(seg['end']):.1f}s] {seg.get('text', '')}"


def normalize_segments(transcript_segments: Any) -> list[dict[str, Any]]:
    """Accept the cached JSON list, a Whisper result dict, or a result object."""
    if transcript_segments is None:
        return []
    if isinstance(transcript_segments, dict):
        raw = transcript_segments.get("segments", [])
    elif hasattr(transcript_segments, "to_dict"):
        raw = transcript_segments.to_dict().get("segments", [])
    else:
        raw = transcript_segments
    out: list[dict[str, Any]] = []
    for seg in raw or []:
        try:
            out.append(
                {
                    "start": float(seg["start"]),
                    "end": float(seg["end"]),
                    "text": str(seg.get("text", "")),
                }
            )
        except (KeyError, TypeError, ValueError):
            # A malformed segment is not a reason to abort the whole video.
            continue
    return sorted(out, key=lambda seg: seg["start"])


def effective_window_chars() -> int:
    """Cap window size so prompt + output fit the real vLLM context window."""
    budget = LLM_MAX_MODEL_LEN - CLIP_WINDOW_MAX_TOKENS - LLM_PROMPT_TOKEN_RESERVE
    if budget <= 0:
        raise ValueError(
            "Invalid clip-selector token budget: "
            f"LLM_MAX_MODEL_LEN={LLM_MAX_MODEL_LEN} - "
            f"CLIP_WINDOW_MAX_TOKENS={CLIP_WINDOW_MAX_TOKENS} - "
            f"LLM_PROMPT_TOKEN_RESERVE={LLM_PROMPT_TOKEN_RESERVE} "
            f"= {budget}; the input budget must be strictly positive."
        )
    return min(CLIP_WINDOW_CHARS, budget * LLM_CHARS_PER_TOKEN)


def build_windows(
    segments: list[dict[str, Any]],
    window_chars: int | None = None,
    overlap: float | None = None,
) -> list[Window]:
    """Split segments into overlapping windows sized for the LLM context.

    Overlap is expressed as a fraction of each window's *segment span* so the
    wording at a window boundary is seen twice and a moment on the seam is not
    missed. A single oversized segment still forms its own window.
    """
    if not segments:
        return []
    budget = window_chars if window_chars is not None else effective_window_chars()
    fraction = overlap if overlap is not None else CLIP_WINDOW_OVERLAP
    fraction = min(max(fraction, 0.0), 0.9)
    lines = [_segment_line(seg) for seg in segments]

    windows: list[Window] = []
    start = 0
    while start < len(segments):
        used = 0
        end = start
        chunk: list[str] = []
        while end < len(segments):
            line = lines[end]
            # Always allow a single (possibly oversized) segment in a window.
            if chunk and used + len(line) + 1 > budget:
                break
            chunk.append(line)
            used += len(line) + 1
            end += 1

        windows.append(
            Window(
                index=len(windows),
                segments=segments[start:end],
                text="\n".join(chunk),
                start=segments[start]["start"],
                end=segments[end - 1]["end"],
            )
        )
        if end >= len(segments):
            break
        span = end - start
        step = max(1, round(span * (1.0 - fraction)))
        start = min(end, start + step)
    return windows


def strip_json_fences(raw: Any) -> str:
    text = str(raw).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_candidate_response(raw: Any) -> list[dict[str, Any]]:
    """Parse window candidates; malformed JSON raises for the caller to log."""
    obj = json.loads(strip_json_fences(raw))
    if isinstance(obj, list):
        payload = obj
    elif isinstance(obj, dict):
        payload = obj.get("candidates", obj.get("clips", []))
    else:
        payload = []
    if not isinstance(payload, list):
        raise TypeError("candidate payload is not a list")

    out: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            start = _as_float(item["start"])
            end = _as_float(item["end"])
            score = _as_float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        hook = str(item.get("hook", "")).strip()
        if start >= end or not (1.0 <= score <= 10.0) or not hook:
            continue
        out.append({"start": start, "end": end, "score": score, "hook": hook})
    return out[:CLIP_CANDIDATES_PER_WINDOW]


async def _ask_window_llm(
    window: Window,
    total_windows: int,
    client: Any,
    model: str,
    custom_prompt: str | None = None,
    vibe: str | None = None,
) -> Any:
    """One windowed LLM request. Returns the raw message content."""
    target = (
        f"Return up to {CLIP_CANDIDATES_PER_WINDOW} candidate moments as JSON "
        f"(absolute seconds inside the window)."
    )
    system_prompt = SYSTEM_PROMPT
    if vibe:
        # Style only shifts the rubric's emphasis; the JSON schema is unchanged.
        system_prompt += (
            f"\nEditorial style: {vibe}. When applying the rubric above, give "
            f"extra weight to moments that fit this style."
        )
        target += f"\nStyle: {vibe}. Prefer moments that fit this style."
    if custom_prompt:
        target += f"\nEditor's extra instruction: {custom_prompt}"
    user_prompt = (
        f"TRANSCRIPT WINDOW {window.index + 1}/{total_windows} "
        f"({window.start:.1f}s - {window.end:.1f}s):\n{window.text}\n\n{target}"
    )
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=CLIP_WINDOW_MAX_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "candidates_response",
                "schema": CANDIDATE_SCHEMA,
            },
        },
    )
    return resp.choices[0].message.content


async def _evaluate_window(
    window: Window,
    total_windows: int,
    client: Any,
    model: str,
    custom_prompt: str | None,
    vibe: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return (candidates, failed). A bad window is logged and skipped."""
    raw: Any = "<no response>"
    try:
        raw = await _ask_window_llm(
            window, total_windows, client, model, custom_prompt, vibe
        )
        candidates = parse_candidate_response(raw)
        print(
            f"[CLIP-SELECT] window={window.index + 1}/{total_windows} "
            f"segments={len(window.segments)} chars={len(window.text)} "
            f"candidates={len(candidates)} status=ok",
            flush=True,
        )
        return candidates, False
    except Exception as exc:  # noqa: BLE001 - one bad window must not abort the video
        print(
            f"[CLIP-SELECT] window={window.index + 1}/{total_windows} FAILED: {exc}",
            flush=True,
        )
        print(f"RAW VLLM OUTPUT (window {window.index + 1}): {raw}", flush=True)
        traceback.print_exc()
        return [], True


def _snap_to_segments(
    start: float, end: float, segments: list[dict[str, Any]]
) -> tuple[float, float] | None:
    """Snap start to a segment start and end to a segment end.

    The result is always within [CLIP_MIN_SECONDS, CLIP_MAX_SECONDS]; returns
    None when the segment grid cannot satisfy those bounds.
    """
    if not segments:
        return None
    snapped_start = min(segments, key=lambda seg: abs(seg["start"] - start))["start"]
    snapped_end = min(segments, key=lambda seg: abs(seg["end"] - end))["end"]
    if snapped_end <= snapped_start:
        later = [seg["end"] for seg in segments if seg["end"] > snapped_start]
        if not later:
            return None
        snapped_end = min(later)

    while snapped_end - snapped_start < CLIP_MIN_SECONDS:
        later = [seg["end"] for seg in segments if seg["end"] > snapped_end]
        if not later:
            return None
        snapped_end = min(later)

    max_end = snapped_start + CLIP_MAX_SECONDS
    if snapped_end > max_end:
        fits = [seg["end"] for seg in segments if snapped_start < seg["end"] <= max_end]
        if not fits or max(fits) - snapped_start < CLIP_MIN_SECONDS:
            return None
        snapped_end = max(fits)
    return round(float(snapped_start), 3), round(float(snapped_end), 3)


def _usable_range(segments: list[dict[str, Any]]) -> tuple[float, float]:
    lo = min(seg["start"] for seg in segments) + CLIP_EDGE_TRIM_SECONDS
    hi = max(seg["end"] for seg in segments) - CLIP_EDGE_TRIM_SECONDS
    return lo, hi


def _clip_within_range(
    start: float,
    end: float,
    segments: list[dict[str, Any]],
    lo: float,
    hi: float,
) -> tuple[float, float] | None:
    """Find a segment-aligned clip inside [lo, hi] closest to (start, end).

    A fixed start only pairs with ends in
    ``[start + CLIP_MIN_SECONDS, start + CLIP_MAX_SECONDS]``, so binary-search
    that interval on the sorted ends instead of scanning the full cross product.
    The pick (and the first-wins tie-breaking) is identical to the brute force.
    """
    valid_starts = sorted({seg["start"] for seg in segments if lo <= seg["start"] <= hi})
    valid_ends = sorted({seg["end"] for seg in segments if lo <= seg["end"] <= hi})
    best: tuple[float, float] | None = None
    best_cost = float("inf")
    for s in valid_starts:
        # Slightly widen the bisect window so float rounding at a bound cannot
        # drop an end the exact duration check would accept, then narrow it
        # back with that same predicate (valid ends form a contiguous range).
        tol = 1e-9 * max(1.0, abs(s), abs(end))
        lo_idx = bisect_left(valid_ends, s + CLIP_MIN_SECONDS - tol)
        hi_idx = bisect_right(valid_ends, s + CLIP_MAX_SECONDS + tol)
        while lo_idx < hi_idx and not (
            CLIP_MIN_SECONDS <= valid_ends[lo_idx] - s <= CLIP_MAX_SECONDS
        ):
            lo_idx += 1
        while hi_idx > lo_idx and not (
            CLIP_MIN_SECONDS <= valid_ends[hi_idx - 1] - s <= CLIP_MAX_SECONDS
        ):
            hi_idx -= 1
        if lo_idx >= hi_idx:
            continue

        # The closest end to the original candidate is next to its insertion
        # point. Check the lower neighbour first so ties pick the smaller end,
        # matching the sorted brute-force scan's first-wins behaviour.
        idx = bisect_left(valid_ends, end, lo_idx, hi_idx)
        chosen: float | None = None
        chosen_dist = float("inf")
        for j in (idx - 1, idx):
            if lo_idx <= j < hi_idx:
                distance = abs(valid_ends[j] - end)
                if distance < chosen_dist:
                    chosen_dist = distance
                    chosen = valid_ends[j]
        if chosen is None:
            continue
        cost = abs(s - start) + chosen_dist
        if cost < best_cost:
            best_cost = cost
            best = (s, chosen)
    return best


def _make_pick(
    start: float, end: float, score: float, hook: str, segments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    snapped = _snap_to_segments(start, end, segments)
    if snapped is None:
        return None
    s, e = snapped
    lo, hi = _usable_range(segments)
    if s < lo or e > hi:
        # Snapping/min-max enforcement can push a boundary past the trimmed
        # range. Re-align to a valid clip inside it, or drop the candidate.
        replacement = _clip_within_range(start, end, segments, lo, hi)
        if replacement is None:
            return None
        s, e = replacement
    return {
        "start": round(float(s), 3),
        "end": round(float(e), 3),
        "score": score,
        "hook": hook,
        "layout": "center_crop",
        "operations": [],
    }


def _gap_compatible(pick: dict[str, Any], picks: list[dict[str, Any]]) -> bool:
    """True when a pick clears the configured gap from every existing pick."""
    return all(
        pick["start"] >= other["end"] + CLIP_MIN_GAP_SECONDS
        or pick["end"] + CLIP_MIN_GAP_SECONDS <= other["start"]
        for other in picks
    )


def select_picks(
    candidates: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    num_clips: int,
) -> list[dict[str, Any]]:
    """Deterministic stage 2: filter, rank, spread and snap picks."""
    if not segments or num_clips <= 0:
        return []
    lo, hi = _usable_range(segments)
    if hi <= lo:
        return []

    valid: list[dict[str, Any]] = []
    for candidate in candidates:
        start, end = candidate["start"], candidate["end"]
        if start < lo or end > hi or start >= end:
            continue
        pick = _make_pick(start, end, candidate["score"], candidate["hook"], segments)
        if pick is not None:
            valid.append(pick)
    valid.sort(key=lambda pick: (-pick["score"], pick["start"]))

    buckets = max(1, num_clips)
    bucket_size = (hi - lo) / buckets
    used_buckets: set[int] = set()
    picks: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    def bucket_of(pick: dict[str, Any]) -> int:
        return min(buckets - 1, max(0, int((pick["start"] - lo) / bucket_size)))

    # At most one pick per equal-sized time bucket until all buckets are used.
    for pick in valid:
        if len(picks) >= num_clips:
            break
        bucket = bucket_of(pick)
        if bucket in used_buckets or not _gap_compatible(pick, picks):
            deferred.append(pick)
            continue
        picks.append(pick)
        used_buckets.add(bucket)

    # Buckets exhausted: fill remaining slots by score, still gap-safe.
    for pick in deferred:
        if len(picks) >= num_clips:
            break
        if _gap_compatible(pick, picks):
            picks.append(pick)

    return sorted(picks, key=lambda pick: pick["start"])


def even_spaced_picks(
    segments: list[dict[str, Any]], num_clips: int
) -> list[dict[str, Any]]:
    """Loud fallback: evenly spaced clips across the *whole* video."""
    if not segments or num_clips <= 0:
        return []
    lo, hi = _usable_range(segments)
    if hi <= lo:
        return []
    step = (hi - lo) / num_clips
    picks: list[dict[str, Any]] = []
    for index in range(num_clips):
        target_start = lo + index * step
        target_end = min(hi, target_start + max(CLIP_MIN_SECONDS, min(step, CLIP_MAX_SECONDS)))
        pick = _make_pick(target_start, target_end, 0.0, "Worth a watch", segments)
        if pick is not None and _gap_compatible(pick, picks):
            picks.append(pick)
            continue
        # Sparse segment grids can snap two slots to the same place; walk
        # forward to the next segment start instead of dropping a clip. The
        # retry must clear the same gap/overlap check as any other pick.
        later = [seg for seg in segments if seg["start"] > target_start + CLIP_MIN_SECONDS]
        if later:
            next_start = min(later, key=lambda seg: seg["start"])["start"]
            retry = _make_pick(
                next_start, next_start + CLIP_MAX_SECONDS, 0.0, "Worth a watch", segments
            )
            if retry is not None and _gap_compatible(retry, picks):
                picks.append(retry)
    if len(picks) < num_clips:
        print(
            "[CLIP-SELECT] fallback timeline cannot satisfy "
            f"{CLIP_MIN_GAP_SECONDS:g}s gap for {num_clips} clips; "
            f"returning {len(picks)}.",
            flush=True,
        )
    return picks[:num_clips]


async def generate_clips(
    transcript_segments: list[dict[str, Any]],
    num_clips: int = 5,
    vibe: str = "Streamer Hype",
    custom_prompt: str | None = None,
    *,
    client: Any = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """Public entry point: select clips from the whole transcript.

    Signature-compatible with the old ``LLMService.generate_clips``; the
    optional keyword-only args let callers/tests inject the LLM client.
    """
    started = time.perf_counter()
    segments = normalize_segments(transcript_segments)
    if not segments or num_clips <= 0:
        print(
            "[CLIP-SELECT] summary tokens_est=0 windows=0 failed=0 candidates=0 "
            f"picks=[] elapsed_s={time.perf_counter() - started:.2f}",
            flush=True,
        )
        return []

    windows = build_windows(segments)
    tokens_estimate = sum(len(line) for seg in segments for line in [_segment_line(seg)]) // LLM_CHARS_PER_TOKEN

    if client is None:  # lazy import avoids a circular import with llm_service
        from app.services.llm_service import client as default_client

        client = default_client
    llm_model = model or "meissa-7b-awq"

    semaphore = asyncio.Semaphore(CLIP_MAX_CONCURRENT_WINDOWS)

    async def run_window(window: Window) -> tuple[list[dict[str, Any]], bool]:
        async with semaphore:
            return await _evaluate_window(
                window, len(windows), client, llm_model, custom_prompt, vibe
            )

    results = await asyncio.gather(*(run_window(window) for window in windows))
    candidates = [candidate for found, _ in results for candidate in found]
    failures = sum(1 for _, failed in results if failed)

    if failures == len(windows):
        print(
            "[CLIP-SELECT] WARNING: ALL WINDOWS FAILED - using evenly-spaced "
            "whole-video fallback (no clip was invented from a bad window).",
            flush=True,
        )
        picks = even_spaced_picks(segments, num_clips)
        used_fallback = True
    else:
        picks = select_picks(candidates, segments, num_clips)
        used_fallback = False

    starts = ", ".join(f"{pick['start']:.1f}" for pick in picks)
    print(
        f"[CLIP-SELECT] summary tokens_est={tokens_estimate} "
        f"windows={len(windows)} failed={failures} candidates={len(candidates)} "
        f"fallback={used_fallback} picks=[{starts}] "
        f"elapsed_s={time.perf_counter() - started:.2f}",
        flush=True,
    )
    return picks
