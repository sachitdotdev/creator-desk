"""LLM service using Ollama to extract short clips and generate social copy."""
from __future__ import annotations

import json
import re
import logging
import traceback
from typing import List, Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)
from app.core.config import OLLAMA_BASE_URL, OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_ACTIVE_MODEL


# Strong system prompt tuned for short-form clip selection + copy generation.
SYSTEM_PROMPT = """CRITICAL: You MUST generate clips that are between 61 and 90 seconds long. Do not generate clips shorter than 60 seconds.
You are an expert short-form video editor and social-media strategist.
Your job is to watch a video transcript (with timestamps) and pick the BEST 4-5 short clips
suitable for TikTok / Instagram Reels / YouTube Shorts (vertical 9:16).
...

For each clip you must return:
- start: float (start timestamp in seconds)
- end: float (end timestamp in seconds)
- title: string (short, scroll-stopping title, <= 60 chars)
- hook: string (the first 1-2 seconds hook line, <= 40 chars)
- description: string (1-2 sentences, <= 200 chars)
- hashtags: array of 3-6 hashtag strings (include #)
- vibe_category: one of ["Streamer Hype", "Rapper Energy", "Technical", "Horror", "Narrative"]
- confidence: float 0-1 (how strong this clip is)
- composite_score: float 0-1 (overall quality score)

Selection rules:
- Generate clips strictly between 60.5 seconds and 90.0 seconds.
- Ensure each clip contains a complete HOOK (0-5s), DENSE BODY (5-75s), and CTA/LOOP CLOSE (75-90s).
- Filter out any clip where the transcript has long silent gaps or low speech density.
- Clips must not overlap each other.
- Pick the most emotional, surprising, funny, or insightful moments.
- Return exactly 4-5 clips unless the transcript is too short.

Output ONLY valid JSON, no markdown fences, no extra text:
{
  "clips": [
    {
      "start": 60.5,
      "end": 90.0,
      "title": "...",
      "hook": "...",
      "description": "...",
      "hashtags": ["#example", "#shorts"],
      "vibe_category": "Streamer Hype",
      "confidence": 0.95,
      "composite_score": 0.9
    }
  ]
}
"""

VIBE_PROMPTS = {
    "Streamer Hype": "High energy, excited tone, gaming/streaming moments, big reactions, all-caps emphasis.",
    "Rapper Energy": "Confident, boastful, rhythm-focused, street-style, punchlines.",
    "Technical": "Informative, precise, tutorial-style, step-by-step, clean.",
    "Horror": "Dark, suspenseful, eerie, slow reveal, chilling.",
    "Narrative": "Story-driven, emotional, character-focused, cinematic.",
    "Custom": "User-defined template style.",
}

SYSTEM_PROMPT_BY_VIBE: Dict[str, str] = {
    vibe: SYSTEM_PROMPT + f"\n\nVibe focus: {VIBE_PROMPTS[vibe]}\nMake all copy match this vibe.\n"
    for vibe in VIBE_PROMPTS
}


#: Active model resolved at startup (auto-detected from GET /api/tags).
#: Downstream LLM prompts (titles, hashtags, script hooks) use this so they
#: never target a model that Ollama hasn't pulled (no 404s).
ACTIVE_MODEL: Optional[str] = None


def set_active_model(name: Optional[str]) -> None:
    """Set the active model (called during startup auto-detection)."""
    global ACTIVE_MODEL
    ACTIVE_MODEL = name


def get_active_model() -> str:
    """Return the active model, falling back to the configured default."""
    return ACTIVE_MODEL or OLLAMA_MODEL


