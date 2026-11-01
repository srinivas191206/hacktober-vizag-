#!/usr/bin/env python3
"""
Simple Plug-and-Play Example
Demonstrates how to import and use StumpDetector in your app.
"""

import os
import sys

# Ensure parent directory is on pythonpath for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

try:
    from stump_detector import StumpDetector
except ImportError:
    from detector import StumpDetector
import cv2

def main():
    # 1. Initialize detector (auto-loads bundled weights/best.pt)
    detector = StumpDetector()

    # 2. Path to any cricket image
    sample_image = os.path.join(os.path.dirname(__file__), "..", "stumps", "Screenshot 2026-09-24 at 3.41.38 PM.png")
    if not os.path.exists(sample_image):
        print(f"Sample image not found, please specify a test image path.")
        return

    # 3. Run detection & pitch calibration
    result = detector.detect(sample_image, conf=0.35, draw=True, calibrate_pitch=True)

    print("=" * 50)
    print(f"Wickets Detected: {result['num_wickets']}")
    for i, b in enumerate(result['boxes']):
        print(f"  Wicket #{i+1}: Box={b['box']}, Conf={b['confidence']:.2f}, Ground Point={b['ground_ref']}")

    if result['pitch_calibration'] and result['pitch_calibration'].get('calibrated'):
        calib = result['pitch_calibration']
        print(f"Pitch Centerline: {calib['distance_px']} px <-> 20.12 m ({calib['px_per_meter']} px/m)")
    print("=" * 50)

    # 4. Save annotated result
    out_file = "test_output.jpg"
    cv2.imwrite(out_file, result["annotated_frame"])
    print(f"Saved annotated image with bounding boxes & pitch guide to: {out_file}")

if __name__ == '__main__':
    main()
