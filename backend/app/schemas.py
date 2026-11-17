import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def _parse_config(v: Any) -> Any:
    if isinstance(v, str):
        return json.loads(v)
    return v


# ---------- Video ----------
class VideoBase(BaseModel):
    filename: str
    original_name: str
    status: str


class VideoCreate(VideoBase):
    path: str
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None


class VideoOut(VideoBase):
    id: int
    path: str
    duration: float | None = None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    transcript_path: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Template ----------
class TemplateBase(BaseModel):
    name: str
    description: str | None = None
    config: dict[str, Any]
    is_default: bool = False


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    is_default: bool | None = None


class TemplateOut(TemplateBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("config", mode="before")
    @classmethod
    def _config_before(cls, v: Any) -> Any:
        return _parse_config(v)


# ---------- Clip ----------
class ClipBase(BaseModel):
    start_time: float
    end_time: float
    title: str | None = None
    description: str | None = None
    hashtags: str | None = None
    hook: str | None = None
    confidence: float | None = None
    file_path: str | None = None


class ClipCreate(ClipBase):
    video_id: int
    template_id: int | None = None


class ClipUpdate(BaseModel):
    start_time: float | None = None
    end_time: float | None = None
    title: str | None = None
    description: str | None = None
    hashtags: str | None = None
    hook: str | None = None
    confidence: float | None = None
    template_id: int | None = None
    status: str | None = None


class ClipOut(ClipBase):
    id: int
    video_id: int
    template_id: int | None = None
    duration: float
    status: str
    output_path: str | None = None
    thumbnail_path: str | None = None
    error_message: str | None = None
    progress: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Pipeline ----------
class PipelineStart(BaseModel):
    video_id: int
    template_id: int | None = None
    num_clips: int = 5
    vibe: str | None = "Streamer Hype"


class PipelineStatus(BaseModel):
    video_id: int
    status: str
    progress: float
    message: str
    clips: list[ClipOut] = []


# ---------- Schedule ----------
class ScheduleBase(BaseModel):
    clip_id: int
    platform: str = "tiktok"
    account_id: int | None = None  # connected social account to post to
    scheduled_at: datetime


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleOut(ScheduleBase):
    id: int
    status: str
    posted_at: datetime | None = None
    account_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class SchedulePostNow(BaseModel):
    schedule_ids: list[int] | None = None  # post specific schedules; omit to post all queued


# ---------- Social Accounts ----------
class SocialAccountBase(BaseModel):
    platform: str  # youtube | tiktok | instagram
    account_name: str
    channel_id: str | None = None
    status: str = "connected"  # connected | disconnected | error


class SocialAccountConnect(SocialAccountBase):
    access_token: str | None = None
    refresh_token: str | None = None


class SocialAccountOut(BaseModel):
    id: int
    platform: str
    account_name: str
    channel_id: str | None = None
    status: str
    connected: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Export ----------
class AccountExport(BaseModel):
    video_id: int
    clip_id: int
    package_path: str
    download_url: str


# ---------- Lead finder ----------
class LeadProcess(BaseModel):
    url: str
    template_id: int | None = None


class LeadProcessOut(BaseModel):
    ok: bool
    message: str
    url: str
    video_id: int | None = None
