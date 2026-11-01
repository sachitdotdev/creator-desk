
---
name: fastapi-backend-rules
type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers: []
---

# FastAPI and SQLAlchemy Backend Rules

You are an expert FastAPI and SQLAlchemy backend developer.

Rules:

1. **ASYNC/AWAIT**: If you write `async def`, you MUST use `await` for any LLM or async network call. If you call a synchronous function inside an async function, it will block the event loop.
2. **BACKGROUND TASKS**: Never pass a request-scoped database session (`db`) into a FastAPI `BackgroundTasks` function. The session closes before the task runs. Background tasks MUST instantiate their own session using `db = SessionLocal()`.
3. **ROUTING**: Ensure all endpoints have the correct path prefix (e.g., `/api/clips`). Check for `404 Not Found` by verifying the frontend URL matches the backend `@router` decorator.
4. **IMPORTS**: If you add a new class or database session, you MUST add the import statement at the top of the file (e.g., `from app.database import SessionLocal`).
5. **DEBUGGING**: Use `print(..., flush=True)` to log to the console so the user can see it in Uvicorn.

