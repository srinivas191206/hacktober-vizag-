import os
import re
import urllib.parse
import time
import subprocess
import json
import base64
import tempfile
import shutil
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from ultralytics import YOLO
from web.sessions_manager import (
    create_session, list_sessions, get_session,
    add_delivery_to_session, delete_session, update_session,
    delete_delivery_from_session, get_multiple_sessions, aggregate_multiple_sessions
)
from web.teams_manager import (
    list_teams, get_team, create_team, update_team,
    list_squads, get_squad, create_squad, update_squad, delete_squad,
    list_players, get_player, create_player, update_player, set_player_status,
    remove_player_from_team, delete_player, assign_existing_player_to_team,
    list_all_registered_players, get_player_sessions,
    list_player_reports, get_report, create_report
)

# Real-world pitch dimensions in meters (MCC Laws of Cricket)
PITCH_LENGTH_M = 20.12      # 22 yards
PITCH_WIDTH_M = 3.05        # 10 feet
BOWLING_CREASE_W_M = 3.00   # Extended professional pitch crease width (10 ft)
POPPING_CREASE_OFFSET_M = 1.22 # 4 ft
POPPING_CREASE_W_M = 5.40   # Extended wide popping crease (18 ft) matching Fulltrack AI
WICKET_WIDTH_M = 0.2286     # 9 inches

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
WEIGHTS_PATH = os.path.join(PROJECT_ROOT, "weights", "best.pt")
BALL_WEIGHTS_PATH = os.path.join(PROJECT_ROOT, "weights", "ball_best.pt")
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUTS_DIR = os.path.join(BASE_DIR, "static", "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# Load Stumps Model
print(f"Loading trained stump model from {WEIGHTS_PATH}...")
model = YOLO(WEIGHTS_PATH)
print("Stump model loaded successfully!")

# Load Ball Model
ball_model = None
if os.path.exists(BALL_WEIGHTS_PATH):
    print(f"Loading trained ball model from {BALL_WEIGHTS_PATH}...")
    ball_model = YOLO(BALL_WEIGHTS_PATH)
    print("Ball model loaded successfully!")

# Ball Tracker
import sys
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from ball_tracker.tracker import BallDetector, BallTrajectoryTracker, draw_stroked_text, apply_trajecta_watermark

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Cricket Stump & Ball Vision AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def project_point(H, X, Y):
    pt = np.array([X, Y, 1.0], dtype=np.float64)
    res = H @ pt
    if abs(res[2]) < 1e-7:
        return None
    u = res[0] / res[2]
    v = res[1] / res[2]
    return (int(round(u)), int(round(v)))

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

def annotate_stump_detection_only(frame, boxes_data, render_mode="black_stumps"):
    annotated = frame.copy()
    h, w = frame.shape[:2]
    
    for item in boxes_data:
        x1, y1, x2, y2 = item["box"]
        conf = item["confidence"]
        
        if render_mode == "black_stumps":
            # 3 Realistic Black Stumps (Off, Middle, Leg)
            draw_three_black_stumps(annotated, x1, y1, x2, y2)
            
            # Sleek label banner above bails
            label = f"WICKET | {conf:.2f}"
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 0.44
            thickness = 1
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            badge_y = max(th + 4, y1 - 6)
            badge_x = max(0, int((x1 + x2)/2 - tw/2 - 4))
            cv2.rectangle(annotated, (badge_x, badge_y - th - 3), (badge_x + tw + 8, badge_y + 3), (18, 22, 28), -1)
            cv2.rectangle(annotated, (badge_x, badge_y - th - 3), (badge_x + tw + 8, badge_y + 3), (0, 235, 120), 1)
            cv2.putText(annotated, label, (badge_x + 4, badge_y - 1), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
        else:
            box_color = (0, 235, 120)     # Emerald Green
            accent_color = (0, 255, 255)  # Bright Yellow
            label_bg = (18, 22, 28)
            text_color = (255, 255, 255)
            
            # Bounding Box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 3)
            
            # Corner highlight brackets
            c_len = min(int((x2 - x1) * 0.25), int((y2 - y1) * 0.25), 22)
            if c_len > 4:
                thick = 4
                cv2.line(annotated, (x1, y1), (x1 + c_len, y1), accent_color, thick)
                cv2.line(annotated, (x1, y1), (x1, y1 + c_len), accent_color, thick)
                cv2.line(annotated, (x2, y1), (x2 - c_len, y1), accent_color, thick)
                cv2.line(annotated, (x2, y1), (x2, y1 + c_len), accent_color, thick)
                cv2.line(annotated, (x1, y2), (x1 + c_len, y2), accent_color, thick)
                cv2.line(annotated, (x1, y2), (x1, y2 - c_len), accent_color, thick)
                cv2.line(annotated, (x2, y2), (x2 - c_len, y2), accent_color, thick)
                cv2.line(annotated, (x2, y2), (x2, y2 - c_len), accent_color, thick)

            # Label Banner
            label = f"WICKET / STUMPS | {conf:.2f}"
            font = cv2.FONT_HERSHEY_DUPLEX
            font_scale = 0.55
            thickness = 1
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            
            badge_y1 = max(0, y1 - th - baseline - 8)
            badge_y2 = badge_y1 + th + baseline + 8
            badge_x1 = max(0, x1)
            badge_x2 = min(w, badge_x1 + tw + 12)
            
            cv2.rectangle(annotated, (badge_x1, badge_y1), (badge_x2, badge_y2), label_bg, -1)
            cv2.rectangle(annotated, (badge_x1, badge_y1), (badge_x2, badge_y2), box_color, 1)
            cv2.putText(annotated, label, (badge_x1 + 6, badge_y2 - baseline - 4),
                        font, font_scale, text_color, thickness, cv2.LINE_AA)
        
    return annotated

def compute_pitch_calibration_model(boxes_data, h_img, w_img=None):
    """
    Compute 4-point perspective homography and calibration model from detected wickets.
    - If 2 wickets are detected: Uses near and far wicket ground contacts to compute exact homography.
    - If 1 wicket is detected: Auto-calibrates pitch using official regulation cricket dimensions
      (0.711m height, 0.229m width, 20.12m pitch length, 1.22m popping crease) and perspective projection.
    """
    if len(boxes_data) == 0:
        return None

    wicket_refs = []
    for item in boxes_data:
        x1, y1, x2, y2 = item["box"]
        conf = item["confidence"]
        xc = (x1 + x2) / 2.0
        yc_bottom = float(y2)
        w_box = max(4.0, float(x2 - x1))
        h_box = max(8.0, float(y2 - y1))
        wicket_refs.append({
            'box': (x1, y1, x2, y2),
            'conf': conf,
            'xc': xc,
            'yc': yc_bottom,
            'ground_ref': (xc, yc_bottom),
            'w_box': w_box,
            'h_box': h_box
        })

    # Sort by Y descending: near wicket has larger Y, far wicket has smaller Y
    wicket_refs.sort(key=lambda item: item['yc'], reverse=True)

    # CASE 1: TWO WICKETS DETECTED
    if len(wicket_refs) >= 2:
        near = wicket_refs[0]
        far = wicket_refs[1]
        y_sep = near['yc'] - far['yc']
        if y_sep >= h_img * 0.08:
            P_near = near['ground_ref']
            P_far = far['ground_ref']
            dx_px = P_far[0] - P_near[0]
            dy_px = P_far[1] - P_near[1]
            dist_px = float(np.sqrt(dx_px**2 + dy_px**2))
            if dist_px > 10.0:
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
                if H is not None:
                    calib_data = {
                        "active": True,
                        "status": "calibrated_two_wickets",
                        "distance_px": round(dist_px, 1),
                        "distance_m": PITCH_LENGTH_M,
                        "px_per_meter": round(px_per_m, 2),
                        "near_ground_ref": [round(P_near[0], 1), round(P_near[1], 1)],
                        "far_ground_ref": [round(P_far[0], 1), round(P_far[1], 1)],
                        "near_box_width": round(near['w_box'], 1),
                        "far_box_width": round(far['w_box'], 1),
                        "depth_ratio": round(far['w_box'] / max(near['w_box'], 1), 3),
                        "mode": "two_wickets"
                    }
                    return {
                        "H": H,
                        "near": near,
                        "far": far,
                        "dist_px": dist_px,
                        "px_per_m": px_per_m,
                        "P_near": P_near,
                        "P_far": P_far,
                        "calib_data": calib_data,
                        "is_single_wicket": False
                    }

    # CASE 2: SINGLE WICKET AUTO-CALIBRATION (Batsman's End Wicket)
    single = wicket_refs[0]
    xc = single['xc']
    y_base = single['yc']
    w_box = single['w_box']
    h_box = single['h_box']

    # Regulation cricket scale from detected wicket
    scale_from_w = w_box / WICKET_WIDTH_M
    scale_from_h = h_box / 0.7112
    scale_wicket = 0.6 * scale_from_w + 0.4 * scale_from_h

    # Check whether detected wicket is at far end (batsman end) or near end (bowler end)
    is_far_end = y_base < h_img * 0.70

    if is_far_end:
        half_w_far = (PITCH_WIDTH_M / 2.0) * (scale_wicket * 0.35)
        y_near = min(float(h_img - 24), y_base + max(220.0, (h_img - y_base) * 0.90))
        depth_ratio = 1.0 + 1.8 * ((y_near - y_base) / max(1.0, y_base))
        half_w_near = half_w_far * depth_ratio

        P_far = (xc, y_base)
        P_near = (xc, y_near)
        dist_px = y_near - y_base

        pts_src = np.array([
            [-PITCH_WIDTH_M / 2.0, PITCH_LENGTH_M],
            [+PITCH_WIDTH_M / 2.0, PITCH_LENGTH_M],
            [+PITCH_WIDTH_M / 2.0, 0.0],
            [-PITCH_WIDTH_M / 2.0, 0.0]
        ], dtype=np.float32)

        pts_dst = np.array([
            [xc - half_w_far, y_base],
            [xc + half_w_far, y_base],
            [xc + half_w_near, y_near],
            [xc - half_w_near, y_near]
        ], dtype=np.float32)

        synthetic_near = {
            'box': (int(xc - w_box*depth_ratio/2), int(y_near - h_box*depth_ratio), int(xc + w_box*depth_ratio/2), int(y_near)),
            'conf': single['conf'],
            'xc': xc,
            'yc': y_near,
            'ground_ref': (xc, y_near),
            'w_box': w_box * depth_ratio,
            'h_box': h_box * depth_ratio,
            'synthetic': True
        }
        near_obj = synthetic_near
        far_obj = single
    else:
        # Detected wicket is at near end (bowler's end, bottom of frame, e.g. Fulltrack AI setup)
        depth_ratio = 3.4
        half_w_near = (PITCH_WIDTH_M / 2.0) * (scale_wicket * 0.32)
        half_w_far = half_w_near / depth_ratio
        # The far pitch end / batsman popping crease is around 45-48% frame height
        y_far = float(h_img * 0.46)

        P_near = (xc, y_base)
        P_far = (xc, y_far)
        dist_px = y_base - y_far

        pts_src = np.array([
            [-PITCH_WIDTH_M / 2.0, PITCH_LENGTH_M],
            [+PITCH_WIDTH_M / 2.0, PITCH_LENGTH_M],
            [+PITCH_WIDTH_M / 2.0, 0.0],
            [-PITCH_WIDTH_M / 2.0, 0.0]
        ], dtype=np.float32)

        pts_dst = np.array([
            [xc - half_w_far, y_far],
            [xc + half_w_far, y_far],
            [xc + half_w_near, y_base],
            [xc - half_w_near, y_base]
        ], dtype=np.float32)

        synthetic_far = {
            'box': (int(xc - w_box/depth_ratio/2), int(y_far - h_box/depth_ratio), int(xc + w_box/depth_ratio/2), int(y_far)),
            'conf': single['conf'],
            'xc': xc,
            'yc': y_far,
            'ground_ref': (xc, y_far),
            'w_box': w_box / depth_ratio,
            'h_box': h_box / depth_ratio,
            'synthetic': True
        }
        near_obj = single
        far_obj = synthetic_far

    H, _ = cv2.findHomography(pts_src, pts_dst)
    if H is None:
        return None

    px_per_m = dist_px / PITCH_LENGTH_M
    calib_data = {
        "active": True,
        "status": "auto_calibrated_single_wicket",
        "distance_px": round(dist_px, 1),
        "distance_m": PITCH_LENGTH_M,
        "px_per_meter": round(px_per_m, 2),
        "near_ground_ref": [round(P_near[0], 1), round(P_near[1], 1)],
        "far_ground_ref": [round(P_far[0], 1), round(P_far[1], 1)],
        "near_box_width": round(near_obj['w_box'], 1),
        "far_box_width": round(far_obj['w_box'], 1),
        "depth_ratio": round(depth_ratio, 3),
        "mode": "single_wicket"
    }

    return {
        "H": H,
        "near": near_obj,
        "far": far_obj,
        "dist_px": dist_px,
        "px_per_m": px_per_m,
        "P_near": P_near,
        "P_far": P_far,
        "calib_data": calib_data,
        "is_single_wicket": True
    }

def render_calibrated_pitch_overlay(frame, calib_model, render_mode="black_stumps", show_pitch_zones=True, batting_end="far"):
    """
    Renders constant, rock-solid pitch creases, 5 length zones, straight middle-stump centerline,
    and stumps on any frame using locked calibration model.
    """
    annotated = frame.copy()
    H = calib_model["H"]
    near = calib_model["near"]
    far = calib_model["far"]
    white = (255, 255, 255)
    RETURN_BACK_M = 0.85  # Extends 0.85m behind bowling crease

    # 0. Luminous Blue Pitch Corridor Beam (Fulltrack AI style)
    # Extends from middle stump along the center pitch corridor all the way down through the bottom of the frame.
    # Width on ground is ~0.26m (width of middle stump / stump corridor).
    STRIP_WIDTH_M = 0.26
    # Extend far past near end so the blue line runs continuously through the bottom of the video
    y_ground_near = -6.0 if calib_model.get("is_single_wicket", False) else -1.5
    y_ground_far = PITCH_LENGTH_M

    p_nl = project_point(H, -STRIP_WIDTH_M / 2.0, y_ground_near)
    p_nr = project_point(H, +STRIP_WIDTH_M / 2.0, y_ground_near)
    p_fr = project_point(H, +STRIP_WIDTH_M / 2.0, y_ground_far)
    p_fl = project_point(H, -STRIP_WIDTH_M / 2.0, y_ground_far)

    if all([p_nl, p_nr, p_fr, p_fl]):
        poly = np.array([p_nl, p_nr, p_fr, p_fl], dtype=np.int32)
        overlay = annotated.copy()
        # Vibrant luminous royal blue BGR: (250, 110, 75)
        cv2.fillPoly(overlay, [poly], (250, 110, 75))
        cv2.addWeighted(overlay, 0.54, annotated, 0.46, 0, annotated)
        # Luminous outer edge rails (clean blue glow, ZERO white line in middle)
        cv2.line(annotated, p_nl, p_fl, (255, 175, 130), 2, cv2.LINE_AA)
        cv2.line(annotated, p_nr, p_fr, (255, 175, 130), 2, cv2.LINE_AA)
    else:
        # Fallback straight centerline if extreme perspective
        c_far = project_point(H, 0.0, y_ground_far)
        c_near = project_point(H, 0.0, y_ground_near) or project_point(H, 0.0, 0.0)
        if c_far and c_near:
            cv2.line(annotated, c_far, c_near, (250, 110, 75), 8, cv2.LINE_AA)
            cv2.line(annotated, c_far, c_near, (255, 180, 130), 2, cv2.LINE_AA)

    # ==================== NEAR END (Bowling End) ====================
    # Only render white bowling, popping, and return creases if bowler's end wickets are genuinely detected
    if not near.get("synthetic", False):
        # 1. Bowling Crease through near stumps (White)
        near_bc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, 0.0)
        near_bc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, 0.0)
        if near_bc_l and near_bc_r:
            cv2.line(annotated, near_bc_l, near_bc_r, white, 2, cv2.LINE_AA)

        # 2. Popping Crease (+1.22m forward towards pitch) (White)
        near_pc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
        near_pc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
        if near_pc_l and near_pc_r:
            cv2.line(annotated, near_pc_l, near_pc_r, white, 3, cv2.LINE_AA)

        # 3. Return Creases (Left & Right, perpendicular to popping crease) (White)
        near_rc_l_back = project_point(H, -BOWLING_CREASE_W_M / 2.0, -RETURN_BACK_M)
        near_rc_l_front = project_point(H, -BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
        if near_rc_l_back and near_rc_l_front:
            cv2.line(annotated, near_rc_l_back, near_rc_l_front, white, 2, cv2.LINE_AA)

        near_rc_r_back = project_point(H, +BOWLING_CREASE_W_M / 2.0, -RETURN_BACK_M)
        near_rc_r_front = project_point(H, +BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
        if near_rc_r_back and near_rc_r_front:
            cv2.line(annotated, near_rc_r_back, near_rc_r_front, white, 2, cv2.LINE_AA)

    # ==================== FAR END (Batsman End) ====================
    # Only render white creases if batsman's end wickets are genuinely detected
    if not far.get("synthetic", False):
        # 1. Bowling Crease through far stumps (White)
        far_bc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
        far_bc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
        if far_bc_l and far_bc_r:
            cv2.line(annotated, far_bc_l, far_bc_r, white, 2, cv2.LINE_AA)

        # 2. Popping Crease (-1.22m forward towards near end) (White)
        far_pc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
        far_pc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
        if far_pc_l and far_pc_r:
            cv2.line(annotated, far_pc_l, far_pc_r, white, 3, cv2.LINE_AA)

        # 3. Return Creases (Left & Right) (White)
        far_rc_l_front = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
        far_rc_l_back = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M + RETURN_BACK_M)
        if far_rc_l_front and far_rc_l_back:
            cv2.line(annotated, far_rc_l_front, far_rc_l_back, white, 2, cv2.LINE_AA)

        far_rc_r_front = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
        far_rc_r_back = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M + RETURN_BACK_M)
        if far_rc_r_front and far_rc_r_back:
            cv2.line(annotated, far_rc_r_front, far_rc_r_back, white, 2, cv2.LINE_AA)

    # 4. Re-render 3 black or neon yellow stumps on top of creases at both pitch ends
    if render_mode in ("black_stumps", "yellow_stumps"):
        stump_color = (15, 225, 245) if render_mode == "yellow_stumps" else (18, 18, 18)
        stump_outline = (10, 160, 200) if render_mode == "yellow_stumps" else (245, 245, 245)
        for item in [near, far]:
            # Down wickets (bowler end) should NEVER come if there isn't any wicket in the bowler end!
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

