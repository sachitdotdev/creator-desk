from app.database import SessionLocal
from app import models
import sys

db = SessionLocal()
error_videos = db.query(models.Video).filter(models.Video.status == "error").all()
for vid in error_videos:
    print(f"ID: {vid.id}, Path: {vid.path}")
db.close()
