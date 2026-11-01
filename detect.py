#!/usr/bin/env python3
"""
Cricket Stumps / Wicket Detector
Inference script for single images or cricket videos.

Usage:
    python detect.py --source <image_or_video_path>
    python detect.py --source test.jpg
    python detect.py --source match_clip.mp4 --conf 0.30
"""

import os
import sys
import argparse
import time
import cv2
from ultralytics import YOLO

DEFAULT_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "best.pt")
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v'}

def draw_stump_detection(frame, box, conf, class_name="WICKET / STUMPS"):
    x1, y1, x2, y2 = map(int, box)
    
    # Visual aesthetics: clean, vibrant bounding box and label
    box_color = (0, 235, 120)     # Neon emerald / green
    label_bg = (20, 24, 30)        # Dark background for high contrast
    text_color = (255, 255, 255)   # White text
    
    # Bounding Box
    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 3)
    
    # Corner accents for sleek UI feel
    corner_len = min(int((x2 - x1) * 0.25), int((y2 - y1) * 0.25), 20)
    if corner_len > 4:
        accent_color = (0, 255, 255) # Bright yellow
        thick = 4
        # Top-left
        cv2.line(frame, (x1, y1), (x1 + corner_len, y1), accent_color, thick)
        cv2.line(frame, (x1, y1), (x1, y1 + corner_len), accent_color, thick)
        # Top-right
        cv2.line(frame, (x2, y1), (x2 - corner_len, y1), accent_color, thick)
        cv2.line(frame, (x2, y1), (x2, y1 + corner_len), accent_color, thick)
        # Bottom-left
        cv2.line(frame, (x1, y2), (x1 + corner_len, y2), accent_color, thick)
        cv2.line(frame, (x1, y2), (x1, y2 - corner_len), accent_color, thick)
        # Bottom-right
        cv2.line(frame, (x2, y2), (x2 - corner_len, y2), accent_color, thick)
        cv2.line(frame, (x2, y2), (x2, y2 - corner_len), accent_color, thick)

    # Label text
    label = f"{class_name} | {conf:.2f}"
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = 0.55
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    
    # Label badge positioning (above box, or inside if near top edge)
    badge_y1 = max(0, y1 - th - baseline - 8)
    badge_y2 = badge_y1 + th + baseline + 8
    badge_x1 = max(0, x1)
    badge_x2 = badge_x1 + tw + 12
    
    cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), label_bg, -1)
    cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), box_color, 1)
    cv2.putText(frame, label, (badge_x1 + 6, badge_y2 - baseline - 4), font, font_scale, text_color, thickness, cv2.LINE_AA)
    
    return frame

def process_image(model, image_path, conf_thresh, output_path=None):
    img = cv2.imread(image_path)
    if img is None:
        print(f"[Error] Could not read image: {image_path}")
        return False
    
    t0 = time.time()
    results = model.predict(source=img, conf=conf_thresh, verbose=False)
    infer_time = (time.time() - t0) * 1000.0

    boxes = results[0].boxes
    num_detected = len(boxes) if boxes is not None else 0
    print(f"\n[Detection] Source: {os.path.basename(image_path)} | Time: {infer_time:.1f}ms")
    print(f"            Found: {num_detected} wicket(s)/stumps")

    if boxes is not None and len(boxes) > 0:
        for idx, box in enumerate(boxes):
            xyxy = box.xyxy[0].cpu().numpy()
            conf = float(box.conf[0].cpu().numpy())
            print(f"            → Box #{idx+1}: ({int(xyxy[0])}, {int(xyxy[1])}) to ({int(xyxy[2])}, {int(xyxy[3])}) | Conf: {conf:.3f}")
            img = draw_stump_detection(img, xyxy, conf, class_name="WICKET / STUMPS")
    else:
        print("            → No wickets detected above confidence threshold.")

    if not output_path:
        base, ext = os.path.splitext(image_path)
        os.makedirs("output", exist_ok=True)
        output_path = os.path.join("output", f"detected_{os.path.basename(base)}.jpg")

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    cv2.imwrite(output_path, img)
    print(f"[Output] Saved annotated image to: {output_path}")
    return True

def process_video(model, video_path, conf_thresh, output_path=None):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[Error] Could not open video: {video_path}")
        return False

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if not output_path:
        base, _ = os.path.splitext(os.path.basename(video_path))
        os.makedirs("output", exist_ok=True)
        output_path = os.path.join("output", f"detected_{base}.mp4")

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    print(f"\n[Video Processing] Source: {video_path}")
    print(f"                   Resolution: {width}x{height} | FPS: {fps:.1f} | Total frames: {total_frames}")
    print(f"                   Output: {output_path}")

    frame_idx = 0
    t_start = time.time()
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

            results = model.predict(source=frame, conf=conf_thresh, verbose=False)
            boxes = results[0].boxes
            if boxes is not None:
                for box in boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    frame = draw_stump_detection(frame, xyxy, conf, class_name="WICKET / STUMPS")

            out.write(frame)
            if frame_idx % 30 == 0 or frame_idx == total_frames:
                elapsed = time.time() - t_start
                curr_fps = frame_idx / elapsed if elapsed > 0 else 0
                print(f"  Frame {frame_idx}/{total_frames} ({frame_idx*100//max(total_frames, 1)}%) - {curr_fps:.1f} FPS", end='\r')
    finally:
        cap.release()
        out.release()

    print(f"\n[Complete] Processed {frame_idx} frames in {time.time() - t_start:.1f}s")
    print(f"[Output] Saved output video to: {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Cricket Wicket / Stump Detector")
    parser.add_argument("--source", type=str, required=True, help="Path to cricket image or video file")
    parser.add_argument("--weights", type=str, default=DEFAULT_WEIGHTS, help="Path to trained YOLO weights")
    parser.add_argument("--conf", type=float, default=0.35, help="Confidence threshold (default: 0.35)")
    parser.add_argument("--output", type=str, default=None, help="Custom output file path")
    args = parser.parse_args()

    if not os.path.exists(args.weights):
        print(f"[Error] Weights file not found at: {args.weights}")
        print("Please verify the model training has completed or specify --weights.")
        sys.exit(1)

    if not os.path.exists(args.source):
        print(f"[Error] Source file not found: {args.source}")
        sys.exit(1)

    print(f"Loading stump detector model from: {args.weights}")
    model = YOLO(args.weights)

    ext = os.path.splitext(args.source)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        process_image(model, args.source, conf_thresh=args.conf, output_path=args.output)
    elif ext in VIDEO_EXTENSIONS:
        process_video(model, args.source, conf_thresh=args.conf, output_path=args.output)
    else:
        # Fallback: attempt image first, then video
        if not process_image(model, args.source, conf_thresh=args.conf, output_path=args.output):
            process_video(model, args.source, conf_thresh=args.conf, output_path=args.output)

if __name__ == '__main__':
    main()
