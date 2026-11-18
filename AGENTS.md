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
- `backend/app/core/config.py`             — settings + ffmpeg binary resolution
- `backend/app/core/gpu_lock.py`           — process-wide single-tenant GPU lock (sync + async)
- `backend/app/core/paths.py`              — single source of truth for filesystem paths
- `backend/app/core/processing_utils.py`   — robust media processing utilities (`run_subprocess`)
- `backend/app/database.py`                — DB session, schema bootstrap
- `backend/app/models.py`                  — SQLAlchemy models (Video, Clip, Template)
- `backend/app/schemas.py`                 — Pydantic models
- `backend/app/services/whisper_service.py`    — faster-whisper transcription
- `backend/app/services/llm_service.py`        — vLLM (OpenAI-compatible) client at http://127.0.0.1:8002/v1, model `meissa-7b-awq`
- `backend/app/services/edit_compiler.py`      — `compile_plan()`; FFmpeg filtergraph builder
- `backend/app/services/render_service.py`     — render orchestration; BGM settings, two-pass loudnorm hook
- `backend/app/services/face_tracker.py`       — YOLOv8 face detection
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
- `backend/tests/`          — pytest suite (audio graph, loudness, music, render, BGM templates)
- `backend/ruff.toml`       — ruff config (FastAPI `Depends` allowed in defaults)
- `.github/workflows/ci.yml` — CI job `backend` (ruff + pytest on Python 3.12, lightweight deps only)
- `.coderabbit.yaml`        — CodeRabbit review config + path-specific instructions

### Docs
- `docs/ROADMAP.md`         — remaining work and known issues; roadmap source of truth

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
