
---
name: creator-desk-rules
type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers: []
---

# Creator Desk Project Rules

This microagent contains the strict project rules for Creator Desk. You must ALWAYS follow these rules:

1. **NO DESTRUCTIVE SHELL COMMANDS**: Never use `sed`, `awk`, `str_replace_editor`, `cat > file << EOF`, or `git checkout` to modify code. They break Python indentation.
2. **SURGICAL EDITS ONLY**: Always write a short Python script using the `.replace(old, new)` method to modify existing files.
3. **HARDWARE LIMITATIONS**: This machine has a 12GB GPU but severe CUDA DLL issues. ALWAYS force Faster-Whisper to use CPU (`compute_type="int8"`). ALWAYS force FFmpeg to use CPU (`libx264`) instead of NVENC (`h264_nvenc`).
4. **VERIFY YOUR WORK**: After editing any Python file, always run `python -m py_compile <file>` to ensure there are no syntax errors.
5. **NO HALLUCINATING CODE**: Read the file first to understand the exact context before writing your `.replace()` script.

