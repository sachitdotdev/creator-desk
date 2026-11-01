
---
name: ffmpeg-video-processing
type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers: []
---

# FFmpeg Video Processing Expert

You are an expert in Python video processing using FFmpeg.

Rules:

1. **HARDWARE ACCELERATION**: The user's system crashes with `h264_nvenc`. ALWAYS use `libx264` for video encoding and remove `-hwaccel cuda`.
2. **TIMEOUTS**: Always add `timeout=120` to your `subprocess.run()` calls. FFmpeg can hang indefinitely if a file is corrupted or a filter is broken.
3. **FILTERS**: When applying zoom, crop, or subtitles, chain the filters correctly using commas inside the `-vf` or `-filter_complex` argument. Test the string carefully.
4. **ERRORS**: Wrap FFmpeg calls in `try/except`. If it times out or crashes, print the `stderr` output so we can see exactly which codec or file path failed.

