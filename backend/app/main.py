import logging
import httpx
from typing import List

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL, RENDERS_DIR, SOURCES_DIR
from app.database import init_db
from app.api import routes
import app.services.llm_service as llm_service

app = FastAPI(title="CreatorDesk AI", version="1.0.0")

logger = logging.getLogger("creatordesk")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"INCOMING REQUEST: {request.method} {request.url.path}", flush=True)
    response = await call_next(request)
    return response

# Static file serving for renders and sources
import os

from app.core.config import RENDERS_DIR

os.makedirs(RENDERS_DIR, exist_ok=True)
app.mount("/renders", StaticFiles(directory=str(RENDERS_DIR)), name="renders")
app.mount("/sources", StaticFiles(directory=str(SOURCES_DIR)), name="sources")

app.include_router(routes.router, prefix="/api")


# async def _init_ollama() -> None:
#     """Initialize Ollama at startup: fetch pulled models via GET /api/tags
#     and auto-select the first one as the active model for LLM prompts."""
#     base = OLLAMA_BASE_URL
#     try:
#         models: List[str] = await llm_service.detect_available_models(base)
#     except Exception as exc:
#         logger.warning(
#             "Ollama is not reachable at %s (%s). LLM features will be unavailable "
#             "until Ollama is running and a model is pulled.",
#             base,
#             exc,
#         )
#         models = []
#
#     if models:
#         listed = "\n".join(f"    - {name}" for name in models)
#         logger.info(
#             "Ollama models available at %s:\n%s", base, listed
#         )
#         active = models[0]
#         llm_service.set_active_model(active)
#         logger.info(
#             "Active Ollama model: %s (configured fallback: %s)",
#             active,
#             OLLAMA_MODEL,
#         )
#     else:
#         logger.warning(
#             "No Ollama models found at %s; using configured fallback: %s",
#             OLLAMA_BASE_URL,
#             OLLAMA_MODEL,
#         )
#
#
# @app.on_event("startup")
# async def on_startup():
#     init_db()
#     await _init_ollama()


@app.get("/")
def root():
    return {"name": "CreatorDesk AI", "version": "1.0.0", "status": "ok"}


# @app.get("/health")
# async def health():
#     ollama_available = False
#     models: List[str] = []
#     try:
#         models = await llm_service.detect_available_models(OLLAMA_BASE_URL)
#         ollama_available = True
#     except Exception:
#         pass
#     return {
#         "status": "healthy",
#         "ollama_available": ollama_available,
#         "ollama_host": OLLAMA_BASE_URL,
#         "ollama_active_model": llm_service.get_active_model(),
#         "ollama_models": models,
#     }

@app.get("/v1/models")
async def proxy_models():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://127.0.0.1:11434/v1/models")
            return response.json()
        except Exception as e:
            return {"error": str(e)}
