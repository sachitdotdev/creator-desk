# Repository Purpose
Creator Desk is an autonomous, AI-powered short-form video editing pipeline. 
It takes raw uploaded videos, transcribes them via Faster-Whisper, uses a local Ollama LLM to identify the most viral/engaging segments, and renders those segments into vertical (9:16) TikTok/Reels style clips with dynamic captions using FFmpeg.


# Tech Stack
- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy (SQLite), Pydantic.
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router.
- **AI/ML:** Faster-Whisper (Transcription), Ollama (Local LLM for clip generation).
- **Video Processing:** FFmpeg (via `subprocess`).


## Project Map — read this before exploring

The layout below is authoritative. **Do not run `tree`, `find`, `rg --files`,
or `ls -R` at the start of a task.** Open only the files you need.

### Backend (Python / FastAPI)
- `backend/app/main.py`                    — FastAPI app entry
- `backend/app/api/routes.py`              — HTTP routes; .wav globbing for processed sources
- `backend/app/core/config.py`             — settings + ffmpeg binary resolution
- `backend/app/core/paths.py`              — (planned — paths centralization task; not yet created)
- `backend/app/database.py`                — DB session, schema bootstrap
- `backend/app/models.py`                  — SQLAlchemy models (Video, Clip, Template)
- `backend/app/services/whisper_service.py`    — faster-whisper transcription
- `backend/app/services/llm_service.py`        — Ollama client (Meissa / Gemma / Qwen)
- `backend/app/services/edit_compiler.py`      — compile_plan(); FFmpeg filtergraph builder
- `backend/app/services/render_service.py`     — sendcmd / crop render writes
- `backend/app/services/face_tracker.py`       — YOLOv8 face detection
- `backend/app/services/audio_compiler.py`     — Phase 3 audio stages (SFX, ducking)
- `backend/app/services/audio_loudness.py`    — Phase 3 loudness normalization (EBU R128 two-pass loudnorm)
      (planned: `audio_stems.py`)
- `backend/app/services/social_service.py`     — export/distribution stubs
- `backend/app/services/batch_service.py`      — Automated batch video processing
- `backend/app/services/lead_finder.py`        — YouTube Shorts candidate discovery
- `backend/app/services/qc_bot.py`             — Rendered clip quality auditing
- `backend/app/services/template_service.py`   — Template management and defaults
- `backend/app/core/processing_utils.py`       — Robust media processing utilities
- `backend/app/schemas.py`                     — Pydantic models for video and clip data

### Frontend (React / Vite / TypeScript)
- `frontend/src/pages/*.tsx`       — UploadStudio, ClipReview, Scheduler, TemplateEditor, Accounts
- `frontend/src/components/**`     — shared UI
- `frontend/src/lib/api.ts`        — ALL fetch() calls live here
- `frontend/src/lib/utils.ts`      — shared helpers

### Data, models, assets
- `data/`                    — runtime DBs, renders, sources, creators, templates (resolve via `paths.py`)
- `data/sources/processed/`  — processed .wav files (was incorrectly documented as backend/data/...)
- `backend/assets/`          — music, sfx, fonts, models/, yolov8n-face.pt
- `backend/assets/models/`   — LLM / LoRA checkpoints (NOT a top-level `models/` dir)

### Host-side scripts (run outside the container)
- `Start-OpenHands.bat`, `Invisible-OpenHands.vbs` — launchers (host-absolute paths; do NOT "fix")
- `docker-compose.yml` — mounts host project dir → container path
- `update_music.py`, `script.py`, `backend/quantize_meissa.py` — one-off tools, not app code

### Files to skip when grepping / reading
`.git`, `node_modules`, `.venv`, `__pycache__`, `dist`, `build`,
`data/renders/**`, `models/*.gguf`, `models/*.safetensors`,
`backend/assets/fonts/**`, `*.db`, `*.sqlite`,
`haarcascade_frontalface_default.xml`.

## Search discipline

- Trust the Project Map above. Do not enumerate the repo before acting.
- For "where is X implemented?", prefer a targeted grep over whole-tree:
    `rg -n 'symbol' backend/app frontend/src`
  Never `rg --files` or `rg -r` on the repo root.
