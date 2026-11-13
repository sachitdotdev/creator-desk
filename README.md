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

## ✨ Key Features
- **🧠 AI Clip Selection:** Uses a local Map-Reduce chunking strategy to analyze entire videos without blowing up the context window.
- **💰 Monetization Ready:** Enforces a minimum 60-second duration for every clip to qualify for TikTok Creator Rewards.
- **🎥 Dynamic Rendering:** Uses FFmpeg to crop to 9:16, apply a slow Ken Burns zoom, and burn in dynamic ASS karaoke captions.
- **💻 Modern Dashboard:** A React + Vite + Tailwind CSS UI with live status polling and clip filtering.
- **🤖 Autonomous Agents:** Configured with OpenHands `AGENTS.md`, custom Microagents, and Stop Hooks to allow AI to safely contribute to the codebase.

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