def annotate_pitch_geometry(frame, boxes_data, render_mode="black_stumps", show_pitch_zones=True, batting_end="far", locked_calibration=None):
    h_img, w_img = frame.shape[:2]

    # If persistent locked calibration is provided (e.g. video processing)
    if locked_calibration is not None:
        annotated = render_calibrated_pitch_overlay(
            frame, locked_calibration, render_mode=render_mode,
            show_pitch_zones=show_pitch_zones, batting_end=batting_end
        )
        return annotated, locked_calibration["calib_data"], locked_calibration

    # Otherwise compute calibration dynamically from current frame
    calib_model = compute_pitch_calibration_model(boxes_data, h_img)
    if calib_model is not None:
        annotated = render_calibrated_pitch_overlay(
            frame, calib_model, render_mode=render_mode,
            show_pitch_zones=show_pitch_zones, batting_end=batting_end
        )
        return annotated, calib_model["calib_data"], calib_model
    else:
        # Fall back to detection boxes if pitch cannot be calibrated
        annotated = annotate_stump_detection_only(frame, boxes_data, render_mode=render_mode)
        calib_data = {
            "active": False,
            "status": "insufficient_wickets",
            "message": "Only 1 wicket visible; 2 wickets required for pitch centerline calibration."
        }
        return annotated, calib_data, None

