"""Phase 4.0 GPU guardrails: lock, VRAM flush and off-loop render.

These tests deliberately avoid torch/CUDA and pytest-asyncio so they run in the
lightweight CI job (which installs no ML wheels).
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import types

import pytest

from app.core import processing_utils
from app.core.gpu_lock import GPULockTimeout, async_gpu_lock, gpu_lock


def test_gpu_lock_serializes_concurrent_threads():
    active = 0
    peak = 0
    counter_lock = threading.Lock()
    barrier = threading.Barrier(4)

    def worker():
        nonlocal active, peak
        barrier.wait()
        with gpu_lock("test:concurrent"):
            with counter_lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with counter_lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert peak == 1


def test_gpu_lock_is_reentrant_in_one_thread():
    done = threading.Event()

    def worker():
        with gpu_lock("test:outer"), gpu_lock("test:inner"):
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert done.is_set()


def test_gpu_lock_timeout_raises_then_releases():
    held = threading.Event()
    release = threading.Event()

    def holder():
        with gpu_lock("test:holder"):
            held.set()
            assert release.wait(timeout=5)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert held.wait(timeout=5)
    try:
        with pytest.raises(GPULockTimeout, match="test:waiter"), gpu_lock(
            "test:waiter", timeout=0.05
        ):
            pass  # pragma: no cover - must never be reached
    finally:
        release.set()
        thread.join(timeout=5)

    acquired = threading.Event()

    def after():
        with gpu_lock("test:after", timeout=1):
            acquired.set()

    waiter = threading.Thread(target=after, daemon=True)
    waiter.start()
    waiter.join(timeout=5)
    assert acquired.is_set()


def test_async_gpu_lock_does_not_block_the_event_loop():
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def holder():
            async with async_gpu_lock("test:async"):
                entered.set()
                await release.wait()

        holder_task = asyncio.create_task(holder())
        await asyncio.wait_for(entered.wait(), timeout=5)

        # A separate task keeps making progress while the GPU lock is held in
        # its worker thread - proof the event loop itself was not blocked.
        async def heartbeat():
            for _ in range(5):
                await asyncio.sleep(0.01)
            return "responsive"

        result = await asyncio.wait_for(heartbeat(), timeout=2)
        assert result == "responsive"

        # The async lock and the sync lock are the same underlying RLock.
        sync_acquired = []

        def try_sync():
            try:
                with gpu_lock("test:sync-while-async", timeout=0.05):
                    sync_acquired.append(True)
            except GPULockTimeout:
                sync_acquired.append(False)

        await asyncio.to_thread(try_sync)
        assert sync_acquired == [False]

        release.set()
        await asyncio.wait_for(holder_task, timeout=5)

    asyncio.run(scenario())


def test_flush_vram_survives_missing_torch_and_failing_comfyui(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)

    def boom():
        raise RuntimeError("ComfyUI is down")

    monkeypatch.setattr(processing_utils, "free_comfyui", boom)
    # Must never raise, even with no torch and a broken ComfyUI hook.
    processing_utils.flush_vram("test:no-torch")


def test_flush_vram_calls_cuda_cleanup_when_available(monkeypatch):
    calls: list[str] = []
    fake_torch = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: calls.append("empty_cache"),
            ipc_collect=lambda: calls.append("ipc_collect"),
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(processing_utils, "free_comfyui", lambda: None)

    processing_utils.flush_vram("test:cuda")

    assert calls == ["empty_cache", "ipc_collect"]


def test_free_comfyui_posts_free_and_never_raises(monkeypatch):
    import httpx

    calls: list[tuple[str, float, dict]] = []

    def fake_post(url, timeout, json):
        calls.append((url, timeout, json))
        return types.SimpleNamespace(
            status_code=200, raise_for_status=lambda: None
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(processing_utils, "COMFYUI_URL", "http://comfy:8188/")
    monkeypatch.setattr(processing_utils, "COMFYUI_FREE_TIMEOUT", 0.25)

    processing_utils.free_comfyui()
    assert calls == [
        (
            "http://comfy:8188/free",
            0.25,
            {"unload_models": True, "free_memory": True},
        )
    ]

    # A non-2xx response is reported by the existing handler, not raised.
    def bad_status(url, timeout, json):
        response = httpx.Response(
            503, request=httpx.Request("POST", url)
        )
        return types.SimpleNamespace(
            status_code=503, raise_for_status=response.raise_for_status
        )

    monkeypatch.setattr(httpx, "post", bad_status)
    processing_utils.free_comfyui()  # must stay non-fatal

    monkeypatch.setattr(processing_utils, "COMFYUI_URL", "")

    processing_utils.free_comfyui()
    assert len(calls) == 1  # unset URL is a silent no-op

    def unreachable(url, timeout, json):
        raise OSError("connection refused")

    monkeypatch.setattr(httpx, "post", unreachable)

    processing_utils.free_comfyui()  # unreachable must not raise


def test_llm_request_keeps_json_format_without_keep_alive():
    from app.services.llm_service import LLMService

    calls: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            content = json.dumps({"clips": []})
            message = types.SimpleNamespace(content=content)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=message)]
            )

    service = LLMService()
    service.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )

    result = asyncio.run(
        service.generate_clips([{"start": 0.0, "end": 1.0, "text": "hello"}])
    )

    assert result == []
    assert "extra_body" not in calls[0]
    assert calls[0]["response_format"]["type"] == "json_schema"


def test_render_worker_uses_fresh_session_and_closes_it(monkeypatch):
    from app.api import routes

    closed: list[bool] = []
    used_sessions: list[object] = []
    rows = iter(
        [
            types.SimpleNamespace(id=11),
            types.SimpleNamespace(id=22),
            types.SimpleNamespace(id=33),
        ]
    )

    class FakeQuery:
        def __init__(self, row):
            self.row = row

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return next(rows)

    class FakeSession:
        def query(self, model):
            return FakeQuery(None)

        def close(self):
            closed.append(True)

    class FakeRenderService:
        def __init__(self, db):
            used_sessions.append(db)

        def render_clip(self, clip, video, template):
            return "/renders/out.mp4"

    def new_session():
        return FakeSession()

    monkeypatch.setattr(routes, "SessionLocal", new_session)
    monkeypatch.setattr(routes, "RenderService", FakeRenderService)

    output = routes._render_clip_in_thread(11, 22, 33)

    assert output == "/renders/out.mp4"
    assert len(used_sessions) == 1
    assert len(closed) == 1
    assert isinstance(used_sessions[0], FakeSession)


def test_whisper_model_load_flushes_vram_when_stage_raises(monkeypatch):
    from app.services import whisper_service

    class FailingModel:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("model load failed")

    fake_fw = types.SimpleNamespace(
        WhisperModel=FailingModel,
        BatchedInferencePipeline=lambda model: types.SimpleNamespace(model=model),
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    flushed: list[str] = []
    monkeypatch.setattr(whisper_service, "flush_vram", flushed.append)

    service = whisper_service.WhisperService()
    with pytest.raises(RuntimeError, match="model load failed"):
        service._load_model()
    assert flushed == ["whisper:model-load"]


def test_whisper_model_load_cuda_fallback_still_flushes(monkeypatch):
    from app.services import whisper_service

    devices: list[str] = []

    class Model:
        def __init__(self, name, device, compute_type):
            devices.append(device)
            if device == "cuda":
                raise RuntimeError("CUDA unavailable")

    fake_fw = types.SimpleNamespace(
        WhisperModel=Model,
        BatchedInferencePipeline=lambda model: types.SimpleNamespace(model=model),
    )
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    flushed: list[str] = []
    monkeypatch.setattr(whisper_service, "flush_vram", flushed.append)

    service = whisper_service.WhisperService()
    assert service._load_model() is not None
    assert devices == ["cuda", "cpu"]
    assert flushed == ["whisper:model-load"]


def _mock_transcribe_env(monkeypatch, tmp_path, *, transcribe_impl, whisperx_stub):
    """Wire a WhisperService.transcribe run without CUDA/ffmpeg/whisperx wheels."""
    import tempfile

    from app.services import whisper_service

    monkeypatch.setattr(tempfile, "mkdtemp", lambda: str(tmp_path))
    monkeypatch.setattr(whisper_service.subprocess, "run", lambda *a, **k: None)
    (tmp_path / "chunk_000.wav").write_bytes(b"fake")

    class FakeBatched:
        def __init__(self, model):
            self.model = model

        def transcribe(self, *args, **kwargs):
            return transcribe_impl()

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(BatchedInferencePipeline=FakeBatched),
    )
    monkeypatch.setitem(sys.modules, "whisperx", whisperx_stub)

    service = whisper_service.WhisperService()
    monkeypatch.setattr(service, "_load_model", lambda: object())
    flushed: list[str] = []
    monkeypatch.setattr(whisper_service, "flush_vram", flushed.append)
    return service, flushed


def test_whisper_transcribe_flushes_vram_when_inference_raises(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("transcribe failed")

    service, flushed = _mock_transcribe_env(
        monkeypatch,
        tmp_path,
        transcribe_impl=boom,
        whisperx_stub=types.SimpleNamespace(
            load_align_model=lambda **k: None, align=lambda *a, **k: None
        ),
    )
    with pytest.raises(RuntimeError, match="transcribe failed"):
        service.transcribe("in.wav")
    # The whole-transcription lock also releases the model and flushes in its
    # own finally, after the per-chunk flush.
    assert flushed == ["whisper:transcribe", "whisper:unload", "whisper:transcribe"]


def test_whisper_alignment_flushes_vram_when_alignment_raises(monkeypatch, tmp_path):
    segment = types.SimpleNamespace(start=0.0, end=1.0, text="hello")

    def ok():
        return ([segment], types.SimpleNamespace(duration=1.0))

    def boom_align(**kwargs):
        raise RuntimeError("alignment failed")

    service, flushed = _mock_transcribe_env(
        monkeypatch,
        tmp_path,
        transcribe_impl=ok,
        whisperx_stub=types.SimpleNamespace(
            load_align_model=boom_align, align=lambda *a, **k: None
        ),
    )
    with pytest.raises(RuntimeError, match="alignment failed"):
        service.transcribe("in.wav")
    assert flushed == [
        "whisper:transcribe",
        "whisper:alignment",
        "whisper:unload",
        "whisper:transcribe",
    ]


def test_face_tracker_flushes_vram_when_detection_raises(monkeypatch, tmp_path):
    from app.services import face_tracker

    model_path = tmp_path / "face.pt"
    model_path.write_bytes(b"fake")
    monkeypatch.setattr(face_tracker, "FACE_MODEL", str(model_path))
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        types.SimpleNamespace(VideoCapture=lambda path: None),
    )

    def boom(*args, **kwargs):
        raise RuntimeError("YOLO failed")

    monkeypatch.setitem(
        sys.modules, "ultralytics", types.SimpleNamespace(YOLO=boom)
    )
    flushed: list[str] = []
    monkeypatch.setattr(face_tracker, "flush_vram", flushed.append)

    sendcmd = tmp_path / "sendcmd.txt"
    result = face_tracker.generate_sendcmd_file(
        "in.mp4", 0.0, 1.0, str(sendcmd)
    )
    assert result is False
    assert flushed == ["face-tracker:yolo"]
    assert sendcmd.read_text(encoding="utf-8").strip() == "0.000 overlay x -420.0;"


def test_concurrent_transcribes_serialize_around_model_load(monkeypatch, tmp_path):
    """Two transcriptions must never each hold a CUDA model at the same time."""
    import tempfile
    from pathlib import Path

    from app.services import whisper_service

    events: list[str] = []
    events_lock = threading.Lock()

    def record(msg: str) -> None:
        with events_lock:
            events.append(msg)

    made_dirs: list[Path] = []

    def make_temp_dir() -> str:
        d = tmp_path / f"chunks_{len(made_dirs)}"
        d.mkdir()
        made_dirs.append(d)
        return str(d)

    def fake_ffmpeg(cmd, *args, **kwargs) -> None:
        Path(cmd[-1].replace("%03d", "000")).write_bytes(b"fake")

    monkeypatch.setattr(tempfile, "mkdtemp", make_temp_dir)
    monkeypatch.setattr(whisper_service.subprocess, "run", fake_ffmpeg)

    class FakeBatched:
        def __init__(self, model):
            self.model = model

        def transcribe(self, *args, **kwargs):
            segment = types.SimpleNamespace(start=0.0, end=1.0, text="hello")
            return ([segment], types.SimpleNamespace(duration=1.0))

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        types.SimpleNamespace(BatchedInferencePipeline=FakeBatched),
    )
    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        types.SimpleNamespace(
            load_align_model=lambda **k: (None, None),
            align=lambda *a, **k: {"segments": []},
        ),
    )
    monkeypatch.setattr(
        whisper_service, "flush_vram", lambda stage: record(f"flush:{stage}")
    )

    first_loading = threading.Event()

    def make_load(name: str, delay: float, started=None):
        def fake():
            record(f"{name}:load-start")
            if started is not None:
                started.set()
            time.sleep(delay)
            record(f"{name}:load-end")
            return object()

        return fake

    def make_unload(name: str):
        def fake():
            record(f"{name}:released")

        return fake

    first = whisper_service.WhisperService()
    second = whisper_service.WhisperService()
    monkeypatch.setattr(first, "_load_model", make_load("first", 0.10, first_loading))
    monkeypatch.setattr(second, "_load_model", make_load("second", 0))
    monkeypatch.setattr(first, "unload_model", make_unload("first"))
    monkeypatch.setattr(second, "unload_model", make_unload("second"))

    t1 = threading.Thread(target=first.transcribe, args=("in.wav",), name="first")
    t2 = threading.Thread(target=second.transcribe, args=("in.wav",), name="second")
    t1.start()
    assert first_loading.wait(timeout=5)
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive() and not t2.is_alive()
    assert events[0] == "first:load-start"
    # Everything the first transcription does - including its final release and
    # VRAM flush - happens before the second one even starts loading a model.
    second_load = events.index("second:load-start")
    first_run = events[:second_load]
    assert "first:load-end" in first_run
    assert "first:released" in first_run
    assert "flush:whisper:transcribe" in first_run
    assert not any(e.startswith("second:") for e in first_run)


def test_qc_audit_runs_off_the_event_loop(monkeypatch, tmp_path):
    """QC's ffprobe subprocess may not block the ASGI event loop."""
    from app.api import routes

    main_thread = threading.get_ident()
    qc_threads: list[int] = []
    entered = threading.Event()
    release = threading.Event()

    def fake_audit(output_path, min_dur, expected_crop_x=False):
        qc_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(timeout=5)
        return True, "ok"

    class FakeTemplate:
        id = 1
        name = "default"
        layout = "split_screen"
        is_default = True

    class FakeVideo:
        id = 1
        path = str(tmp_path / "in.mp4")
        status = "uploaded"
        transcript_path = None
        error_message = None

    class FakeClip:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.id = 99
            self.output_path = "/renders/out.mp4"
            self.file_path = None
            self.status = "pending"
            self.error_message = None

    class FakeQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self.result

    class FakeSession:
        def query(self, model):
            if model is routes.models.Template:
                return FakeQuery(FakeTemplate())
            if model is routes.models.Video:
                return FakeQuery(FakeVideo())
            return FakeQuery(None)

        def add(self, obj):
            pass

        def commit(self):
            pass

        def refresh(self, obj):
            pass

        def close(self):
            pass

    class FakeWhisper:
        def transcribe(self, path):
            return []

    class FakeLLM:
        async def generate_clips(self, **kwargs):
            return [{"start": 0.0, "end": 1.0, "text": "hi"}]

    (tmp_path / "in.mp4").write_bytes(b"fake")
    monkeypatch.setattr(routes, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(routes.models, "Clip", FakeClip)
    monkeypatch.setattr(routes, "WhisperService", FakeWhisper)
    monkeypatch.setattr(routes, "LLMService", FakeLLM)
    monkeypatch.setattr(routes, "audit_clip", fake_audit)
    monkeypatch.setattr(
        routes, "_render_clip_in_thread", lambda *a, **k: "/renders/out.mp4"
    )
    monkeypatch.setattr(routes, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr(routes, "PROCESSED_DIR", tmp_path / "processed")

    async def scenario():
        task = asyncio.create_task(routes._run_pipeline("1"))
        # entered is a threading.Event set from the QC worker; waiting on it
        # directly would block the loop we are trying to prove is responsive.
        await asyncio.to_thread(entered.wait, 5)
        assert entered.is_set()
        # The loop must keep making progress while QC is blocked in its worker.
        for _ in range(5):
            await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())
    assert qc_threads and qc_threads[0] != main_thread
