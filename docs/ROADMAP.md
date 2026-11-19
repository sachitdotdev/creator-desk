# Creator Desk Roadmap: remaining work (updated Nov 17, 2026)

## Principles
- Ship every sub-phase independently; never break what works.
- Max one new required dependency per feature; prefer optional extras with graceful degradation.
- Permissive licenses only (Apache-2.0, MIT, BSD, LGPL).
- Every AI stage is a swappable provider.
- The edit is data (Timeline-as-Data), not imperative code.
- Third-party code policy: see AGENTS.md.
- Content rights: a public channel uses only content we own, license or have permission for; third-party test clips stay local and untracked.

## Status
| Phase | Status |
|---|---|
| 1 Core pipeline | Done |
| 2 Template engine + UI | Done |
| 3 Audio stack | Done except optional 3.4 stem separation |
| 4.0 GPU guardrails | 4.0.1 and 4.0.2 merged (PR #35); 4.0.3 ComfyUI sidecar pending |
| Framing and captions | face tracker stability (#41) and caption legibility plus per-shot zoom (#42) merged |
| 4.1-4.5 Local video gen | Not started |
| 5 Remotion captions | Not started |
| 6 Active speaker crop | Not started (center_crop exists) |
| 7 Timeline-as-Data + agents | Not started |
| 8 Distribution | Not started |
| 9 UI makeover | Not started |

Critical path: 4.0 -> 4.1 -> 4.2 -> 7.1 -> everything else.

## Immediate queue (housekeeping)
1. Clip vetting: reject picks whose face-visible fraction is below CLIP_MIN_FACE_COVERAGE (about 0.6, switch CLIP_VETTING_ENABLED), and a visible_face_fraction metric measured by running the detector on the RENDERED mp4, not on tracker data; render checks include frame count and audio versus video duration.
2. README: fill "Runtime setup: TBD" and remove or mark legacy Ollama and port 8001 instructions.
3. Confirm asset-licensing cleanup is merged.
4. Deferred launcher hardening: PID creation-time identity check in stop.bat; PID tracking when a service is still alive after a readiness timeout; local model paths containing "!" under delayed expansion.

## Phase 3: Audio stack
- 3.7 (optional) Dead-air trimming: evaluate auto-editor (Unlicense) or FFmpeg silencedetect [S]

## Phase 4: Local AI video generation
4.0.3 ComfyUI sidecar: add to launcher, --listen 127.0.0.1 --port 8188.

4.1 Style Analyzer (decide VLM provider first: vLLM vs Ollama; on 12 GB the VLM must swap with the LLM via the GPU lock)
- 4.1.1 FFmpeg keyframe extraction (3 frames) [XS]
- 4.1.2 VLM style profile JSON: style_prompt, camera_motion, mood, palette, grain [S]
- 4.1.3 LoRA classifier picks closest registry match [S]

4.2 ComfyUI generation engine
- 4.2.1 Client: POST /prompt, poll /history, extract output [S]
- 4.2.2 Workflow injection into exported api_workflow.json [S]
- 4.2.3 LTX-Video T2V workflow, fast 9:16 B-roll [M]
- 4.2.4 Wan 2.2 I2V cinematic shots with FLUX keyframe [M]
- 4.2.5 UI engine toggle: Fast (LTX) vs Cinematic (Wan) [XS]

4.3 B-roll gap detection
- 4.3.1 Transcript topic-shift timestamps [M]
- 4.3.2 Gap window generator, 3-5 s slots [S]
- 4.3.3 Prompt builder: style profile + topic + gap context [S]

4.4 Assembly
- 4.4.1 Generated clip as FFmpeg overlay layer in compile_plan() [M]
- 4.4.2 Transitions (xfade) between B-roll and talking head [S]
- 4.4.3 React "Video Gen" tab [M]

4.5 LoRA registry: 4.5.1 directory + sidecar metadata [XS]; 4.5.2 VLM-to-LoRA matching [S]; 4.5.3 LTX trainer for custom aesthetics [L, defer].

## Phase 7: Timeline-as-Data + agents (end of critical path)
- 7.1.1 Pydantic timeline model (tracks, clips, effects, transitions, audio layers)
- 7.1.2 Deterministic renderer: compile_plan() becomes render(timeline)
- 7.1.3 OTIO export bridge for DaVinci/Premiere
- 7.1.4 Output profiles: 9:16 short and 16:9 long-form rendered from the same timeline (YouTube long-form)
- 7.2 Verb API: remove_silences, reframe, insert_broll, caption, duck_music, assemble, qc
- 7.3 Optional agents: planner, QC (VLM watches render and iterates), multi-agent swarm
- 7.4 (optional) OpenFilm export: timeline to film.html (OpenFilm is MIT) after 7.1; not a required dependency

## Phase 6: Active speaker cropping (best early win after 7.1; fixes face tracker glitches)
- 6.1 Speaker diarization (pyannote or Senko) [M]; WhisperX or pyannote diarization; read the WhisperX LICENSE file (sources disagree between BSD-2 and BSD-4); pyannote models are gated on Hugging Face (token plus accepted terms), default model reportedly CC-BY-4.0 (attribution); swap with vLLM through the GPU lock
- 6.2 Face-to-speaker mapping (YOLOv8 + diarization) [M]
- 6.2b (optional) Active speaker detection model only if 6.1 and 6.2 are not enough: TalkNet-ASD (MIT, last updated 2023), LR-ASD (license unverified); check the pretrained weights' dataset terms
- 6.3 Dynamic crop keyframes via sendcmd per speaker turn [M]
- 6.4 Speaker-aware transitions, smooth pan [S]
- 6.5 UI speaker preview in timeline [S]
- 6.6 Two-person framing (stacked or split layout when two speakers alternate) and stabilized hold-still crop; OpenShorts (MIT) is a reference, reimplement or copy with attribution [M]
- Optional: PySceneDetect (BSD-3-Clause) as a second opinion on cut detection
- Known issue: Face tracker instability: between shots the tracker sometimes gets confused about which speaker to follow and the crop glitches mid-frame for a period. Planned: speaker diarization plus face-to-speaker mapping (6.1 and 6.2), shot-cut detection to reset tracking, and temporal smoothing (hold the last stable position when confidence drops, require N consecutive frames before switching target).

## Phase 5: Hero captions (Remotion)
- 5.0 License decision gate before 5.1: Remotion is source-available (free for individuals and teams of up to 3, paid at 4 or more), so it does not meet our permissive-only rule. Evaluate Apache or MIT alternatives (HyperFrames, Motion Canvas, Revideo; unverified), or keep ASS captions. Re-check current terms first.
- 5.1 Remotion microservice scaffold, Node + FastAPI bridge [M]
- 5.2 Word-level timestamp ingestion [S]
- 5.3 17 animated caption presets [L]
- 5.4 UI style picker in Template Editor [S]
- 5.5 Transparent caption layer export (ProRes 4444) [S]

## Phase 8: Distribution and automation
- 8.0 Prerequisites: check current YouTube Data API quota and whether uploads from an unaudited API project are forced private; default to private or draft uploads
- 8.1 YouTube upload (Data API v3) [M]
- 8.2 TikTok/Reels upload or manual export queue [M]
- 8.3 Scheduling via APScheduler [S]
- 8.4 Thumbnail generator [S] — reference OpenShorts' title, description and thumbnail flow (MIT)
- 8.5 SRT/subtitle export, multi-language [XS]

## Phase 9: UI makeover
- 9.1 Design tokens + shadcn/ui reskin [M]
- 9.2 Timeline scrubber backed by the 7.1 schema [L]
- 9.3 Template gallery with live previews [M]
- 9.4 Job dashboard: queue, progress, logs [S]

## Optional / low priority
- 3.4 Stem separation via audio-separator (BS-RoFormer) [M]
- Frontend ESLint flat config (npm run lint currently can't run)

## Stale items in the original v4.0 roadmap
- 4.0.2 "keep_alive: 0 on Ollama" is obsolete (vLLM ignores it). Replaced by flush_vram plus ComfyUI /free with {"unload_models": true, "free_memory": true}.
- 4.1.2 assumes an Ollama VLM (qwen2.5vl:7b); revisit for vLLM on 12 GB.
- 3.1/3.2 are compile_plan()/filtergraph extensions; 3.3 is a Python caption truncator in edit_compiler.py.

## Candidate dependencies and license notes (checked Nov 18, 2026; verify before adopting)

| Project | License | Use | Note |
| --- | --- | --- | --- |
| auto-editor | Unlicense | dead-air cuts | optional |
| PySceneDetect | BSD-3-Clause | cut detection second opinion | optional |
| WhisperX | BSD (-2 or -4, read LICENSE) | word timing and diarization wrapper | gated diarization models |
| pyannote.audio | MIT code; models gated | diarization | token and terms on Hugging Face |
| TalkNet-ASD | MIT | active speaker reference | old, weights terms unchecked |
| LR-ASD | unverified | lighter active speaker model | check original repo |
| OpenShorts | MIT | reference: stabilized crop, two-person framing, publishing | uses cloud Gemini; credit if code is reused |
| OpenFilm | MIT | optional export target | needs Node and a coding agent |
| Remotion | source-available | captions (Phase 5) | free up to 3 people; not permissive |
| HyperFrames, Motion Canvas, Revideo | Apache-2.0 / MIT (unverified) | Remotion alternatives | verify |
| MediaPipe | Apache-2.0 (unverified) | face detection alternative to YOLO | verify |

Do not copy code from: Clips Kitty, SupoClip, vibeclip (AGPL-3.0), ClippedAI (CC BY-NC 4.0).
