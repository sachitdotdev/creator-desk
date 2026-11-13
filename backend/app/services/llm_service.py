"""LLM service using OpenAI client (vLLM) to extract short clips and generate social copy."""
from __future__ import annotations

import json
import logging
import traceback
from typing import List, Optional, Dict, Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

client = AsyncOpenAI(base_url="http://localhost:8002/v1", api_key="not-needed")
print("DEBUG: Initialized vLLM Client at http://localhost:8002/v1")

logger = logging.getLogger(__name__)

# --- The Pydantic Schema Definitions ---
class TextOperation(BaseModel):
    type: str = Field(default="text")
    start: float
    end: float
    text: str

class Clip(BaseModel):
    clip_id: int
    start: float
    end: float
    layout: str = Field(default="center_crop")
    operations: List[TextOperation]

class ClipsResponse(BaseModel):
    clips: List[Clip]
# ---------------------------------------

SYSTEM_PROMPT = """You are a ruthless TikTok editor. Identify the most viral, scroll-stopping moments in the transcript.

DO NOT just copy random nouns from the transcript (e.g., "CHEESE CARS", "BIODEGRADABLE"). 
You must invent a compelling, emotional hook based on what is being said.

Use one of these PROVEN VIRAL HOOK FORMULAS:
- Negation: "It's not X, it's Y"
- Curiosity Gap: "The truth about X"
- Contrarian: "You've been lied to about X"
- Personal Confession: "I wish I knew this sooner"

CRITICAL INSTRUCTIONS:
1. The "text" field MUST be exactly 3 to 5 WORDS.
2. YOU MUST GENERATE AT LEAST 3 TEXT OPERATIONS PER CLIP. Spread them out across the 60-second duration.
3. The "start" and "end" timestamps for your text operations MUST be absolute timestamps from the original transcript.

EXAMPLES OF BAD HOOKS (DO NOT DO THIS):
- "CHEESE CARS"
- "BIODEGRADABLE"
- "WINDSHIELD WIPERS"

EXAMPLES OF GOOD VIRAL HOOKS (DO THIS):
- "THE TRUTH ABOUT CHEESE"
- "STOP MAKING BAD DECISIONS"
- "WHY YOU FEEL GUILTY"
- "THIS CHANGES EVERYTHING"

Return ONLY valid JSON matching the schema."""

class LLMService:
    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.client = client
        self.model = model or "meissa-7b-awq"

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> List[str]:
        return [self.model]

    async def generate_clips(
        self,
        transcript_segments: List[dict],
        num_clips: int = 5,
        vibe: str = "Streamer Hype",
        custom_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        
        transcript_text = "\n".join(
            f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}"
            for s in transcript_segments
        )
        transcript_text = transcript_text[:4000]

        user_prompt = f"TRANSCRIPT:\n{transcript_text}\n\nTARGET: Select exactly {num_clips} best short clips. Return ONLY valid JSON."

        try:
            # Pass the schema to vLLM to enforce structured JSON output
            schema = ClipsResponse.model_json_schema()
            
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
                response_format={"type": "json_schema", "json_schema": {"name": "clips_response", "schema": schema}}
            )
            
            raw = resp.choices[0].message.content
            print(f"RAW VLLM RESPONSE: {raw}", flush=True)
            
            obj = json.loads(raw)
            clips = obj.get("clips", [])
            
            normalized = []
            for c in clips:
                raw_start = c.get("start", 0.0)
                raw_end = c.get("end", 60.0)
                if isinstance(raw_start, str):
                    raw_start = float(raw_start.replace("s", "").strip())
                if isinstance(raw_end, str):
                    raw_end = float(raw_end.replace("s", "").strip())
                
                if "operations" not in c and "text" in c:
                    ops = [{"type": "text", "start": raw_start, "end": raw_end, "text": c.get("text")}]
                else:
                    ops = c.get("operations", [])
                    
                normalized.append({
                    "start": raw_start,
                    "end": raw_end,
                    "layout": c.get("layout", "center_crop"),
                    "operations": ops
                })
            return normalized
            
        except Exception as exc:
            print(f"LLM CRASHED - FALLING BACK: {exc}", flush=True)
            traceback.print_exc()
            return self._generate_fallback_clips(transcript_segments, num_clips, vibe)

    @staticmethod
    def _generate_fallback_clips(transcript_segments: List[dict], num_clips: int, vibe: str) -> List[Dict[str, Any]]:
        if not transcript_segments: return []
        starts = [s['start'] for s in transcript_segments]
        ends = [s['end'] for s in transcript_segments]
        duration = max(ends) - min(starts)
        step = min(duration / num_clips, 60.0)
        clips = []
        for i in range(num_clips):
            s = min(starts) + (i * step)
            e = s + 61.0
            clips.append({"start": round(s, 1), "end": round(e, 1), "layout": "center_crop", "operations": []})
        return clips