async def detect_available_models(host: str = OLLAMA_BASE_URL) -> List[str]:
    """Query GET /api/tags and return the list of pulled model names."""
    async with httpx.AsyncClient(
        base_url=host.rstrip("/"), timeout=httpx.Timeout(10.0)
    ) as client:
        resp = await client.get("/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


class LLMService:
    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = (host or OLLAMA_HOST).rstrip("/")
        # Use the startup-detected active model first, then the explicit
        # argument, then the configured default (never an unpulled model).
        self.model = model or get_active_model()
        self._client: Optional[httpx.AsyncClient] = None

    async def _client_instance(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.host, timeout=httpx.Timeout(300.0))
        return self._client

    async def is_available(self) -> bool:
        try:
            client = await self._client_instance()
            resp = await client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        try:
            client = await self._client_instance()
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    async def ensure_model(self) -> bool:
        """Pull the model if missing (best-effort)."""
        try:
            models = await self.list_models()
            if self.model in models:
                return True
            client = await self._client_instance()
            await client.post("/api/pull", json={"name": self.model}, timeout=httpx.NoneTimeout())
            return True
        except Exception:
            return False

    async def generate_clips(
        self,
        transcript_segments: List[dict],
        num_clips: int = 5,
        vibe: str = "Streamer Hype",
        custom_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Call Ollama and return parsed clip list, with a fail-safe fallback."""
        # Build transcript text with timestamps
        transcript_text = "\n".join(
            f"[{s.start:.1f}s - {s.end:.1f}s] {s.text}"
            for s in transcript_segments
        )
        transcript_text = transcript_text[:15000]
        system = SYSTEM_PROMPT_BY_VIBE.get(vibe, SYSTEM_PROMPT)
        if custom_prompt:
            system += f"\n\nCustom instructions: {custom_prompt}\n"

        user_prompt = f"""
TRANSCRIPT (with timestamps):
{transcript_text}

TARGET: Select exactly {num_clips} best short clips.
Return ONLY valid JSON matching the schema. No markdown, no explanation.
"""

        try:
            client = await self._client_instance()
            logger.info(f"Sending {len(transcript_text)} characters to Ollama. Waiting for response...")
            resp = await client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "system": system,
                    "prompt": user_prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.4,
                        "num_predict": 1024,
                        "num_ctx": 32768,
                    },
                },
                timeout=120.0,
            )
            resp.raise_for_status()

            data = resp.json()
            raw = data.get("response", "{}")
            clips = self._parse_response(raw)

            # Filter out clips shorter than 60 seconds
            clips = [clip for clip in clips if (clip["end"] - clip["start"]) >= 60]

            for clip in clips:
                duration = clip["end"] - clip["start"]
                if duration < 60:
                    logger.warning(f"Clip duration {duration:.1f}s is too short. Expanding to 61.0s.")
                    clip["end"] = clip["start"] + 61.0

            return clips
        except Exception as exc:
            print(f"LLM CRASHED - FALLING BACK TO DUMMY CLIPS: {exc}", flush=True)
            print(f"Raw response: {raw}", flush=True)
            print(traceback.format_exc(), flush=True)
            logger.warning(f"LLM request failed ({exc}). Falling back to equal-length clips.")
            return self._generate_fallback_clips(transcript_segments, num_clips, vibe)

    def _parse_response(self, raw: str) -> List[Dict[str, Any]]:
        """Parses the LLM response and returns a list of normalized clip dictionaries."""
        # Strip any markdown fences just in case
        cleaned = re.sub(r"```json|```", "", raw).strip()
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find a JSON object inside the text
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    obj = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return []
            else:
                return []
        
        clips = obj.get("clips", []) if isinstance(obj, dict) else []
        normalized = []
        for c in clips:
            try:
                normalized.append({
                    "start": float(c.get("start", 0)),
                    "end": float(c.get("end", 0)),
                    "title": str(c.get("title", ""))[:80],
                    "hook": str(c.get("hook", ""))[:60],
                    "description": str(c.get("description", ""))[:300],
                    "hashtags": c.get("hashtags", []) if isinstance(c.get("hashtags"), list) else [],
                    "vibe_category": str(c.get("vibe_category", "Custom")),
                    "confidence": float(c.get("confidence", 0.8)),
                    "composite_score": float(c.get("composite_score", 0.8)),
                })
            except Exception:
                continue
        return normalized

    @staticmethod
    def _generate_fallback_clips(transcript_segments: List[dict], num_clips: int, vibe: str) -> List[Dict[str, Any]]:
        """Generates equal-length clip windows as a fallback when the LLM is unreachable."""
        if not transcript_segments:
            return []

        # Find the range of the transcript
        starts = [s.start for s in transcript_segments]
        ends = [s.end for s in transcript_segments]
        min_start = min(starts)
        max_end = max(ends)
        duration = max_end - min_start

        if duration <= 0:
            duration = 60.0

        step = duration / num_clips
        clips: List[Dict[str, Any]] = []
        for i in range(num_clips):
            s = min_start + (i * step)
            e = min(s + step, max_end)
            
            # Ensure minimum duration of 61.0 seconds
            if e - s < 61.0:
                e = s + 61.0
            
            # If even after expansion we're still too close to max_end, 
            # we might need to adjust the step or just accept slightly larger chunks
            # For fallback, we just want to ensure we cover the transcript and satisfy num_clips
            
            # If the step is too small to satisfy the 61s requirement, we might need to
            # adjust the way we spread the clips.
            # But for now, let's just do the expansion.
            
            clips.append({
                "start": round(s, 1),
                "end": round(e, 1),
                "title": f"Clip {i+1}",
                "hook": "Check this out",
                "description": "Auto-generated clip.",
                "hashtags": ["#shorts", "#viral"],
                "vibe_category": vibe,
                "confidence": 0.5,
            })
        return clips

    @staticmethod
    def snap_and_trim_timestamps(self, clips: List[Dict[str, Any]], transcript_words: List[Any]) -> List[Dict[str, Any]]:
        """
        Snaps start times to the beginning of the nearest spoken word.
        Snaps end times to the end of the nearest spoken word.
        Rejects clips that contain silent gaps longer than 1.5 seconds.
        Guarantees minimum duration of 61.0 seconds.
        """
        processed_clips = []
        for clip in clips:
            # Find nearest word for start
            best_start_word = None
            min_start_diff = float("inf")
            for word in transcript_words:
                diff = abs(word.start - clip["start"])
                if diff < min_start_diff:
                    min_start_diff = diff
                    best_start_word = word
            
            clip["start"] = best_start_word.start if best_start_word else clip["start"]

            # Find nearest word for end
            best_end_word = None
            min_end_diff = float("inf")
            for word in transcript_words:
                diff = abs(word.end - clip["end"])
                if diff < min_end_diff:
                    min_end_diff = diff
                    best_end_word = word
            
            clip["end"] = best_end_word.end if best_end_word else clip["end"]

            # Check for silent gaps > 1.5s
            # We can check this by seeing if any large gaps exist between words within the clip range
            # Or more simply, if there is a gap > 1.5s between any two adjacent words in the transcript
            # that fall within this clip's timeframe.
            
            has_large_gap = False
            # This is a bit simplified, but let's check adjacent words in transcript_words
            for i in range(len(transcript_words) - 1):
                w1 = transcript_words[i]
                w2 = transcript_words[i+1]
                if w1.end < clip["start"] or w2.start > clip["end"]:
                    continue
                if w2.start - w1.end > 1.5:
                    has_large_gap = True
                    break
            
            if not has_large_gap:
                # Ensure minimum duration of 61.0 seconds
                if clip["end"] - clip["start"] < 61.0:
                    # Extend the end to reach 61s if possible
                    clip["end"] = clip["start"] + 61.0
                
                processed_clips.append(clip)
        
        return processed_clips
