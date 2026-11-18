# Asset licensing policy

Only audio that is **original**, **generated**, or **clearly licensed** may be
committed to this repository. Every committed audio file must have its origin
and license recorded in this document, and every file in `backend/assets/music/`
must additionally carry a `<filename>.json` sidecar with `license` and `source`
fields (see `backend/assets/music/README.md`). Downloaded stock effects,
copyrighted music, and AI-vocal tracks (e.g. Suno output) must **not** be
committed. Audio that is merely used locally stays git-ignored.

All originally generated assets below are reproducible from
`tools/generate_sfx.py`, which contains the exact FFmpeg commands. Re-run it
from the repository root with `python tools/generate_sfx.py` (requires FFmpeg
on `PATH`).

## Tracked audio files

| File | Size | Origin | License |
| --- | --- | --- | --- |
| `backend/assets/sfx/boom.mp3` | 51,034 B | Generated with FFmpeg `aevalsrc` (low sine, pitch drop + exponential decay) by `tools/generate_sfx.py` | CC0 (original work) |
| `backend/assets/sfx/pop.mp3` | 12,581 B | Generated with FFmpeg `aevalsrc` (short sine burst, fast decay) by `tools/generate_sfx.py` | CC0 (original work) |
| `backend/assets/sfx/whoosh.mp3` | 10,492 B | Generated with FFmpeg `anoisesrc` + rising `aevalsrc` chirp, mixed with `amix` by `tools/generate_sfx.py` | CC0 (original work) |
| `backend/assets/music/ambient-pad.mp3` | 641,192 B | Generated with FFmpeg `aevalsrc` (four layer harmonics) + slow `tremolo`, 40 s seamless loop, by `tools/generate_sfx.py` | CC0 (original work) |

The BGM placeholder is named `ambient-pad.mp3` rather than reusing the old
`lofi.mp3` name. No default template or test depends on a specific BGM filename
(the test suite builds its own files in temporary directories), so the rename
breaks nothing. It is explicitly un-ignored in `.gitignore` and documented by
its `ambient-pad.mp3.json` sidecar.

All four files were measured with `ffmpeg -af volumedetect`: peak levels are
−6.6 dB (boom), −5.0 dB (pop), −4.7 dB (whoosh) and −10.0 dB (ambient pad), all
below the −3 dBFS ceiling.

## `lofi.mp3` (Suno-generated)

`backend/assets/music/lofi.mp3` was an AI-generated (Suno) track introduced in
commit `1525472`. It is **no longer tracked**: it was removed from the index in
commit `aadd556`, which is already on `main`, and its exact path is now listed
in `.gitignore` to prevent it from being re-added. It was deliberately left in
the local working tree untouched (no deletion on disk) and no git history was
rewritten — the file's bytes remain reachable in earlier history at commit
`1525472`. Whether to scrub it from history is the repository owner's decision
and was not done here.
