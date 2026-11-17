# Repository Purpose

Creator Desk is an autonomous, AI-powered short-form video editing pipeline.
It takes raw uploaded videos, transcribes them via Faster-Whisper, uses a local
Ollama LLM to identify the most viral/engaging segments, and renders those
segments into vertical (9:16) TikTok/Reels style clips with dynamic captions
using FFmpeg.

# Tech Stack

- **Backend:** Python 3.12 (launchers fall back to 3.11), FastAPI, Uvicorn,
  SQLAlchemy (SQLite), Pydantic.
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router,
  TanStack Query.
- **AI/ML:** Faster-Whisper (transcription), Ollama (local LLM).
- **Video/Audio:** FFmpeg (via `subprocess`).

## Project Map — read this before exploring

The layout below is authoritative. **Do not run `tree`, `find`, `rg --files`,
or `ls -R` at the start of a task.** Open only the files you need.

### Backend (Python / FastAPI)
- `backend/app/main.py`                    — FastAPI app entry; mounts `/api`, `/renders`, `/sources`
- `backend/app/api/routes.py`              — HTTP routes (videos, clips, templates, accounts, `/api/music`)
- `backend/app/core/config.py`             — settings + ffmpeg binary resolution
- `backend/app/core/paths.py`              — single source of truth for filesystem paths
- `backend/app/core/processing_utils.py`   — robust media processing utilities (`run_subprocess`)
- `backend/app/database.py`                — DB session, schema bootstrap
- `backend/app/models.py`                  — SQLAlchemy models (Video, Clip, Template)
- `backend/app/schemas.py`                 — Pydantic models
- `backend/app/services/whisper_service.py`    — faster-whisper transcription
- `backend/app/services/llm_service.py`        — Ollama client (Meissa / Gemma / Qwen)
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

### Tests & tooling
- `backend/tests/`          — pytest suite (audio graph, loudness, music, render, BGM templates)
- `backend/ruff.toml`       — ruff config (FastAPI `Depends` allowed in defaults)

### Host-side scripts (run outside the app)
- `start.bat`, `start.ps1`  — one-click launchers (venv + backend + frontend; host-absolute paths)
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

- **Backend:** from `backend/`, activate the venv and run
  `python -m uvicorn app.main:app --reload --port 8080` → `http://localhost:8080`
  (`start.bat` creates the venv with Python 3.12/3.11, installs
  `requirements.txt`, and starts both apps). `start.ps1` and the Vite proxy
  still reference port 8000 — stale.
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

## 4. Ollama & JSON Parsing
- **FORMAT:** ALWAYS pass `"format": "json"` to the Ollama API payload.
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

# Testing & Verification

Before declaring a task complete:
1. From `backend/`: `ruff check .` and `python -m pytest tests -q`.
2. For frontend changes: `npx tsc --noEmit`.
3. For route changes: verify with `curl` or the FastAPI test client.
4. Update the Project Map here if files were added or moved.

No CI workflow is checked in yet; when one is added it must run these same
checks on every PR.
