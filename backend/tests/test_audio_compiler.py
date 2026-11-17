"""Phase 3.1/3.2 - SFX insertion + BGM ducking: filtergraph and real-FFmpeg tests."""

import logging
import subprocess

import numpy as np
import pytest

from app.core.config import (
    AUDIO_DUCK_ATTACK,
    AUDIO_DUCK_RATIO,
    AUDIO_DUCK_RELEASE,
    AUDIO_DUCK_THRESHOLD,
    AUDIO_SFX_VOLUME,
    FFMPEG_PATH,
)
from app.core.processing_utils import run_subprocess
from app.services import audio_compiler, edit_compiler
from app.services.audio_compiler import build_audio_filter
from app.services.audio_loudness import is_ffmpeg_available

SAMPLE_RATE = 44100
VOICE_HZ = 440.0   # "speech" proxy tone
MUSIC_HZ = 220.0   # BGM bed tone

SILENT_GRAPH = "[0:a]anull[voice_mix];[voice_mix]anull[audio_mix]"
LOUDNORM_TAIL = "[audio_mix]loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
NO_LOUDNORM_TAIL = "[audio_mix]anull[aout]"


def _make_file(path, payload=b"\x00"):
    path.write_bytes(payload)
    return str(path)


@pytest.fixture
def sfx_path(tmp_path):
    return _make_file(tmp_path / "boom.mp3")


@pytest.fixture
def music_path(tmp_path):
    return _make_file(tmp_path / "lofi.mp3")


# --------------------------------------------------------------- filtergraph
def test_no_sfx_no_bgm_is_unchanged_passthrough():
    graph, extra_inputs = build_audio_filter(sfx_events=[])

    assert extra_inputs == []
    assert graph == f"{SILENT_GRAPH};{LOUDNORM_TAIL}"


def test_sfx_only_layers_with_adelay_and_amix_normalize_0(sfx_path):
    events = [{"path": sfx_path, "start": 1.5, "volume": 0.6}]

    graph, extra_inputs = build_audio_filter(sfx_events=events)

    assert extra_inputs == [sfx_path]
    assert graph == (
        "[0:a]anull[voice_mix];"
        "[1:a]adelay=1500|1500,volume=0.6[sfx0];"
        "[voice_mix][sfx0]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[audio_mix];"
        f"{LOUDNORM_TAIL}"
    )
    # No BGM present -> no ducking / no sidechain compressor at all.
    assert "sidechaincompress" not in graph
    assert "asplit" not in graph
    # The voice is never attenuated when effects are layered on top of it.
    assert "normalize=0" in graph


def test_bgm_only_ducks_music_against_voice(music_path):
    graph, extra_inputs = build_audio_filter(sfx_events=[], music_path=music_path)

    assert extra_inputs == [music_path]
    assert graph == (
        "[0:a]asplit=2[voice_mix][voice_ctrl];"
        "[1:a]volume=0.25,atrim=0:61.0,asetpts=PTS-STARTPTS[music_raw];"
        "[music_raw][voice_ctrl]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[music_duck];"
        "[voice_mix][music_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[audio_mix];"
        f"{LOUDNORM_TAIL}"
    )
    assert "adelay" not in graph


def test_sfx_and_bgm_chain_order(sfx_path, music_path):
    events = [{"path": sfx_path, "start": 1.5, "volume": 0.6}]

    graph, extra_inputs = build_audio_filter(sfx_events=events, music_path=music_path)

    assert extra_inputs == [sfx_path, music_path]
    assert graph == (
        "[0:a]asplit=2[voice_mix][voice_ctrl];"
        "[1:a]adelay=1500|1500,volume=0.6[sfx0];"
        "[2:a]volume=0.25,atrim=0:61.0,asetpts=PTS-STARTPTS[music_raw];"
        "[music_raw][voice_ctrl]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400[music_duck];"
        "[voice_mix][sfx0][music_duck]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[audio_mix];"
        f"{LOUDNORM_TAIL}"
    )
    # Graph order: SFX layer -> duck BGM against voice -> sum -> loudnorm last.
    assert graph.index("adelay") < graph.index("sidechaincompress")
    assert graph.index("sidechaincompress") < graph.index("amix=")
    assert graph.index("amix=") < graph.index("loudnorm")


def test_inline_loudnorm_is_skipped_when_two_pass_pass_runs(sfx_path, music_path):
    events = [{"path": sfx_path, "start": 1.5, "volume": 0.6}]

    graph, _ = build_audio_filter(
        sfx_events=events, music_path=music_path, inline_loudnorm=False
    )

    assert "loudnorm" not in graph
    assert graph.endswith(NO_LOUDNORM_TAIL)


