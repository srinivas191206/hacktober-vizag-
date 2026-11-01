"""
Standalone Microservice API for Cricket Stump Detection
Run this if your application is written in Node.js, React, Mobile, or Go.

Start server:
    python api.py
    (or uvicorn api:app --port 8000)
"""

import cv2
import numpy as np
import base64
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from .detector import StumpDetector

app = FastAPI(title="Cricket Stump & Pitch Geometry API")
detector = StumpDetector()

@app.post("/detect")
async def detect_endpoint(
    file: UploadFile = File(...),
    conf: float = Form(0.35),
    calibrate_pitch: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far")
):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    res = detector.detect(
        frame,
        conf=conf,
        draw=True,
        calibrate_pitch=calibrate_pitch,
        render_mode=render_mode,
        show_pitch_zones=show_pitch_zones,
        batting_end=batting_end
    )

    # Encode annotated image to Base64
    _, buf = cv2.imencode('.jpg', res["annotated_frame"], [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    b64 = base64.b64encode(buf).decode('utf-8')

    return JSONResponse({
        "success": True,
        "num_wickets": res["num_wickets"],
        "boxes": res["boxes"],
        "pitch_calibration": res["pitch_calibration"],
        "annotated_image_base64": f"data:image/jpeg;base64,{b64}"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
