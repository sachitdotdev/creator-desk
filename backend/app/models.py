from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
import datetime

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String)
    filename = Column(String)
    path = Column(String)
    transcript_path = Column(String, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    clips = relationship("Clip", back_populates="video")

class Clip(Base):
    __tablename__ = "clips"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"))
    start_time = Column(Float)
    end_time = Column(Float)
    title = Column(String, nullable=True)
    description = Column(String, nullable=True)
    hashtags = Column(JSON, nullable=True)
    hook = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    composite_score = Column(Float, nullable=True)
    vibe_category = Column(String, nullable=True)
    status = Column(String, default="pending")
    output_path = Column(String, nullable=True)
    file_path = Column(String, nullable=True)
    layout = Column(String, default="center_crop")
    operations = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    video = relationship("Video", back_populates="clips")

class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    layout = Column(String, default="center_crop")
    config = Column(JSON, nullable=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)