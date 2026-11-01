#!/usr/bin/env python3
"""
Cricket Pitch Geometry & Perspective Calibration Module
Uses trained YOLO wicket detections to:
1. Locate wicket base reference points (bottom-center of bounding boxes).
2. Connect near and far wickets to establish the pitch longitudinal center axis.
3. Measure image pixel distance vs 20.12 m (22 yards) physical pitch length.
4. Analyze visible pitch references (creases, wicket widths, ground markings).
5. Build perspective transformation (homography) to project pitch boundaries and creases.
6. Generate comprehensive visual debug output.
"""

import os
import sys
import cv2
import numpy as np
from ultralytics import YOLO

# Real-world pitch dimensions in meters (MCC Laws of Cricket)
PITCH_LENGTH_M = 20.12      # 22 yards between wicket bases
PITCH_WIDTH_M = 3.05        # 10 feet total pitch width (1.524m each side of centerline)
BOWLING_CREASE_W_M = 2.64   # 8 ft 8 in (1.32m each side)
POPPING_CREASE_OFFSET_M = 1.22 # 4 ft in front of bowling crease
POPPING_CREASE_W_M = 3.66   # At least 12 ft long (1.83m each side)
WICKET_WIDTH_M = 0.2286     # 9 inches (stump set width)

def project_point(H, X, Y):
    """Transform ground coordinate (X, Y) to image pixel coordinate (u, v) using homography H."""
    pt = np.array([X, Y, 1.0], dtype=np.float64)
    res = H @ pt
    if abs(res[2]) < 1e-7:
        return None
    u = res[0] / res[2]
    v = res[1] / res[2]
    return (int(round(u)), int(round(v)))

def draw_hud_box(img, lines, origin=(25, 30)):
    font = cv2.FONT_HERSHEY_DUPLEX
    font_scale = 0.52
    thickness = 1
    line_h = 24
    max_w = 0
    for l in lines:
        (tw, th), _ = cv2.getTextSize(l, font, font_scale, thickness)
        max_w = max(max_w, tw)
    
    x, y = origin
    pad = 12
    card_w = max_w + pad * 2
    card_h = len(lines) * line_h + pad * 2
    
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + card_w, y + card_h), (12, 16, 22), -1)
    cv2.addWeighted(overlay, 0.85, img, 0.15, 0, img)
    cv2.rectangle(img, (x, y), (x + card_w, y + card_h), (0, 235, 120), 1)
    
    for i, line in enumerate(lines):
        color = (255, 255, 255)
        if "PITCH" in line or "AXIS" in line:
            color = (0, 235, 120)
        elif "WARNING" in line or "NOTE" in line:
            color = (0, 220, 255)
        elif "20.12m" in line:
            color = (255, 200, 50)
        cv2.putText(img, line, (x + pad, y + pad + (i + 1) * line_h - 6),
                    font, font_scale, color, thickness, cv2.LINE_AA)

