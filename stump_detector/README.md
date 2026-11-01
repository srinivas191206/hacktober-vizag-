# 🏏 Cricket Stump & Wicket AI Detector Module

A lightweight, self-contained drop-in module for real-time cricket stump detection and pitch calibration.

---

## 📁 What's in this folder:
```text
stump_detector/
├── __init__.py           # Package init
├── detector.py           # Core StumpDetector class
├── api.py                # Standalone REST API microservice (optional)
├── example_usage.py      # Quick 5-line test example
├── requirements.txt      # Python dependencies
└── weights/
    └── best.pt           # Trained YOLO11n weights (5.5 MB)
```

---

## 🚀 How to use in your app:

### 1. Copy this folder
Copy the entire `stump_detector/` folder into your app's project directory:
```bash
cp -r /Users/thaladasrinivas/Downloads/stumps/stump_detector /path/to/your/app/
```

### 2. Install dependencies
```bash
pip install -r stump_detector/requirements.txt
```

---

## 💻 Python Code Integration (FastAPI, Flask, Django, etc.):

```python
from stump_detector import StumpDetector
import cv2

# Initialize detector (auto-loads weights/best.pt)
detector = StumpDetector()

# 1. Detect on an image path or numpy frame
result = detector.detect("match_frame.jpg", conf=0.35, draw=True, calibrate_pitch=True)

# Access detection results:
print("Wickets found:", result["num_wickets"])
for w in result["boxes"]:
    print("Box:", w["box"])               # [x1, y1, x2, y2]
    print("Confidence:", w["confidence"])  # 0.85
    print("Ground contact:", w["ground_ref"]) # [x, y] bottom-center of stumps

# Pitch 22-Yard Calibration (when 2 wickets are visible):
if result["pitch_calibration"] and result["pitch_calibration"].get("calibrated"):
    calib = result["pitch_calibration"]
    print(f"Pitch length in pixels: {calib['distance_px']} px")
    print(f"Real-world length: {calib['distance_m']} m (22 yards)")
    print(f"Scale: {calib['px_per_meter']} px/m")

# Save or stream the annotated frame:
cv2.imwrite("output_frame.jpg", result["annotated_frame"])
```

### 2. Video Processing:
```python
# Process an entire cricket match video:
output_video_path = detector.detect_video("match_clip.mp4", output_path="detected_clip.mp4")
```

---

## 🌐 Using with Node.js, React, Mobile, or Go:
If your app is not Python-based, run the included microservice:
```bash
python stump_detector/api.py
```
Then make a standard `POST` request from Node / React / Swift:
```javascript
const formData = new FormData();
formData.append('file', imageBlob);
formData.append('conf', 0.35);

const res = await fetch('http://localhost:8000/detect', {
  method: 'POST',
  body: formData
});
const data = await res.json();
console.log("Wickets:", data.num_wickets);
console.log("Boxes:", data.boxes);
```
