import sys
import os
import traceback
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd() + "/backend")

from app.database import SessionLocal
from app import models
from app.core.config import RENDERS_DIR, DATA_DIR
from app.services import whisper_service, llm_service, render_service
from app.api.routes import _run_pipeline

# Mock some environment variables if needed
os.environ["PYTHONPATH"] = "backend"

def main():
    db_session = SessionLocal()
    try:
        # Find a video that is either 'uploaded' or 'transcribing' or 'error'
        # We'll pick one from data/sources
        video = db_session.query(models.Video).filter(models.Video.status.in_(["uploaded", "transcribing", "error"])).first()
        if not video:
            print("No suitable video found. Try adding one to backend/data/sources")
            return

        print(f"Processing video ID: {video.id} - {video.filename}")
        # We need to make sure video.path is correct and it exists
        # In our case, it's already there.
        
        # Call the pipeline
        _run_pipeline(
            video_id=video.id,
            num_clips=5,
            template_id=None,
            vibe="Streamer Hype"
        )
        print("Pipeline completed successfully!")
    except Exception:
        traceback.print_exc()
    finally:
        db_session.close()

if __name__ == "__main__":
    main()
