from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
import os
import glob
import json
import shutil
import traceback
from pathlib import Path
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.database import get_db
from app.services.whisper_service import WhisperService
from app.services.llm_service import LLMService
from app.services.render_service import RenderService
from app.services.qc_bot import audit_clip
from app import models
from app.core.config import BASE_DIR, SOURCES_DIR, TRANSCRIPTS_DIR

router = APIRouter()

@router.get("/videos")
def get_videos(db: Session = Depends(get_db)):
    return db.query(models.Video).filter(
        models.Video.status.notin_(["processing", "rendering"])
    ).all()

@router.post("/videos/upload", response_model=int)
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    os.makedirs(SOURCES_DIR, exist_ok=True)
    print(f"RECEIVED UPLOAD: {file.filename}", flush=True)

    import uuid

    filename = f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"
    file_path = str(SOURCES_DIR / "processed" / filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_video = models.Video(
        filename=filename,
        original_name=file.filename,
        path=file_path,
        status="uploaded"
    )
    db.add(new_video)
    db.commit()
    db.refresh(new_video)
    print(f"UPLOAD SUCCESS: Saved video {new_video.id} - {new_video.filename}", flush=True)
    return new_video.id





@router.post("/videos/{video_id}/process")
async def process_video(video_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_pipeline, video_id)
    return {"message": "Processing started", "video_id": video_id}

async def _run_pipeline(video_id: str):
    print("DEBUG: Pipeline started", flush=True)
    db = SessionLocal()
    # Check for template early to avoid wasting 5 minutes on Whisper if none exists
    template = db.query(models.Template).filter(models.Template.is_default == True).first()
    if not template:
        template = db.query(models.Template).first()
    if template is None:
        # No template exists in DB; fetch by ID fallback if available, otherwise error.
        template = db.query(models.Template).filter(models.Template.id == video_id).first()
        if template is None:
            raise HTTPException(status_code=404, detail="No template found")
    print(f"DEBUG: Using template '{template.name}' (layout={template.layout})", flush=True)
    try:
        # Get the video from the database
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="Video not found")

        # Resolve video path to absolute
        if not os.path.isabs(video.path):
            video_path = os.path.join(str(BASE_DIR), video.path)
        else:
            video_path = video.path
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file missing: {video.path}")

        print("DEBUG: Starting transcription", flush=True)
        # Call WhisperService to transcribe the video
        whisper_result = WhisperService().transcribe(video_path)
        video.status = "transcribed"
        transcript_dir = Path(str(TRANSCRIPTS_DIR))
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcript_dir / f"video_{video.id}_transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(whisper_result, f, indent=2)
        video.transcript_path = str(transcript_path)
        db.add(video)
        db.commit()

        print("DEBUG: Starting LLM clip generation", flush=True)
        # Call LLMService to generate clips
        clips = await LLMService().generate_clips(
            transcript_segments=whisper_result,
            num_clips=5,
            vibe="Streamer Hype",
        )

        print("DEBUG: Starting rendering", flush=True)
        # Loop through clips, create Clip records, and render each one
        clips = clips or []
        for idx, clip_data in enumerate(clips):
            start_t = float(clip_data.get("start", 0.0))
            end_t = start_t + 61.0
            clip = models.Clip(
                video_id=video.id,
                start_time=start_t,
                end_time=end_t,
                title=clip_data.get("title", ""),
                description=clip_data.get("description", ""),
                hashtags=", ".join(clip_data.get("hashtags", [])),
                hook=clip_data.get("hook", ""),
                confidence=clip_data.get("confidence", 0.0),
                composite_score=clip_data.get("composite_score", 0.0),
                vibe_category=clip_data.get("vibe_category", "Custom"),
                status="pending",
                layout=clip_data.get("layout", "split_screen"),
                operations=clip_data.get("operations", []),
            )
            db.add(clip)
            db.commit()
            db.refresh(clip)

            # Render each clip
            print(f"DEBUG: Rendering clip {idx+1}/{len(clips)}", flush=True)
            try:
                RenderService(db).render_clip(clip, video, template)
            except Exception as e:
                print(f"DEBUG: Failed to render clip {clip.id}: {e}", flush=True)
                clip.status = "error"
                clip.error_message = str(e)
                db.commit()
                continue

            # QC: Audit the rendered clip
            output_path = clip.output_path if clip.output_path else clip.file_path
            if output_path:
                min_dur = 60.0
                try:
                    passed, reason = audit_clip(output_path, min_dur, expected_crop_x=clip.layout == "split_screen")
                    if not passed:
                        print(f"DEBUG: QC failed for clip {clip.id}: {reason}", flush=True)
                        clip.status = "failed"
                        clip.error_message = reason
                        clip.file_path = None
                        clip.output_path = None
                        db.commit()
                        continue
                except Exception as qc_exc:
                    print(f"DEBUG: QC error on clip {clip.id}: {qc_exc}", flush=True)
                    clip.status = "failed"
                    clip.error_message = f"QC error: {qc_exc}"
                    clip.file_path = None
                    clip.output_path = None
                    db.commit()
                    continue

        # Update video status to done
        print(f"DEBUG: All clips rendered, updating video status", flush=True)
        video.status = "done"
        db.add(video)
        db.commit()

        # Cleanup temp audio chunks
        for f in glob.glob("C:/Sachit/Creator Desk/backend/data/sources/processed/*.wav"):
            try: os.remove(f)
            except: pass

    except Exception as exc:
        # Set status to error if anything fails
        print(f"PIPELINE CRASHED: {exc}", flush=True)
        print(traceback.format_exc(), flush=True)
        video.status = "error"
        video.error_message = str(exc)
        db.add(video)
        db.commit()
    finally:
        db.close()

