<div align="center">
  <h1>🎬 CreatorDesk</h1>
  <p><b>An AI-powered, autonomous short-form video editing pipeline.</b></p>

  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" />
  <img src="https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white" />
  <img src="https://img.shields.io/badge/FFmpeg-007808?style=for-the-badge&logo=ffmpeg&logoColor=white" />
</div>

<br/>

## 📖 Overview

CreatorDesk takes raw long-form video, transcribes it, uses a local LLM to find the most viral 60+ second moments, and renders them into vertical (9:16) TikTok/Reels-ready clips with dynamic captions and zoom effects.

> *"I built this to solve the bottleneck of manual short-form editing, leveraging local AI to run entirely offline and eliminate API costs."*

## 📸 Screenshots

<div align="center">
  <img src="https://github.com/user-attachments/assets/53c0d8d2-0a0c-4573-b102-ddc5e6fb1faa" alt="CreatorDesk Dashboard" width="80%" />
</div>

<br/>

## ✨ Key Features

- **🧠 AI Clip Selection:** Uses a local Map-Reduce chunking strategy to analyze entire videos without blowing up the context window.
- **💰 Monetization Ready:** Enforces a minimum 60-second duration for every clip to qualify for TikTok Creator Rewards.
- **🎥 Dynamic Rendering:** Uses FFmpeg to crop to 9:16, apply a slow Ken Burns zoom, and burn in dynamic ASS karaoke captions.
- **💻 Modern Dashboard:** A React + Vite + Tailwind CSS UI with live status polling and clip filtering.
- **🤖 Autonomous Agents:** Configured with the root `AGENTS.md`, custom Microagents, and Stop Hooks to allow AI to safely contribute to the codebase.

## 🏗️ Architecture Overview

CreatorDesk runs two parallel pipelines:

1. **Audio Pipeline:** Raw audio is transcribed using **faster-whisper**. The transcript is chunked, and an AI agent analyzes each chunk to identify engaging moments.
2. **Video Pipeline:** The original video is processed simultaneously. The moments identified by the audio pipeline guide the clipping process.
3. **Final Assembly:** Clips are rendered vertically (9:16) with dynamic effects, captions, and zoom, ready for platform distribution.

## 🛠️ Tech Stack

| Component | Technology |
| :--- | :--- |
| **Backend** | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, SQLite |
| **Frontend** | React, TypeScript, Vite, Tailwind CSS |
| **LLM Inference** | Ollama (Qwen 2.5 Coder) or vLLM |
| **Audio Processing** | faster-whisper (VAD & Transcription) |
| **Video Rendering** | FFmpeg, OpenCV |

## 🚀 Local Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- [FFmpeg](https://ffmpeg.org/) installed and added to your system PATH.
- [Ollama](https://ollama.com/) installed and running.

### 2. Model Setup (Ollama)

Create the agent model with a large context window:

```bash
echo FROM qwen2.5-coder:14b > Modelfile
echo PARAMETER num_ctx 32768 >> Modelfile
echo PARAMETER num_predict 8192 >> Modelfile
ollama create qwen-agent -f Modelfile
```

### 3. Backend Setup

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open your browser and navigate to `http://localhost:5173` (or the port Vite provides). The app connects to the backend API at `http://localhost:8001`.

## 🧠 LLM model setup

> The Ollama / port-8001 instructions above are legacy. The pipeline now uses a
> local vLLM server as described here.

CreatorDesk does not call a hosted LLM API. It runs a local **vLLM** server
(OpenAI-compatible, `http://127.0.0.1:8002/v1`), started automatically by
`start.bat` through `services\vllm\start_vllm.bat`. Readiness is checked at
`GET http://127.0.0.1:8002/health`.

**Model location.** The model directory is passed to vLLM as `--model` and is
controlled by the `VLLM_MODEL` environment variable. Set it in either:

- the gitignored `launcher.env.local.bat` (copy `launcher.env.local.bat.example`
  and uncomment/adjust the `VLLM_MODEL` line), or
- your shell environment before running `start.bat`.

If `VLLM_MODEL` is empty or unset, `services\vllm\start_vllm.bat` falls back to
its built-in default path, so an existing setup keeps working unchanged.

**GPU memory.** The VRAM budget is the `--gpu-memory-utilization` flag in the
`services\vllm` launch script (currently `0.60`). Expected hardware: a **12 GB
GPU** runs the default AWQ model at `--gpu-memory-utilization 0.60` alongside the
Whisper and face-tracking stages. Adjust that flag to match your card.

**Where the model comes from.** The model served at runtime is a local directory
named `meissa-7b-awq`. It is produced from the public base model repo
[`Orion-zhen/Meissa-Qwen2.5-7B-Instruct`](https://huggingface.co/Orion-zhen/Meissa-Qwen2.5-7B-Instruct)
using the AWQ (W4A16) quantization recipe in `backend/quantize_meissa.py` (its
calibration dataset is `neuralmagic/calibration`). To obtain it:

1. Download the base model from the Hugging Face repo linked above.
2. Install `transformers`, `datasets` and `llmcompressor`, adjust `model_id` and
   `output_dir` in `backend/quantize_meissa.py`, then run
   `python backend/quantize_meissa.py` (about 10-15 minutes). It writes the
   `meissa-7b-awq` directory.
3. Point `VLLM_MODEL` at that directory (or rely on the fallback) and run
   `start.bat`.

> **Download link for the pre-quantized `meissa-7b-awq` build: TBD** — the AWQ
> artifact itself is not published in this repository; reproduce it with the
> script above. **License:** none documented in this repository — check the base
> model's Hugging Face card before use.

**Using a different OpenAI-compatible model.** Point `VLLM_MODEL` at any model
directory vLLM can serve, and update the model *name* the backend sends with each
request: the default `meissa-7b-awq` lives in
`backend/app/services/llm_service.py` (`self.model = model or "meissa-7b-awq"`).
The `OLLAMA_MODEL` value in `backend/app/core/config.py` is vestigial and no
longer used by the vLLM pipeline. Keep the name consistent with what vLLM reports
at `GET /v1/models`.

## 📂 Project Structure

- **`backend/`**: FastAPI application (Python, uvicorn)
- **`frontend/`**: React dashboard (npm, vite)
- **`backend/app/api/`**: API route handlers
- **`backend/app/services/`**: Core business logic (llm, render, whisper)
- **`frontend/src/`**: React components, API wrappers
- **`.openhands/`**: Agent skills, setup scripts, hooks
- **`AGENTS.md`**: root AI agent configuration guide

---

<div align="center">
  <i>Built by <a href="https://github.com/sachitdotdev">Sachit Jaswal</a></i>
</div>
