import traceback
import sys
import os

# Add the parent directory to the path so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.api.routes import _run_pipeline
except ImportError:
    # Fallback if 'app' is not at the parent level
    import backend.app.api.routes as routes
    _run_pipeline = routes._run_pipeline

if __name__ == "__main__":
    try:
        # Call for video ID 8
        # Note: Using some default values for num_clips, template_id, and vibe.
        _run_pipeline(
            video_id=8,
            num_clips=5,
            template_id=None,
            vibe="Streamer Hype"
        )
    except Exception as e:
        print(traceback.format_exc())
