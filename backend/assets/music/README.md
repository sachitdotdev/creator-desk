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

## Optional metadata

Add a sidecar JSON next to a track named `<filename>.json`
(for example `lofi.mp3.json`) to describe it in the Template Editor picker:

```json
{
  "title": "Late Night",
  "artist": "Your Name",
  "license": "CC0",
  "mood": "chill",
  "bpm": 92
}
```

Every field is optional. Without a sidecar the filename stem is used as the
title. Templates reference a track by filename (`bgm_track`), e.g.
`"bgm_track": "lofi.mp3"`.
