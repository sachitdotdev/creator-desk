import logging
import os

log = logging.getLogger(__name__)




def build_audio_filter(
    sfx_events: list,
    music_path=None,
    music_volume: float = 0.25,
    duck: bool = True,
    output_duration: float = 61.0,
    duck_threshold: float = 0.03,
    duck_ratio: int = 8,
    duck_attack: int = 20,
    duck_release: int = 500,
):
    extra_inputs = []
    filters = []
    mix_labels = []


    has_music = bool(music_path) and os.path.exists(music_path)
    need_split = has_music and duck


    if need_split:
        filters.append("[0:a]asplit=2[voice_mix][voice_ctrl]")
    else:
        filters.append("[0:a]anull[voice_mix]")
    mix_labels.append("[voice_mix]")


    sfx_idx = 0
    for ev in sfx_events:
        path = ev.get("path", "")
        if not path or not os.path.exists(path):
            continue
        idx = len(extra_inputs) + 1
        extra_inputs.append(path)
        delay_ms = max(0, int(ev.get("start", 0.0) * 1000))
        label = f"[sfx{sfx_idx}]"
        filters.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume=0.9{label}")
        mix_labels.append(label)
        sfx_idx += 1
        log.info(f"[AUDIO] SFX at {ev.get('start', 0):.2f}s -> {os.path.basename(path)}")


    if has_music:
        idx = len(extra_inputs) + 1
        extra_inputs.append(music_path)
        filters.append(
            f"[{idx}:a]volume={music_volume},"
            f"atrim=0:{output_duration},asetpts=PTS-STARTPTS[music_raw]"
        )
        if duck and need_split:
            filters.append(
                "[music_raw][voice_ctrl]sidechaincompress="
                f"threshold={duck_threshold}:ratio={duck_ratio}:"
                f"attack={duck_attack}:release={duck_release}[music_duck]"
            )
            mix_labels.append("[music_duck]")
            log.info(f"[AUDIO] Music ducked: {os.path.basename(music_path)} @ vol {music_volume}")
        else:
            mix_labels.append("[music_raw]")
            log.info(f"[AUDIO] Music (no duck): {os.path.basename(music_path)} @ vol {music_volume}")


    if len(mix_labels) > 1:
        filters.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
            "duration=first:dropout_transition=0:normalize=0[audio_mix]"
        )
    else:
        filters.append("[voice_mix]anull[audio_mix]")


    filters.append("[audio_mix]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")


    return ";".join(filters), extra_inputs