- When code needs a filesystem path, import it from
  `backend/app/core/paths.py`. Never introduce a new absolute path in
  service code.
- If the Project Map is wrong or a file is missing, say so in one sentence
  and propose the map update — do not fall back to full-tree exploration.
- After adding or moving a file that appears in the Project Map, update the
  map in the same commit.


# Setup & Run Commands
- **Backend:** `cd backend && uvicorn app.main:app --reload` (Runs on `http://127.0.0.1:8080`)
- **Frontend:** `cd frontend && npm run dev` (Runs on `http://localhost:5173`)


# 🚨 CRITICAL ARCHITECTURAL RULES 🚨
Local AI models (like the 9B model currently used) must strictly adhere to these rules to prevent breaking the application.


## 1. File Editing Rules
- **NEVER** use `sed`, `awk`, or `cat > file` to edit code. These break indentation.
- **ALWAYS** write a Python script and use `.replace()` via `execute_bash` to make surgical edits.
- **NEVER** rewrite an entire file unless explicitly instructed. Use targeted replacements.


## 2. FFmpeg & Video Rendering
- **CODEC:** ALWAYS use `libx264` for video encoding. NEVER use `h264_nvenc` (it crashes due to hardware incompatibility).
- **HARDWARE ACCEL:** Do NOT use `-hwaccel cuda`.
- **TIMEOUTS:** ALWAYS add `timeout=120` to `subprocess.run()` calls to prevent the pipeline from hanging indefinitely.
- **ERRORS:** Wrap FFmpeg calls in `try/except` and print `stderr` to expose errors.


## 3. FastAPI & Database
- **BACKGROUND TASKS:** NEVER pass a request-scoped `db` session into a `BackgroundTasks` function. The session closes before the task runs. ALWAYS instantiate a new session inside the function (`db = SessionLocal()`).
- **ROUTING:** Ensure new endpoints match the frontend's fetch calls exactly (watch for 404s).
- **IMPORTS:** If you add a new model or session, always import it at the top of the file.


## 4. Ollama & JSON Parsing
- **FORMAT:** ALWAYS pass `"format": "json"` to the Ollama API payload.
- **PARSING:** Local models frequently return markdown (```json`). Strip backticks before running `json.loads()`.
- **FAIL LOUDLY:** If the LLM fails, print the RAW output and the traceback. Do not silently fall back to dummy data without logging the error.


## 5. Frontend (React)
- **NAVIGATION:** ALWAYS use `useNavigate` from `react-router-dom`. Do NOT use `<a href>` for internal routing.
- **API CALLS:** Keep all `fetch()` calls in `frontend/src/lib/api.ts`.
- **STATE:** Do not break the polling logic for video status (`status === 'done'`).


# Testing & Verification
Before declaring a task complete:
1. Backend changes MUST be verified with `python -m py_compile <file_path>`.
2. Frontend changes MUST be verified by checking for TypeScript errors (`npx tsc --noEmit`) if possible.
3. If modifying API routes, verify the endpoint using a curl command or FastAPI test client.


# ⚙️ Sandbox / Editing Notes (session-learned)

- The repo is mounted at `/workspace` inside the container
    (`docker-compose.yml`: `C:\Projects Openhands:/workspace`, 9p fs).
    Note: earlier docs referred to `/creator-desk` — that path is stale.
- **`file_editor` tool fails to write** on this mount (`Errno 13: Operation not permitted`) and creates a temp file. Use terminal-based Python `.replace()` edits instead (per AGENTS.md rule #1).
- Avoid `grep -r "<port>"` across `backend/` or the whole repo — it chokes on the huge `haarcascade_frontalface_default.xml`, venv, and vLLM service trees. Scope greps to `backend/app` and `frontend/src`, excluding `venv`, `__pycache__`, `.git`, `node_modules`, and `assets`.
- Infra ports left untouched: vLLM :8002, Ollama :11434/11435, Vite UI :5173 (browser auto-open in start.bat).
