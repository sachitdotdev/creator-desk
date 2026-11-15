# YASB Spotify Media Widget Setup

Copy and paste the following blocks into your YASB configuration files.

## Prerequisites

- Install the widgets package: `pip install yasb-widgets`
- Use a recent YASB release that ships widget support (v0.15+).

---

### Section 1: `config.yaml`

Add this list item to your `right:` key under `widgets:` in `~/.config/yasb/config.yaml`:

```yaml
right:
  - type: media
    source: spotify
    title_format: "{title} - {artist}"
    icon_format: ""
    controls_format: "[⏮] [⏪] ⏵ [⏩] [⏭]"
    hide_when_empty: true
```

- `source: spotify` — the media source to listen to (alternatives include `vlc`, `mpd`).
- `title_format` — display string; `{artist}`, `{album}`, and `{percentage}` are also available.
- `icon_format: ""` — shows the source's default icon. Point it at a local artwork file for a custom thumbnail, e.g. `icon_format: "/path/to/album.png"`.
- `controls_format` — playback buttons; the center token (`⏵`) toggles play/pause, the outer tokens seek/switch tracks.
- `hide_when_empty: true` — hides the widget when nothing is playing.

---

### Section 2: `styles.css`

Add both blocks to your `~/.config/yasb/styles.css`:

```css
/* Base media widget styling */
.media-widget {
    background-color: rgba(40, 40, 55, 0.6);
    border-radius: 8px;
    padding: 6px 12px;
    margin-right: 8px;
}

/* Spotify-specific tint */
.media-widget.media-source-spotify {
    background-color: rgba(30, 215, 96, 0.2);
}
```

- `.media-widget` — your dark frosted-glass base with rounded corners and spacing.
- `.media-widget.media-source-spotify` — overrides the background with a subtle Spotify green tint while Spotify is active.
