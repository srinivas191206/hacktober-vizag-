"""
Cricket Stump & Wicket AI Detector Module
Self-contained, production-ready inference & pitch calibration class.
"""

import os
import cv2
import numpy as np
from ultralytics import YOLO

# Standard Cricket Dimensions (MCC Laws 7 & 8)
PITCH_LENGTH_M = 20.12        # 22 yards between bowling creases
PITCH_WIDTH_M = 3.05          # 10 feet pitch width
BOWLING_CREASE_W_M = 2.64     # 8 ft 8 in
POPPING_CREASE_OFFSET_M = 1.22 # 4 ft in front of bowling crease
POPPING_CREASE_W_M = 3.66     # At least 12 ft
WICKET_WIDTH_M = 0.2286       # 9 inches (stump set width)

DEFAULT_WEIGHTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weights", "best.pt")

def draw_three_black_stumps(annotated, x1, y1, x2, y2, color=(15, 15, 15), outline=(245, 245, 245), draw_bails=True):
    """
    Draw 3 realistic black cricket stumps (Off, Middle, Leg) with bails and top caps.
    """
    W = max(int(x2 - x1), 6)
    H = max(int(y2 - y1), 12)

    # Stump width proportional to bounding box
    sw = max(2, int(round(W * 0.16)))
    half_sw = max(1, sw // 2)

    # 3 stump horizontal centers: Left, Middle, Right
    c1 = x1 + half_sw + max(0, int(round(W * 0.04)))
    c2 = int(round((x1 + x2) / 2.0))
    c3 = x2 - half_sw - max(0, int(round(W * 0.04)))

    bail_h = max(2, int(round(H * 0.038)))
    top_y = y1 + bail_h
    bot_y = y2

    # Draw 3 vertical black stumps
    for cx in [c1, c2, c3]:
        sx1 = cx - half_sw
        sx2 = cx + half_sw
        # Crisp outline for clear visibility on grass / pitch
        cv2.rectangle(annotated, (sx1 - 1, top_y - 1), (sx2 + 1, bot_y + 1), outline, 1, cv2.LINE_AA)
        # Jet black stump core
        cv2.rectangle(annotated, (sx1, top_y), (sx2, bot_y), color, -1)
        # Top cap
        cv2.ellipse(annotated, (cx, top_y), (half_sw, max(1, half_sw // 2)), 0, 0, 360, outline, 1, cv2.LINE_AA)
        cv2.ellipse(annotated, (cx, top_y), (max(0, half_sw - 1), max(0, half_sw // 2 - 1)), 0, 0, 360, color, -1)

    if draw_bails:
        # Bail 1: Left to middle stump
        cv2.rectangle(annotated, (c1 - half_sw, y1), (c2 + half_sw // 2, y1 + bail_h), outline, 1, cv2.LINE_AA)
        cv2.rectangle(annotated, (c1 - half_sw + 1, y1 + 1), (c2 + half_sw // 2 - 1, y1 + bail_h - 1), color, -1)
        # Bail 2: Middle to right stump
        cv2.rectangle(annotated, (c2 - half_sw // 2, y1), (c3 + half_sw, y1 + bail_h), outline, 1, cv2.LINE_AA)
        cv2.rectangle(annotated, (c2 - half_sw // 2 + 1, y1 + 1), (c3 + half_sw - 1, y1 + bail_h - 1), color, -1)

def draw_pitch_zones(annotated, H, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M=1.22, PITCH_WIDTH_M=3.05, batting_end="far"):
    """
    Divide the pitch from the batting side popping crease (0m) into standard cricket length zones:
    - 0m - 2m: YORKER
    - 2m - 4m: FULL LENGTH
    - 4m - 6m: GOOD LENGTH
    - 6m - 8m: BACK OF A LENGTH
    - 8m+: SHORT / BOUNCER
    """
    def proj(X, Y):
        pt = np.array([X, Y, 1.0], dtype=np.float64)
        res = H @ pt
        if abs(res[2]) < 1e-7: return None
        return (int(round(res[0]/res[2])), int(round(res[1]/res[2])))

    overlay = annotated.copy()
    hw = PITCH_WIDTH_M / 2.0

    if batting_end == "far":
        y_base = PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M
        sign = -1.0
    else:
        y_base = POPPING_CREASE_OFFSET_M
        sign = 1.0

    # Official cricket bowling length zones
    zones = [
        (0.0, 2.0, "YORKER", (220, 60, 180)),
        (2.0, 4.0, "FULL LENGTH", (230, 150, 30)),
        (4.0, 6.0, "GOOD LENGTH", (40, 200, 50)),
        (6.0, 8.0, "BACK OF A LENGTH", (20, 190, 240)),
        (8.0, 10.5, "SHORT PITCH", (40, 50, 230))
    ]

    dividing_lines = [0.0, 2.0, 4.0, 6.0, 8.0]

    # 1. Fill pitch zone polygons with translucent tint
    for d_start, d_end, name, color in zones:
        y1 = y_base + sign * d_start
        y2 = y_base + sign * d_end
        p1 = proj(-hw, y1)
        p2 = proj(+hw, y1)
        p3 = proj(+hw, y2)
        p4 = proj(-hw, y2)

        if all([p1, p2, p3, p4]):
            poly = np.array([p1, p2, p3, p4], dtype=np.int32)
            cv2.fillPoly(overlay, [poly], color)

    cv2.addWeighted(overlay, 0.32, annotated, 0.68, 0, annotated)

    # 2. Draw white pitch boundary side edges & back boundary line
    p_top_l = proj(-hw, y_base)
    p_bot_l = proj(-hw, y_base + sign * 10.5)
    p_top_r = proj(+hw, y_base)
    p_bot_r = proj(+hw, y_base + sign * 10.5)
    if all([p_top_l, p_bot_l, p_top_r, p_bot_r]):
        cv2.line(annotated, p_top_l, p_bot_l, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.line(annotated, p_top_r, p_bot_r, (255, 255, 255), 1, cv2.LINE_AA)

    p_end_l = proj(-hw, y_base + sign * 10.5)
    p_end_r = proj(+hw, y_base + sign * 10.5)
    if p_end_l and p_end_r:
        cv2.line(annotated, p_end_l, p_end_r, (255, 255, 255), 1, cv2.LINE_AA)

    def draw_stroked_text(img, text, org, fontFace, fontScale, color=(255, 255, 255), thickness=2, stroke_color=(0, 0, 0), stroke_thickness=4):
        cv2.putText(img, text, org, fontFace, fontScale, stroke_color, stroke_thickness, cv2.LINE_AA)
        cv2.putText(img, text, org, fontFace, fontScale, color, thickness, cv2.LINE_AA)

    # 3. Draw dividing lines at 0m, 2m, 4m, 6m, 8m with distance markers on the right
    for d in dividing_lines:
        y_line = y_base + sign * d
        p_left = proj(-hw, y_line)
        p_right = proj(+hw, y_line)

        if p_left and p_right:
            # White boundary line across pitch
            cv2.line(annotated, p_left, p_right, (255, 255, 255), 2 if d == 0.0 else 1, cv2.LINE_AA)

            # Indicator tick extending to the right
            dx = p_right[0] - p_left[0]
            dy = p_right[1] - p_left[1]
            L = max(np.hypot(dx, dy), 1.0)
            ux, uy = dx / L, dy / L
            tick_len = 14
            p_tick_end = (int(round(p_right[0] + ux * tick_len)), int(round(p_right[1] + uy * tick_len)))
            cv2.line(annotated, p_right, p_tick_end, (255, 255, 255), 2, cv2.LINE_AA)

            # Large, crisp white distance text: "0m", "2m", "4m", "6m", "8m" (NO black box)
            dist_txt = f"{int(d)}m"
            font = cv2.FONT_HERSHEY_DUPLEX
            scale_dist = 0.58 if batting_end == "far" else 0.62
            thick_dist = 2
            (tw, th), bl = cv2.getTextSize(dist_txt, font, scale_dist, thick_dist)

            tag_x = p_tick_end[0] + 8
            tag_y = p_tick_end[1] + th // 2

            draw_stroked_text(annotated, dist_txt, (tag_x, tag_y), font, scale_dist,
                              color=(255, 255, 255), thickness=thick_dist,
                              stroke_color=(0, 0, 0), stroke_thickness=4)

    # 4. Large, visible white text for length zone names (to the left of 0m-8m right edge, NO black boxes)
    for d_start, d_end, name, color in zones:
        y1 = y_base + sign * d_start
        y2 = y_base + sign * d_end
        y_mid = (y1 + y2) / 2.0

        p_right_mid = proj(+hw, y_mid)
        p_top_r = proj(+hw, y1)
        p_bot_r = proj(+hw, y2)

        if p_right_mid and p_top_r and p_bot_r:
            box_h_px = abs(p_bot_r[1] - p_top_r[1])
            scale_name = 0.58 if box_h_px > 25 else 0.48
            thick_name = 2
            font = cv2.FONT_HERSHEY_DUPLEX
            (tw, th), bl = cv2.getTextSize(name, font, scale_name, thick_name)

            # Position to the left of the right edge (inside the box on the right)
            margin_left_of_edge = 16
            bx = p_right_mid[0] - tw - margin_left_of_edge
            by = p_right_mid[1] + th // 2

            draw_stroked_text(annotated, name, (bx, by), font, scale_name,
                              color=(255, 255, 255), thickness=thick_name,
                              stroke_color=(0, 0, 0), stroke_thickness=4)

def project_point(H, X, Y):
    pt = np.array([X, Y, 1.0], dtype=np.float64)
    res = H @ pt
    if abs(res[2]) < 1e-7:
        return None
    return (int(round(res[0] / res[2])), int(round(res[1] / res[2])))

def compute_pitch_calibration_model(boxes_data, h_img):
    if len(boxes_data) < 2:
        return None

    wicket_refs = []
    for b in boxes_data:
        x1, y1, x2, y2 = b['box']
        conf = b['confidence']
        xc = (x1 + x2) / 2.0
        yc_bottom = float(y2)
        w_box = x2 - x1
        h_box = y2 - y1
        wicket_refs.append({
            'box': (x1, y1, x2, y2),
            'conf': conf,
            'xc': xc,
            'yc': yc_bottom,
            'ground_ref': (xc, yc_bottom),
            'w_box': w_box,
            'h_box': h_box
        })

    wicket_refs.sort(key=lambda item: item['yc'], reverse=True)
    near = wicket_refs[0]
    far = wicket_refs[1]

    y_sep = near['yc'] - far['yc']
    if y_sep < h_img * 0.10:
        return None

    P_near = near['ground_ref']
    P_far = far['ground_ref']

    dx_px = P_far[0] - P_near[0]
    dy_px = P_far[1] - P_near[1]
    dist_px = float(np.sqrt(dx_px**2 + dy_px**2))
    if dist_px < 1e-4:
        return None

    px_per_m = dist_px / PITCH_LENGTH_M
    perp_dx = -dy_px / dist_px
    perp_dy = dx_px / dist_px
    half_w_near = near['w_box'] / 2.0
    half_w_far = far['w_box'] / 2.0

    img_pt1 = (P_near[0] - perp_dx * half_w_near, P_near[1] - perp_dy * half_w_near)
    img_pt2 = (P_near[0] + perp_dx * half_w_near, P_near[1] + perp_dy * half_w_near)
    img_pt3 = (P_far[0] + perp_dx * half_w_far, P_far[1] + perp_dy * half_w_far)
    img_pt4 = (P_far[0] - perp_dx * half_w_far, P_far[1] - perp_dy * half_w_far)

    pts_src = np.array([
        [-WICKET_WIDTH_M / 2.0, 0.0],
        [+WICKET_WIDTH_M / 2.0, 0.0],
        [+WICKET_WIDTH_M / 2.0, PITCH_LENGTH_M],
        [-WICKET_WIDTH_M / 2.0, PITCH_LENGTH_M]
    ], dtype=np.float32)

    pts_dst = np.array([img_pt1, img_pt2, img_pt3, img_pt4], dtype=np.float32)
    H, _ = cv2.findHomography(pts_src, pts_dst)
    if H is None:
        return None

    calib_data = {
        "calibrated": True,
        "distance_px": round(dist_px, 1),
        "distance_m": PITCH_LENGTH_M,
        "px_per_meter": round(px_per_m, 2),
        "near_ground_ref": [round(P_near[0], 1), round(P_near[1], 1)],
        "far_ground_ref": [round(P_far[0], 1), round(P_far[1], 1)],
        "near_box_width": round(near['w_box'], 1),
        "far_box_width": round(far['w_box'], 1),
        "depth_ratio": round(far['w_box'] / max(near['w_box'], 1), 3),
        "homography": H.tolist()
    }

    return {
        "H": H,
        "near": near,
        "far": far,
        "dist_px": dist_px,
        "px_per_m": px_per_m,
        "P_near": P_near,
        "P_far": P_far,
        "calib_data": calib_data
    }

def render_calibrated_pitch_overlay(frame, calib_model, render_mode="black_stumps", show_pitch_zones=True, batting_end="far"):
    annotated = frame.copy()
    H = calib_model["H"]
    near = calib_model["near"]
    far = calib_model["far"]
    white = (255, 255, 255)
    RETURN_BACK_M = 0.7

    if show_pitch_zones:
        draw_pitch_zones(annotated, H, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M, PITCH_WIDTH_M, batting_end=batting_end)

    # Near End
    nbc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, 0.0)
    nbc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, 0.0)
    if nbc_l and nbc_r:
        cv2.line(annotated, nbc_l, nbc_r, white, 2, cv2.LINE_AA)

    npc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    npc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if npc_l and npc_r:
        cv2.line(annotated, npc_l, npc_r, white, 3, cv2.LINE_AA)

    nrc_l_back = project_point(H, -BOWLING_CREASE_W_M / 2.0, -RETURN_BACK_M)
    nrc_l_front = project_point(H, -BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if nrc_l_back and nrc_l_front:
        cv2.line(annotated, nrc_l_back, nrc_l_front, white, 2, cv2.LINE_AA)

    nrc_r_back = project_point(H, +BOWLING_CREASE_W_M / 2.0, -RETURN_BACK_M)
    nrc_r_front = project_point(H, +BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if nrc_r_back and nrc_r_front:
        cv2.line(annotated, nrc_r_back, nrc_r_front, white, 2, cv2.LINE_AA)

    # Far End
    fbc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
    fbc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
    if fbc_l and fbc_r:
        cv2.line(annotated, fbc_l, fbc_r, white, 2, cv2.LINE_AA)

    fpc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    fpc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    if fpc_l and fpc_r:
        cv2.line(annotated, fpc_l, fpc_r, white, 2, cv2.LINE_AA)

    frc_l_front = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    frc_l_back = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M + RETURN_BACK_M)
    if frc_l_front and frc_l_back:
        cv2.line(annotated, frc_l_front, frc_l_back, white, 2, cv2.LINE_AA)

    frc_r_front = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    frc_r_back = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M + RETURN_BACK_M)
    if frc_r_front and frc_r_back:
        cv2.line(annotated, frc_r_front, frc_r_back, white, 2, cv2.LINE_AA)

    # 3 Black or Yellow Stumps
    if render_mode in ("black_stumps", "yellow_stumps"):
        stump_color = (15, 225, 245) if render_mode == "yellow_stumps" else (15, 15, 15)
        stump_outline = (10, 160, 200) if render_mode == "yellow_stumps" else (245, 245, 245)
        for item in [near, far]:
            if item is near and item.get("synthetic", False):
                continue
            x1, y1, x2, y2 = item['box']
            draw_three_black_stumps(annotated, x1, y1, x2, y2, color=stump_color, outline=stump_outline)
            xc = (x1 + x2) / 2.0
            yc = float(y2)
            gx, gy = int(round(xc)), int(round(yc))
            cv2.circle(annotated, (gx, gy), 5, (0, 0, 255), -1)
            cv2.circle(annotated, (gx, gy), 8, (0, 235, 120), 2)
            cv2.drawMarker(annotated, (gx, gy), (255, 255, 255), cv2.MARKER_CROSS, 12, 1)

    return annotated

class StumpDetector:
    def __init__(self, weights_path=None, device=""):
        """
        Initialize the Cricket Stump Detector.
        :param weights_path: Path to best.pt (defaults to bundled weights/best.pt)
        :param device: "mps" (Mac), "cuda" (NVIDIA), or "cpu" (auto-detected if empty)
        """
        self.weights_path = weights_path or DEFAULT_WEIGHTS
        if not os.path.exists(self.weights_path):
            raise FileNotFoundError(f"Model weights not found at: {self.weights_path}")
        
        self.model = YOLO(self.weights_path)
        self.device = device

    def detect(self, image_input, conf=0.35, draw=True, calibrate_pitch=True,
               render_mode="black_stumps", show_pitch_zones=True, batting_end="far",
               locked_calibration=None):
        """
        Detect cricket stumps in an image, draw white creases, 3 black stumps, and bowling length zones.
        :param image_input: Image filepath (str) OR cv2 BGR numpy array
        :param conf: Confidence score threshold (0.10 to 0.95, default 0.35)
        :param draw: Whether to draw annotations on the frame
        :param calibrate_pitch: Whether to calculate pitch centerline and perspective creases
        :param render_mode: 'black_stumps' (renders 3 realistic black stumps) or 'bbox'
        :param show_pitch_zones: Whether to divide pitch into 0-2m (Yorker), 2-4m (Full), 4-6m (Good Length), 6-8m (Back of Length), 8m+ (Short)
        :param batting_end: 'far' (default for broadcast cameras) or 'near'
        :param locked_calibration: Pre-calibrated pitch model to apply consistently across frames
        :return: dict with detection boxes, calibration data, and annotated frame
        """
        if isinstance(image_input, str):
            frame = cv2.imread(image_input)
            if frame is None:
                raise ValueError(f"Could not read image from path: {image_input}")
        elif isinstance(image_input, np.ndarray):
            frame = image_input.copy()
        else:
            raise TypeError("image_input must be a file path string or numpy BGR image array.")

        h_img, w_img = frame.shape[:2]
        
        # If locked_calibration is provided, render constant pitch directly
        if locked_calibration is not None and draw and calibrate_pitch:
            annotated = render_calibrated_pitch_overlay(
                frame, locked_calibration, render_mode=render_mode,
                show_pitch_zones=show_pitch_zones, batting_end=batting_end
            )
            return {
                "num_wickets": 2,
                "boxes": [
                    {"box": list(locked_calibration["near"]["box"]), "confidence": locked_calibration["near"].get("conf", 1.0), "label": "WICKET / STUMPS (LOCKED)"},
                    {"box": list(locked_calibration["far"]["box"]), "confidence": locked_calibration["far"].get("conf", 1.0), "label": "WICKET / STUMPS (LOCKED)"}
                ],
                "pitch_calibration": locked_calibration["calib_data"],
                "calib_model": locked_calibration,
                "annotated_frame": annotated,
                "image_size": {"width": w_img, "height": h_img}
            }

        # Run YOLO inference
        results = self.model.predict(source=frame, conf=conf, device=self.device or None, verbose=False)[0]
        
        boxes_out = []
        if results.boxes is not None and len(results.boxes) > 0:
            for b in results.boxes:
                xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                confidence = float(b.conf[0].cpu().numpy())
                x1, y1, x2, y2 = xyxy
                xc = (x1 + x2) / 2.0
                yc_bottom = float(y2)
                
                boxes_out.append({
                    "box": xyxy,
                    "confidence": round(confidence, 4),
                    "center_x": round(xc, 1),
                    "ground_ref": [round(xc, 1), round(yc_bottom, 1)],
                    "width": x2 - x1,
                    "height": y2 - y1,
                    "label": "WICKET / STUMPS"
                })

        annotated = frame.copy() if draw else None
        calib_data = None
        calib_model = None

        if calibrate_pitch and len(boxes_out) >= 2:
            calib_model = compute_pitch_calibration_model(boxes_out, h_img)
            if calib_model is not None:
                calib_data = calib_model["calib_data"]
                if draw:
                    annotated = render_calibrated_pitch_overlay(
                        frame, calib_model, render_mode=render_mode,
                        show_pitch_zones=show_pitch_zones, batting_end=batting_end
                    )
            else:
                # Draw boxes if vertical separation is insufficient
                if draw:
                    for w in boxes_out:
                        x1, y1, x2, y2 = w["box"]
                        if render_mode == "black_stumps":
                            draw_three_black_stumps(annotated, x1, y1, x2, y2)
                        else:
                            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 235, 120), 2)
        elif draw:
            for w in boxes_out:
                x1, y1, x2, y2 = w["box"]
                if render_mode == "black_stumps":
                    draw_three_black_stumps(annotated, x1, y1, x2, y2)
                else:
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 235, 120), 2)

        if calibrate_pitch and len(boxes_out) == 1:
            calib_data = {
                "calibrated": False,
                "status": "single_wicket",
                "message": "Only 1 wicket detected. 2 wickets required for pitch longitudinal centerline."
            }

        return {
            "num_wickets": len(boxes_out),
            "boxes": boxes_out,
            "pitch_calibration": calib_data,
            "calib_model": calib_model,
            "annotated_frame": annotated,
            "image_size": {"width": w_img, "height": h_img}
        }

    def detect_video(self, video_path, output_path=None, conf=0.35, calibrate_pitch=True,
                     render_mode="black_stumps", show_pitch_zones=True, batting_end="far",
                     lock_calibration=True):
        """
        Process an entire video file with stump detection and pitch calibration.
        When lock_calibration is True, once the pitch is calibrated with stumps,
        it remains rock-solid and constant throughout the whole video!
        :param video_path: Input video file path
        :param output_path: Destination .mp4 file path (auto-generated if None)
        :param conf: Confidence score threshold
        :param calibrate_pitch: Whether to calibrate pitch
        :param render_mode: 'black_stumps' or 'bbox'
        :param show_pitch_zones: Whether to show 5 bowling length zones
        :param batting_end: 'far' or 'near'
        :param lock_calibration: Keep pitch calibration constant across all video frames
        :return: Path to processed video
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if not output_path:
            base, _ = os.path.splitext(video_path)
            output_path = f"{base}_detected.mp4"

        raw_output_path = output_path.replace(".mp4", "_raw.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(raw_output_path, fourcc, fps, (w, h))

        # 1. Pre-scan to lock optimal calibration upfront
        locked_calib = None
        if calibrate_pitch and lock_calibration:
            scan_cap = cv2.VideoCapture(video_path)
            scan_limit = min(total_frames, 90)
            best_score = -1.0
            idx = 0
            while idx < scan_limit:
                ret, sframe = scan_cap.read()
                if not ret:
                    break
                if idx % 2 == 0:
                    sres = self.model.predict(source=sframe, conf=conf, device=self.device or None, verbose=False)[0]
                    sboxes = []
                    if sres.boxes is not None:
                        for b in sres.boxes:
                            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                            c = float(b.conf[0].cpu().numpy())
                            sboxes.append({"box": xyxy, "confidence": c})
                    cmodel = compute_pitch_calibration_model(sboxes, h)
                    if cmodel is not None:
                        score = cmodel["near"]["conf"] + cmodel["far"]["conf"]
                        if score > best_score:
                            best_score = score
                            locked_calib = cmodel
                            if score > 1.6:
                                break
                idx += 1
            scan_cap.release()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if calibrate_pitch and lock_calibration:
                    if locked_calib is not None:
                        ann = render_calibrated_pitch_overlay(
                            frame, locked_calib, render_mode=render_mode,
                            show_pitch_zones=show_pitch_zones, batting_end=batting_end
                        )
                    else:
                        res = self.detect(frame, conf=conf, draw=True, calibrate_pitch=True,
                                          render_mode=render_mode, show_pitch_zones=show_pitch_zones,
                                          batting_end=batting_end)
                        if res.get("calib_model") is not None:
                            locked_calib = res["calib_model"]  # Lock it for all subsequent frames!
                        ann = res["annotated_frame"]
                else:
                    res = self.detect(frame, conf=conf, draw=True, calibrate_pitch=calibrate_pitch,
                                      render_mode=render_mode, show_pitch_zones=show_pitch_zones,
                                      batting_end=batting_end)
                    ann = res["annotated_frame"]

                out.write(ann)
        finally:
            cap.release()
            out.release()

        # Convert with ffmpeg for seamless browser compatibility
        try:
            import subprocess
            subprocess.run([
                "/usr/local/bin/ffmpeg", "-y", "-i", raw_output_path,
                "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                output_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(raw_output_path):
                os.remove(raw_output_path)
        except Exception:
            if os.path.exists(raw_output_path) and not os.path.exists(output_path):
                os.rename(raw_output_path, output_path)

        return output_path