@router.get("/videos/{video_id}/clips")
def get_clips(video_id: str, db: Session = Depends(get_db)): return db.query(models.Clip).filter(models.Clip.video_id == video_id).all()

@router.get("/templates")
def get_templates(db: Session = Depends(get_db)):
    return db.query(models.Template).all()


@router.post("/templates")
def create_template(data: dict, db: Session = Depends(get_db)):
    new_template = models.Template(
        name=data.get("name", "Untitled Template"),
        description=data.get("description", ""),
        layout=data.get("layout", "center_crop"),
        config=data.get("config", {}),
        is_default=data.get("is_default", False)
    )
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    return new_template


@router.put("/templates/{template_id}")
def update_template(template_id: int, data: dict, db: Session = Depends(get_db)):
    template = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if "name" in data: template.name = data["name"]
    if "description" in data: template.description = data["description"]
    if "layout" in data: template.layout = data["layout"]
    if "config" in data: template.config = data["config"]
    if "is_default" in data: template.is_default = data["is_default"]
    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(models.Template).filter(models.Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"status": "success", "message": "Template deleted"}


@router.post("/templates/seed")
def seed_default_templates(db: Session = Depends(get_db)):
    try:
        import seed_templates
        seed_templates.seed()
        return {"status": "success", "message": "Templates seeded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clips")
def get_all_clips(video_id: Optional[int] = None, videoId: Optional[str] = None, db: Session = Depends(get_db)):
    vid = video_id or videoId
    if vid:
        query = db.query(models.Clip).filter(models.Clip.video_id == int(vid))
    else:
        query = db.query(models.Clip)
    return query.all()

@router.get("/status")
def get_status(): return {"status": "ok"}

@router.get("/discover/trending")
def get_trending_sources():
    return [
        {"id": "v1", "title": "Kai Cenat Reacts", "source": "Twitch", "views": "1.2M", "duration": "12:45", "url": "#", "thumbnail": "https://picsum.photos/seed/v1/400/225"},
        {"id": "v2", "title": "Speed IRL Stream", "source": "YouTube", "views": "850K", "duration": "45:10", "url": "#", "thumbnail": "https://picsum.photos/seed/v2/400/225"},
        {"id": "v3", "title": "Adin Ross Moments", "source": "Kick", "views": "2.1M", "duration": "22:30", "url": "#", "thumbnail": "https://picsum.photos/seed/v3/400/225"}
    ]

@router.delete("/clips/{clip_id}")
def delete_clip(clip_id: int, db: Session = Depends(get_db)):
    clip = db.query(models.Clip).filter(models.Clip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    # Delete the physical file if it exists
    if clip.output_path and os.path.exists(clip.output_path):
        os.remove(clip.output_path)
    # Delete from database
    db.delete(clip)
    db.commit()
    return {"message": "Clip deleted"}

@router.post("/clips/{clip_id}/render")
def render_clip(clip_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    clip = db.query(models.Clip).filter(models.Clip.id == clip_id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    
    video = db.query(models.Video).filter(models.Video.id == clip.video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    template = db.query(models.Template).filter(models.Template.is_default == True).first()
    if not template:
        template = db.query(models.Template).first()
    
    rs = RenderService(db)
    try:
        render_clip_output_path = rs.render_clip(clip, video, template)
    except Exception as e:
        print(f"RenderService error: {e}", flush=True)
        raise
    
    return {"message": "Rendering started", "clip_id": clip_id}