
---
name: debugging-rules
type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers: []
---

# Debugging and Bug-Fixing Rules

When debugging or fixing bugs, you MUST follow these rules strictly:

1. **NO HALLUCINATION**: If the `read_file` tool fails, DO NOT pretend you read it. Immediately use `execute_bash` with `cat` or `head` to read the file manually. Do not summarize a file you did not successfully open.
2. **NO SED OR CAT**: Never use `sed`, `awk`, or `cat > file` to write code. Only use Python scripts with `.replace()` via `execute_bash`.
3. **ONE FILE AT A TIME**: Fix the first file, run `py_compile` on it. If it succeeds, move to the second file. Do not try to fix multiple files in one giant script.
4. **EXPOSE ERRORS**: Whenever you add a `try/except` block, you MUST add `import traceback` and `print(traceback.format_exc(), flush=True)` inside the `except` block so the user can see exactly what failed.
5. **STOP IF STUCK**: If a `.replace()` script fails to find the target string, STOP. Print the surrounding lines of code and ask the user for help. Do not rewrite the entire file.