def test_ducking_can_be_disabled(music_path):
    graph, extra_inputs = build_audio_filter(
        sfx_events=[], music_path=music_path, duck=False
    )

    assert extra_inputs == [music_path]
    assert "asplit" not in graph
    assert "sidechaincompress" not in graph
    assert "[voice_mix][music_raw]amix=inputs=2" in graph


def test_graph_uses_configured_ducking_defaults(music_path):
    graph, _ = build_audio_filter(sfx_events=[], music_path=music_path)

    assert (
        f"threshold={AUDIO_DUCK_THRESHOLD:g}:ratio={AUDIO_DUCK_RATIO:g}:"
        f"attack={AUDIO_DUCK_ATTACK}:release={AUDIO_DUCK_RELEASE}"
    ) in graph


def test_ducking_constants_are_tuned_for_voice():
    assert audio_compiler.DEFAULT_DUCK_THRESHOLD == pytest.approx(0.05)
    assert audio_compiler.DEFAULT_DUCK_RATIO == pytest.approx(8)
    assert audio_compiler.DEFAULT_DUCK_ATTACK == 20
    assert audio_compiler.DEFAULT_DUCK_RELEASE == 400


def test_missing_sfx_is_skipped_with_a_warning(tmp_path, caplog):
    missing = str(tmp_path / "does_not_exist.mp3")

    with caplog.at_level(logging.WARNING, logger="app.services.audio_compiler"):
        graph, extra_inputs = build_audio_filter(sfx_events=[{"path": missing, "start": 1.0}])

    assert extra_inputs == []
    assert graph == f"{SILENT_GRAPH};{LOUDNORM_TAIL}"
    assert "SFX skipped" in caplog.text


def test_multiple_sfx_events_are_layered(tmp_path):
    first = _make_file(tmp_path / "boom.mp3")
    second = _make_file(tmp_path / "whoosh.mp3")

    graph, extra_inputs = build_audio_filter(
        sfx_events=[{"path": first, "start": 0.5}, {"path": second, "start": 2.0, "volume": 0.4}]
    )

    assert extra_inputs == [first, second]
    assert "[1:a]adelay=500|500,volume=0.9[sfx0]" in graph
    assert "[2:a]adelay=2000|2000,volume=0.4[sfx1]" in graph
    assert "amix=inputs=3" in graph


def test_sfx_volume_is_clamped_and_sanitized(sfx_path):
    # LLM percent values and junk must not produce an unusable filtergraph.
    graph, _ = build_audio_filter(sfx_events=[{"path": sfx_path, "start": 0, "volume": 50}])
    assert "volume=0.5[sfx0]" in graph

    graph, _ = build_audio_filter(sfx_events=[{"path": sfx_path, "start": 0, "volume": "loud"}])
    assert f"volume={audio_compiler.DEFAULT_SFX_VOLUME:g}[sfx0]" in graph


# ------------------------------------------------------------- compile_plan
def _plan(operations, monkeypatch, tmp_path, clip_start_time=0.0):
    monkeypatch.setattr(edit_compiler, "SFX_DIR", tmp_path)
    return edit_compiler.compile_plan(
        operations=operations,
        layout="center_crop",
        ass_filename="subs.ass",
        clip_start_time=clip_start_time,
        sendcmd_path="crop.txt",
    )


def test_compile_plan_resolves_sfx_name_through_paths(monkeypatch, tmp_path):
    expected = _make_file(tmp_path / "boom.mp3")

    _, sfx_files = _plan(
        [{"type": "sfx", "name": "boom", "time_sec": 5.0, "volume": 0.35}],
        monkeypatch, tmp_path, clip_start_time=2.0,
    )

    assert sfx_files == [
        {"path": expected, "name": "boom", "start": pytest.approx(3.0), "volume": 0.35}
    ]


def test_compile_plan_accepts_file_field_and_default_volume(monkeypatch, tmp_path):
    expected = _make_file(tmp_path / "whoosh.wav")

    _, sfx_files = _plan(
        [{"type": "sfx", "file": "whoosh.wav", "start": 1.0}],
        monkeypatch, tmp_path,
    )

    assert sfx_files[0]["path"] == expected
    assert sfx_files[0]["name"] == "whoosh"
    assert sfx_files[0]["volume"] == pytest.approx(AUDIO_SFX_VOLUME)
    # `start` is accepted when `time_sec` is absent.
    assert sfx_files[0]["start"] == pytest.approx(1.0)


