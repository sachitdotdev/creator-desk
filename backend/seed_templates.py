from app.database import SessionLocal, engine, Base
import app.models
from app.models import Template

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
                "caption": {"font": "Arial", "size": 48, "bold": 1, "primary": "&H00FFFFFF&", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 120, "outline_w": 3, "shadow": 0, "highlight_color": "&H0068EE7B&", "karaoke": False, "kinetic": True},
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
                "caption": {"font": "Montserrat", "size": 54, "bold": 1, "primary": "&H00FFFFFF&", "outline": "&H00000000&", "back": "&H4D000000&", "alignment": 2, "margin_v": 100, "outline_w": 2, "shadow": 0, "highlight_color": "&H000000FF&", "karaoke": True, "kinetic": True},
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