@app.get("/api/samples")
def list_samples(category: str = "all", media_type: str = "all"):
    samples_dir = os.path.join(STATIC_DIR, "samples")
    files = [f for f in os.listdir(samples_dir) if not f.startswith('.')]
    out = []
    for f in sorted(files):
        ext = os.path.splitext(f)[1].lower()
        is_vid = ext in ['.mp4', '.mov', '.avi']
        if media_type == "image" and is_vid:
            continue
        if media_type == "video" and not is_vid:
            continue
        is_ball = "ball" in f or "deliv" in f
        cat = "ball" if is_ball else "stumps"
        if category == "all" or category == cat:
            sample_titles = {
                "sample_deliv_kohli.mp4": "Virat Kohli Delivery (DRS Arc)",
                "sample_deliv_01.mp4": "Delivery 1 (Flight Arc)",
                "sample_deliv_02.mp4": "Delivery 2 (In-Swing)",
                "sample_deliv_03.mp4": "Delivery 3 (Full Pitch Delivery)",
                "sample_ball_1_delivery.png": "Match Ball Delivery",
                "sample_ball_2_flight.png": "Flight In Mid-Air",
                "sample_ball_3_pitch.png": "Pitch Turf Impact",
                "sample_ball_4_spin.png": "Spin Turn Angle"
            }
            title = sample_titles.get(f, f.replace("sample_", "").replace(".png", "").replace(".jpg", "").replace(".mp4", "").replace("_", " ").title())
            out.append({
                "id": f,
                "title": title,
                "url": f"/static/samples/{f}",
                "category": cat,
                "media_type": "video" if is_vid else "image"
            })
    return out

@app.post("/api/detect")
async def detect_image(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    conf: float = Form(0.35),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far")
):
    if file:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        filename = file.filename
    elif sample_id:
        sample_path = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_path):
            raise HTTPException(status_code=404, detail="Sample image not found")
        img = cv2.imread(sample_path)
        filename = sample_id
    else:
        raise HTTPException(status_code=400, detail="Either file or sample_id required")

    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    h, w = img.shape[:2]
    t0 = time.time()
    results = model.predict(source=img, conf=conf, verbose=False)
    infer_ms = (time.time() - t0) * 1000.0

    boxes_out = []
    if results[0].boxes is not None and len(results[0].boxes) > 0:
        for b in results[0].boxes:
            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
            confidence = float(b.conf[0].cpu().numpy())
            boxes_out.append({
                "box": xyxy,
                "confidence": round(confidence, 4),
                "width": xyxy[2] - xyxy[0],
                "height": xyxy[3] - xyxy[1],
                "label": "WICKET / STUMPS"
            })

    calib_info = None
    if pitch_calibration:
        annotated, calib_info, _ = annotate_pitch_geometry(
            img, boxes_out, render_mode=render_mode,
            show_pitch_zones=show_pitch_zones, batting_end=batting_end
        )
    else:
        annotated = annotate_stump_detection_only(img, boxes_out, render_mode=render_mode)
    
    # Save output image
    out_name = f"result_{int(time.time()*1000)}.jpg"
    out_path = os.path.join(OUTPUTS_DIR, out_name)
    cv2.imwrite(out_path, annotated)

    # Encode base64
    _, buf = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    base64_img = base64.b64encode(buf).decode('utf-8')

    return JSONResponse({
        "success": True,
        "filename": filename,
        "inference_ms": round(infer_ms, 1),
        "fps_estimate": round(1000.0 / max(infer_ms, 1), 1),
        "num_wickets": len(boxes_out),
        "image_size": {"width": w, "height": h},
        "boxes": boxes_out,
        "calibration": calib_info,
        "image_data": f"data:image/jpeg;base64,{base64_img}",
        "download_url": f"/api/download?file={out_name}&filename=detected_{filename}"
    })

@app.post("/api/detect-ball")
async def detect_ball_endpoint(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    ball_conf: float = Form(0.20),
    ball_color: str = Form("auto"),
    max_ball_size: float = Form(120.0),
    detect_stumps: bool = Form(True),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far")
):
    if file:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        filename = file.filename
    elif sample_id:
        sample_path = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_path):
            raise HTTPException(status_code=404, detail="Sample image not found")
        img = cv2.imread(sample_path)
        filename = sample_id
    else:
        raise HTTPException(status_code=400, detail="Either file or sample_id required")

    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    h, w = img.shape[:2]
    t0 = time.time()

    # 1. Optionally detect stumps and calibrate pitch
    annotated = img.copy()
    calib_model = None
    calib_info = None
    if detect_stumps:
        stump_res = model.predict(source=img, conf=0.35, verbose=False)
        stump_boxes = []
        if stump_res[0].boxes is not None:
            for b in stump_res[0].boxes:
                xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                c = float(b.conf[0].cpu().numpy())
                stump_boxes.append({"box": xyxy, "confidence": c})
        if pitch_calibration:
            annotated, calib_info, calib_model = annotate_pitch_geometry(
                img, stump_boxes, render_mode=render_mode,
                show_pitch_zones=show_pitch_zones, batting_end=batting_end
            )
        else:
            annotated = annotate_stump_detection_only(img, stump_boxes, render_mode=render_mode)

    # 2. Detect Ball with smart color & size verification
    ball_detector = BallDetector(ball_model if ball_model is not None else BALL_WEIGHTS_PATH)
    ball_detections = ball_detector.detect(img, conf=ball_conf, ball_color=ball_color, max_ball_size=max_ball_size, is_video=False)
    infer_ms = (time.time() - t0) * 1000.0

    # 3. Project to pitch coordinates if pitch is calibrated
    pitch_mapping = None
    H = calib_model["H"] if calib_model else None

    if len(ball_detections) > 0:
        best_ball = ball_detections[0]
        bxc, byc = best_ball["center"]
        br = best_ball["radius"]
        bconf = best_ball["confidence"]

        if H is not None:
            pitch_mapping = BallTrajectoryTracker.project_to_pitch(H, bxc, byc, PITCH_LENGTH_M, POPPING_CREASE_OFFSET_M)

        # Draw glowing ball target
        cr = int(round(max(br, 6)))
        cx, cy = int(round(bxc)), int(round(byc))
        cv2.circle(annotated, (cx, cy), cr + 8, (0, 140, 255), 2, cv2.LINE_AA)
        cv2.circle(annotated, (cx, cy), cr + 3, (0, 240, 255), 2, cv2.LINE_AA)
        cv2.circle(annotated, (cx, cy), cr, (0, 70, 255), -1, cv2.LINE_AA)
        cv2.circle(annotated, (cx, cy), max(cr - 2, 2), (255, 255, 255), -1, cv2.LINE_AA)

        label_txt = f"CRICKET BALL {int(round(bconf * 100))}%"
        if pitch_mapping:
            label_txt += f" | {pitch_mapping['dist_from_crease_m']}m ({pitch_mapping['zone'].upper()})"
        draw_stroked_text(annotated, label_txt, (cx + cr + 10, cy + 5), cv2.FONT_HERSHEY_DUPLEX, 0.52,
                          color=(255, 255, 255), thickness=1, stroke_thickness=3)

    # Apply TRAJECTA.ai Dynamic Cricket watermark (Bottom-Left, pure transparent) for reels and export
    annotated = apply_trajecta_watermark(annotated, position="bottom-left")

    # Save output image
    out_name = f"ball_result_{int(time.time()*1000)}.jpg"
    out_path = os.path.join(OUTPUTS_DIR, out_name)
    cv2.imwrite(out_path, annotated)

    # Encode base64
    _, buf = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    base64_img = base64.b64encode(buf).decode('utf-8')

    return JSONResponse({
        "success": True,
        "filename": filename,
        "inference_ms": round(infer_ms, 1),
        "fps_estimate": round(1000.0 / max(infer_ms, 1), 1),
        "ball_detected": len(ball_detections) > 0,
        "ball_detections": ball_detections,
        "pitch_mapping": pitch_mapping,
        "image_size": {"width": w, "height": h},
        "calibration": calib_info,
        "image_data": f"data:image/jpeg;base64,{base64_img}",
        "download_url": f"/api/download?file={out_name}&filename=detected_ball_{filename}"
    })

