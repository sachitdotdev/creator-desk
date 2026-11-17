"""Phase 3.1 - SFX paths are confined to ``paths.SFX_DIR``."""

import logging

from app.services import edit_compiler


def _make_file(path, payload=b"\x00"):
    path.write_bytes(payload)
    return str(path)


def _plan(operations, monkeypatch, tmp_path):
    monkeypatch.setattr(edit_compiler, "SFX_DIR", tmp_path)
    return edit_compiler.compile_plan(
        operations=operations,
        layout="center_crop",
        ass_filename="subs.ass",
        clip_start_time=0.0,
        sendcmd_path="crop.txt",
    )


def test_absolute_path_resolves_under_sfx_dir(monkeypatch, tmp_path):
    # A file with the same name exists in SFX_DIR: the absolute input resolves
    # to the SFX copy, never to the absolute path itself.
    expected = _make_file(tmp_path / "secret.wav")

    _, sfx_files = _plan(
        [{"type": "sfx", "file": "C:/x/secret.wav", "start": 1.0}],
        monkeypatch, tmp_path,
    )

    assert sfx_files[0]["path"] == expected


def test_absolute_path_missing_from_sfx_dir_is_skipped(monkeypatch, tmp_path, caplog):
    secret = tmp_path.parent / "secret.wav"
    secret.write_bytes(b"secret")

    with caplog.at_level(logging.WARNING, logger="app.services.edit_compiler"):
        _, sfx_files = _plan(
            [{"type": "sfx", "file": str(secret), "start": 1.0}],
            monkeypatch, tmp_path,
        )

    assert sfx_files == []
    assert "skipped" in caplog.text


def test_unc_path_never_reads_outside_sfx_dir(monkeypatch, tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.edit_compiler"):
        _, sfx_files = _plan(
            [{"type": "sfx", "file": r"\\host\share\a.wav", "start": 1.0}],
            monkeypatch, tmp_path,
        )

    assert sfx_files == []
    assert "skipped" in caplog.text


def test_parent_traversal_resolves_inside_sfx_dir(monkeypatch, tmp_path):
    expected = _make_file(tmp_path / "boom.mp3")

    _, sfx_files = _plan(
        [{"type": "sfx", "file": "../boom.mp3", "start": 1.0}],
        monkeypatch, tmp_path,
    )

    assert sfx_files[0]["path"] == expected


def test_resolve_sfx_path_rejects_empty_names(monkeypatch, tmp_path):
    monkeypatch.setattr(edit_compiler, "SFX_DIR", tmp_path)

    assert edit_compiler.resolve_sfx_path({}) is None
    assert edit_compiler.resolve_sfx_path({"file": "   "}) is None
    assert edit_compiler.resolve_sfx_path({"file": ".."}) is None
