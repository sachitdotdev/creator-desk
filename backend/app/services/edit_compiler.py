import logging
import math
import re
import textwrap
from pathlib import Path

from app.core.config import AUDIO_SFX_VOLUME
from app.core.paths import SFX_DIR

log = logging.getLogger(__name__)

FONT_PATH = "C\\:/Windows/Fonts/impact.ttf"
_SFX_EXTENSIONS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
# A sane ceiling for an SFX's CLIP-RELATIVE delay: beyond this the LLM output
# is junk (overflowing floats) and the event is skipped. Absolute source
# timestamps can legitimately be much larger than this (e.g. a clip cut from
# hour 2 of a stream), so the ceiling applies after subtracting clip_start.
MAX_SFX_START_SECONDS = 3600.0

_SENDCMD_RE = re.compile(r"^\s*[\d.]+\s+overlay\s+x\s+(-?[\d.]+)")


def first_sendcmd_overlay_x(sendcmd_path: str) -> str:
    """Return the overlay x of the first sendcmd command (e.g. ``-981.32``).

    The FFmpeg ``sendcmd`` filter does not reliably apply a command whose
    timestamp equals the first frame's timestamp, so the filtergraph seeds the
    initial overlay position from this first command instead of relying on the
    sendcmd queue alone. Returns ``"0"`` when the file is missing/unparseable.
    """
    try:
        text = Path(sendcmd_path).read_text(encoding="utf-8")
    except OSError:
        return "0"
    for line in text.splitlines():
        match = _SENDCMD_RE.match(line)
        if match:
            return match.group(1)
    return "0"


