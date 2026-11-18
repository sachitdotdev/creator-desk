# Creator Desk Roadmap: remaining work (updated Nov 17, 2026)

## Principles
- Ship every sub-phase independently; never break what works.
- Max one new required dependency per feature; prefer optional extras with graceful degradation.
- Permissive licenses only (Apache-2.0, MIT, BSD, LGPL).
- Every AI stage is a swappable provider.
- The edit is data (Timeline-as-Data), not imperative code.

## Status
| Phase | Status |
|---|---|
| 1 Core pipeline | Done |
| 2 Template engine + UI | Done |
| 3 Audio stack | Done except optional 3.4 stem separation |
| 4.0 GPU guardrails | 4.0.1 GPU lock and 4.0.2 VRAM flush merged (PR #35); 4.0.3 ComfyUI sidecar pending |
| 4.1-4.5 Local video gen | Not started |
| 5 Remotion captions | Not started |
| 6 Active speaker crop | Not started (center_crop exists) |
| 7 Timeline-as-Data + agents | Not started |
| 8 Distribution | Not started |
| 9 UI makeover | Not started |

Critical path: 4.0 -> 4.1 -> 4.2 -> 7.1 -> everything else.

## Immediate queue (housekeeping)
1. Protect-main ruleset on GitHub: block deletion and force pushes, require PR (0 approvals), require status check "backend", no bypass.
2. Cleanup batch: license check for lofi.mp3 (Suno-generated, in git history) and the 3 undocumented SFX files; optional face tracker smoothing (hold last stable position, require N consecutive frames before switching target).
3. Deferred launcher hardening: PID creation-time identity check in stop.bat; PID tracking when a service is still alive after a readiness timeout.

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
- 7.2 Verb API: remove_silences, reframe, insert_broll, caption, duck_music, assemble, qc
- 7.3 Optional agents: planner, QC (VLM watches render and iterates), multi-agent swarm

## Phase 6: Active speaker cropping (best early win after 7.1; fixes face tracker glitches)
- 6.1 Speaker diarization (pyannote or Senko) [M]
- 6.2 Face-to-speaker mapping (YOLOv8 + diarization) [M]
- 6.3 Dynamic crop keyframes via sendcmd per speaker turn [M]
- 6.4 Speaker-aware transitions, smooth pan [S]
- 6.5 UI speaker preview in timeline [S]
- Known issue: Face tracker instability: between shots the tracker sometimes gets confused about which speaker to follow and the crop glitches mid-frame for a period. Planned: speaker diarization plus face-to-speaker mapping (6.1 and 6.2), shot-cut detection to reset tracking, and temporal smoothing (hold the last stable position when confidence drops, require N consecutive frames before switching target).

## Phase 5: Hero captions (Remotion)
- 5.1 Remotion microservice scaffold, Node + FastAPI bridge [M]
- 5.2 Word-level timestamp ingestion [S]
- 5.3 17 animated caption presets [L]
- 5.4 UI style picker in Template Editor [S]
- 5.5 Transparent caption layer export (ProRes 4444) [S]

## Phase 8: Distribution and automation
- 8.1 YouTube upload (Data API v3) [M]
- 8.2 TikTok/Reels upload or manual export queue [M]
- 8.3 Scheduling via APScheduler [S]
- 8.4 Thumbnail generator [S]
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
