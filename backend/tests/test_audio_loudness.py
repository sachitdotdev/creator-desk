"""Phase 3.5 - Loudness normalization: unit + end-to-end tests for EBU R128 two-pass loudnorm."""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.core.processing_utils import run_subprocess
from app.services import audio_loudness

LOUDNESS_JSON = """{
	"input_i" : "-21.75",
	"input_tp" : "-21.07",
	"input_lra" : "0.00",
	"input_thresh" : "-31.75",
	"output_i" : "-14.03",
	"output_tp" : "-13.28",
	"output_lra" : "0.00",
	"output_thresh" : "-24.03",
	"normalization_type" : "dynamic",
	"target_offset" : "0.03"
}"""


def _fake_process(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    return proc


def test_is_ffmpeg_available_false_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("FFMPEG_PATH", str(tmp_path / "does_not_exist_ffmpeg"))
    assert audio_loudness.is_ffmpeg_available() is False


def test_is_ffmpeg_available_true_when_executable_exists(monkeypatch, tmp_path):
    exe = tmp_path / "ffmpeg"
    exe.write_text("fake", encoding="utf-8")
    monkeypatch.setenv("FFMPEG_PATH", str(exe))
    assert audio_loudness.is_ffmpeg_available() is True


def test_measure_loudness_parses_print_format_json(monkeypatch):
    proc = _fake_process(stdout=LOUDNESS_JSON)
    with patch.object(audio_loudness, "run_subprocess", return_value=proc) as mock_run:
        stats = audio_loudness.measure_loudness("C:/media/in.mp4")
    mock_run.assert_called_once()
    cmd = mock_run.call_args.args[0]
    af_index = cmd.index("-af")
    assert "loudnorm=I=-14:TP=-2:LRA=11" in cmd[af_index + 1]
    assert "print_format=json" in cmd[af_index + 1]
    assert stats["input_i"] == pytest.approx(-21.75)
    assert stats["input_tp"] == pytest.approx(-21.07)
    assert stats["input_lra"] == pytest.approx(0.0)
    assert stats["output_i"] == pytest.approx(-14.03)


def test_apply_loudness_runs_two_pass(monkeypatch, tmp_path):
    proc = _fake_process(stdout=LOUDNESS_JSON)
    out = tmp_path / "out.mp4"
    with patch.object(audio_loudness, "run_subprocess", return_value=proc) as mock_run, \
            patch.object(audio_loudness, "is_ffmpeg_available", return_value=True):
        stats = audio_loudness.apply_loudness_normalization("C:/media/in.mp4", str(out))
    assert stats is not None
    assert mock_run.call_count == 2
    first_cmd = mock_run.call_args_list[0].args[0]
    second_cmd = mock_run.call_args_list[1].args[0]
    first_af = first_cmd[first_cmd.index("-af") + 1]
    assert "print_format=json" in first_af
    second_af = second_cmd[second_cmd.index("-af") + 1]
    assert "measured_I=-21.75" in second_af
    assert "measured_TP=-21.07" in second_af
    assert "measured_LRA=0.00" in second_af
    assert "-c:a" in second_cmd
    assert str(out) in second_cmd


def test_apply_loudness_returns_none_when_ffmpeg_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("FFMPEG_PATH", str(tmp_path / "nope_ffmpeg"))
    assert audio_loudness.apply_loudness_normalization("C:/media/in.mp4", str(tmp_path / "out.mp4")) is None


@pytest.mark.skipif(not audio_loudness.is_ffmpeg_available(), reason="FFmpeg is not installed")
def test_two_pass_loudness_end_to_end(tmp_path):
    """Real FFmpeg two-pass loudnorm round trip on a generated 6s tone."""
    tone = tmp_path / "tone.wav"
    ffmpeg = str(os.environ.get("FFMPEG_PATH") or "ffmpeg")
    run_subprocess(
        [
            ffmpeg, "-nostats", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-ar", "44100", "-ac", "2", str(tone),
        ],
        timeout=120,
    )
    before = audio_loudness.measure_loudness(str(tone))
    normalized = tmp_path / "tone_loudnorm.mp4"
    stats = audio_loudness.apply_loudness_normalization(str(tone), str(normalized))
    assert stats is not None
    assert normalized.exists()
    after = audio_loudness.measure_loudness(str(normalized))
    # Before: source was far from the EBU R128 target; after: within ~1 LUFS of -14.
    assert after["input_i"] > before["input_i"]
    assert abs(after["input_i"] - (-14.0)) < 1.0