def resolve_sfx_path(op: dict) -> str | None:
    """Resolve an ``sfx`` operation to an existing file under ``paths.SFX_DIR``.

    The operation schema is extended, never replaced: ``file`` and ``name`` are
    both accepted (``name`` is the bare effect name, ``file`` may carry an
    extension). Only the final file name is ever honoured: absolute and UNC
    values are reduced to their basename so a plan can never read a file from
    outside the SFX folder. Returns ``None`` when the effect cannot be found -
    callers log a warning and skip the event.
    """
    raw = str(op.get("file") or op.get("name") or "").strip()
    if not raw:
        return None

    # Normalize Windows separators first so ``Path(...).name`` also yields the
    # bare file name on POSIX: Path(r"C:\x\boom.mp3").name -> "boom.mp3".
    # Confine every value to SFX_DIR, whatever form it arrived in.
    name = Path(raw.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        log.warning("[SFX] rejected empty/invalid file name: %r", raw)
        return None
    if not name.lower().endswith(_SFX_EXTENSIONS):
        name = f"{name}.mp3"

    sfx_dir = Path(SFX_DIR)
    path = sfx_dir / name
    try:
        resolved_dir = sfx_dir.resolve()
        resolved = path.resolve()
    except OSError:
        log.warning("[SFX] rejected unresolvable path: %r", raw)
        return None
    if resolved_dir != resolved and resolved_dir not in resolved.parents:
        log.warning("[SFX] rejected path outside SFX_DIR: %r", raw)
        return None
    return str(path) if resolved.is_file() else None

# Phase 3.3 - Short hooks: Meissa-generated caption/hook text is truncated to a
# punchy 3-5 word hook before the edit plan is compiled into the FFmpeg graph.
HOOK_MAX_WORDS = 5
_HOOK_FILLER_WORDS = {
    "um", "uh", "erm", "uhh", "hmm", "like", "literally", "actually",
    "really", "just", "simply", "sort", "kinda", "well", "so",
}


def truncate_hook_text(text: str, max_words: int = HOOK_MAX_WORDS) -> str:
    """Post-process LLM hook/caption text into a short, punchy 3-5 word hook.

    Drops filler words, keeps the most meaningful words and caps the result at
    ``max_words`` (3-5 words for short hooks). Original casing and punctuation
    are preserved. Returns "" for empty/whitespace-only input.
    """
    if not text or not str(text).strip():
        return ""
    cleaned = str(text).strip().strip("*").strip("`").strip()
    if not cleaned:
        return ""
    kept_words = []
    for word in cleaned.split():
        key = word.strip(".,!?;:'()[]{}*-<>").lower()
        if not key or key in _HOOK_FILLER_WORDS:
            continue
        kept_words.append(word)
        if len(kept_words) >= max_words:
            break
    return " ".join(kept_words).strip()


def compile_plan(
    operations: list,
    layout: str,
    ass_filename: str,
    clip_start_time: float = 0.0,
    sendcmd_path: str = "",
    template_config: dict | None = None,
) -> tuple:
    if template_config is None:
        template_config = {}
    
    # Extract template config
    caption_cfg = template_config.get("caption", {})
    animation_type = template_config.get("text_animation", "spring_bounce")
    
    font_name = caption_cfg.get("font", "Impact")
    if "Montserrat" in font_name:
        font_path = "C\\:/Windows/Fonts/arialbd.ttf"
    elif "Arial" in font_name:
        font_path = "C\\:/Windows/Fonts/arial.ttf"
    else:
        font_path = "C\\:/Windows/Fonts/impact.ttf"
    
    text_color = "yellow"
    if caption_cfg.get("primary") == "&H00FFFFFF&":
        text_color = "white"
    
    font_size = caption_cfg.get("size", 75)
    
    filters = []
    sfx_files = []
    
    # 1. Base Layout
    if layout == "center_crop":
        # The overlay's MAIN input must be the video stream itself ([0:v] split
        # -> main + overlay). A generated colour source as the overlay main makes
        # the first composited frame come out black (verified with ffmpeg: frame 0
        # of the composite is black with a colour source main, real content with a
        # video main). The crop itself is applied by the sendcmd overlay x below;
        # the filtergraph seeds the initial overlay x from the first sendcmd
        # position because sendcmd does not reliably apply a t=0 command to frame 0.
        initial_overlay_x = first_sendcmd_overlay_x(sendcmd_path)
        base = f"[0:v]split=2[a][b];[a]scale=-1:1920[main];[b]scale=-1:1920[ov];[main][ov]overlay=x={initial_overlay_x}:y=0:shortest=1[ovl];[ovl]sendcmd=f='{sendcmd_path}'[vstack]"
    else:
        base = "[0:v]split=2[v1][v2];[v1]crop=iw:ih/2:0:0,scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[top];[v2]crop=iw:ih/2:0:ih/2,scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[bottom];[top][bottom]vstack=inputs=2[vstack]"
    
    filters.append(base)
    
    current_video = "[vstack]"
    if operations:
        for i, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_type = op.get("type")
            
            rel_start = max(0.0, op.get("start", 0.0) - clip_start_time)
            rel_end = max(rel_start + 0.5, op.get("end", 0.0) - clip_start_time)
            
            if op_type == "text":
                text = truncate_hook_text(op.get("text", ""))
                text = text.replace("'", "").replace(":", "").replace("[", "").replace("]", "").replace(",", "")
                wrapped_text = "\\n".join(textwrap.wrap(text, width=20))
                out_label = f"[v{i}]" if i < len(operations) - 1 else "[vout]"
                
                rel_end = max(rel_start + 5.0, rel_end)
                
                # Defaults (safety net for all animation types)
                y_expr = "h*0.1"
                alpha_expr = "1"
                
                if animation_type == "spring_bounce":
                    fade_end = rel_start + 0.2
                    alpha_expr = f"if(lt(t,{fade_end}),(t-{rel_start})/0.2,1)"
                    y_expr = f"if(lt(t,{rel_start}),-100, h*0.1 - 60*exp(-8*(t-{rel_start}))*sin(25*(t-{rel_start})))"
                elif animation_type == "fade_in":
                    fade_end = rel_start + 0.5
                    alpha_expr = f"if(lt(t,{fade_end}),(t-{rel_start})/0.5,1)"
                
                drawtext = f"drawtext=fontfile='{font_path}':text='{wrapped_text}':x=(w-text_w)/2:y='{y_expr}':fontsize={font_size}:fontcolor={text_color}:box=1:boxcolor=black@0.8:alpha='{alpha_expr}':enable='between(t,{rel_start},{rel_end})'"
                filters.append(f"{current_video}{drawtext}{out_label}")
                current_video = out_label
            
            elif op_type == "sfx":
                sfx_path = resolve_sfx_path(op)
                if not sfx_path:
                    # Missing effect files are skipped, never fatal.
                    log.warning(
                        "[SFX] skipped: file not found (name=%r file=%r)",
                        op.get("name"), op.get("file"),
                    )
                    continue
                raw_time = op.get("time_sec")
                if raw_time is None:
                    raw_time = op.get("start", rel_start + clip_start_time)
                try:
                    event_time = float(str(raw_time).strip().rstrip("s"))
                    # Non-finite source timestamps are always junk.
                    if not math.isfinite(event_time):
                        raise ValueError(f"non-finite time_sec/start: {event_time!r}")
                    # The ceiling applies to the CLIP-RELATIVE delay, not to the
                    # absolute source timestamp: a clip cut from hour 2 of a
                    # stream can legitimately contain an SFX at 7202s that must
                    # play 2s into the clip. Reject non-finite/over-ceiling
                    # delays; a negative delay is still clamped to 0 below.
                    rel_delay = event_time - clip_start_time
                    if not math.isfinite(rel_delay) or rel_delay > MAX_SFX_START_SECONDS:
                        raise ValueError(f"out-of-range clip-relative delay: {rel_delay!r}")
                except (TypeError, ValueError):
                    log.warning("[SFX] skipped: invalid time_sec/start=%r", raw_time)
                    continue
                sfx_files.append({
                    "path": sfx_path,
                    "name": op.get("name") or Path(sfx_path).stem,
                    "start": max(0.0, rel_delay),
                    "volume": op.get("volume", AUDIO_SFX_VOLUME),
                })
                log.info(
                    "[SFX] %s at %.2fs (clip-relative %.2fs, vol=%s)",
                    Path(sfx_path).name, event_time,
                    max(0.0, rel_delay),
                    op.get("volume", AUDIO_SFX_VOLUME),
                )
    
    # 3. Burn ASS Captions
    if current_video == "[vstack]":
        filters.append(f"[vstack]ass='{ass_filename}'[out_final]")
    else:
        filters.append(f"{current_video}ass='{ass_filename}'[out_final]")
    
    return ";".join(filters), sfx_files