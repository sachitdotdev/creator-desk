
import re
import os

def update_routes():
    path = "backend/app/api/routes.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Find _run_pipeline and insert the progress update
    # We look for the section where the transcript is finished and LLM is called.
    # Original:
    #         ws.reset()
    #         clear_gpu_memory()
    # 
    #         _set_progress(video_id, 35, "Selecting clips with AI...")
    # 
    #         # --- 2. LLM clip selection
    #         llm = llm_service.LLMService()
    
    # Looking for the specific location:
    #        ws.reset()
    #        clear_gpu_memory()
    # 
    #        _set_progress(video_id, 35, "Selecting clips with AI...")
    # 
    #         # --- 2. LLM clip selection
    
    # I will use a precise replacement for the segment between clear_gpu_memory() and llm = llm_service.LLMService()
    
    pattern = r"(clear_gpu_memory\(\)\n\s*)\n\s*(#\s*---\s*2\.\s*LLM clip selection)"
    new_content = re.sub(pattern, r"\1\n\s*_set_progress(video_id, 35, \"Selecting clips with AI...\")\n\n\s*\2", content)
    
    with open(path, "w") as f:
        f.write(new_content)

def update_llm_service():
    path = "backend/app/services/llm_service.py"
    with open(path, "r") as f:
        content = f.read()

    new_func = """
    async def generate_clips(
        self,
        transcript_segments: List[dict],
        num_clips: int = 5,
        vibe: str = "Streamer Hype",
        custom_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        \"\"\"Call Ollama and return parsed clip list, with a fail-safe fallback.\"\"\"
        # Build transcript text with timestamps
        transcript_text = "\\n".join(
            f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}"
            for s in transcript_segments
        )
        
        # Chunking
        chunk_size = 8000
        overlap = 500
        chunks = []
        start = 0
        while start < len(transcript_text):
            chunks.append(transcript_text[start : start + chunk_size])
            start += chunk_size - overlap
            if start >= len(transcript_text):
                break

        system = SYSTEM_PROMPT_BY_VIBE.get(vibe, SYSTEM_PROMPT)
        if custom_prompt:
            system += f"\\n\\nCustom instructions: {custom_prompt}\\n"

        all_clips = []
        total_chunks = len(chunks)

        # Map (Process Chunks)
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{total_chunks}...")
            user_prompt = f\"\"\"
            Here is a portion of the transcript. Find the best 1 or 2 clips in this portion that meet the 60-second criteria.
            
            TRANSCRIPT PORTION:
            {chunk}
            
            Return ONLY valid JSON matching the schema. No markdown, no explanation.
            \"\"\"
            
            try:
                client = await self._client_instance()
                resp = await client.post(
                    "/api/generate",
                    json={
                        "model": "qwen2.5-coder:3b",
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
                chunk_clips = self._parse_response(raw)
                all_clips.extend(chunk_clips)
            except Exception as exc:
                logger.warning(f"Chunk {i+1} failed ({exc}). Skipping.")

        # Reduce (Sort and Filter)
        # Sort all clips by composite_score descending
        all_clips.sort(key=lambda x: x.get("composite_score", 0.0), reverse=True)
        
        # Return only the top num_clips
        top_clips = all_clips[:num_clips]

        # Filter out clips shorter than 60 seconds (final check)
        final_clips = []
        for clip in top_clips:
            duration = clip["end"] - clip["start"]
            if duration >= 60:
                final_clips.append(clip)
            else:
                logger.warning(f"Clip duration {duration:.1f}s is too short even after selection. Skipping.")

        if not final_clips:
            return self._generate_fallback_clips(transcript_segments, num_clips)

        return final_clips
"""

    # Find the function by its signature
    # The structure of generate_clips in llm_service.py:
    #    async def generate_clips(
    #        self,
    #        transcript_segments: List[dict],
    #        num_clips: int = 5,
    #        vibe: str = "Streamer Hype",
    #        custom_prompt: Optional[str] = None,
    #    ) -> List[Dict[str, Any]]:
    
    # This regex targets the function and its body until the next method definition (_parse_response)
    pattern = r"async def generate_clips\s*\((.*?)\)\s*->\s*List\[Dict\[str, Any\]\]:.*?def _parse_response"
    
    # We use DOTALL so . matches newlines
    new_content = re.sub(pattern, new_func, content, flags=re.DOTALL)
    
    with open(path, "w") as f:
        f.write(new_content)

if __name__ == "__main__":
    update_routes()
    update_llm_service()
    print("Done")
