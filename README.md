# CreatorDesk AI

Fully local, zero-cost tool that takes long-form videos, transcribes them with
**faster-whisper**, uses **Ollama** to find the best short clips + generate
titles/descriptions/hashtags/hooks, renders **9:16 vertical clips with FFmpeg +
NVENC + burned captions + templates**, and lets you review/approve them.

Includes a powerful **Template Editor** to create, edit, preview and delete
templates (fonts, colors, positions, watermarks, background, etc.).

## Tech Stack (do not change)

- **Backend:** FastAPI + SQLAlchemy + SQLite + faster-whisper + Ollama + FFmpeg (NVENC)
- **Frontend:** Vite + React + TypeScript + Tailwind + shadcn/ui + React Router + TanStack Query
- **No packaging.** Just `localhost:8000` (API) + `localhost:5173` (UI)

## Hardware

- RTX 4070 Ti (NVENC + CUDA whisper)
- 1 user, 100% local

## Project Structure

```
creatordesk-ai/
├── backend/                # FastAPI app
│   ├── app/
│   │   ├── main.py         # FastAPI app + static mounts + CORS
│   │   ├── core/config.py  # paths, ollama, whisper, ffmpeg settings
│   │   ├── database.py     # SQLAlchemy session + init
│   │   ├── models.py       # Video, Template, Clip, Schedule
│   │   ├── schemas.py      # Pydantic schemas
│   │   ├── api/routes.py   # all REST endpoints
│   │   ├── services/
│   │   │   ├── whisper_service.py   # faster-whisper transcription (SRT/ASS)
│   │   │   ├── llm_service.py       # Ollama clip selection + copy
│   │   │   ├── template_service.py  # CRUD + default templates
│   │   │   └── render_service.py    # FFmpeg NVENC 9:16 + ASS captions + overlay
│   │   └── __init__.py
│   ├── data/
│   │   ├── sources/        # uploaded videos
│   │   ├── renders/        # rendered clips + subtitles + exports
│   │   └── templates/      # (templates live in SQLite)
│   ├── requirements.txt
│   └── venv/               # created on first run
├── frontend/               # Vite + React + TS + Tailwind
│   ├── src/
│   │   ├── main.tsx        # entry + QueryClient + Toaster
│   │   ├── App.tsx         # router + layout + offline guard
│   │   ├── pages/          # 5 pages (studio, clips, templates, scheduler, accounts)
│   │   ├── components/     # layout + shadcn/ui
│   │   ├── lib/            # api (axios) + utils
│   │   ├── types.ts
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts      # proxies /api -> localhost:8000
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── tsconfig.json
├── README.md
```

## Pages

1. **Upload & Auto-Edit Studio** — drag-drop upload, style/vibe selector, start pipeline, progress feedback
2. **Clip Review & Approval** — grid of clips, preview, edit times/hook/title/description/hashtags, change template, approve/reject, re-render, export
3. **Template Editor** — create/edit/duplicate/delete templates with live 9:16 canvas preview + JSON config (fonts, colors, positions, watermarks, background)
4. **Scheduler** — queue rendered/approved clips with platform + scheduled time
5. **Accounts** — export package (video + title + description + hashtags), copy-paste text

## Pipeline

1. `faster-whisper large-v3` with timestamps + VAD
2. **Ollama** returns structured JSON: best clip windows + titles + descriptions + hashtags + hooks (+ vibe/confidence)
3. **FFmpeg** does 9:16 center crop (no face tracking), burns ASS subtitles, applies template (captions/title/watermark/background)
4. Supports vibes: Streamer Hype, Rapper Energy, Technical, Horror, Narrative, Custom

## Default Templates

Streamer Hype, Rapper Energy, Technical, Horror, Narrative, Custom (seeded on first run or via `POST /api/templates/seed`).

## LLM System Prompt

A strong style-aware system prompt instructs the model to pick 4-5 non-overlapping clips (15-60s each) with a clear beginning/peak/resolution, returning JSON with `start`, `end`, `title`, `hook`, `description`, `hashtags`, `vibe`, `confidence`. Each vibe appends targeted copy instructions.

## Quick Start

```powershell
# Backend
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173**.

### One-click startup (Windows)

Double-click **`start.bat`**, or run **`start.ps1`** in PowerShell:

```
# PowerShell (right-click "Run with PowerShell")
.\start.ps1
```

Both scripts:
1. Create the Python venv at `backend/venv` if it doesn't exist
2. Install backend requirements from `backend/requirements.txt`
3. Start the FastAPI backend on `http://localhost:8000` in its own window
4. Run `npm install` (if `node_modules` is missing) and `npm run dev` for the frontend on `http://localhost:5173` in another window

Backend docs: `http://localhost:8000/docs`  
Frontend UI: `http://localhost:5173`

Close each service window to stop it.

### Run everything in one terminal

From the project root (run `npm install` here once):

```
npm run dev
```

This uses the root `package.json` with `concurrently` to run backend and frontend together in a single terminal.

### Prerequisites (install once)

- **FFmpeg** (with NVENC support) — available on PATH as `ffmpeg` and `ffprobe`
- **Ollama** running at `http://localhost:11434` with a model pulled, e.g.:
  `ollama pull llama3.2:3b`
- CUDA-capable GPU (RTX 4070 Ti) for NVENC + faster-whisper `cuda`

If Ollama/FFmpeg are missing, the app still starts and the UI works; transcription/render steps will return clear errors until they are installed.

## Configuration

Edit `backend/app/core/config.py` for:
- `OLLAMA_HOST`, `OLLAMA_MODEL`
- `WHISPER_MODEL`, `WHISPER_DEVICE` (`cuda`/`cpu`)
- `FFMPEG_DEVICE` (`cuda`/`cpu`)
- Output resolution (default `1080x1920 @ 30fps`)

## API

- `GET/POST /api/videos` — upload / list videos
- `POST /api/videos/{id}/process` — start the transcription → LLM → render pipeline
- `GET /api/pipeline/{id}/status` — pipeline progress
- `GET/PUT/DELETE /api/clips` — clip review & updates
- `POST /api/clips/{id}/render` — re-render a clip
- `GET/POST/PUT/DELETE /api/templates` — template CRUD
- `POST /api/templates/seed` — seed default templates
- `GET/POST/PUT/DELETE /api/schedules` — scheduling queue
- `POST /api/accounts/export` — export clip package
- `GET /api/status` — backend health (ollama/ffmpeg)

## Notes

- 100% local — no data leaves your machine.
- No face tracking — pure center crop for 9:16.
- Rendered clips + subtitles are stored in `backend/data/renders/`.
- SQLite database: `backend/data/creatordesk.db`.
