import cv2
import numpy as np
import os


def generate_sendcmd_file(video_path: str, start_time: float, duration: float, sendcmd_path: str, target_width: int = 1080) -> bool:
    try:
        os.makedirs(os.path.dirname(sendcmd_path), exist_ok=True)
        
        model_path = "C:/Sachit/Creator Desk/backend/yolov8n-face.pt"
        if not os.path.exists(model_path):
            print(f"DEBUG: YOLO model not found at {model_path}!")
            return False
            
        from ultralytics import YOLO
        model = YOLO(model_path)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): return False
        
        cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0: fps = 30
        original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        scale_factor = 1920 / original_height
        
        smoothed_x = None
        alpha = 0.15
        frame_count = 0
        sampled_positions = []
        frame_skip = 5
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame_count > (duration * fps): break
            
            if frame_count % frame_skip == 0:
                results = model(frame, verbose=False, device="cuda")
                current_x = None
                max_area = 0
                
                for r in results:
                    for box in r.boxes:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        area = (x2 - x1) * (y2 - y1)
                        if area > max_area:
                            max_area = area
                            current_x = x1 + (x2 - x1) / 2
                
                if current_x is not None:
                    if smoothed_x is None: smoothed_x = current_x
                    else: smoothed_x = (alpha * current_x) + ((1 - alpha) * smoothed_x)
                
                if smoothed_x is not None:
                    sampled_positions.append((frame_count, smoothed_x))
            
            frame_count += 1
            
        cap.release()
        
        final_commands = []
        if sampled_positions:
            for i in range(frame_count):
                prev_pos = sampled_positions[0]
                next_pos = sampled_positions[-1]
                for pos in sampled_positions:
                    if pos[0] <= i: prev_pos = pos
                    if pos[0] >= i: 
                        next_pos = pos
                        break
                
                if prev_pos[0] == next_pos[0]:
                    crop_x = prev_pos[1]
                else:
                    t = (i - prev_pos[0]) / (next_pos[0] - prev_pos[0])
                    crop_x = prev_pos[1] + t * (next_pos[1] - prev_pos[1])
                    
                scaled_x = crop_x * scale_factor
                overlay_x = (target_width / 2) - scaled_x
                scaled_width = original_width * scale_factor
                min_overlay_x = target_width - scaled_width
                max_overlay_x = 0
                overlay_x = max(min_overlay_x, min(max_overlay_x, overlay_x))
                
                time_sec = i / fps
                final_commands.append(f"{time_sec:.3f} overlay x {overlay_x:.2f};")
        
        with open(sendcmd_path, 'w') as f:
            f.write("\n".join(final_commands))
            
        return True
    except Exception as e:
        import traceback
        print(f"DEBUG: Face tracking failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        try:
            with open(sendcmd_path, 'w') as f:
                f.write("0.000 overlay x -420.0;\n")
        except Exception:
            pass
        return False
