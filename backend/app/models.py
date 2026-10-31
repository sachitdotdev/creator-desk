import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="uploaded")  # uploaded | transcribing | transcribed | error
    transcript_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clips: Mapped[List["Clip"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    clips: Mapped[List["Clip"]] = relationship(back_populates="template")

    def get_config(self) -> Dict[str, Any]:
        return json.loads(self.config)

    def set_config(self, config: Dict[str, Any]):
        self.config = json.dumps(config)


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    video_id: Mapped[int] = mapped_column(Integer, ForeignKey("videos.id"), nullable=False)
    template_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("templates.id"), nullable=True)

    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)

    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma separated
    hook: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    composite_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vibe_category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    clip_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending")  # pending | rendering | rendered | approved | rejected | error
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    output_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    progress: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    video: Mapped["Video"] = relationship(back_populates="clips")
    template: Mapped[Optional["Template"]] = relationship(back_populates="clips")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id"), nullable=False)
    account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("social_accounts.id"), nullable=True
    )  # connected channel the clip is posted to
    platform: Mapped[str] = mapped_column(String, default="tiktok")  # tiktok | instagram | youtube | x
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued")  # queued | posted | failed
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    clip: Mapped["Clip"] = relationship(back_populates="schedules")
    account: Mapped[Optional["SocialAccount"]] = relationship(back_populates="schedules")


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)  # youtube | tiktok | instagram
    account_name: Mapped[str] = mapped_column(String, nullable=False)
    channel_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="connected")  # connected | disconnected | error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    schedules: Mapped[List["Schedule"]] = relationship(back_populates="account")


Clip.schedules = relationship("Schedule", back_populates="clip", cascade="all, delete-orphan")
