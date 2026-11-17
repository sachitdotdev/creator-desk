import os
import textwrap

FONT_PATH = "C\\:/Windows/Fonts/impact.ttf"
SFX_DIR = "C:/Projects Openhands/Active/Creator Desk/backend/assets/sfx"

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
        base = f"[0:v]scale=-1:1920[scaled];color=black:s=1080x1920[bg];[scaled]sendcmd=f='{sendcmd_path}'[scaled_cmd];[bg][scaled_cmd]overlay=x=0:y=0:shortest=1[vstack]"
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
                sfx_name = op.get("name", "").lower()
                sfx_path = f"{SFX_DIR}/{sfx_name}.mp3"
                if not os.path.exists(sfx_path):
                    sfx_path = f"{SFX_DIR}/boom.mp3"
                if os.path.exists(sfx_path):
                    sfx_files.append({"path": sfx_path, "start": rel_start})
    
    # 3. Burn ASS Captions
    if current_video == "[vstack]":
        filters.append(f"[vstack]ass='{ass_filename}'[out_final]")
    else:
        filters.append(f"{current_video}ass='{ass_filename}'[out_final]")
    
    return ";".join(filters), sfx_files