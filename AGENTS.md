# Repository Purpose

Creator Desk is an autonomous, AI-powered short-form video editing pipeline.
It takes raw uploaded videos, transcribes them via Faster-Whisper, uses a local
local vLLM LLM (OpenAI-compatible, http://127.0.0.1:8002, model `meissa-7b-awq`)
to identify the most viral/engaging segments, and renders those
segments into vertical (9:16) TikTok/Reels style clips with dynamic captions
using FFmpeg.

# Tech Stack

- **Backend:** Python 3.12 (launchers fall back to 3.11), FastAPI, Uvicorn,
  SQLAlchemy (SQLite), Pydantic.
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router,
  TanStack Query.
- **AI/ML:** Faster-Whisper (transcription), vLLM 0.27.1 (OpenAI-compatible LLM on 127.0.0.1:8002, model `meissa-7b-awq`). Ollama is no longer used by the pipeline; its config keys are vestigial.
- **Video/Audio:** FFmpeg (via `subprocess`).

## Project Map — read this before exploring

The layout below is authoritative. **Do not run `tree`, `find`, `rg --files`,
or `ls -R` at the start of a task.** Open only the files you need.

### Backend (Python / FastAPI)
- `backend/app/main.py`                    — FastAPI app entry; mounts `/api`, `/renders`, `/sources`
- `backend/app/api/routes.py`              — HTTP routes (videos, clips, templates, accounts, `/api/music`)
- `backend/app/core/config.py`             — settings + ffmpeg binary resolution; LLM context limits (`LLM_MAX_MODEL_LEN`, `LLM_MAX_NUM_SEQS`) and `CLIP_*` window/gap/length knobs live here; face-tracking knobs (`FACE_*`, `FACE_CUT_*`), per-shot zoom knobs (`FACE_ZOOM_ENABLED` default true, `FACE_ZOOM_TARGET_PCT` 0.18, `FACE_ZOOM_MAX_ZOOM` 2.0, `FACE_ZOOM_MAX_UPSCALE` 3.0, `FACE_ZOOM_HEADROOM_PCT` 0.12) and caption knobs live here: safe zone (`CAPTION_SAFE_BOTTOM_PCT` 0.18, `CAPTION_SAFE_ZONE_ENFORCE` true) plus the default burned caption style (`CAPTION_FONT`, `CAPTION_BOLD`, `CAPTION_FONT_SIZE_PCT` 0.065 -> 125 px of 1920, `CAPTION_PRIMARY_COLOR` white, `CAPTION_OUTLINE_COLOR` black, `CAPTION_OUTLINE_W` 5, `CAPTION_SHADOW` 3, `CAPTION_MAX_LINES` 2, `CAPTION_WORD_WRAP`). Caption style comes from these config defaults; a template overrides a key only when it sets that key explicitly (the seeded templates set no caption style keys). `FACE_MODEL` and `FACE_CUT_CACHE_DIR` (alias of `CUT_CACHE_DIR`) are re-exported from `core/paths.py` (repo-relative default, `FACE_MODEL_PATH` env override)
- `backend/app/core/gpu_lock.py`           — process-wide single-tenant GPU lock (sync + async)
- `backend/app/core/paths.py`              — single source of truth for filesystem paths; repo-relative `__file__` anchors (no developer absolute paths), `FACE_MODEL` defaults to `backend/yolov8n-face.pt` with a `FACE_MODEL_PATH` env override; `CUT_CACHE_DIR` (`TEMP_DIR / "cut_cache"`) lives here and is imported by config; `FONT_DIR` + `resolve_font_file()` resolve drawtext fonts from bundled `backend/assets/fonts` first, then system dirs (never a personal path)
- `backend/app/core/processing_utils.py`   — robust media processing utilities (`run_subprocess`)
- `backend/app/database.py`                — DB session, schema bootstrap
- `backend/app/models.py`                  — SQLAlchemy models (Video, Clip, Template)
- `backend/app/schemas.py`                 — Pydantic models
- `backend/app/services/whisper_service.py`    — faster-whisper transcription
- `backend/app/services/llm_service.py`        — vLLM (OpenAI-compatible) client at http://127.0.0.1:8002/v1, model `meissa-7b-awq`; `generate_clips()` delegates to `clip_selector`
- `backend/app/services/clip_selector.py`      — whole-video clip selection: windowed LLM candidate search (up to 4 concurrent windows) + deterministic gap/bucket/snapped-boundary picking; shared by `routes._run_pipeline` and `batch_service`
- `backend/app/services/edit_compiler.py`      — `compile_plan()`; FFmpeg filtergraph builder. `center_crop` uses the scaled video (not a black colour source) as overlay main, seeds the initial overlay x from the first sendcmd command, and crops the composited frame back to `1080x1920` before captions. Optional `zoom_sendcmd_path`/`zoom_initial` append a second `crop@zc` + `scale=1080:1920` stage (constant per shot, step changes at cuts) - no Ken Burns zoom exists elsewhere, so there is no double zoom
- `backend/app/services/render_service.py`     — render orchestration; BGM settings, two-pass loudnorm hook, render-time caption bottom-margin clamp (`effective_caption_margin_v`, never edits stored templates), `resolve_caption_style()` (config defaults + explicit template overrides), ASS word wrap (`wrap_caption_text`), and per-shot zoom plan generation (`zoom_<clip_id>.txt` + `.json`)
- `backend/app/services/face_tracker.py`       — YOLOv8 face detection with real-FFmpeg shot-cut detection (`-loglevel info -nostats`, cached under `CUT_CACHE_DIR`, cut scan runs outside the GPU lock), live nearest-center target tracking (stale bboxes never freeze the crop), source-pixel coordinate mapping after optional upscale, target hysteresis + reacquisition (a sole new face outside `SAME_TARGET_PX` is acquired after `FACE_TARGET_MIN_DWELL_S`), spring smoothing, hold-then-ease loss handling; writes a per-frame detection sidecar (`.track.json`) next to each sendcmd. Fallbacks (disabled / model missing / capture failure / exception) write a fresh center-crop sendcmd whose overlay is derived from the probed source frame size (not hard-coded 16:9) and replace any stale sidecar with `{"fallback": true, "reason": "..."}`. `_model_file_exists()` is the single, overridable weights check so tests can inject a fake detector with no model file on disk (CI). `compute_zoom_window()` / `plan_shot_zooms()` / `generate_zoom_sendcmd_file()` add the per-shot wide-shot zoom (median face height per shot, headroom, source-frame clamping, `MAX_ZOOM` + `MAX_UPSCALE` caps, zoom 1.0 for close-ups); the tracker-fallback sidecar makes zoom a no-op
- `backend/app/services/audio_compiler.py`     — audio graph: SFX layering, BGM ducking, limiter
- `backend/app/services/audio_loudness.py`     — EBU R128 two-pass loudnorm
- `backend/app/services/music_service.py`      — BGM library (scan, sidecars, safe uploads)
- `backend/app/services/social_service.py`     — export/distribution stubs
- `backend/app/services/batch_service.py`      — automated batch video processing
- `backend/app/services/lead_finder.py`        — YouTube Shorts candidate discovery
- `backend/app/services/qc_bot.py`             — rendered clip quality auditing
- `backend/app/services/template_service.py`   — template management and defaults

### Frontend (React / Vite / TypeScript)
- `frontend/src/pages/`            — `UploadStudio`, `ClipReview`, `Scheduler`, `TemplateEditor`, `Accounts`
- `frontend/src/components/layout/` — `Navbar`, `Sidebar`
- `frontend/src/components/ui/`     — shadcn-style primitives (button, card, dialog, select, tabs, …)
- `frontend/src/hooks/`             — shared hooks
- `frontend/src/lib/api.ts`         — ALL fetch() calls live here (`BASE_URL` http://127.0.0.1:8080)
- `frontend/src/lib/utils.ts`       — shared helpers
- `frontend/src/App.tsx`, `types.ts` — routes / shared types

### Data, models, assets
- `data/`                    — runtime DBs, renders, sources, creators, templates (resolve via `paths.py`)
- `data/sources/processed/`  — processed .wav files
- `backend/assets/`          — `music/`, `sfx/`, `fonts/`, `models/`, `yolov8n-face.pt`
- `backend/assets/models/`   — LLM / LoRA checkpoints (NOT a top-level `models/` dir)
- `backend/assets/music/`    — BGM library; served by `/api/music` (GET list, POST upload,
  GET `/{name}/preview`). Audio files are git-ignored; optional `<file>.json` sidecars
  carry title/artist/license. Templates select BGM via `bgm_track` + `bgm_volume`
  (and `bgm_duck`), resolved in `render_service.py`.
- `services/vllm/`            — self-contained vLLM 0.27.1 on Windows (bundled Python 3.13,
  no WSL/Docker). `start_vllm.bat` owns the exact command:
  `launch.bat --model <meissa-7b-awq path> --port 8002 --max-model-len 4096
  --gpu-memory-utilization 0.60 --max-num-seqs 4 --enforce-eager`. It exposes an
  OpenAI-compatible `/v1` API and `GET /health`. Called by root `start.bat`; the
  model path/flags live in that script (gitignored). Model: `<model-directory>\meissa-7b-awq`.
  The real model directory is configured in the gitignored local launcher, not
  in this tracked document.

### Tests & tooling
- `backend/tests/`          — pytest suite (audio graph, loudness, music, render, BGM templates, face tracker (incl. a real-FFmpeg hard-cut source, no model/GPU), render review, **caption safe zone**, **caption style** (default ASS values, width-based wrapping that never drops words, split timed dialogues, explicit template unchanged, safe seeded defaults), **caption font security** (family-name validation on template routes + render fallback, two-layer FFmpeg fontfile escaping incl. a real drawtext run), **render metrics**, **edit compiler**, **layout render** (filtergraph string invariants + one real-FFmpeg render per layout, detector faked so CI needs no model/GPU), **face zoom** (pure zoom-window math with overlay pan, crop@zc command targeting, one real-FFmpeg multi-shot render with mocked detector))
- `tools/render_metrics.py` — pure stability metrics for crop trajectories: jumps, switches, holds, no-detection (with `FACE_DETECTION_STRIDE > 1`, only sampled frames count; population size reported as `no_detection_population`; seconds derived from sampled-timestamp cadence, not `frames/fps`), **travel per rolling 1 s window, direction reversals, fast sweeps**, **face-in-crop violation fraction + longest violation timestamps** (added to `glitch_score` at weight 10; touching the margin counts), reweighted `glitch_score`; **blackdetect (`d=0.04`, `pix_th=0.10`)** and **first-5-frame mean luma via signalstats** (bounded with `-frames:v`); failed/timed-out ffmpeg analysis returns explicit `UNAVAILABLE`, successful empty scans stay `[]`; `SAFE_ZONE_BOTTOM_PCT = 0.18` mirror of the render clamp; a fallback-marker sidecar returns "tracker fallback used, tracking metrics unavailable"; unit-tested with synthetic trajectories
- `tools/render_review.py`  — per-render review: contact sheet, **black-frame diagnostics (black periods reported separately; black first frame comes from frame-zero luma)**, **face-in-crop violation report**, **caption safe-zone check (per-dialogue inherited style margin resolved before min, explicit overrides preserved, bottom margin % of height, threshold 18%)**, **missed-frames contact sheet** (up to 16 sampled no-face frames from the tracker sidecar with timestamps), `metrics.json` echoing all metrics including `unavailable` status when ffmpeg analysis fails. ASS selection matches by clip id and render-name token and **requires explicit `--ass` when more than one `subs_<id>_*.ass` candidate exists** (no silent stale pick); a tracker fallback sidecar is reported as "tracker fallback used, tracking metrics unavailable"
- `backend/ruff.toml`       — ruff config (FastAPI `Depends` allowed in defaults)
- `.github/workflows/ci.yml` — CI job `backend` (ruff + pytest on Python 3.12, lightweight deps only)
- `.coderabbit.yaml`        — CodeRabbit review config + path-specific instructions

Render-stability notes:
- Per-shot zoom: after the full-height crop, an optional named `crop@zc` (driven by its own `zoom_<clip_id>.txt` sendcmd) plus `scale=1080:1920` enlarges wide shots in constant steps at cuts only. It is capped by `FACE_ZOOM_MAX_ZOOM` and `FACE_ZOOM_MAX_UPSCALE` (source-to-output pixels), keeps headroom above the face, clamps the window inside the frame, and is disabled entirely by a tracker-fallback sidecar. `FACE_ZOOM_TARGET_PCT` is measured against the 1920 px output height; a face already at/above the target leaves zoom at 1.0.
- Black first frame: a colour-source overlay main produced a black frame 0; the video-main graph also needed a final `crop=1080:1920:0:0` (the scaled source is 3413 px wide) plus a seeded initial overlay x. `-ss` stays before `-i` with no `-copyts`; fresh renders match the source at offset `+0.00 s` (crop-fidelity SSIM ≥ 0.9 at 9/10 sample times).
- The tracker sidecar records `detected`, `sampled`, `bbox`, `conf`, `crop_center_x` and `target_x` per frame (`sampled` is false for stride-skipped frames, which are excluded from no-detection counts and the missed-frames sheet). `crop_violation_metrics()` checks that the chosen target's bbox centre stays inside the crop window with a configurable margin (25 px); touching the margin is a violation. On a fallback the sidecar is `{"fallback": true, "reason": "..."}` instead of per-frame records; both tools detect that marker and report "tracker fallback used, tracking metrics unavailable" rather than reading a stale sidecar.
- The renderer supports two filtergraph layouts in `compile_plan()`: `center_crop` (video-main overlay + seeded initial x + sendcmd, cropped back to 1080x1920) and `split_screen` (the fallback used by every other layout name: two 1080x960 halves stacked to 1080x1920). `tests/test_layout_render.py` checks each layout's graph string and renders a short 1280x720 `testsrc2` + tone clip through real FFmpeg, asserting 1080x1920, clean decode, non-black first frame and an audio stream. The face detector is faked for `center_crop`, so these tests need no model file, torch or GPU and run in the lightweight CI job.

### Docs
- `docs/ROADMAP.md`         — remaining work and known issues; roadmap source of truth
- `docs/ASSETS.md`          — audio licensing policy and provenance of tracked audio

### Host-side scripts (run outside the app)
- `start.bat`               — one-click launcher: health-checks then starts vLLM (8002),
  backend (8080) and frontend (5173) in minimized windows, in that order. Tunables
  (ports, health URLs, timeouts, LLM script) are at the top of the file; output goes
  to `logs\*.log` and PIDs to `.run\*.pid` (both gitignored). `stop.bat` stops only
  those PIDs. Bootstraps the backend venv when missing.
- `stop.bat`                — stops the processes recorded in `.run\*.pid` and frees the ports.
- `start.ps1`               — legacy PowerShell launcher (backend + frontend only).
- `Start-OpenHands.bat`     — host launcher for the OpenHands Docker/WSL environment (not the app)
- `script.py`, `backend/quantize_meissa.py`, `backend/update_music.py` (stub),
  `backend/fix_paths.py` (one-off DB path migration), `backend/init_db_script.py`,
  `backend/seed_templates.py` — one-off tools, not app code

### Files to skip when grepping / reading
`.git`, `node_modules`, `backend/venv`, `__pycache__`, `dist`, `build`,
`.ruff_cache`, `.pytest_cache`, `data/renders/**`,
`backend/assets/models/*.gguf`, `backend/assets/models/*.safetensors`,
`backend/assets/fonts/**`, `backend/torch-*.whl`, `*.db`, `*.sqlite`,
`haarcascade_frontalface_default.xml`.

## Search discipline

- Trust the Project Map above. Do not enumerate the repo before acting.
- For "where is X implemented?", prefer a targeted grep over whole-tree:
  `rg -n 'symbol' backend/app frontend/src`. Never `rg --files` on the repo root.
- When code needs a filesystem path, import it from
  `backend/app/core/paths.py`. Never introduce a new absolute path in
  service code.
- If the Project Map is wrong or a file is missing, say so in one sentence
  and propose the map update — do not fall back to full-tree exploration.
- After adding or moving a file that appears in the Project Map, update the
  map in the same commit.

# Setup & Run Commands

- **One-click:** run `start.bat` from the repo root. It starts, in order:
  vLLM (`services\vllm\start_vllm.bat`, `http://127.0.0.1:8002/v1`, model
  `meissa-7b-awq`; health `GET /health`), the backend (8080, health
  `/api/status`), and the frontend (5173), then opens the browser. Each service
  is skipped if its health endpoint already answers. Polls every 3s; the LLM
  timeout defaults to 300s (model load is slow) and is tunable at the top of the
  script. On LLM timeout it prints the service name and log path and exits
  before starting the backend. Run `stop.bat` to stop only what it started.
- **Backend:** from `backend/`, activate the venv and run
  `python -m uvicorn app.main:app --reload --port 8080` → `http://localhost:8080`
  (`start.bat` bootstraps the venv with Python 3.12/3.11 when missing).
  `start.ps1` and the Vite proxy also use port 8080.
- **Frontend:** `cd frontend && npm run dev` (Vite on `http://localhost:5173`).
  `npm run build` = `tsc && vite build`.
- **Tests:** from `backend/`, `python -m pytest tests -q` and `ruff check .`.

# 🚨 CRITICAL ARCHITECTURAL RULES 🚨

## 1. File Editing Rules
- Make small, targeted edits. Never rewrite a whole file unless explicitly asked.
- Preserve existing indentation and the file's CRLF/LF line endings.
- Do not use `sed`/`awk`/`cat >` style edits that mangle indentation.

## 2. FFmpeg & Video Rendering
- **CODEC:** ALWAYS use `libx264`. NEVER use `h264_nvenc` (crashes on this hardware).
- **HARDWARE ACCEL:** Do NOT use `-hwaccel cuda`.
- **TIMEOUTS:** ALWAYS pass `timeout=120` to `subprocess.run()`/`run_subprocess()`.
  Long renders may need a larger timeout passed explicitly.
- **ERRORS:** Wrap FFmpeg calls in `try/except` and print `stderr` to expose errors.

## 3. FastAPI & Database
- **BACKGROUND TASKS:** NEVER pass a request-scoped `db` session into a
  `BackgroundTasks` function. Instantiate a new session inside the function
  (`db = SessionLocal()`).
- **ROUTING:** Endpoints must match the frontend's fetch calls exactly (watch for 404s).
- **IMPORTS:** Import new models/sessions at the top of the file.

## 4. vLLM & JSON Parsing
- **FORMAT:** ALWAYS request structured JSON via `response_format={"type": "json_schema", ...}` on the OpenAI-compatible `/v1/chat/completions` call; never send Ollama-only fields (`format`, `keep_alive`).
- **PARSING:** Strip markdown backticks before `json.loads()`.
- **FAIL LOUDLY:** On LLM failure print the RAW output and traceback; never silently
  substitute dummy data.

## 5. Frontend (React)
- **NAVIGATION:** Use `useNavigate` from `react-router-dom`; no `<a href>` for internal routes.
- **API CALLS:** Keep all `fetch()` calls in `frontend/src/lib/api.ts`.
- **STATE:** Do not break the video status polling (`status === 'done'`).

## 6. Audio pipeline rules
- `loudnorm` runs **LAST and exactly once**. When `LOUDNESS_NORMALIZE` is on, the
  filtergraph uses `inline_loudnorm=False` and the two-pass pass in
  `audio_loudness.py` normalizes after the render; inline `loudnorm` appears only
  when `LOUDNESS_NORMALIZE` is off.
- Fixed graph order: voice + SFX mix (`adelay`, `amix` with `normalize=0`) →
  BGM looping (`aloop` before `atrim`) and ducking (`sidechaincompress` controlled
  by the voice) → sum (`amix`) → peak limiter (`alimiter=...:level=0`, only when
  inline loudnorm is off) → `loudnorm`.
- SFX and BGM files resolve through `core/paths.py` (`SFX_DIR`, `MUSIC_DIR`).
- Missing SFX/BGM files are skipped with a logged warning, never a crash.
- With no SFX and no BGM the graph must be byte-identical to plain voice passthrough.

## 7. Public repo
Never commit `.env`, API keys, personal absolute paths, or copyrighted audio.
BGM files are git-ignored; document license/source in a sidecar JSON.

## 8. GPU rules
- Every VRAM-touching stage holds `gpu_lock(stage)` from `core/gpu_lock.py` for
  the minimum span of GPU work, then calls `flush_vram(stage)` at the end.
  The lock is process-wide and re-entrant; `GPULockTimeout` fails loudly.
- vLLM has no per-request unload: VRAM is released by the server lifetime, not per-request. Do not send Ollama's `keep_alive`.
- Never run blocking render work on the event loop: offload with
  `asyncio.to_thread` and instantiate a new `SessionLocal()` inside the worker.

# Testing & Verification

Tooling: Check Context7 before guessing library or framework APIs. The GitHub
MCP server can open PRs and read CodeRabbit review threads on this repo.

Before declaring a task complete:
1. From `backend/`: `ruff check .` and `python -m pytest tests -q`.
2. For frontend changes: `npx tsc --noEmit`.
3. For route changes: verify with `curl` or the FastAPI test client.
4. Update the Project Map here if files were added or moved.

CI (`.github/workflows/ci.yml`) runs `ruff check .` and `python -m pytest tests -q`
on Python 3.12 for every pull request and every push to `main`. CI installs only
lightweight test dependencies (pytest, fastapi, httpx, sqlalchemy, pydantic,
python-dotenv, python-multipart, numpy, openai) plus apt `ffmpeg` — it never
installs torch, torchvision, CUDA wheels or ultralytics. The CI job named
`backend` must pass before merging.
