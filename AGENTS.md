# Repository Purpose
Creator Desk is an autonomous, AI-powered short-form video editing pipeline. 
It takes raw uploaded videos, transcribes them via Faster-Whisper, uses a local Ollama LLM to identify the most viral/engaging segments, and renders those segments into vertical (9:16) TikTok/Reels style clips with dynamic captions using FFmpeg.


# Tech Stack
- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy (SQLite), Pydantic.
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router.
- **AI/ML:** Faster-Whisper (Transcription), Ollama (Local LLM for clip generation).
- **Video Processing:** FFmpeg (via `subprocess`).


# Directory Structure
- `/backend/app/api/`: FastAPI routers (`routes.py`).
- `/backend/app/services/`: Core business logic (`whisper_service.py`, `llm_service.py`, `render_service.py`).
- `/backend/app/models.py`: SQLAlchemy database models (Video, Clip, Template).
- `/backend/app/database.py`: DB connection and `SessionLocal` setup.
- `/frontend/src/pages/`: React views (`UploadStudio.tsx`, `ClipReview.tsx`).
- `/frontend/src/components/`: Reusable UI components.
- `/frontend/src/lib/api.ts`: Centralized fetch calls to the backend.
- `/.openhands/microagents/`: Specialized skill files (React, FastAPI, FFmpeg, Ollama, Debugging).


# Setup & Run Commands
- **Backend:** `cd backend && uvicorn app.main:app --reload` (Runs on `http://127.0.0.1:8000`)
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