def test_compile_plan_missing_sfx_is_skipped_not_fatal(monkeypatch, tmp_path, caplog):
    # boom.mp3 exists, but the requested "riser" does not: no boom fallback.
    _make_file(tmp_path / "boom.mp3")

    with caplog.at_level(logging.WARNING, logger="app.services.edit_compiler"):
        _, sfx_files = _plan(
            [{"type": "sfx", "name": "riser", "start": 1.0}],
            monkeypatch, tmp_path,
        )

    assert sfx_files == []
    assert "skipped" in caplog.text


# ---------------------------------------------------------- real FFmpeg duck
def _build_speech_clip(ffmpeg, tmp_path):
    """2s silence + 2s 440Hz 'speech' + 2s silence, plus a steady 220Hz BGM."""
    voice = tmp_path / "voice.wav"
    music = tmp_path / "music.wav"
    run_subprocess(
        [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono:d=2",
            "-f", "lavfi", "-i", f"sine=frequency={VOICE_HZ:g}:sample_rate={SAMPLE_RATE}:duration=2",
            "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono:d=2",
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1,volume=4[a]",
            "-map", "[a]", "-ac", "1", str(voice),
        ],
        timeout=120,
    )
    run_subprocess(
        [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", f"sine=frequency={MUSIC_HZ:g}:sample_rate={SAMPLE_RATE}:duration=6",
            "-af", "volume=0.3", "-ac", "1", str(music),
        ],
        timeout=120,
    )
    return voice, music


def _render(ffmpeg, voice, music, out_path, duck):
    graph, extra_inputs = build_audio_filter(
        sfx_events=[],
        music_path=str(music),
        music_volume=1.0,
        duck=duck,
        output_duration=6.0,
        inline_loudnorm=False,
    )
    assert extra_inputs == [str(music)]
    run_subprocess(
        [
            ffmpeg, "-y", "-i", str(voice), "-i", str(music),
            "-filter_complex", graph, "-map", "[aout]",
            "-ar", str(SAMPLE_RATE), "-ac", "1", str(out_path),
        ],
        timeout=120,
    )
    return graph


def _decode_mono(ffmpeg, path):
    proc = subprocess.run(
        [
            ffmpeg, "-nostats", "-i", str(path),
            "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
        ],
        capture_output=True,
        timeout=120,
        check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _tone_amplitude(segment, frequency):
    """Single-bin DFT amplitude of ``frequency`` in ``segment``."""
    times = np.arange(len(segment)) / SAMPLE_RATE
    return float(abs(np.dot(segment, np.exp(-2j * np.pi * frequency * times))) * 2 / len(segment))


@pytest.mark.skipif(not is_ffmpeg_available(), reason="FFmpeg is not installed")
def test_music_level_drops_during_speech(tmp_path):
    """Real FFmpeg run: the BGM is measurably quieter while the voice speaks."""
    ffmpeg = str(FFMPEG_PATH)
    voice, music = _build_speech_clip(ffmpeg, tmp_path)

    ducked_graph = _render(ffmpeg, voice, music, tmp_path / "ducked.wav", duck=True)
    _render(ffmpeg, voice, music, tmp_path / "flat.wav", duck=False)

    assert "sidechaincompress" in ducked_graph

    ducked = _decode_mono(ffmpeg, tmp_path / "ducked.wav")
    flat = _decode_mono(ffmpeg, tmp_path / "flat.wav")

    speech_window = slice(int(2.5 * SAMPLE_RATE), int(3.5 * SAMPLE_RATE))
    quiet_window = slice(int(0.2 * SAMPLE_RATE), int(1.2 * SAMPLE_RATE))

    music_during_speech = _tone_amplitude(ducked[speech_window], MUSIC_HZ)
    music_during_quiet = _tone_amplitude(ducked[quiet_window], MUSIC_HZ)
    voice_during_speech = _tone_amplitude(ducked[speech_window], VOICE_HZ)

    # Without ducking the BGM bed is flat across both windows.
    assert _tone_amplitude(flat[speech_window], MUSIC_HZ) == pytest.approx(
        _tone_amplitude(flat[quiet_window], MUSIC_HZ), rel=0.05
    )

    # With ducking the music is at least ~12 dB quieter under the voice ...
    assert music_during_speech < 0.25 * music_during_quiet
    # ... but is still present (not fully muted).
    assert music_during_speech > 0.001
    # The voice itself is untouched by the ducking stage.
    assert voice_during_speech > 0.9 * _tone_amplitude(flat[speech_window], VOICE_HZ)
