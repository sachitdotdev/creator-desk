from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator
import json


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
    duration: Optional[float] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


class VideoOut(VideoBase):
    id: int
    path: str
    duration: Optional[float] = None
    fps: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    transcript_path: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Template ----------
class TemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    is_default: bool = False


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


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
    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: Optional[str] = None
    hook: Optional[str] = None
    confidence: Optional[float] = None
    file_path: Optional[str] = None


class ClipCreate(ClipBase):
    video_id: int
    template_id: Optional[int] = None


class ClipUpdate(BaseModel):
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: Optional[str] = None
    hook: Optional[str] = None
    confidence: Optional[float] = None
    template_id: Optional[int] = None
    status: Optional[str] = None


class ClipOut(ClipBase):
    id: int
    video_id: int
    template_id: Optional[int] = None
    duration: float
    status: str
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    error_message: Optional[str] = None
    progress: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Pipeline ----------
class PipelineStart(BaseModel):
    video_id: int
    template_id: Optional[int] = None
    num_clips: int = 5
    vibe: Optional[str] = "Streamer Hype"


class PipelineStatus(BaseModel):
    video_id: int
    status: str
    progress: float
    message: str
    clips: List[ClipOut] = []


# ---------- Schedule ----------
class ScheduleBase(BaseModel):
    clip_id: int
    platform: str = "tiktok"
    account_id: Optional[int] = None  # connected social account to post to
    scheduled_at: datetime


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleOut(ScheduleBase):
    id: int
    status: str
    posted_at: Optional[datetime] = None
    account_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SchedulePostNow(BaseModel):
    schedule_ids: Optional[List[int]] = None  # post specific schedules; omit to post all queued


# ---------- Social Accounts ----------
class SocialAccountBase(BaseModel):
    platform: str  # youtube | tiktok | instagram
    account_name: str
    channel_id: Optional[str] = None
    status: str = "connected"  # connected | disconnected | error


class SocialAccountConnect(SocialAccountBase):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class SocialAccountOut(BaseModel):
    id: int
    platform: str
    account_name: str
    channel_id: Optional[str] = None
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
    template_id: Optional[int] = None


class LeadProcessOut(BaseModel):
    ok: bool
    message: str
    url: str
    video_id: Optional[int] = None