@app.post("/api/track-ball-video")
@app.post("/api/detect-ball-video")
async def track_ball_video(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    video_path: str = Form(None),
    session_id: str = Form(None),
    ball_conf: float = Form(0.20),
    ball_color: str = Form("auto"),
    max_ball_size: float = Form(48.0),
    trail_length: int = Form(25),
    show_trail: bool = Form(True),
    detect_stumps: bool = Form(True),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    ball_render_mode: str = Form("both"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far"),
    trajectory_mode: str = Form("pop_at_delivery"),
    start_time: float = Form(0.0),
    end_time: float = Form(None),
    no_wicket_mode: bool = Form(False),
    manual_stump_data: str = Form(None),
    apply_to_all_videos: bool = Form(True),
    use_session_calibration: bool = Form(True),
    player_id: str = Form(None),
    team_id: str = Form(None)
):
    src_video_path = None
    is_temp = False
    input_filename = "video.mp4"

    if file and file.filename:
        input_filename = file.filename
        temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
        src_video_path = temp_in.name
        is_temp = True
        with open(src_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    elif sample_id:
        sample_file = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_file):
            raise HTTPException(status_code=404, detail="Sample video not found")
        src_video_path = sample_file
        input_filename = sample_id
    elif video_path:
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Local video not found: {video_path}")
        src_video_path = video_path
        input_filename = os.path.basename(video_path)
    else:
        raise HTTPException(status_code=400, detail="Provide a video file, sample_id, or video_path")

    try:
        cap = cv2.VideoCapture(src_video_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot read video file")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        start_frame = int(round(start_time * fps)) if start_time and start_time > 0 else 0
        max_allowed_frames = int(round(12.0 * fps))
        if end_time and end_time > 0:
            end_frame = int(round(end_time * fps))
        else:
            # Process entire video up to 12s limit
            end_frame = min(total_frames, start_frame + max_allowed_frames)

        start_frame = max(0, min(start_frame, total_frames - 1))
        if (end_frame - start_frame) > max_allowed_frames:
            end_frame = start_frame + max_allowed_frames
        end_frame = max(start_frame + 1, min(end_frame, total_frames))
        num_target_frames = end_frame - start_frame

        out_name = f"ball_track_{int(time.time())}.mp4"
        out_path = os.path.join(OUTPUTS_DIR, out_name)
        raw_out_path = os.path.join(OUTPUTS_DIR, f"raw_{out_name}")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(raw_out_path, fourcc, fps, (w, h))

        # 1. Pre-scan for locked constant pitch calibration ONLY if combined mode is active
        locked_calib = None
        if pitch_calibration or detect_stumps:
            scan_cap = cv2.VideoCapture(src_video_path)
            scan_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            scan_limit = min(num_target_frames, 90)
            best_score = -1.0
            idx = 0
            while idx < scan_limit:
                ret, sframe = scan_cap.read()
                if not ret: break
                if idx % 2 == 0:
                    sres = model.predict(source=sframe, conf=0.35, verbose=False)
                    sboxes = []
                    if sres[0].boxes is not None:
                        for b in sres[0].boxes:
                            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                            c = float(b.conf[0].cpu().numpy())
                            sboxes.append({"box": xyxy, "confidence": c})
                    cmodel = compute_pitch_calibration_model(sboxes, h)
                    if cmodel is not None:
                        score = cmodel["near"]["conf"] + cmodel["far"]["conf"]
                        if score > best_score:
                            best_score = score
                            locked_calib = cmodel
                            if score > 1.6: break
                idx += 1
            scan_cap.release()

        ball_detector = BallDetector(ball_model if ball_model is not None else BALL_WEIGHTS_PATH)
        ball_detector.reset_video_memory()
        ball_tracker = BallTrajectoryTracker()

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        raw_frames = []
        frame_detections = {}
        ball_frames = 0
        total_ball_detections = 0
        t0 = time.time()

        # Pass 1: Fast inference & detection collection (storing clean frames for cinematic delivery)
        for curr_frame_idx in range(start_frame, end_frame):
            ret, frame = cap.read()
            if not ret: break

            raw_frames.append((curr_frame_idx, frame.copy()))

            # Pure frame-by-frame ball object detection with anti-shoe, anti-head & color filtering
            ball_dets = ball_detector.detect(
                frame,
                conf=ball_conf,
                is_video=True,
                ball_color=ball_color,
                max_ball_size=max_ball_size,
                frame_idx=curr_frame_idx
            )
            if len(ball_dets) > 0:
                ball_frames += 1
                total_ball_detections += len(ball_dets)

            frame_detections[curr_frame_idx] = ball_dets

        cap.release()

        # Pass 2: Extract SINGLE unified delivery trajectory (Zero false lines, Zero spiderwebs)
        H_pitch = locked_calib["H"] if locked_calib is not None else None
        delivery_traj = ball_tracker.extract_delivery_trajectory(
            frame_detections,
            fps=fps,
            H_pitch=H_pitch,
            pitch_length_m=PITCH_LENGTH_M,
            popping_crease_offset_m=POPPING_CREASE_OFFSET_M,
            calib_data=locked_calib["calib_data"] if locked_calib is not None else None
        )

        # Pass 3: Render clean delivery with Fulltrack AI Pop-Up & Dramatic Pause on completion
        end_f = delivery_traj["end_frame"] if delivery_traj is not None else (len(raw_frames) - 1)
        popup_frame = None
        if delivery_traj is not None and len(raw_frames) > 0:
            comp_idx = min(len(raw_frames) - 1, max(0, end_f - start_frame))
            target_base = raw_frames[comp_idx][1].copy()
            popup_frame = ball_tracker.render_delivery_popup(
                target_base,
                delivery_traj,
                locked_calib=locked_calib,
                render_mode=render_mode,
                show_pitch_zones=show_pitch_zones,
                batting_end=batting_end,
                calib_overlay_fn=render_calibrated_pitch_overlay
            )

        delivered = False
        last_annotated = None
        for curr_frame_idx, clean_frame in raw_frames:
            if delivery_traj is not None and show_trail:
                if curr_frame_idx < end_f:
                    # In-flight delivery: Keep video 100% natural, clean & uncluttered
                    annotated = clean_frame.copy()
                    annotated = apply_trajecta_watermark(annotated, position="bottom-left")
                    out_writer.write(annotated)
                    last_annotated = annotated
                else:
                    # Delivery completed! POP UP Wickets, Blue Pitch Line, Trajectory & Fulltrack AI HUD!
                    # Freeze / Pause on this frame for 3.0 seconds (~75-90 frames)
                    delivered = True
                    pause_frames = int(round(fps * 3.0))
                    for _ in range(pause_frames):
                        out_writer.write(popup_frame)
                    last_annotated = popup_frame
                    break
            else:
                # If no delivery trajectory found or trail disabled, render clean detections
                dets = frame_detections.get(curr_frame_idx, [])
                annotated = ball_detector.annotate_frame(
                    clean_frame,
                    dets,
                    render_mode=ball_render_mode,
                    show_trail=False
                )
                annotated = apply_trajecta_watermark(annotated, position="bottom-left")
                out_writer.write(annotated)
                last_annotated = annotated

        # Fallback: if loop ended before reaching end_f, write the freeze frame pause
        if delivery_traj is not None and show_trail and not delivered and popup_frame is not None:
            pause_frames = int(round(fps * 3.0))
            for _ in range(pause_frames):
                out_writer.write(popup_frame)
            last_annotated = popup_frame

        out_writer.release()
        frame_count = len(raw_frames)
        total_time = time.time() - t0
        avg_fps = frame_count / total_time if total_time > 0 else 0

        # Convert to browser-compatible H.264 ultrafast
        try:
            import subprocess
            subprocess.run([
                "/usr/local/bin/ffmpeg", "-y", "-i", raw_out_path,
                "-vcodec", "libx264", "-preset", "ultrafast", "-crf", "22", "-threads", "4",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                out_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(raw_out_path):
                os.remove(raw_out_path)
        except Exception:
            if os.path.exists(raw_out_path) and not os.path.exists(out_path):
                os.rename(raw_out_path, out_path)

        traj_data = None
        if delivery_traj is not None:
            traj_data = {
                "found": True,
                "release_frame": delivery_traj["start_frame"],
                "bounce_frame": delivery_traj["bounce_frame"],
                "end_frame": delivery_traj["end_frame"],
                "speed_mph": delivery_traj["speed_mph"],
                "speed_kph": delivery_traj["speed_kph"],
                "release_speed_mph": delivery_traj.get("release_speed_mph", delivery_traj["speed_mph"]),
                "pre_bounce_speed_mph": delivery_traj.get("pre_bounce_speed_mph"),
                "post_bounce_speed_mph": delivery_traj.get("post_bounce_speed_mph"),
                "arrival_speed_mph": delivery_traj.get("arrival_speed_mph"),
                "speed_drop_air_mph": delivery_traj.get("speed_drop_air_mph"),
                "speed_drop_turf_mph": delivery_traj.get("speed_drop_turf_mph"),
                "total_speed_decay_mph": delivery_traj.get("total_speed_decay_mph"),
                "frame_speeds": delivery_traj.get("frame_speeds", []),
                "swing_sf": delivery_traj.get("swing_sf", 0.2),
                "spin_deg": delivery_traj.get("spin_deg", 5.3),
                "distance_from_crease_m": delivery_traj["distance_from_crease_m"],
                "length_zone": delivery_traj["length_zone"],
                "lateral_line": delivery_traj["lateral_line"],
                "bounce_coord": delivery_traj.get("bounce_coord"),
                "trajectory_3d": delivery_traj.get("trajectory_3d"),
                "release_height_m": delivery_traj.get("release_height_m", 2.15),
                "release_lateral_m": delivery_traj.get("release_lateral_m", 0.0),
                "arrival_height_m": delivery_traj.get("arrival_height_m", 0.68)
            }

        session_info = None
        if session_id:
            try:
                delivery_record = {
                    "filename": input_filename,
                    "video_url": f"/static/outputs/{out_name}",
                    "download_url": f"/api/download?file={out_name}&filename=detected_ball_{input_filename}",
                    "speed_mph": traj_data.get("speed_mph", 0.0) if traj_data else 0.0,
                    "speed_kph": traj_data.get("speed_kph", 0.0) if traj_data else 0.0,
                    "release_speed_mph": traj_data.get("release_speed_mph", 0.0) if traj_data else 0.0,
                    "pre_bounce_speed_mph": traj_data.get("pre_bounce_speed_mph") if traj_data else None,
                    "post_bounce_speed_mph": traj_data.get("post_bounce_speed_mph") if traj_data else None,
                    "arrival_speed_mph": traj_data.get("arrival_speed_mph") if traj_data else None,
                    "speed_drop_air_mph": traj_data.get("speed_drop_air_mph") if traj_data else None,
                    "speed_drop_turf_mph": traj_data.get("speed_drop_turf_mph") if traj_data else None,
                    "total_speed_decay_mph": traj_data.get("total_speed_decay_mph") if traj_data else None,
                    "frame_speeds": traj_data.get("frame_speeds", []) if traj_data else [],
                    "swing_sf": traj_data.get("swing_sf", 0.2) if traj_data else 0.2,
                    "spin_deg": traj_data.get("spin_deg", 5.0) if traj_data else 5.0,
                    "distance_from_crease_m": traj_data.get("distance_from_crease_m", 4.5) if traj_data else 4.5,
                    "length_zone": traj_data.get("length_zone", "Good Length") if traj_data else "Good Length",
                    "lateral_line": traj_data.get("lateral_line", "Middle Stump") if traj_data else "Middle Stump",
                    "bounce_coord": traj_data.get("bounce_coord") if traj_data else None,
                    "trajectory_3d": traj_data.get("trajectory_3d") if traj_data else None,
                    "release_height_m": traj_data.get("release_height_m", 2.15) if traj_data else 2.15,
                    "release_lateral_m": traj_data.get("release_lateral_m", 0.0) if traj_data else 0.0,
                    "arrival_height_m": traj_data.get("arrival_height_m", 0.68) if traj_data else 0.68,
                    "release_frame": traj_data.get("release_frame") if traj_data else None,
                    "bounce_frame": traj_data.get("bounce_frame") if traj_data else None,
                    "end_frame": traj_data.get("end_frame") if traj_data else None,
                    "frames_processed": frame_count
                }
                session_info = add_delivery_to_session(session_id, delivery_record)
                if session_info:
                    updated = False
                    if player_id and session_info.get("player_id") != player_id:
                        session_info["player_id"] = player_id
                        updated = True
                    if team_id and session_info.get("team_id") != team_id:
                        session_info["team_id"] = team_id
                        updated = True
                    if updated:
                        update_session(session_id, session_info)
            except Exception as e:
                print(f"[Session] Failed to add delivery to session {session_id}: {e}")

        return JSONResponse({
            "success": True,
            "filename": input_filename,
            "frames_processed": frame_count,
            "ball_frames_tracked": ball_frames,
            "ball_frames_detected": ball_frames,
            "total_ball_detections": total_ball_detections,
            "duration_sec": round(frame_count / fps, 2),
            "processing_time_sec": round(total_time, 2),
            "avg_fps": round(avg_fps, 1),
            "calibration_locked": locked_calib is not None,
            "trajectory": traj_data,
            "video_url": f"/static/outputs/{out_name}",
            "download_url": f"/api/download?file={out_name}&filename=detected_ball_{input_filename}",
            "session": session_info
        })
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Delivery processing error: {str(e)}")
    finally:
        if is_temp and src_video_path and os.path.exists(src_video_path):
            os.remove(src_video_path)

# ==========================================================
# CRICKET SESSION MANAGEMENT APIS
# ==========================================================
@app.get("/api/sessions")
async def api_list_sessions(team_id: str = None, player_id: str = None):
    return JSONResponse(list_sessions(team_id=team_id, player_id=player_id))

@app.post("/api/sessions")
async def api_create_session(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = body.get("name", "")
    bowler_name = body.get("bowler_name", "")
    bowling_type = body.get("bowling_type", "Right-arm Fast")
    target_balls = int(body.get("target_balls", 5))
    has_wickets = bool(body.get("has_wickets", True))
    player_id = body.get("player_id")
    team_id = body.get("team_id")
    squad_id = body.get("squad_id")
    session = create_session(
        name=name,
        bowler_name=bowler_name,
        bowling_type=bowling_type,
        target_balls=target_balls,
        has_wickets=has_wickets,
        player_id=player_id,
        team_id=team_id,
        squad_id=squad_id
    )
    return JSONResponse(session)

@app.get("/api/players")
async def api_list_all_players(team_id: str = None):
    return JSONResponse(list_players(team_id=team_id))

@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(sess)

@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    ok = delete_session(session_id)
    return JSONResponse({"success": ok})

@app.delete("/api/sessions/{session_id}/deliveries/{delivery_id}")
async def api_delete_delivery(session_id: str, delivery_id: str):
    sess = delete_delivery_from_session(session_id, delivery_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session or delivery not found")
    return JSONResponse(sess)

@app.post("/api/sessions/multi-stats")
async def api_get_multi_stats(request: Request):
    """
    Computes unified analytics across multiple selected sessions.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    session_ids = body.get("session_ids") or []
    if not session_ids:
        raise HTTPException(status_code=400, detail="session_ids list is required")

    combined = aggregate_multiple_sessions(session_ids)
    if not combined:
        raise HTTPException(status_code=404, detail="No matching sessions found")
    return JSONResponse(combined)

# ==========================================================
# TEAMS & SQUADS HIERARCHY APIS (Fulltrack AI Model)
# ==========================================================
@app.get("/api/teams")
async def api_list_teams():
    return JSONResponse(list_teams())

@app.post("/api/teams")
async def api_create_team(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")
    desc = body.get("description", "")
    new_team = create_team(name=name, description=desc)
    return JSONResponse(new_team)

@app.get("/api/teams/{team_id}")
async def api_get_team(team_id: str):
    team = get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return JSONResponse(team)

@app.put("/api/teams/{team_id}")
async def api_update_team(team_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    team = update_team(team_id, body)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return JSONResponse(team)

# Squads API
@app.get("/api/teams/{team_id}/squads")
async def api_list_squads(team_id: str):
    return JSONResponse(list_squads(team_id))

@app.post("/api/teams/{team_id}/squads")
async def api_create_squad(team_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Squad name is required")
    squad = create_squad(
        team_id=team_id,
        name=name,
        category=body.get("category", "Senior Men"),
        age_group=body.get("age_group", "Open"),
        supported_format=body.get("supported_format", "All Formats"),
        description=body.get("description", ""),
        coach=body.get("coach", ""),
        status=body.get("status", "Active")
    )
    return JSONResponse(squad)

@app.put("/api/teams/{team_id}/squads/{squad_id}")
async def api_update_squad(team_id: str, squad_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    squad = update_squad(squad_id, body)
    if not squad:
        raise HTTPException(status_code=404, detail="Squad not found")
    return JSONResponse(squad)

@app.delete("/api/teams/{team_id}/squads/{squad_id}")
async def api_delete_squad(team_id: str, squad_id: str):
    delete_squad(squad_id)
    return JSONResponse({"success": True, "message": "Squad deleted successfully"})

# Players API
@app.get("/api/teams/{team_id}/players")
async def api_list_team_players(team_id: str):
    players = list_players(team_id=team_id)
    return JSONResponse(players)

@app.post("/api/teams/{team_id}/players")
async def api_add_team_player(team_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Player name is required")

    result = create_player(
        team_id=team_id,
        name=name,
        display_name=body.get("display_name", ""),
        role=body.get("role", "All-rounder"),
        batting_style=body.get("batting_style", "Right"),
        bowling_style=body.get("bowling_style", "Right Medium"),
        bowling_type=body.get("bowling_type", ""),
        is_wicketkeeper=bool(body.get("is_wicketkeeper", False)),
        jersey_number=str(body.get("jersey_number", "")),
        preferred_position=body.get("preferred_position", ""),
        squad_id=body.get("squad_id", ""),
        status=body.get("status", "Active"),
        is_admin=bool(body.get("is_admin", False)),
        is_captain=bool(body.get("is_captain", False)),
        is_vice_captain=bool(body.get("is_vice_captain", False)),
        dob=body.get("dob", ""),
        gender=body.get("gender", "Male"),
        contact=body.get("contact", ""),
        email=body.get("email", ""),
        city=body.get("city", ""),
        avatar_url=body.get("avatar_url", "")
    )
    if isinstance(result, dict) and result.get("error") == "duplicate":
        return JSONResponse(result, status_code=409)
    return JSONResponse(result)

@app.post("/api/teams/{team_id}/players/assign-existing")
async def api_assign_existing_player(team_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    player_id = body.get("player_id", "").strip()
    squad_id = body.get("squad_id", "").strip()
    if not player_id:
        raise HTTPException(status_code=400, detail="player_id is required")
    player = assign_existing_player_to_team(player_id, team_id, squad_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return JSONResponse(player)

@app.get("/api/registered-players")
async def api_list_registered_players():
    return JSONResponse(list_all_registered_players())

@app.get("/api/players/{player_id}")
async def api_get_player(player_id: str):
    player = get_player(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return JSONResponse(player)

@app.put("/api/players/{player_id}")
async def api_update_player(player_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    player = update_player(player_id, body)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return JSONResponse(player)

@app.patch("/api/players/{player_id}/status")
async def api_set_player_status(player_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = body.get("status", "Active")
    player = set_player_status(player_id, status)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return JSONResponse(player)

@app.delete("/api/teams/{team_id}/players/{player_id}")
async def api_remove_player_from_team(team_id: str, player_id: str):
    success = remove_player_from_team(team_id, player_id)
    if not success:
        raise HTTPException(status_code=404, detail="Player not found in team")
    return JSONResponse({"success": True, "message": "Player removed from team successfully"})

@app.post("/api/upload-avatar")
async def api_upload_avatar(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")
    ext = os.path.splitext(file.filename)[1].lower() or ".jpg"
    filename = f"avatar_{int(time.time())}_{os.urandom(3).hex()}{ext}"
    out_dir = os.path.join(BASE_DIR, "static", "images", "avatars")
    os.makedirs(out_dir, exist_ok=True)
    fpath = os.path.join(out_dir, filename)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5MB")
    with open(fpath, "wb") as f:
        f.write(contents)
    return JSONResponse({"avatar_url": f"/static/images/avatars/{filename}"})

@app.get("/api/players/{player_id}/sessions")
async def api_get_player_sessions(player_id: str):
    sessions = get_player_sessions(player_id)
    return JSONResponse(sessions)

@app.post("/api/sessions/team-bundle")
async def api_get_team_bundle(request: Request):
    """
    Returns complete multi-session data, player, team and deliveries for team analysis view.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    session_ids = body.get("session_ids") or []
    if not session_ids:
        raise HTTPException(status_code=400, detail="session_ids list is required")

    sessions_data = []
    all_deliveries = []
    player_id = body.get("player_id")
    team_id = body.get("team_id")

    global_ball_idx = 1
    for sid in session_ids:
        sess = get_session(sid)
        if not sess:
            continue
        if not player_id and sess.get("player_id"):
            player_id = sess.get("player_id")
        if not team_id and sess.get("team_id"):
            team_id = sess.get("team_id")

        deliveries = sess.get("deliveries", [])
        speeds_mph = [float(d.get("speed_mph", 0)) for d in deliveries if d.get("speed_mph") and float(d.get("speed_mph", 0)) > 0]
        avg_mph = round(sum(speeds_mph)/len(speeds_mph), 1) if speeds_mph else 0.0
        avg_kph = round(avg_mph * 1.60934, 1)

        enriched_deliveries = []
        for d in deliveries:
            d_item = dict(d)
            d_item["session_id"] = sess["id"]
            d_item["session_name"] = sess.get("name", "Session")
            d_item["global_ball_number"] = global_ball_idx
            if not d_item.get("speed_kph") and d_item.get("speed_mph"):
                d_item["speed_kph"] = round(float(d_item["speed_mph"]) * 1.60934, 1)
            enriched_deliveries.append(d_item)
            all_deliveries.append(d_item)
            global_ball_idx += 1

        sessions_data.append({
            "id": sess["id"],
            "name": sess.get("name", "Session"),
            "bowler_name": sess.get("bowler_name", ""),
            "created_at": sess.get("created_at", ""),
            "avg_speed_mph": avg_mph,
            "avg_speed_kph": avg_kph,
            "deliveries": enriched_deliveries,
            "deliveries_count": len(enriched_deliveries)
        })

    player = get_player(player_id) if player_id else None
    team = get_team(team_id) if team_id else None

    return JSONResponse({
        "team": team,
        "player": player,
        "sessions": sessions_data,
        "total_deliveries": len(all_deliveries),
        "all_deliveries": all_deliveries
    })

@app.get("/api/players/{player_id}/reports")
async def api_get_player_reports(player_id: str):
    """Returns saved analysis reports for the player."""
    reports = list_player_reports(player_id)
    return JSONResponse(reports)

@app.post("/api/reports/generate")
async def api_generate_report(request: Request):
    """Generates and persists an analysis report for player and selected sessions."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    report = create_report(data)
    return JSONResponse(report)

@app.get("/api/reports/{report_id}/download")
async def api_download_report(report_id: str):
    """Downloads a report as JSON/printable summary."""
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    content = json.dumps(report, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=\"{report_id}_analysis_report.json\""}
    )

@app.post("/api/sessions/compile-highlight")
async def api_compile_highlight(request: Request):
    """
    Stitches multiple tracked delivery MP4s into a single continuous Highlight Reel video.
    Supports session_ids, session_id, or delivery_ids.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    
    session_ids = body.get("session_ids") or []
    if not session_ids and body.get("session_id"):
        session_ids = [body["session_id"]]
    delivery_ids = body.get("delivery_ids") or []

    # Gather all valid delivery MP4 paths
    delivery_items = []
    bowler_name = "Bowler"
    speeds = []

    for sid in session_ids:
        sess = get_session(sid)
        if not sess:
            continue
        bowler_name = sess.get("bowler_name") or bowler_name
        for d in sess.get("deliveries", []):
            if delivery_ids:
                did = str(d.get("id") or d.get("ball_number"))
                if did not in [str(x) for x in delivery_ids]:
                    continue
            v_url = d.get("video_url")
            if v_url:
                fname = os.path.basename(v_url)
                abs_v = os.path.join(STATIC_DIR, "outputs", fname)
                if os.path.exists(abs_v):
                    spd_mph = float(d.get("speed_mph", 0.0)) if d.get("speed_mph") else 0.0
                    spd_kph = float(d.get("speed_kph", 0.0)) if d.get("speed_kph") else (spd_mph * 1.60934)
                    if spd_mph > 0:
                        speeds.append(spd_mph)
                    delivery_items.append({
                        "path": abs_v,
                        "ball_number": len(delivery_items) + 1,
                        "speed_mph": round(spd_mph, 1),
                        "speed_kph": round(spd_kph, 1),
                        "length_zone": d.get("length_zone", "Good Length"),
                        "lateral_line": d.get("lateral_line", "Off Stump"),
                        "bowler_name": bowler_name
                    })

    if not delivery_items:
        raise HTTPException(status_code=400, detail="No delivery video files found for compilation.")

    timestamp = int(time.time())
    out_filename = f"spell_compilation_{timestamp}.mp4"
    out_path = os.path.join(STATIC_DIR, "outputs", out_filename)

    temp_dir = tempfile.mkdtemp()
    stamped_clips = []

    try:
        # Stamp broadcast lower-third overlay on each delivery clip
        for idx, item in enumerate(delivery_items):
            vp = item["path"]
            ball_no = item["ball_number"]
            spd = item["speed_mph"]
            zone = item["length_zone"].upper()
            bname = bowler_name.upper()

            banner_text = f"{bname}  |  BALL {ball_no}  |  {spd} MPH  |  {zone}"
            clean_banner = banner_text.replace("'", "").replace(":", "-")
            filter_str = f"drawtext=text='{clean_banner}':fontcolor=white:fontsize=14:box=1:boxcolor=black@0.65:boxborderw=6:x=(w-text_w)/2:y=h-48"

            stamped_clip = os.path.join(temp_dir, f"stamped_{idx}.mp4")
            cmd_stamp = [
                "/usr/local/bin/ffmpeg", "-y",
                "-i", vp,
                "-vf", filter_str,
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                stamped_clip
            ]
            run_res = subprocess.run(cmd_stamp, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if run_res.returncode == 0 and os.path.exists(stamped_clip):
                stamped_clips.append(stamped_clip)
            else:
                stamped_clips.append(vp)

        # Concat stamped clips
        if len(stamped_clips) == 1:
            shutil.copyfile(stamped_clips[0], out_path)
        else:
            concat_txt = os.path.join(temp_dir, "concat.txt")
            with open(concat_txt, "w") as f_txt:
                for sc in stamped_clips:
                    f_txt.write(f"file '{sc}'\n")

            cmd_concat = [
                "/usr/local/bin/ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_txt,
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                out_path
            ]
            subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Highlight reel compilation failed: {str(e)}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

    avg_spd = round(sum(speeds) / len(speeds), 1) if speeds else 0.0
    max_spd = round(max(speeds), 1) if speeds else 0.0

    # Save meta json alongside the mp4 for the shareable web player page
    meta_path = os.path.join(STATIC_DIR, "outputs", f"spell_compilation_{timestamp}.json")
    try:
        with open(meta_path, "w") as f_meta:
            json.dump({
                "filename": out_filename,
                "bowler_name": bowler_name,
                "deliveries_count": len(delivery_items),
                "avg_speed_mph": avg_spd,
                "max_speed_mph": max_spd,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(timestamp)),
                "deliveries": delivery_items
            }, f_meta, indent=2)
    except Exception:
        pass

    return JSONResponse({
        "success": True,
        "video_url": f"/static/outputs/{out_filename}",
        "reel_url": f"/reel/{out_filename}",
        "download_url": f"/api/download?file={out_filename}&filename=Spell_Highlight_{bowler_name}_{timestamp}.mp4",
        "deliveries_count": len(delivery_items),
        "bowler_name": bowler_name,
        "avg_speed_mph": avg_spd,
        "max_speed_mph": max_spd
    })


@app.get("/reel/{compilation_name}", response_class=HTMLResponse)
async def view_shared_reel(compilation_name: str, request: Request):
    """
    Public shareable broadcast reel player page with video, telemetry cards,
    viral caption copy box, and 1-click social media sharing buttons.
    """
    if not compilation_name.endswith(".mp4"):
        compilation_name = f"{compilation_name}.mp4"

    video_rel_path = f"/static/outputs/{compilation_name}"
    abs_path = os.path.join(STATIC_DIR, "outputs", compilation_name)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Highlight compilation video not found.")

    meta_name = compilation_name.replace(".mp4", ".json")
    abs_meta = os.path.join(STATIC_DIR, "outputs", meta_name)
    meta = {}
    if os.path.exists(abs_meta):
        try:
            with open(abs_meta, "r") as f:
                meta = json.load(f)
        except Exception:
            pass

    bowler = meta.get("bowler_name") or "Bowler"
    count = meta.get("deliveries_count") or 1
    avg_spd = meta.get("avg_speed_mph") or 0.0
    peak_spd = meta.get("max_speed_mph") or 0.0

    caption_text = (
        f"🏏 Watch my cricket bowling spell tracked with Trajecta Coach AI!\n"
        f"Bowler: {bowler}\n"
        f"🎯 {count} deliveries tracked with 3D Hawk-Eye DRS Telemetry\n"
        f"⚡ Avg Speed: {avg_spd} mph | Peak: {peak_spd} mph\n"
        f"#CricketVision #HawkEye #CricketTraining #BowlingSpell #TrajectaAI"
    )

    full_video_url = str(request.url)
    download_url = f"/api/download?file={compilation_name}&filename=Spell_Highlight_{bowler}.mp4"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{bowler} · Bowling Highlight Reel | Trajecta Coach AI</title>
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-dark: #0a0d14;
      --bg-card: #151822;
      --text-white: #f8fafc;
      --text-muted: #94a3b8;
      --primary-red: #ef4444;
      --primary-blue: #0284c7;
      --primary-green: #10b981;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg-dark);
      color: var(--text-white);
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 24px 16px 48px 16px;
    }}
    .reel-container {{
      width: 100%;
      max-width: 620px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .brand-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 4px 0 12px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .brand-title {{
      font-size: 1.15rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .brand-highlight {{ color: var(--primary-red); }}
    .badge-live {{
      background: rgba(239, 68, 68, 0.16);
      color: #ef4444;
      border: 1px solid rgba(239, 68, 68, 0.35);
      border-radius: 9999px;
      padding: 3px 10px;
      font-size: 0.70rem;
      font-weight: 700;
      letter-spacing: 0.05em;
    }}
    .video-card {{
      background: #000000;
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
      display: flex;
      justify-content: center;
    }}
    video {{
      width: 100%;
      max-height: 72vh;
      display: block;
      background: #000000;
      object-fit: contain;
    }}
    .telemetry-strip {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      background: var(--bg-card);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 14px 16px;
      text-align: center;
    }}
    .strip-label {{
      font-size: 0.68rem;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 4px;
    }}
    .strip-val {{
      font-size: 1.05rem;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
    }}
    .caption-card {{
      background: var(--bg-card);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 16px 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .caption-title {{
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .caption-text {{
      font-size: 0.88rem;
      line-height: 1.55;
      color: #e2e8f0;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 12px;
      white-space: pre-wrap;
      font-family: inherit;
    }}
    .btn-copy-caption {{
      background: rgba(255, 255, 255, 0.1);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 8px;
      padding: 10px;
      font-size: 0.84rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }}
    .btn-copy-caption:hover {{ background: rgba(255, 255, 255, 0.18); }}
    .social-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
    }}
    .btn-social {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 12px 6px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: var(--bg-card);
      color: #ffffff;
      font-size: 0.78rem;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .btn-social:hover {{ transform: translateY(-2px); }}
    .btn-wa:hover {{ background: #25D366; color: #fff; }}
    .btn-x:hover {{ background: #000; border-color: #fff; color: #fff; }}
    .btn-ig:hover {{ background: linear-gradient(45deg, #f09433, #dc2743, #bc1888); color: #fff; }}
    .btn-yt:hover {{ background: #ff0000; color: #fff; }}
    .bottom-actions {{
      display: flex;
      gap: 10px;
      margin-top: 4px;
    }}
    .btn-download {{
      flex: 1;
      padding: 12px;
      border-radius: 10px;
      background: var(--primary-blue);
      color: #ffffff;
      font-weight: 700;
      text-decoration: none;
      text-align: center;
      font-size: 0.88rem;
      box-shadow: 0 4px 14px rgba(2, 132, 199, 0.35);
      transition: all 0.2s ease;
    }}
    .btn-home {{
      flex: 1;
      padding: 12px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.08);
      color: #ffffff;
      border: 1px solid rgba(255, 255, 255, 0.14);
      font-weight: 700;
      text-decoration: none;
      text-align: center;
      font-size: 0.88rem;
      transition: all 0.2s ease;
    }}
  </style>
</head>
<body>
  <div class="reel-container">
    <div class="brand-header">
      <div class="brand-title">
        <span>TRAJECTA</span><span class="brand-highlight">.AI</span>
      </div>
      <span class="badge-live">HAWK-EYE DRS BROADCAST</span>
    </div>

    <div class="video-card">
      <video src="{video_rel_path}" controls playsinline autoplay loop></video>
    </div>

    <div class="telemetry-strip">
      <div>
        <div class="strip-label">Bowler</div>
        <div class="strip-val">{bowler}</div>
      </div>
      <div>
        <div class="strip-label">Balls</div>
        <div class="strip-val" style="color:#ef4444;">{count}</div>
      </div>
      <div>
        <div class="strip-label">Avg Pace</div>
        <div class="strip-val" style="color:#0284c7;">{avg_spd} mph</div>
      </div>
      <div>
        <div class="strip-label">Peak Pace</div>
        <div class="strip-val" style="color:#10b981;">{peak_spd} mph</div>
      </div>
    </div>

    <div class="caption-card">
      <div class="caption-title">Broadcast Caption &amp; Telemetry</div>
      <div class="caption-text" id="caption-content">{caption_text}</div>
      <button type="button" class="btn-copy-caption" id="btn-copy-caption" onclick="copyCaption()">
        <span id="copy-btn-text">📋 Copy Caption &amp; Viral Hashtags</span>
      </button>
    </div>

    <div class="social-grid">
      <a class="btn-social btn-wa" href="https://api.whatsapp.com/send?text={urllib.parse.quote(caption_text + chr(10) + chr(10) + 'Watch Reel: ' + full_video_url)}" target="_blank">
        <span>WhatsApp</span>
      </a>
      <a class="btn-social btn-x" href="https://twitter.com/intent/tweet?text={urllib.parse.quote(caption_text)}&url={urllib.parse.quote(full_video_url)}" target="_blank">
        <span>Post to X</span>
      </a>
      <button type="button" class="btn-social btn-ig" onclick="copyAndDownload()">
        <span>Instagram</span>
      </button>
      <button type="button" class="btn-social btn-yt" onclick="copyAndDownload()">
        <span>YouTube</span>
      </button>
    </div>

    <div class="bottom-actions">
      <a class="btn-download" href="{download_url}" download>Download MP4 Video</a>
      <a class="btn-home" href="/">Track Your Bowling Spell</a>
    </div>
  </div>

  <script>
    function copyCaption() {{
      const text = document.getElementById('caption-content').innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.getElementById('copy-btn-text');
        btn.innerText = "✓ Copied to Clipboard!";
        setTimeout(() => {{ btn.innerText = "📋 Copy Caption & Viral Hashtags"; }}, 2500);
      }}).catch(() => {{
        prompt("Copy Caption:", text);
      }});
    }}

    function copyAndDownload() {{
      copyCaption();
      const a = document.createElement('a');
      a.href = '{download_url}';
      a.download = 'Spell_Highlight_{bowler}.mp4';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      alert("Caption copied! The MP4 video is downloading. Open your social app to upload.");
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.patch("/api/sessions/{session_id}")
@app.put("/api/sessions/{session_id}")
async def api_update_session(session_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    sess = update_session(session_id, body)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(sess)

@app.post("/api/sessions/{session_id}/avatar")
async def api_upload_session_avatar(session_id: str, file: UploadFile = File(...)):
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    
    avatar_dir = os.path.join(os.path.dirname(__file__), "static", "outputs", "avatars")
    os.makedirs(avatar_dir, exist_ok=True)
    
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        ext = ".jpg"
        
    out_filename = f"avatar_{session_id}_{int(time.time())}{ext}"
    out_path = os.path.join(avatar_dir, out_filename)
    
    content = await file.read()
    with open(out_path, "wb") as f:
        f.write(content)
        
    avatar_url = f"/static/outputs/avatars/{out_filename}"
    sess = update_session(session_id, {"avatar_url": avatar_url})
    return JSONResponse({"success": True, "avatar_url": avatar_url, "session": sess})



@app.post("/api/detect-video")
async def detect_video(
    file: UploadFile = File(None),
    sample_id: str = Form(None),
    video_path: str = Form(None),
    conf: float = Form(0.35),
    pitch_calibration: bool = Form(True),
    render_mode: str = Form("black_stumps"),
    show_pitch_zones: bool = Form(True),
    batting_end: str = Form("far"),
    start_time: float = Form(0.0),
    end_time: float = Form(None)
):
    src_video_path = None
    is_temp = False
    input_filename = "video.mp4"

    if file and file.filename:
        input_filename = file.filename
        temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1])
        src_video_path = temp_in.name
        is_temp = True
        with open(src_video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    elif sample_id:
        sample_file = os.path.join(STATIC_DIR, "samples", sample_id)
        if not os.path.exists(sample_file):
            raise HTTPException(status_code=404, detail="Sample video not found")
        src_video_path = sample_file
        input_filename = sample_id
    elif video_path:
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail=f"Local video not found: {video_path}")
        src_video_path = video_path
        input_filename = os.path.basename(video_path)
    else:
        raise HTTPException(status_code=400, detail="Provide a video file, sample_id, or video_path")

    try:
        cap = cv2.VideoCapture(src_video_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot read video file")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        start_frame = int(round(start_time * fps)) if start_time and start_time > 0 else 0
        end_frame = int(round(end_time * fps)) if end_time and end_time > 0 else total_frames
        start_frame = max(0, min(start_frame, total_frames - 1))
        end_frame = max(start_frame + 1, min(end_frame, total_frames))
        num_target_frames = end_frame - start_frame

        out_name = f"video_{int(time.time())}.mp4"
        out_path = os.path.join(OUTPUTS_DIR, out_name)
        raw_out_path = os.path.join(OUTPUTS_DIR, f"raw_{out_name}")
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(raw_out_path, fourcc, fps, (w, h))

        # 1. Fast pre-scan upfront within delivery window to lock pitch calibration
        locked_calib = None
        if pitch_calibration:
            scan_cap = cv2.VideoCapture(temp_in.name)
            scan_cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            scan_limit = min(num_target_frames, 90)
            best_score = -1.0
            idx = 0
            while idx < scan_limit:
                ret, sframe = scan_cap.read()
                if not ret:
                    break
                if idx % 2 == 0:
                    sres = model.predict(source=sframe, conf=conf, verbose=False)
                    sboxes = []
                    if sres[0].boxes is not None:
                        for b in sres[0].boxes:
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

        frame_count = 0
        total_detections = 0
        t0 = time.time()

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        for curr_frame_idx in range(start_frame, end_frame):
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            
            if pitch_calibration:
                if locked_calib is not None:
                    # Locked constant pitch calibration across the whole video
                    annotated = render_calibrated_pitch_overlay(
                        frame, locked_calib, render_mode=render_mode,
                        show_pitch_zones=show_pitch_zones, batting_end=batting_end
                    )
                    total_detections += 2
                else:
                    # Dynamically detect on current frame and lock as soon as 2 wickets are detected
                    results = model.predict(source=frame, conf=conf, verbose=False)
                    boxes_data = []
                    if results[0].boxes is not None:
                        for b in results[0].boxes:
                            xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                            confidence = float(b.conf[0].cpu().numpy())
                            boxes_data.append({"box": xyxy, "confidence": confidence})
                            total_detections += 1
                    
                    cmodel = compute_pitch_calibration_model(boxes_data, h)
                    if cmodel is not None:
                        locked_calib = cmodel  # Constant lock from here on!
                        annotated = render_calibrated_pitch_overlay(
                            frame, locked_calib, render_mode=render_mode,
                            show_pitch_zones=show_pitch_zones, batting_end=batting_end
                        )
                    else:
                        annotated = annotate_stump_detection_only(frame, boxes_data, render_mode=render_mode)
            else:
                results = model.predict(source=frame, conf=conf, verbose=False)
                boxes_data = []
                if results[0].boxes is not None:
                    for b in results[0].boxes:
                        xyxy = b.xyxy[0].cpu().numpy().astype(int).tolist()
                        confidence = float(b.conf[0].cpu().numpy())
                        boxes_data.append({"box": xyxy, "confidence": confidence})
                        total_detections += 1
                annotated = annotate_stump_detection_only(frame, boxes_data, render_mode=render_mode)

            out_writer.write(annotated)

        cap.release()
        out_writer.release()
        total_time = time.time() - t0
        avg_fps = frame_count / total_time if total_time > 0 else 0

        # Convert to browser-compatible H.264 mp4 via ffmpeg if available
        try:
            import subprocess
            subprocess.run([
                "/usr/local/bin/ffmpeg", "-y", "-i", raw_out_path,
                "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                out_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(raw_out_path):
                os.remove(raw_out_path)
        except Exception:
            if os.path.exists(raw_out_path) and not os.path.exists(out_path):
                os.rename(raw_out_path, out_path)

        return JSONResponse({
            "success": True,
            "filename": input_filename,
            "frames_processed": frame_count,
            "duration_sec": round(frame_count / fps, 2),
            "processing_time_sec": round(total_time, 2),
            "avg_fps": round(avg_fps, 1),
            "total_stump_detections": total_detections,
            "calibration_locked": locked_calib is not None,
            "video_url": f"/static/outputs/{out_name}",
            "download_url": f"/api/download?file={out_name}&filename=detected_{input_filename}"
        })
    finally:
        if is_temp and src_video_path and os.path.exists(src_video_path):
            os.remove(src_video_path)

@app.api_route("/api/download", methods=["GET", "HEAD"])
async def download_file(file: str, filename: str = None):
    """
    Guarantees reliable, browser-compliant binary file download with explicit
    Content-Disposition: attachment and matching MIME type (video/mp4 or image/jpeg).
    Prevents browsers from misinterpreting video outputs as text files.
    """
    base_file = os.path.basename(file)
    file_path = os.path.join(OUTPUTS_DIR, base_file)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Requested file not found")

    ext = os.path.splitext(base_file)[1].lower()
    
    if not filename:
        download_name = base_file
    else:
        download_name = os.path.basename(filename)

    # Sanitize download name: remove hashes (#), spaces, emojis, and illegal characters
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', download_name)
    clean_name = re.sub(r'_+', '_', clean_name).strip('_')
    if not clean_name.lower().endswith(ext):
        clean_name += ext

    media_type = "video/mp4" if ext == ".mp4" else ("image/jpeg" if ext in [".jpg", ".jpeg"] else "application/octet-stream")
    encoded_name = urllib.parse.quote(clean_name)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=clean_name,
        headers={
            "Content-Disposition": f'attachment; filename="{clean_name}"; filename*=UTF-8\'\'{encoded_name}',
            "Content-Type": media_type,
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )

# Mount static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# Root fallback route for direct static asset requests (e.g. /styles.css, /app.js, /logo.png, /favicon.png)
@app.get("/{file_path:path}")
def serve_static_root(file_path: str):
    full_path = os.path.join(STATIC_DIR, file_path)
    if os.path.isfile(full_path):
        return FileResponse(full_path)
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
