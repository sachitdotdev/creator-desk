import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd() + "/backend")

from app.core.config import WHISPER_MODEL
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

from app.services.whisper_service import WhisperService

def main():
    print(f"Testing Whisper with Model: {WHISPER_MODEL}, Device: {WHISPER_DEVICE}, Compute: {WHISPER_COMPUTE_TYPE}")
    
    # We'll use one of the failed videos
    video_path = "backend/data/sources/4d37c313d7464f058d560f6d98336ad3.mp4"
    
    if not os.path.exists(video_path):
        print(f"Video not found at {video_path}")
        return

    service = WhisperService()
    print("Loading model...")
    try:
        result = service.transcribe(video_path)
        print(f"Transcription successful! Language: {result.language}, Duration: {result.duration}")
        print(f"Number of segments: {len(result.segments)}")
        # Print first segment text
        if result.segments:
            print(f"First segment: {result.segments[0].text}")
    except Exception as e:
        print(f"Transcription failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
