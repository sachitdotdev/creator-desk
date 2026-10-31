"""Template service: CRUD + default templates."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from app.models import Template
from app.schemas import TemplateCreate, TemplateUpdate, TemplateOut
from app.core.config import TEMPLATES_DIR


# Default template configs. Each is a full design system for 9:16 vertical shorts.
DEFAULT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "Streamer Hype",
        "description": "High-energy gaming/streamer style with big bold captions and glow.",
        "is_default": True,
        "config": {
            "vibe": "Streamer Hype",
            "colors": {
                "primary": "#FFFFFF",
                "accent": "#FF00FF",
                "background": "#000000",
                "highlight": "#FFFF00",
            },
            "caption": {
                "font": "Arial",
                "size": 56,
                "bold": 1,
                "primary": "&H00FFFFFF&",
                "outline": "&H00000000&",
                "back": "&H4D000000&",
                "alignment": 2,
                "margin_v": 120,
                "outline_w": 4,
                "shadow": 0,
                "highlight_color": "&H0000FFFF&",
                "karaoke": True,
                "kinetic": True,
            },
            "title": {
                "font": "Arial",
                "size": 40,
                "bold": 1,
                "color": "&H00FFFFFF&",
                "position": "top",
                "margin_v": 80,
                "outline_w": 3,
                "glow": True,
            },
            "watermark": {
                "text": "CREATOR DESK",
                "font": "Arial",
                "size": 24,
                "color": "&H00FFFFFF&",
                "opacity": 0.4,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "blur",  # blur | solid | bars
                "blur_amount": 25,
                "color": "#000000",
            },
        },
    },
    {
        "name": "Rapper Energy",
        "description": "Bold, confident, street-style with gold accents and heavy outlines.",
        "is_default": True,
        "config": {
            "vibe": "Rapper Energy",
            "colors": {
                "primary": "#FFD700",
                "accent": "#FF4500",
                "background": "#0A0A0A",
                "highlight": "#FFD700",
            },
            "caption": {
                "font": "Impact",
                "size": 60,
                "bold": 1,
                "primary": "&H00D7FF&",
                "outline": "&H00000000&",
                "back": "&H66000000&",
                "alignment": 2,
                "margin_v": 140,
                "outline_w": 6,
                "shadow": 2,
                "highlight_color": "&H0000FFFF&",
                "karaoke": False,
                "kinetic": True,
            },
            "title": {
                "font": "Impact",
                "size": 44,
                "bold": 1,
                "color": "&H00D7FF&",
                "position": "top",
                "margin_v": 70,
                "outline_w": 5,
                "glow": True,
            },
            "watermark": {
                "text": "CREATOR DESK",
                "font": "Impact",
                "size": 26,
                "color": "&H00D7FF&",
                "opacity": 0.5,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "solid",
                "blur_amount": 0,
                "color": "#0A0A0A",
            },
        },
    },
    {
        "name": "Technical",
        "description": "Clean, informative, tutorial style with neutral tones.",
        "is_default": True,
        "config": {
            "vibe": "Technical",
            "colors": {
                "primary": "#FFFFFF",
                "accent": "#00BFA6",
                "background": "#0B1015",
                "highlight": "#00BFA6",
            },
            "caption": {
                "font": "Arial",
                "size": 44,
                "bold": 0,
                "primary": "&H00FFFFFF&",
                "outline": "&H00000000&",
                "back": "&H4D000000&",
                "alignment": 2,
                "margin_v": 110,
                "outline_w": 2,
                "shadow": 0,
                "highlight_color": "&H00A6BF00&",
                "karaoke": False,
                "kinetic": True,
            },
            "title": {
                "font": "Arial",
                "size": 36,
                "bold": 1,
                "color": "&H00FFFFFF&",
                "position": "top",
                "margin_v": 70,
                "outline_w": 2,
                "glow": False,
            },
            "watermark": {
                "text": "CREATOR DESK",
                "font": "Arial",
                "size": 22,
                "color": "&H00FFFFFF&",
                "opacity": 0.3,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "blur",
                "blur_amount": 18,
                "color": "#0B1015",
            },
        },
    },
    {
        "name": "Horror",
        "description": "Dark, suspenseful, eerie with red accents and slow reveal.",
        "is_default": True,
        "config": {
            "vibe": "Horror",
            "colors": {
                "primary": "#FFFFFF",
                "accent": "#8B0000",
                "background": "#050505",
                "highlight": "#8B0000",
            },
            "caption": {
                "font": "Arial",
                "size": 50,
                "bold": 1,
                "primary": "&H00FFFFFF&",
                "outline": "&H00000080&",
                "back": "&H80000000&",
                "alignment": 2,
                "margin_v": 130,
                "outline_w": 3,
                "shadow": 2,
                "highlight_color": "&H000080FF&",
                "karaoke": False,
                "kinetic": True,
            },
            "title": {
                "font": "Arial",
                "size": 42,
                "bold": 1,
                "color": "&H00FFFFFF&",
                "position": "top",
                "margin_v": 70,
                "outline_w": 3,
                "glow": False,
            },
            "watermark": {
                "text": "CREATOR DESK",
                "font": "Arial",
                "size": 22,
                "color": "&H00FFFFFF&",
                "opacity": 0.35,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "solid",
                "blur_amount": 0,
                "color": "#050505",
            },
        },
    },
    {
        "name": "Narrative",
        "description": "Cinematic, story-driven, emotional with soft styling.",
        "is_default": True,
        "config": {
            "vibe": "Narrative",
            "colors": {
                "primary": "#FFFFFF",
                "accent": "#7B68EE",
                "background": "#0F0B1A",
                "highlight": "#7B68EE",
            },
            "caption": {
                "font": "Georgia",
                "size": 46,
                "bold": 0,
                "primary": "&H00FFFFFF&",
                "outline": "&H00000000&",
                "back": "&H4D000000&",
                "alignment": 2,
                "margin_v": 120,
                "outline_w": 2,
                "shadow": 1,
                "highlight_color": "&H0068EE7B&",
                "karaoke": False,
                "kinetic": True,
            },
            "title": {
                "font": "Georgia",
                "size": 38,
                "bold": 0,
                "color": "&H00FFFFFF&",
                "position": "top",
                "margin_v": 70,
                "outline_w": 2,
                "glow": False,
            },
            "watermark": {
                "text": "CREATOR DESK",
                "font": "Georgia",
                "size": 22,
                "color": "&H00FFFFFF&",
                "opacity": 0.3,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "blur",
                "blur_amount": 22,
                "color": "#0F0B1A",
            },
        },
    },
    {
        "name": "Custom",
        "description": "Blank canvas template — build your own design.",
        "is_default": True,
        "config": {
            "vibe": "Custom",
            "colors": {
                "primary": "#FFFFFF",
                "accent": "#7B68EE",
                "background": "#000000",
                "highlight": "#7B68EE",
            },
            "caption": {
                "font": "Arial",
                "size": 48,
                "bold": 1,
                "primary": "&H00FFFFFF&",
                "outline": "&H00000000&",
                "back": "&H4D000000&",
                "alignment": 2,
                "margin_v": 120,
                "outline_w": 3,
                "shadow": 0,
                "highlight_color": "&H0068EE7B&",
                "karaoke": False,
                "kinetic": True,
            },
            "title": {
                "font": "Arial",
                "size": 36,
                "bold": 1,
                "color": "&H00FFFFFF&",
                "position": "top",
                "margin_v": 70,
                "outline_w": 2,
                "glow": False,
            },
            "watermark": {
                "text": "",
                "font": "Arial",
                "size": 22,
                "color": "&H00FFFFFF&",
                "opacity": 0.3,
                "position": "bottom-right",
                "margin_x": 40,
                "margin_y": 40,
            },
            "background": {
                "mode": "blur",
                "blur_amount": 25,
                "color": "#000000",
            },
        },
    },
]


def seed_defaults(db: Session):
    """Insert default templates if none exist."""
    existing = db.query(Template).count()
    if existing > 0:
        return
    for t in DEFAULT_TEMPLATES:
        db.add(Template(
            name=t["name"],
            description=t["description"],
            config=json.dumps(t["config"]),
            is_default=t["is_default"],
        ))
    db.commit()


def list_templates(db: Session) -> List[Template]:
    return db.query(Template).order_by(Template.is_default.desc(), Template.name.asc()).all()


def get_template(db: Session, template_id: int) -> Optional[Template]:
    return db.query(Template).filter(Template.id == template_id).first()


def create_template(db: Session, data: TemplateCreate) -> Template:
    tmpl = Template(
        name=data.name,
        description=data.description,
        config=json.dumps(data.config),
        is_default=data.is_default,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


def update_template(db: Session, template_id: int, data: TemplateUpdate) -> Optional[Template]:
    tmpl = get_template(db, template_id)
    if not tmpl:
        return None
    if data.name is not None:
        tmpl.name = data.name
    if data.description is not None:
        tmpl.description = data.description
    if data.config is not None:
        tmpl.set_config(data.config)
    if data.is_default is not None:
        tmpl.is_default = data.is_default
        # ensure only one default
        if data.is_default:
            others = db.query(Template).filter(Template.id != template_id).all()
            for o in others:
                o.is_default = False
    db.commit()
    db.refresh(tmpl)
    return tmpl


def delete_template(db: Session, template_id: int) -> bool:
    tmpl = get_template(db, template_id)
    if not tmpl:
        return False
    db.delete(tmpl)
    db.commit()
    return True
