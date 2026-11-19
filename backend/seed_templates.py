from app.database import Base, SessionLocal, engine
from app.models import Template

# Burned caption styling comes from config.py defaults. A template may still
# override a key explicitly (resolve_caption_style honours it), but the seeded
# defaults must stay empty so they inherit the current, legible style.
CAPTION_STYLE_KEYS = frozenset({
    "font", "size", "bold", "primary", "secondary", "outline", "back",
    "outline_w", "shadow", "alignment", "max_lines", "highlight_color",
})


def seed():
    # Create the tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    if db.query(Template).count() > 0:
        print("Templates already seeded.")
        db.close()
        return

    templates = [
        Template(
            name="Podcast Clip",
            layout="center_crop",
            is_default=False,
            config={
                "vibe": "Podcast",
                "colors": {"primary": "#FFFFFF", "accent": "#7B68EE", "background": "#000000", "highlight": "#7B68EE"},
                # No caption style keys: inherit config.py defaults (Arial,
                # ~125 px, bold, white/black outline, soft shadow, max 2 lines).
                # Non-style keys such as margin_v are kept.
                "caption": {"margin_v": 120, "karaoke": False, "kinetic": True},
                "title": {"font": "Arial", "size": 36, "bold": 1, "color": "&H00FFFFFF&", "position": "top", "margin_v": 70, "outline_w": 2, "glow": False, "text": "CREATOR DESK"},
                "watermark": {"text": "", "font": "Arial", "size": 22, "color": "&H00FFFFFF&", "opacity": 0.3, "position": "bottom-right", "margin_x": 40, "margin_y": 40},
                "background": {"mode": "blur", "blur_amount": 25, "color": "#000000"}
            }
        ),
        Template(
            name="Streamer Hype",
            layout="split_screen",
            is_default=False,
            config={
                "vibe": "Streamer",
                "colors": {"primary": "#FFFFFF", "accent": "#FF0000", "background": "#000000", "highlight": "#FF0000"},
                "caption": {"margin_v": 100, "karaoke": True, "kinetic": True},
                "title": {"font": "Montserrat", "size": 40, "bold": 1, "color": "&H00FF0000&", "position": "top", "margin_v": 80, "outline_w": 2, "glow": True, "text": "LIVE STREAM"},
                "watermark": {"text": "@Streamer", "font": "Arial", "size": 24, "color": "&H00FFFFFF&", "opacity": 0.5, "position": "top-right", "margin_x": 20, "margin_y": 20},
                "background": {"mode": "solid", "blur_amount": 0, "color": "#111111"}
            }
        )
    ]

    for t in templates:
        db.add(t)
    db.commit()
    print("✅ Seeded default templates.")
    db.close()

if __name__ == "__main__":
    seed()