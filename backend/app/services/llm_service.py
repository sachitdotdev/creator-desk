"""LLM service using OpenAI client (vLLM) to extract short clips and generate social copy.

Clip selection itself lives in ``app.services.clip_selector`` so the interactive
pipeline and the batch service share one implementation. The public
``generate_clips`` signature is kept here for backwards compatibility.
"""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

client = AsyncOpenAI(base_url="http://localhost:8002/v1", api_key="not-needed")
print("DEBUG: Initialized vLLM Client at http://localhost:8002/v1")

# --- The Pydantic Schema Definitions ---
class TextOperation(BaseModel):
    type: str = Field(default="text")
    start: float
    end: float
    text: str

class SFXOperation(BaseModel):
    # Fields are extended (not replaced) for Phase 3.1 SFX insertion: the LLM may
    # name an effect ("boom"), point at a file explicitly, and control its level.
    type: str = Field(default="sfx")
    start: float
    name: str
    file: str | None = None
    time_sec: float | None = None
    volume: float | None = None

class Clip(BaseModel):
    clip_id: int
    start: float
    end: float
    layout: str = Field(default="center_crop")
    operations: list[TextOperation | SFXOperation]

class ClipsResponse(BaseModel):
    clips: list[Clip]
# ---------------------------------------

class LLMService:
    def __init__(self, host: str | None = None, model: str | None = None):
        self.client = client
        self.model = model or "meissa-7b-awq"

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> list[str]:
        return [self.model]

    async def generate_clips(
        self,
        transcript_segments: list[dict],
        num_clips: int = 5,
        vibe: str = "Streamer Hype",
        custom_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Delegate to the shared whole-video selector (signature preserved)."""
        from app.services.clip_selector import generate_clips as select_clips

        return await select_clips(
            transcript_segments,
            num_clips=num_clips,
            vibe=vibe,
            custom_prompt=custom_prompt,
            client=self.client,
            model=self.model,
        )