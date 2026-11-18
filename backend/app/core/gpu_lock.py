"""Process-wide single-tenant GPU lock (Phase 4.0).

Only one VRAM-touching stage may run at a time. The lock is a ``threading.RLock``
so a stage that calls another guarded stage in the same thread (e.g. Whisper's
transcribe -> model load) cannot deadlock itself.

This module deliberately imports **no** ML libraries: the lock must work on CI
machines that have no torch/CUDA installed.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import AsyncIterator, Iterator

from app.core.config import GPU_LOCK_TIMEOUT

logger = logging.getLogger(__name__)

_GPU_LOCK = threading.RLock()


class GPULockTimeout(TimeoutError):
    """Raised when a VRAM stage waits too long for the single-tenant GPU lock."""


@contextlib.contextmanager
def gpu_lock(stage: str, timeout: float | None = None) -> Iterator[None]:
    """Hold the GPU lock for exactly one VRAM stage.

    Logs acquisition (including wait time) and release. Raises
    :class:`GPULockTimeout` instead of blocking forever when ``timeout``
    expires; ``timeout=None`` uses ``GPU_LOCK_TIMEOUT`` from config.
    """
    limit = GPU_LOCK_TIMEOUT if timeout is None else timeout
    start = time.monotonic()
    acquired = _GPU_LOCK.acquire(timeout=limit)
    if not acquired:
        waited = time.monotonic() - start
        logger.error(
            "[GPU-LOCK] %s: timed out after %.3fs (limit %.3fs)",
            stage, waited, limit,
        )
        raise GPULockTimeout(
            f"GPU lock timed out for stage '{stage}' after {waited:.2f}s "
            f"(limit {limit}s)"
        )
    wait = time.monotonic() - start
    logger.info("[GPU-LOCK] %s: acquired after %.3fs", stage, wait)
    try:
        yield
    finally:
        _GPU_LOCK.release()
        logger.info(
            "[GPU-LOCK] %s: released (held %.3fs)",
            stage, time.monotonic() - start - wait,
        )


@contextlib.asynccontextmanager
async def async_gpu_lock(stage: str) -> AsyncIterator[None]:
    """Async view of the same lock; acquisition happens in a worker thread.

    ``threading.RLock`` must be released by the thread that acquired it, so a
    single ``asyncio.to_thread`` job acquires the lock and waits on a
    ``threading.Event`` until the context exits. The event loop itself only
    awaits a Future and is never blocked.
    """
    loop = asyncio.get_running_loop()
    acquired: asyncio.Future[float] = loop.create_future()
    release = threading.Event()

    def _hold_lock() -> None:
        start = time.monotonic()
        if not _GPU_LOCK.acquire(timeout=GPU_LOCK_TIMEOUT):
            waited = time.monotonic() - start
            loop.call_soon_threadsafe(
                acquired.set_exception,
                GPULockTimeout(
                    f"GPU lock timed out for async stage '{stage}' after "
                    f"{waited:.2f}s (limit {GPU_LOCK_TIMEOUT}s)"
                ),
            )
            return
        wait = time.monotonic() - start
        loop.call_soon_threadsafe(
            lambda: None if acquired.done() else acquired.set_result(wait)
        )
        # The lock stays owned by this worker thread for the whole context.
        release.wait()
        _GPU_LOCK.release()

    holder = asyncio.ensure_future(asyncio.to_thread(_hold_lock))
    try:
        wait = await acquired
        logger.info("[GPU-LOCK] %s: acquired after %.3fs (async)", stage, wait)
        try:
            yield
        finally:
            release.set()
    finally:
        release.set()
        # Reap the worker so the RLock is definitely released before returning.
        await holder
