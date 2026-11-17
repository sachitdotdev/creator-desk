import logging
import math
import os

log = logging.getLogger(__name__)

# Default SFX layer gain. Kept under 1.0 so effects sit beneath the voice; the
# voice itself is never attenuated because the final amix runs with normalize=0.
DEFAULT_SFX_VOLUME = 0.9

# Phase 3.2 - music ducking defaults (sidechaincompress keyed by the voice).
DEFAULT_DUCK_THRESHOLD = 0.05
DEFAULT_DUCK_RATIO = 8
DEFAULT_DUCK_ATTACK = 20     # ms
DEFAULT_DUCK_RELEASE = 400   # ms

# Phase 3.5 - inline loudnorm used when the caller does not run the two-pass
# loudness pass afterwards.
DEFAULT_LOUDNORM = "I=-14:TP=-1.5:LRA=11"

# Safety ceiling applied to summed layers when inline loudnorm is disabled.
# amix runs with normalize=0 so overlapping SFX/BGM peaks can exceed 0 dBFS;
# the limiter keeps the mix below full scale before AAC encoding.
DEFAULT_MIX_LIMIT = 0.95


def _as_volume(value, default: float = DEFAULT_SFX_VOLUME) -> float:
    """Coerce an SFX event volume to a safe linear gain.

    Accepts numbers or numeric strings; values above 2 are treated as a 0-100
    percentage (local LLMs sometimes emit "50"). Falls back to ``default`` for
    anything unusable and clamps the result to 0.0-1.0.
    """
    try:
        vol = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(vol):
        return default
    if vol > 2.0:
        vol = vol / 100.0
    return min(max(vol, 0.0), 1.0)


def build_audio_filter(
    sfx_events: list,
    music_path=None,
    music_volume: float = 0.25,
    duck: bool = True,
    output_duration: float = 61.0,
    duck_threshold: float = DEFAULT_DUCK_THRESHOLD,
    duck_ratio: float = DEFAULT_DUCK_RATIO,
    duck_attack: int = DEFAULT_DUCK_ATTACK,
    duck_release: int = DEFAULT_DUCK_RELEASE,
    inline_loudnorm: bool = True,
):
    """Build the audio filtergraph for a clip.

    Fixed chain order:
      1. split the voice (only needed when a BGM track must be ducked),
      2. layer every SFX event with ``adelay`` (``amix`` keeps ``normalize=0``,
         so layering an effect never lowers the voice level),
      3. duck the BGM against the voice with ``sidechaincompress``,
      4. sum every layer,
      5. normalize loudness last - inline here, or skipped when the caller runs
         the two-pass ``loudnorm`` pass afterwards (``inline_loudnorm=False``).

    When the two-pass pass runs (``inline_loudnorm=False``) a summed mix gets
    an ``alimiter`` ceiling after ``amix`` so overlapping layers cannot clip.

    The BGM is looped before ``atrim`` so tracks shorter than the clip still
    cover its full duration.

    Without SFX events and without a BGM track the graph is a plain ``anull``
    passthrough (plus the inline loudnorm), i.e. unchanged from the
    pre-Phase-3 behavior.
    """
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
    for ev in sfx_events or []:
        if not isinstance(ev, dict):
            log.warning("[AUDIO] SFX skipped: event is not a dict (%r)", ev)
            continue
        path = ev.get("path") or ""
        if not path or not os.path.exists(path):
            # A missing SFX file must never abort the render.
            log.warning(
                "[AUDIO] SFX skipped: file not found (path=%r name=%r)",
                path, ev.get("name") or ev.get("file"),
            )
            continue
        try:
            start = float(ev.get("start", 0.0))
        except (TypeError, ValueError):
            log.warning("[AUDIO] SFX skipped: invalid start=%r", ev.get("start"))
            continue
        idx = len(extra_inputs) + 1
        extra_inputs.append(path)
        delay_ms = max(0, round(start * 1000))
        volume = _as_volume(ev.get("volume"))
        label = f"[sfx{sfx_idx}]"
        filters.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume={volume:g}{label}")
        mix_labels.append(label)
        sfx_idx += 1
        log.info("[AUDIO] SFX at %.2fs vol=%.2f -> %s", start, volume, os.path.basename(path))


    if has_music:
        idx = len(extra_inputs) + 1
        extra_inputs.append(music_path)
        filters.append(
            f"[{idx}:a]volume={float(music_volume):g},"
            # Loop first: a BGM track shorter than the clip must still cover the
            # full duration, and swapping it out for silence is never desirable.
            f"aloop=loop=-1:size=2e+09,"
            f"atrim=0:{output_duration},asetpts=PTS-STARTPTS[music_raw]"
        )
        if duck and need_split:
            # sidechaincompress: the voice controls how hard the music is
            # ducked, so BGM never fights the spoken word.
            filters.append(
                "[music_raw][voice_ctrl]sidechaincompress="
                f"threshold={float(duck_threshold):g}:ratio={float(duck_ratio):g}:"
                f"attack={int(duck_attack)}:release={int(duck_release)}[music_duck]"
            )
            mix_labels.append("[music_duck]")
            log.info(
                "[AUDIO] Music ducked: %s @ vol %.2f (threshold=%s ratio=%s attack=%sms release=%sms)",
                os.path.basename(music_path), float(music_volume),
                float(duck_threshold), float(duck_ratio), int(duck_attack), int(duck_release),
            )
        else:
            mix_labels.append("[music_raw]")
            log.info("[AUDIO] Music (no duck): %s @ vol %.2f", os.path.basename(music_path), float(music_volume))


    if len(mix_labels) > 1:
        filters.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
            "duration=first:dropout_transition=0:normalize=0[audio_mix]"
        )
    else:
        filters.append("[voice_mix]anull[audio_mix]")


    # Loudness normalization is always the final stage of the graph. When the
    # caller runs the two-pass EBU R128 pass after the render, keep a neutral
    # passthrough here so the audio is normalized exactly once.
    if inline_loudnorm:
        filters.append(f"[audio_mix]loudnorm={DEFAULT_LOUDNORM}[aout]")
    elif len(mix_labels) > 1:
        # No loudnorm here means the caller normalizes afterwards, but the
        # summed mix still has to stay below 0 dBFS. Guard it with a limiter.
        filters.append(
            f"[audio_mix]alimiter=limit={DEFAULT_MIX_LIMIT:g}[aout]"
        )
    else:
        # Passthrough must stay byte-identical for the no-SFX/no-BGM case.
        filters.append("[audio_mix]anull[aout]")


    return ";".join(filters), extra_inputs
