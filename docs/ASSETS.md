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
| `backend/assets/music/lofi.mp3` | 2,963,430 B | "Moon Over Red Dunes" from [btahir/open-lofi](https://github.com/btahir/open-lofi) — generated with Suno v5 by the collection owner and donated to the public domain | CC0 1.0 Universal |

The BGM placeholder is named `ambient-pad.mp3` rather than reusing the old
`lofi.mp3` name. No default template or test depends on a specific BGM filename
(the test suite builds its own files in temporary directories), so the rename
breaks nothing. It is explicitly un-ignored in `.gitignore` and documented by
its `ambient-pad.mp3.json` sidecar.

All four originally generated files were measured with `ffmpeg -af volumedetect`:
peak levels are −6.6 dB (boom), −5.0 dB (pop), −4.7 dB (whoosh) and −10.0 dB
(ambient pad), all below the −3 dBFS ceiling.

## `lofi.mp3` (open-lofi, CC0)

`backend/assets/music/lofi.mp3` is **"Moon Over Red Dunes"** from
[btahir/open-lofi](https://github.com/btahir/open-lofi), released under
**CC0 1.0 Universal** (public domain). The entire OpenLo-Fi collection was
generated with Suno v5 by its owner, btahir, who donated the tracks to the
public domain. Attribution is not required, but we credit the source in the
`lofi.mp3.json` sidecar anyway.

The file was verified byte-for-byte against `moon-over-red-dunes.mp3` from the
v1.0.0 release archive: identical SHA-1, 2,963,430 bytes, 138.28 s. It was
briefly untracked during the asset-licensing cleanup and has now been restored;
no git history was rewritten.

## Bundled fonts

| File | Source | License | Copyright |
| --- | --- | --- | --- |
| `backend/assets/fonts/Anton-Regular.ttf` | [google/fonts `ofl/anton`](https://github.com/google/fonts/tree/main/ofl/anton) (`Anton-Regular.ttf`) | SIL Open Font License 1.1 | Copyright 2020 The Anton Project Authors (https://github.com/googlefonts/AntonFont.git) |

The full SIL OFL 1.1 text, including the copyright line above, is retained
verbatim in `backend/assets/fonts/OFL.txt`. Anton replaced the previously
bundled `impact.ttf`, a proprietary Monotype font that must not be
redistributed. `impact.ttf` is now git-ignored and kept only on local disks;
a fresh clone does not contain it.

Font lookup (`backend/app/core/paths.py::resolve_font_file`) prefers the bundled
Anton file, then system font directories, and finally logs a warning and lets
FFmpeg fall back to the fontconfig family name if neither is available. Seeded
templates use the family name `Anton`. Stored templates that still say
`Impact` are not edited; the `impact` family key is mapped to the same bundled
Anton file so they keep rendering with a lookalike instead of the proprietary
font.

## Bundled OpenCV data file

| File | Origin | License |
| --- | --- | --- |
| `backend/assets/models/haarcascade_frontalface_default.xml` | OpenCV frontal-face cascade (created by Rainer Lienhart), distributed with OpenCV | "Intel License Agreement For Open Source Computer Vision Library", Copyright (C) 2000, Intel Corporation — permissive redistribution terms retained verbatim in the file's top-of-file comment header |

The first 40 lines of the XML were inspected: they contain the Intel OpenCV
license block with the three redistribution conditions (source notice,
binary notice, no Intel endorsement) and the "as is" disclaimer. No other
license is claimed for this file. It is retained in the repository because the
license text is preserved in the file itself (`docs/CREDITS.md`). The paired
`deploy.prototxt` has no license header and is unreferenced, so it is
git-ignored (as is the `res10_300x300_ssd_iter_140000.caffemodel` it belongs to).
