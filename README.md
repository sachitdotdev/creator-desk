Creator Desk is an AI-powered, autonomous short-form video editing pipeline. It takes raw long-form video, transcribes it, uses a local LLM to find the most viral 60+ second moments, and renders them into vertical (9:16) TikTok/Reels-ready clips with dynamic captions and zoom effects.

## ✨ Features
- **AI Clip Selection:** Uses local Ollama with a Map-Reduce chunking strategy to analyze the entire video without blowing up the context window.
- **Monetization Ready:** Enforces a minimum 60-second duration for every clip to qualify for TikTok Creator Rewards.
- **Dynamic Rendering:** Uses FFmpeg to crop to 9:16, apply a slow Ken Burns zoom, and burn in dynamic ASS karaoke captions.
- **Modern UI:** React + Vite + Tailwind CSS dashboard with live status polling and clip filtering.
- **Autonomous Agents:** Configured with OpenHands `AGENTS.md`, custom Microagents, and Stop Hooks to allow AI to safely contribute to the codebase.

## 🛠️ Tech Stack
- **Backend:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, SQLite.
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, React Router.
- **AI & Media:** Ollama (Local LLM), Faster-Whisper (Transcription), FFmpeg (Video Processing).

## 🚀 Local Setup

### 1. Prerequisites
- Python 3.11+
- Node.js 18+
- FFmpeg installed and added to your system PATH.
- Ollama installed and running.

### 2. Model Setup
Create the agent model with a large context window:
```bash
echo FROM qwen2.5-coder:14b > Modelfile
echo PARAMETER num_ctx 32768 >> Modelfile
echo PARAMETER num_predict 8192 >> Modelfile
ollama create qwen-agent -f Modelfile
3. Backend Setup
bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
4. Frontend Setup
bash
cd frontend
npm install
npm run dev
📂 Project Structure
/backend/app/api: FastAPI routes.

/backend/app/services: Core logic (llm_service.py, render_service.py, whisper_service.py).

/frontend/src: React components and API wrappers.

/.openhands: Agent skills, setup scripts, and quality gate hooks.

AGENTS.md: The handbook for AI agents working on this repository.

