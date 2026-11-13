with open(r'C:\Sachit\Creator Desk\backend\app\services\llm_service.py', 'r') as f:
    lines = f.readlines()

new_text = 'SYSTEM_PROMPT = """You are a viral video director. Identify exactly 3 of the best moments. For each clip, generate a JSON object with '"'"'clip_id'"'"', '"'"'start'"'"' (float), '"'"'end'"'"' (float), '"'"'layout'"'"' ('"'"'center_crop'"'"'), and an '"'"'operations'"'"' array. \n\n\n   CRITICAL: For '"'"'text'"'"' operations, you MUST extract the exact hook as 3 to 5 WORDS ONLY. Do NOT output the entire sentence. Example: '"'"'If you think being gay is a choice'"'"' becomes '"'"'If you think being gay'"'"'. Break long sentences into multiple separate text operations if needed.\n\n\n   Operations can be: {{"type": "text", "start": <float>, "end": <float>, "text": "<string>"}, {"type": "sfx", "start": <float>, "end": <float>, "name": "<string>"}. For '"'"'sfx'"'"', ONLY use '"'"'boom'"'"', '"'"'whoosh'"'"', or '"'"'pop'"'"'. Return ONLY a raw JSON object with a '"'"'clips'"'"' array.""""""'

for i, line in enumerate(lines):
    if line.startswith('SYSTEM_PROMPT ='):
        lines[i] = new_text
        with open(r'C:\Sachit\Creator Desk\backend\app\services\llm_service.py', 'w') as f:
            f.writelines(lines)
        print('Done!')
        break
