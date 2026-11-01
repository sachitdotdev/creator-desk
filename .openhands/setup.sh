#!/bin/bash
# Install backend dependencies
cd backend
pip install -r requirements.txt || pip install fastapi uvicorn sqlalchemy python-dotenv faster-whisper python-multipart httpx
cd ..

# Install frontend dependencies and TypeScript
cd frontend
npm install
npm install -D typescript
cd ..
