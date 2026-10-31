"""Verify batch sidecar metadata is written next to a captioned render."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from app.services.batch_service import BatchService  # noqa: E402


def main() -> int:
    # Pick an existing rendered clip MP4 (produced by test_render.py).
    renders = Path("data/renders")
    mp4s = sorted(renders.glob("clip_*.mp4"))
    if not mp4s:
        print("No rendered clip MP4 found; run test_render.py first.")
        return 1
    clip_mp4 = mp4s[0]
    print(f"Using render: {clip_mp4.name}")

    # Write sidecar metadata via BatchService (no DB needed for this helper).
    from app.database import Base  # noqa: E402
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.models  # noqa: E402

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        batch = BatchService(db)
        meta = {
            "clip_id": 999,
            "title": "Demo Kinetic Clip",
            "description": "Ready-to-post vertical short.",
            "hashtags": "#shorts #demo",
            "start_time": 0.0,
            "end_time": 5.0,
            "duration": 5.0,
            "output_path": str(clip_mp4),
            "status": "rendered",
        }
        meta_path = batch.write_sidecar_metadata(str(clip_mp4), meta)
    finally:
        db.close()

    # Verify sidecar exists and is valid JSON with expected keys.
    assert meta_path.exists(), f"sidecar not written: {meta_path}"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    for k in ("clip_id", "title", "output_path", "status", "duration"):
        assert k in data, f"missing key {k}"
    assert meta_path == clip_mp4.with_suffix(".json"), "sidecar not beside the mp4"
    print(f"Sidecar written: {meta_path.name}")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\n=== BATCH SIDECAR VERIFICATION PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