def analyze_and_calibrate_pitch(image_path, model, output_path=None):
    img = cv2.imread(image_path)
    if img is None:
        print(f"[Error] Could not read image: {image_path}")
        return None

    h_img, w_img = img.shape[:2]
    print(f"\n{'='*70}")
    print(f"CALIBRATING PITCH GEOMETRY: {os.path.basename(image_path)}")
    print(f"Image Resolution: {w_img} x {h_img}")
    print(f"{'='*70}")

    # STEP 1: Run Stump Detector
    results = model.predict(source=img, conf=0.30, verbose=False)[0]
    boxes = results.boxes

    if boxes is None or len(boxes) == 0:
        print("[!] No wickets detected in frame.")
        return None

    wicket_detections = []
    for b in boxes:
        xyxy = b.xyxy[0].cpu().numpy()
        conf = float(b.conf[0].cpu().numpy())
        x1, y1, x2, y2 = xyxy
        xc = (x1 + x2) / 2.0
        yc_bottom = y2 # Bottom-center reference point (ground contact)
        w_box = x2 - x1
        h_box = y2 - y1
        wicket_detections.append({
            'box': (int(x1), int(y1), int(x2), int(y2)),
            'conf': conf,
            'xc': xc,
            'ground_ref': (xc, yc_bottom),
            'w_box': w_box,
            'h_box': h_box
        })

    print(f"[Step 1 & 2] Detected {len(wicket_detections)} wicket(s):")
    for i, w in enumerate(wicket_detections):
        print(f"   Wicket #{i+1}: Box={w['box']} | Ground Ref (xc, y2)=({w['ground_ref'][0]:.1f}, {w['ground_ref'][1]:.1f}) | Conf={w['conf']:.3f}")

    vis_img = img.copy()

    # Draw individual wicket centerlines and reference points
    for i, w in enumerate(wicket_detections):
        x1, y1, x2, y2 = w['box']
        xc = int(round(w['xc']))
        
        # 1. Bounding box
        cv2.rectangle(vis_img, (x1, y1), (x2, y2), (0, 235, 120), 2)
        
        # 2. Vertical centerline through middle of box
        cv2.line(vis_img, (xc, y1), (xc, y2), (0, 255, 255), 2)
        
        # 3. Bottom-center reference point (ground contact)
        gx, gy = int(round(w['ground_ref'][0])), int(round(w['ground_ref'][1]))
        cv2.circle(vis_img, (gx, gy), 7, (0, 0, 255), -1)          # Red inner dot
        cv2.circle(vis_img, (gx, gy), 11, (0, 235, 120), 2)        # Green ring
        cv2.drawMarker(vis_img, (gx, gy), (255, 255, 255), cv2.MARKER_CROSS, 16, 1)

        # Label ground reference
        cv2.putText(vis_img, f"Wicket #{i+1} Ground Ref ({gx},{gy})", (gx + 12, gy + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    # STEP 3 & 4: Two Wickets Verification & Pitch Axis
    if len(wicket_detections) < 2:
        print("\n[Notice] Single wicket detected. Cannot form 2-point pitch axis without second wicket.")
        draw_hud_box(vis_img, [
            "PITCH CALIBRATION AUDIT: SINGLE WICKET",
            f"Wicket Detected: Ground Ref=({wicket_detections[0]['ground_ref'][0]:.1f}, {wicket_detections[0]['ground_ref'][1]:.1f})",
            "STATUS: Pitch longitudinal axis requires 2 wickets.",
            "FULL CALIBRATION: Need bowler & batsman wickets or pitch corners."
        ])
        if output_path:
            cv2.imwrite(output_path, vis_img)
        return False

    # Sort wickets by Y coordinate: Near wicket is lower down (larger Y), Far wicket is higher up (smaller Y)
    wicket_detections.sort(key=lambda item: item['ground_ref'][1], reverse=True)
    near_wicket = wicket_detections[0]
    far_wicket = wicket_detections[1]

    P_near = near_wicket['ground_ref']
    P_far = far_wicket['ground_ref']

    print(f"\n[Step 3] Near Wicket (Bowler's End): Ground Ref = ({P_near[0]:.1f}, {P_near[1]:.1f})")
    print(f"         Far Wicket (Batsman's End): Ground Ref = ({P_far[0]:.1f}, {P_far[1]:.1f})")

    # Image distance
    dx_px = P_far[0] - P_near[0]
    dy_px = P_far[1] - P_near[1]
    dist_px = np.sqrt(dx_px**2 + dy_px**2)
    axis_angle_deg = np.degrees(np.arctan2(dy_px, dx_px)) # Angle of longitudinal axis

    print(f"\n[Step 4] Measured Image Distance between wickets: {dist_px:.1f} pixels")
    print(f"         Real-World Pitch Length: {PITCH_LENGTH_M} m (22.0 yards)")
    print(f"         Longitudinal Scale (Average): {dist_px / PITCH_LENGTH_M:.2f} pixels/meter")
    print(f"         Longitudinal Axis Angle: {axis_angle_deg:.2f}° from horizontal")

    # Draw Pitch Center Line
    p_near_int = (int(round(P_near[0])), int(round(P_near[1])))
    p_far_int = (int(round(P_far[0])), int(round(P_far[1])))
    
    # Draw thicker neon cyan pitch center line
    cv2.line(vis_img, p_near_int, p_far_int, (255, 230, 0), 3) # Cyan line
    
    # Label Pitch Center Line at midpoint
    mid_x = int((p_near_int[0] + p_far_int[0]) / 2)
    mid_y = int((p_near_int[1] + p_far_int[1]) / 2)
    
    cv2.putText(vis_img, "PITCH CENTER LINE (20.12 m / 22 YDS)",
                (mid_x - 140, mid_y - 12), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 230, 0), 1, cv2.LINE_AA)
    cv2.putText(vis_img, f"Dist: {dist_px:.1f} px <-> 20.12 m",
                (mid_x - 140, mid_y + 12), cv2.FONT_HERSHEY_DUPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    # STEP 5: Additional Visible References & Perspective Homography Construction
    # Let's inspect available width references:
    # 1. Bounding box widths of near & far wickets:
    w_near_px = near_wicket['w_box']
    w_far_px = far_wicket['w_box']
    
    # Physical wicket set width is 9 inches = 0.2286m
    # Lateral scale at near wicket:
    s_near_lateral = w_near_px / WICKET_WIDTH_M # px/meter
    # Lateral scale at far wicket:
    s_far_lateral = w_far_px / WICKET_WIDTH_M   # px/meter

    print(f"\n[Step 5] Additional References Analyzed:")
    print(f"   Near Wicket Box Width: {w_near_px:.1f} px -> Lateral Scale: {s_near_lateral:.1f} px/m")
    print(f"   Far Wicket Box Width:  {w_far_px:.1f} px -> Lateral Scale: {s_far_lateral:.1f} px/m")
    print(f"   Perspective Depth Ratio (Far/Near): {s_far_lateral / s_near_lateral:.3f}")

    # Establish 4 ground-plane correspondence points for Homography:
    # World Coordinates (X, Y) in meters on ground plane:
    # X: Lateral distance from pitch centerline (positive right, negative left)
    # Y: Distance along pitch centerline from near wicket (0 to 20.12m)
    # Point 1: Near wicket left base  (-WICKET_WIDTH_M/2, 0)
    # Point 2: Near wicket right base (+WICKET_WIDTH_M/2, 0)
    # Point 3: Far wicket right base  (+WICKET_WIDTH_M/2, 20.12)
    # Point 4: Far wicket left base   (-WICKET_WIDTH_M/2, 20.12)
    
    # Compute image coordinates of these 4 ground points:
    # Normal vector to pitch centerline in image:
    perp_dx = -dy_px / dist_px
    perp_dy = dx_px / dist_px

    half_w_near = w_near_px / 2.0
    half_w_far = w_far_px / 2.0

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

    # Compute Perspective Homography Matrix H
    H, status = cv2.findHomography(pts_src, pts_dst)

    if H is None:
        print("[!] Homography matrix could not be solved.")
        return False

    print("\n[Step 6 & 7] Projective Homography Matrix H (Ground [X,Y] -> Image [u,v]):")
    print(H)

    # STEP 6 & 7: Draw Projective Pitch Overlay & Creases
    # 1. Pitch Boundary (Width = 3.05m: X = -1.524m to +1.524m, Y = 0 to 20.12m)
    p_bnd_bl = project_point(H, -PITCH_WIDTH_M / 2.0, 0.0)
    p_bnd_br = project_point(H, +PITCH_WIDTH_M / 2.0, 0.0)
    p_bnd_tr = project_point(H, +PITCH_WIDTH_M / 2.0, PITCH_LENGTH_M)
    p_bnd_tl = project_point(H, -PITCH_WIDTH_M / 2.0, PITCH_LENGTH_M)

    if all([p_bnd_bl, p_bnd_br, p_bnd_tr, p_bnd_tl]):
        pitch_poly = np.array([p_bnd_bl, p_bnd_br, p_bnd_tr, p_bnd_tl], dtype=np.int32)
        # Semi-transparent overlay on pitch surface
        pitch_overlay = vis_img.copy()
        cv2.fillPoly(pitch_overlay, [pitch_poly], (40, 90, 30)) # subtle stadium green fill
        cv2.addWeighted(pitch_overlay, 0.25, vis_img, 0.75, 0, vis_img)
        
        # Longitudinal side boundaries
        cv2.line(vis_img, p_bnd_bl, p_bnd_tl, (0, 165, 255), 2, cv2.LINE_AA) # Left edge (Orange)
        cv2.line(vis_img, p_bnd_br, p_bnd_tr, (0, 165, 255), 2, cv2.LINE_AA) # Right edge (Orange)
        
        # Pitch end boundaries
        cv2.line(vis_img, p_bnd_bl, p_bnd_br, (0, 165, 255), 1, cv2.LINE_AA)
        cv2.line(vis_img, p_bnd_tl, p_bnd_tr, (0, 165, 255), 1, cv2.LINE_AA)
        
        # Label boundary
        cv2.putText(vis_img, "PITCH BOUNDARY (3.05 m)", (p_bnd_bl[0] - 170, p_bnd_bl[1] + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1, cv2.LINE_AA)

    # 2. Bowling Creases (2.64m wide, through wicket base)
    near_bc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, 0.0)
    near_bc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, 0.0)
    if near_bc_l and near_bc_r:
        cv2.line(vis_img, near_bc_l, near_bc_r, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.putText(vis_img, "BOWLING CREASE (Near)", (near_bc_r[0] + 10, near_bc_r[1] + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

    far_bc_l = project_point(H, -BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
    far_bc_r = project_point(H, +BOWLING_CREASE_W_M / 2.0, PITCH_LENGTH_M)
    if far_bc_l and far_bc_r:
        cv2.line(vis_img, far_bc_l, far_bc_r, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(vis_img, "BOWLING CREASE (Far)", (far_bc_r[0] + 10, far_bc_r[1] + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

    # 3. Popping Creases (1.22m inside from bowling crease)
    near_pc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    near_pc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M)
    if near_pc_l and near_pc_r:
        cv2.line(vis_img, near_pc_l, near_pc_r, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(vis_img, "POPPING CREASE (+1.22m)", (near_pc_l[0] - 180, near_pc_l[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    far_pc_l = project_point(H, -POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    far_pc_r = project_point(H, +POPPING_CREASE_W_M / 2.0, PITCH_LENGTH_M - POPPING_CREASE_OFFSET_M)
    if far_pc_l and far_pc_r:
        cv2.line(vis_img, far_pc_l, far_pc_r, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(vis_img, "POPPING CREASE (-1.22m)", (far_pc_l[0] - 180, far_pc_l[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1, cv2.LINE_AA)

    # 4. Return Creases (Connect bowling and popping crease ends)
    ret_near_l1 = project_point(H, -BOWLING_CREASE_W_M / 2.0, 0.0)
    ret_near_l2 = project_point(H, -BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M + 1.22)
    if ret_near_l1 and ret_near_l2:
        cv2.line(vis_img, ret_near_l1, ret_near_l2, (200, 200, 200), 1, cv2.LINE_AA)

    ret_near_r1 = project_point(H, +BOWLING_CREASE_W_M / 2.0, 0.0)
    ret_near_r2 = project_point(H, +BOWLING_CREASE_W_M / 2.0, POPPING_CREASE_OFFSET_M + 1.22)
    if ret_near_r1 and ret_near_r2:
        cv2.line(vis_img, ret_near_r1, ret_near_r2, (200, 200, 200), 1, cv2.LINE_AA)

    # STEP 8: Overlay Detailed Geometric Legend / Telemetry HUD
    hud_lines = [
        "CRICKET PITCH GEOMETRIC CALIBRATION",
        f"Wickets Detected: 2 (Near: {P_near[1]:.0f}px, Far: {P_far[1]:.0f}px)",
        f"Pitch Center Line: {dist_px:.1f} px <-> 20.12 m (22 YDS)",
        f"Avg Longitudinal Scale: {dist_px/PITCH_LENGTH_M:.2f} px/m",
        f"Near Lateral Scale: {s_near_lateral:.1f} px/m (Box W={w_near_px:.0f}px)",
        f"Far Lateral Scale:  {s_far_lateral:.1f} px/m (Box W={w_far_px:.0f}px)",
        f"Homography: 4 Ground Ref Points (Wicket Bases)",
        "Crease Geometry: Bowling (2.64m) | Popping (+1.22m)",
        "STATUS: Perspective Pitch Guide Active"
    ]
    draw_hud_box(vis_img, hud_lines, origin=(25, 25))

    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        cv2.imwrite(output_path, vis_img)
        print(f"[Output] Calibration visual debug output saved to: {output_path}")

    return {
        'num_wickets': len(wicket_detections),
        'P_near': P_near,
        'P_far': P_far,
        'dist_px': dist_px,
        'homography': H,
        'w_near_px': w_near_px,
        'w_far_px': w_far_px,
        'scale_near': s_near_lateral,
        'scale_far': s_far_lateral
    }

def main():
    model_path = "/Users/thaladasrinivas/Downloads/stumps/weights/best.pt"
    model = YOLO(model_path)

    # Test on key two-wicket frames
    test_frames = [
        ("dataset/images/test/test_010_Screenshot_2026-09-24_at_3.46.25_PM.png",
         "output/pitch_calibration_test_010.jpg"),
        ("stumps/Screenshot 2026-09-24 at 3.41.55 PM.png",
         "output/pitch_calibration_grass_creases.jpg"),
        ("dataset/images/test/test_004_Screenshot_2026-09-24_at_3.47.14_PM.png",
         "output/pitch_calibration_test_004.jpg")
    ]

    for src, dst in test_frames:
        if os.path.exists(src):
            analyze_and_calibrate_pitch(src, model, dst)

if __name__ == '__main__':
    main()
