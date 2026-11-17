# Background music library

Creator Desk does **not** bundle any music. Only add tracks that you own or that
are licensed for your use (royalty-free / Creative Commons with attribution as
required). Do not commit copyrighted music to this repository.

Drop supported files directly in this folder:

- `.mp3`
- `.wav`
- `.m4a`
- `.ogg`

Audio files in this folder are git-ignored; this README is the only tracked file.

## Metadata (required for every track)

Each track **must** have a sidecar JSON next to it, named `<filename>.json`
(for example `lofi.mp3.json`), documenting its **license** and **source**. Do not
add a track without one: the picker shows the license, and an undocumented track
cannot be verified as usable.

```json
{
  "license": "CC0",
  "source": "https://example.com/lofi",
  "title": "Late Night",
  "artist": "Your Name",
  "mood": "chill",
  "bpm": 92
}
```

`license` and `source` are required. `title`, `artist`, `mood` and `bpm` stay
optional: without a sidecar the filename stem is used as the title. Templates
reference a track by filename (`bgm_track`), e.g. `"bgm_track": "lofi.mp3"`.
