from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.database import get_db
from app.services.whisper_service import WhisperService
from app.services.llm_service import LLMService
from app.services.render_service import RenderService
from app import models

router = APIRouter()

@router.get("/videos")
def get_videos(db: Session = Depends(get_db)): return db.query(models.Video).all()

@router.post("/videos/upload", response_model=int)
async def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    import uuid
    import os
    from datetime import datetime

    filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"
    file_path = os.path.join("backend/data/sources/processed/", filename)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    new_video = models.Video(
        filename=filename,
        original_name=file.filename,
        path=file_path,
        status="uploaded"
    )
    db.add(new_video)
    db.commit()
    db.refresh(new_video)
    return new_video.id





@router.post("/videos/{video_id}/process")
async def process_video(video_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_pipeline, video_id)
    return {"message": "Processing started", "video_id": video_id}

async def _run_pipeline(video_id: str):
    db = SessionLocal()
    try:
        # Get the video from the database
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Call WhisperService to transcribe the video
        whisper_result = WhisperService().transcribe(video.path)
        video.status = "transcribed"
        db.add(video)
        db.commit()

        # Call LLMService to generate clips
        clips = await LLMService().generate_clips(
            transcript_segments=whisper_result.segments,
            num_clips=5,
            vibe="Streamer Hype",
        )

        # Loop through clips, create Clip records, and render each one
        for clip_data in clips:
            clip = models.Clip(
                video_id=video.id,
                start_time=clip_data["start"],
                end_time=clip_data["end"],
                duration=clip_data["end"] - clip_data["start"],
                title=clip_data.get("title", ""),
                description=clip_data.get("description", ""),
                hashtags=", ".join(clip_data.get("hashtags", [])),
                hook=clip_data.get("hook", ""),
                confidence=clip_data.get("confidence", 0.0),
                composite_score=clip_data.get("composite_score", 0.0),
                vibe_category=clip_data.get("vibe_category", "Custom"),
                status="pending",
            )
            db.add(clip)
            db.commit()
            db.refresh(clip)

            # Render each clip
            RenderService(db).render_clip(clip, video)

        # Update video status to done
        video.status = "done"
        db.add(video)
        db.commit()

    except Exception as exc:
        # Set status to error if anything fails
        video.status = "error"
        video.error_message = str(exc)
        db.add(video)
        db.commit()
    finally:
        db.close()

@router.get("/videos/{video_id}/clips")
def get_clips(video_id: str, db: Session = Depends(get_db)): return db.query(models.Clip).filter(models.Clip.video_id == video_id).all()

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)): return db.query(models.Template).all()

@router.get("/status")
def get_status(): return {"status": "ok"}

@router.get("/discover/trending")
def get_trending_sources():
    return [
        {"id": "v1", "title": "Kai Cenat Reacts", "source": "Twitch", "views": "1.2M", "duration": "12:45", "url": "#", "thumbnail": "https://picsum.photos/seed/v1/400/225"},
        {"id": "v2", "title": "Speed IRL Stream", "source": "YouTube", "views": "850K", "duration": "45:10", "url": "#", "thumbnail": "https://picsum.photos/seed/v2/400/225"},
        {"id": "v3", "title": "Adin Ross Moments", "source": "Kick", "views": "2.1M", "duration": "22:30", "url": "#", "thumbnail": "https://picsum.photos/seed/v3/400/225"}
    ]