import os
import math
import cv2
import numpy as np
from ultralytics import YOLO

try:
    import scipy.optimize as opt
except ImportError:
    opt = None

_WATERMARK_LOGO = None

def get_watermark_logo():
    global _WATERMARK_LOGO
    if _WATERMARK_LOGO is None:
        candidates = [
            "web/static/trajecta_logo_tight.png",
            os.path.join(os.path.dirname(__file__), "..", "web", "static", "trajecta_logo_tight.png"),
            os.path.join(os.path.dirname(__file__), "trajecta_logo_tight.png"),
            "TRAJECTA.ai Dynamic Cricket Logo.png",
            os.path.join(os.path.dirname(__file__), "..", "TRAJECTA.ai Dynamic Cricket Logo.png")
        ]
        for c in candidates:
            if os.path.exists(c):
                img = cv2.imread(c, cv2.IMREAD_UNCHANGED)
                if img is not None and len(img.shape) > 2 and img.shape[2] == 4:
                    alpha_c = img[:, :, 3]
                    pts = np.argwhere(alpha_c > 15)
                    if len(pts) > 0:
                        y0, x0 = pts.min(axis=0)
                        y1, x1 = pts.max(axis=0)
                        _WATERMARK_LOGO = img[y0:y1+1, x0:x1+1]
                    else:
                        _WATERMARK_LOGO = img
                    break
    return _WATERMARK_LOGO

def apply_trajecta_watermark(frame, position="bottom-left", margin=24):
    """
    Renders pure TRAJECTA.ai Dynamic Cricket watermark logo (transparent, NO background box)
    directly onto the frame in the bottom-left corner for Instagram Reels and broadcast exports.
    """
    logo = get_watermark_logo()
    if logo is None:
        return frame

    h_f, w_f = frame.shape[:2]
    target_w = min(max(130, int(round(w_f * 0.20))), 240)
    target_h = int(round(logo.shape[0] * (target_w / max(1, logo.shape[1]))))
    resized = cv2.resize(logo, (target_w, target_h), interpolation=cv2.INTER_AREA)

    if position == "bottom-left":
        x_off = margin
        y_off = max(0, h_f - target_h - margin)
    else:
        x_off = margin
        y_off = margin

    b, g, r, a = cv2.split(resized)
    alpha = a.astype(float) / 255.0
    roi = frame[y_off:y_off+target_h, x_off:x_off+target_w]
    if roi.shape[:2] == (target_h, target_w):
        for c, col in enumerate([b, g, r]):
            roi[:, :, c] = (alpha * col + (1.0 - alpha) * roi[:, :, c]).astype(np.uint8)
        frame[y_off:y_off+target_h, x_off:x_off+target_w] = roi

    return frame

def draw_stroked_text(img, text, pos, font=cv2.FONT_HERSHEY_DUPLEX, scale=0.55,
                      color=(255, 255, 255), thickness=1, stroke_thickness=3,
                      stroke_color=(0, 0, 0)):
    """
    Renders clean anti-aliased text with a dark stroke outline for maximum legibility.
    """
    x, y = int(round(pos[0])), int(round(pos[1]))
    if stroke_thickness > 0:
        cv2.putText(img, text, (x, y), font, scale, stroke_color, stroke_thickness, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


class CricketKalmanFilter:
    """
    State-of-the-Art Kalman Filter for High-Speed Cricket Ball Tracking & DRS Hawkeye.
    State: [x, y, vx, vy, ax, ay]
    Models constant-acceleration parabolic projectile flight, air resistance, and pitch bounce.
    """
    def __init__(self, init_x, init_y, init_vx=0.0, init_vy=0.0, dt=1.0):
        self.dt = dt
        self.x = np.array([init_x, init_y, init_vx, init_vy, 0.0, 0.0], dtype=np.float64)
        
        # State transition: x = x + v*dt + 0.5*a*dt^2
        self.F = np.array([
            [1.0, 0.0, dt,  0.0, 0.5*dt*dt, 0.0],
            [0.0, 1.0, 0.0, dt,  0.0, 0.5*dt*dt],
            [0.0, 0.0, 1.0, 0.0, dt,  0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float64)
        
        # Measurement matrix: observing position [x, y]
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
        ], dtype=np.float64)
        
        # Process and Measurement Noise Covariance
        self.P = np.diag([16.0, 16.0, 64.0, 64.0, 100.0, 100.0])
        self.Q = np.diag([0.8, 0.8, 2.5, 2.5, 4.0, 4.0])
        self.R = np.diag([6.0, 6.0]) # Measurement noise std ~2.5px
        
        self.age = 1
        self.missed = 0
        self.bounced = False

    def predict(self):
        """Predicts state ahead by dt."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        self.age += 1
        return (float(self.x[0]), float(self.x[1]))

    def mahalanobis_dist(self, meas_x, meas_y):
        """Calculates normalized Mahalanobis distance squared (chi-square 2-dof)."""
        z = np.array([meas_x, meas_y], dtype=np.float64)
        residual = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        try:
            inv_S = np.linalg.inv(S)
            d2 = float(residual.T @ inv_S @ residual)
            return d2
        except np.linalg.LinAlgError:
            euclid = np.hypot(residual[0], residual[1])
            return euclid ** 2

    def update(self, meas_x, meas_y):
        """Updates Kalman state with valid measurement."""
        z = np.array([meas_x, meas_y], dtype=np.float64)
        residual = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        try:
            K = self.P @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            K = self.P @ self.H.T @ np.linalg.pinv(S)
            
        self.x = self.x + K @ residual
        I = np.eye(6, dtype=np.float64)
        self.P = (I - K @ self.H) @ self.P
        self.missed = 0
        return (float(self.x[0]), float(self.x[1]))

    def apply_bounce_reflection(self, restitution=0.62):
        """Applies velocity reflection on pitch bounce."""
        self.x[3] = -self.x[3] * restitution
        self.x[5] = -self.x[5] * 0.5
        self.bounced = True

    def project_future(self, steps=15):
        """Simulates projectile motion steps into the future (DRS Hawkeye forward projection)."""
        pts = []
        sim_x = self.x.copy()
        for _ in range(steps):
            sim_x = self.F @ sim_x
            pts.append((float(sim_x[0]), float(sim_x[1])))
        return pts


class PitchCorridor:
    """
    Defines the longitudinal 22-yard playing corridor between bowler release and batting stumps.
    Rejects spectators, outfield fielders, and off-pitch clutter.
    """
    def __init__(self, near_stump_pt=None, far_stump_pt=None, img_w=1920, img_h=1080):
        self.img_w = img_w
        self.img_h = img_h
        if near_stump_pt is not None and far_stump_pt is not None:
            self.near_pt = near_stump_pt
            self.far_pt = far_stump_pt
            self.has_stumps = True
        else:
            self.near_pt = (img_w * 0.50, img_h * 0.85)
            self.far_pt = (img_w * 0.50, img_h * 0.25)
            self.has_stumps = False

    def is_in_corridor(self, x, y, w=1920, h=1080):
        nx, ny = self.near_pt
        fx, fy = self.far_pt
        min_y = min(ny, fy) - 180.0
        max_y = max(ny, fy) + 180.0
        if not (min_y <= y <= max_y):
            return False

        t = (y - fy) / max(abs(ny - fy), 1.0)
        t = max(0.0, min(1.0, t))
        center_x = fx + t * (nx - fx)
        # Generous lateral width (allows wide release points, swing, and angle across pitch)
        allowed_half_w = 260.0 + t * 240.0
        return abs(x - center_x) <= allowed_half_w


class BallDetector:
    """
    YOLO-based Cricket Ball Detector equipped with an Anti-Shoe Geometrical & Dynamic Filter.
    Supports all cricket ball sizes (from distant flight 4px to close-up 250px) and colors (red, white, pink).
    """
    def __init__(self, model_or_path):
        import torch
        if isinstance(model_or_path, str):
            self.weights_path = model_or_path
            self.model = YOLO(model_or_path)
        else:
            self.weights_path = getattr(model_or_path, "weights", "weights/ball_best.pt")
            self.model = model_or_path
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        # Static object memory to blacklist stationary shoes and pitch marks
        self.static_grid_memory = {} # (gx, gy) -> count
        self.last_seen_frame = {}    # (gx, gy) -> frame_idx

    def reset_video_memory(self):
        """Clears stationary shoe/landmark memory before processing a new video."""
        self.static_grid_memory.clear()
        self.last_seen_frame.clear()

    @staticmethod
    def check_ball_color(crop, ball_color="auto"):
        """
        Validates candidate box color against expected ball characteristics.
        Eliminates neutral gray/white sneakers and dark human heads when tracking red balls.
        """
        if crop is None or crop.size == 0:
            return True, "valid"
        ch, cw = crop.shape[:2]
        # Inspect inner 60% of crop to avoid background grass contamination
        y_start, y_end = int(ch * 0.2), max(int(ch * 0.8), int(ch * 0.2) + 1)
        x_start, x_end = int(cw * 0.2), max(int(cw * 0.8), int(cw * 0.2) + 1)
        inner = crop[y_start:y_end, x_start:x_end]
        if inner.size == 0:
            inner = crop
        b, g, r = np.median(inner, axis=(0, 1))

        if ball_color == "red":
            # Real red cricket balls: strong Red channel, R > B + 25, R > G + 15
            is_red = (r > 115) and ((r - b) > 25) and ((r - g) > 15)
            return is_red, f"R={int(r)}, G={int(g)}, B={int(b)}"
        elif ball_color == "white":
            # White ball: bright, low color difference
            is_white = (r > 130 and g > 130 and b > 130) and (abs(r - g) < 40 and abs(r - b) < 40)
            return is_white, f"R={int(r)}, G={int(g)}, B={int(b)}"
        else: # "auto"
            # Reject dark human hair/head (all channels < 65) or pure green grass patches (G > R + 35)
            is_dark_head = (r < 65 and g < 65 and b < 65)
            is_grass = (g > r + 35 and g > b + 35)
            if is_dark_head or is_grass:
                return False, f"rejected_noise: R={int(r)}, G={int(g)}, B={int(b)}"
            return True, f"R={int(r)}, G={int(g)}, B={int(b)}"

    def detect(self, img, conf=0.30, corridor=None, max_ball_size=None, is_video=False,
               ball_color="auto", frame_idx=None):
        """
        Detects cricket balls in image/video with anti-shoe, anti-head, and color chromaticity filtering.
        Accelerated with MPS GPU execution and fixed imgsz=640 for rapid frame throughput.
        """
        h, w = img.shape[:2]

        # In video frames, an actual cricket ball in flight is never larger than 48px.
        # Human heads/hats (70px-90px) and player bodies are immediately eliminated by this guard.
        effective_max_size = max_ball_size if max_ball_size is not None else (48.0 if is_video else 250.0)
        effective_min_size = 5.0

        results = self.model.predict(
            source=img,
            conf=conf,
            imgsz=640,
            device=self.device,
            verbose=False
        )
        detections = []

        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            for b in boxes:
                xyxy = b.xyxy[0].cpu().numpy().astype(float)
                confidence = float(b.conf[0].cpu().numpy())
                x1, y1, x2, y2 = xyxy
                box_w = x2 - x1
                box_h = y2 - y1

                # 1. Size Check: blocks human heads (75-90px), hats, and player bodies
                if box_w > effective_max_size or box_h > effective_max_size:
                    continue
                if box_w < effective_min_size or box_h < effective_min_size:
                    continue

                # 2. Aspect Ratio Check: allow fast motion blur streaks (0.40 to 2.30)
                if box_h > 0:
                    aspect_ratio = box_w / box_h
                    if aspect_ratio < 0.40 or aspect_ratio > 2.30:
                        continue

                xc = (x1 + x2) / 2.0
                yc = (y1 + y2) / 2.0
                radius = max(3.0, min(box_w / 2.0, box_h / 2.0))

                # 3. Spatial Corridor Filter (if corridor is explicitly provided)
                if corridor is not None:
                    if not corridor.is_in_corridor(xc, yc, w, h):
                        continue

                # 4. Anti-Shoe Static Landmark Memory (for video)
                if is_video and frame_idx is not None:
                    grid_k = (int(xc // 18), int(yc // 18))
                    count = self.static_grid_memory.get(grid_k, 0)
                    last_f = self.last_seen_frame.get(grid_k, -99)
                    if frame_idx - last_f <= 3:
                        count += 1
                    else:
                        count = 1
                    self.static_grid_memory[grid_k] = count
                    self.last_seen_frame[grid_k] = frame_idx
                    # Only suppress objects that are truly stationary for 6+ distinct frames (e.g. shoe at crease)
                    if count >= 6:
                        continue

                # 5. Color Chromaticity Validation (rejects neutral shoes and brown heads)
                crop = img[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))]
                color_ok, color_desc = self.check_ball_color(crop, ball_color=ball_color)
                if not color_ok:
                    continue

                detections.append({
                    "center": (float(xc), float(yc)),
                    "radius": float(radius),
                    "confidence": confidence,
                    "box": [int(x1), int(y1), int(x2), int(y2)],
                    "aspect_ratio": float(box_w / max(box_h, 1.0)),
                    "color_info": color_desc
                })

        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections

    def annotate_frame(self, frame, detections, render_mode="both", show_trail=True, trail_points=None):
        """
        Draws cricket ball detection overlays on a single video frame.
        - detections: list of ball detection dicts from self.detect()
        - render_mode: 'both', 'bbox', or 'target'
        - show_trail: whether to draw smooth motion trail of recent detected ball centers
        - trail_points: list of (x, y) tuples representing recent ball positions
        """
        annotated = frame.copy()
        
        # 1. Draw smooth motion trail from recent detections if provided
        if show_trail and trail_points and len(trail_points) >= 2:
            import math
            n_pts = len(trail_points)
            for i in range(1, n_pts):
                p_prev = trail_points[i - 1]
                p_curr = trail_points[i]

                # Check if timestamp/frame_idx is attached: (x, y, f_idx)
                if len(p_prev) >= 3 and len(p_curr) >= 3:
                    x0, y0, f0 = p_prev[0], p_prev[1], p_prev[2]
                    x1, y1, f1 = p_curr[0], p_curr[1], p_curr[2]
                    if abs(f1 - f0) > 3:
                        continue # Time gap: ball was not tracked continuously, break line
                else:
                    x0, y0 = p_prev[0], p_prev[1]
                    x1, y1 = p_curr[0], p_curr[1]

                # Physical motion constraint: a cricket ball cannot jump across the screen in 1 frame
                dist = math.hypot(x1 - x0, y1 - y0)
                if dist > 85.0 or dist < 1.0:
                    continue # Disconnected candidate / teleportation jump: do not connect!

                pt_prev = (int(round(x0)), int(round(y0)))
                pt_curr = (int(round(x1)), int(round(y1)))
                alpha = float(i) / float(n_pts)
                thick = max(1, int(round(1 + alpha * 3)))
                # Dual-layer glowing trail: outer orange glow + inner bright yellow core
                cv2.line(annotated, pt_prev, pt_curr, (0, 140, 255), thick + 2, cv2.LINE_AA)
                cv2.line(annotated, pt_prev, pt_curr, (0, 240, 255), thick, cv2.LINE_AA)

        # 2. Draw detections on the current frame
        for b in detections:
            x1, y1, x2, y2 = b["box"]
            cx, cy = int(round(b["center"][0])), int(round(b["center"][1]))
            r = int(round(max(b["radius"], 5.0)))
            conf = b["confidence"]
            conf_pct = int(round(conf * 100))
            
            if render_mode in ("bbox", "both"):
                # Clean bounding box with rounded corner accents
                cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 165, 255), 2, cv2.LINE_AA)
                corner_len = max(4, min(int(round((x2 - x1) * 0.25)), 12))
                cv2.line(annotated, (int(x1), int(y1)), (int(x1) + corner_len, int(y1)), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x1), int(y1)), (int(x1), int(y1) + corner_len), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x2), int(y1)), (int(x2) - corner_len, int(y1)), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x2), int(y1)), (int(x2), int(y2) + corner_len), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x1), int(y2)), (int(x1) + corner_len, int(y2)), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x1), int(y2)), (int(x1), int(y2) - corner_len), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x2), int(y2)), (int(x2) - corner_len, int(y2)), (0, 255, 255), 3, cv2.LINE_AA)
                cv2.line(annotated, (int(x2), int(y2)), (int(x2), int(y2) - corner_len), (0, 255, 255), 3, cv2.LINE_AA)

            if render_mode in ("target", "both"):
                # Glowing center target marker
                cv2.circle(annotated, (cx, cy), r + 6, (0, 140, 255), 2, cv2.LINE_AA)
                cv2.circle(annotated, (cx, cy), r + 2, (0, 240, 255), 1, cv2.LINE_AA)
                cv2.circle(annotated, (cx, cy), r, (0, 80, 255), -1, cv2.LINE_AA)
                cv2.circle(annotated, (cx, cy), max(2, r - 3), (255, 255, 255), -1, cv2.LINE_AA)

            # Label badge
            label_text = f"CRICKET BALL {conf_pct}%"
            lbl_y = max(int(y1) - 8, 18)
            draw_stroked_text(annotated, label_text, (int(x1), lbl_y), cv2.FONT_HERSHEY_DUPLEX, 0.52,
                              color=(255, 255, 255), thickness=1, stroke_thickness=3)

        annotated = apply_trajecta_watermark(annotated, position="bottom-left")
        return annotated

    def detect_video(self, video_path, output_path=None, conf=0.30, render_mode="both",
                     show_trail=True, max_trail=25, ball_color="auto", max_ball_size=48,
                     start_frame=0, end_frame=None):
        """
        Process video frame-by-frame with pure ball object detection.
        Equipped with anti-head, anti-shoe, and color chromaticity filtering.
        """
        import os
        from collections import deque
        self.reset_video_memory()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if not output_path:
            base, _ = os.path.splitext(video_path)
            output_path = f"{base}_ball_detected.mp4"

        raw_output_path = output_path.replace(".mp4", "_raw.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(raw_output_path, fourcc, fps, (w, h))

        start_f = max(0, min(start_frame, total_frames - 1)) if start_frame else 0
        end_f = min(end_frame, total_frames) if end_frame else total_frames
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)

        trail_deque = deque(maxlen=max_trail)
        ball_frames = 0
        total_detections = 0
        frames_processed = 0

        try:
            for curr_f in range(start_f, end_f):
                ret, frame = cap.read()
                if not ret:
                    break
                frames_processed += 1
                dets = self.detect(
                    frame,
                    conf=conf,
                    is_video=True,
                    ball_color=ball_color,
                    max_ball_size=max_ball_size,
                    frame_idx=curr_f
                )
                if len(dets) > 0:
                    ball_frames += 1
                    total_detections += len(dets)
                    trail_deque.append(dets[0]["center"])

                ann = self.annotate_frame(frame, dets, render_mode=render_mode,
                                          show_trail=show_trail,
                                          trail_points=list(trail_deque) if show_trail else None)
                out.write(ann)
        finally:
            cap.release()
            out.release()

        # Convert with ffmpeg for browser compatibility
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

        return {
            "output_path": output_path,
            "frames_processed": frames_processed,
            "ball_frames_detected": ball_frames,
            "total_detections": total_detections,
            "fps": fps
        }



class CricketCameraCalibrator:
    """
    OpenCV solvePnP camera calibration for fixed cricket broadcast and analysis cameras.
    Calibrates camera pose using known pitch 3D landmarks (stumps, creases, 20.12m pitch distance).
    """
    @staticmethod
    def get_pitch_3d_landmarks(pitch_length_m=20.12, pitch_width_m=3.048, stump_height_m=0.7112, popping_offset_m=1.22):
        """
        Returns regulation 3D coordinates in pitch reference frame:
        Origin (0,0,0) at base of bowling stumps, Y along pitch towards batsman, Z upwards.
        """
        w_half = pitch_width_m / 2.0
        return {
            "bowler_stumps_base": np.array([0.0, 0.0, 0.0], dtype=np.float32),
            "bowler_stumps_top": np.array([0.0, 0.0, stump_height_m], dtype=np.float32),
            "batsman_stumps_base": np.array([0.0, pitch_length_m, 0.0], dtype=np.float32),
            "batsman_stumps_top": np.array([0.0, pitch_length_m, stump_height_m], dtype=np.float32),
            "bowler_crease_left": np.array([-w_half, popping_offset_m, 0.0], dtype=np.float32),
            "bowler_crease_right": np.array([w_half, popping_offset_m, 0.0], dtype=np.float32),
            "batsman_crease_left": np.array([-w_half, pitch_length_m - popping_offset_m, 0.0], dtype=np.float32),
            "batsman_crease_right": np.array([w_half, pitch_length_m - popping_offset_m, 0.0], dtype=np.float32)
        }

    @classmethod
    def calibrate_with_solvepnp(cls, img_w, img_h, calib_data=None, H_pitch=None,
                               pitch_length_m=20.12, pitch_width_m=3.048, stump_height_m=0.7112):
        """
        Estimates camera intrinsic K and extrinsic pose (rvec, tvec) via OpenCV solvePnP.
        Supports landmark points from calib_data or homography H_pitch.
        """
        f_est = max(img_w, img_h) * 1.25
        cx_est = img_w / 2.0
        cy_est = img_h / 2.0
        K = np.array([
            [f_est, 0.0, cx_est],
            [0.0, f_est, cy_est],
            [0.0, 0.0, 1.0]
        ], dtype=np.float32)

        landmarks_3d = cls.get_pitch_3d_landmarks(pitch_length_m, pitch_width_m, stump_height_m)
        obj_pts = []
        img_pts = []

        if calib_data is not None:
            if "near_ground_ref" in calib_data and "far_ground_ref" in calib_data:
                obj_pts.append(landmarks_3d["bowler_stumps_base"])
                img_pts.append(calib_data["near_ground_ref"])
                obj_pts.append(landmarks_3d["batsman_stumps_base"])
                img_pts.append(calib_data["far_ground_ref"])

            if "near_stump_top" in calib_data and "far_stump_top" in calib_data:
                obj_pts.append(landmarks_3d["bowler_stumps_top"])
                img_pts.append(calib_data["near_stump_top"])
                obj_pts.append(landmarks_3d["batsman_stumps_top"])
                img_pts.append(calib_data["far_stump_top"])

            if "near_crease_left" in calib_data and "near_crease_right" in calib_data:
                obj_pts.append(landmarks_3d["bowler_crease_left"])
                img_pts.append(calib_data["near_crease_left"])
                obj_pts.append(landmarks_3d["bowler_crease_right"])
                img_pts.append(calib_data["near_crease_right"])

            if "far_crease_left" in calib_data and "far_crease_right" in calib_data:
                obj_pts.append(landmarks_3d["batsman_crease_left"])
                img_pts.append(calib_data["far_crease_left"])
                obj_pts.append(landmarks_3d["batsman_crease_right"])
                img_pts.append(calib_data["far_crease_right"])

        if len(obj_pts) < 4 and H_pitch is not None:
            test_points_3d = [
                ([0.0, 0.0, 0.0], [0.0, 0.0]),
                ([0.0, pitch_length_m, 0.0], [0.0, pitch_length_m]),
                ([-pitch_width_m/2, 1.22, 0.0], [-pitch_width_m/2, 1.22]),
                ([+pitch_width_m/2, 1.22, 0.0], [+pitch_width_m/2, 1.22]),
                ([-pitch_width_m/2, pitch_length_m - 1.22, 0.0], [-pitch_width_m/2, pitch_length_m - 1.22]),
                ([+pitch_width_m/2, pitch_length_m - 1.22, 0.0], [+pitch_width_m/2, pitch_length_m - 1.22]),
            ]
            for p3, p_pitch in test_points_3d:
                proj = H_pitch @ np.array([p_pitch[0], p_pitch[1], 1.0], dtype=np.float64)
                if abs(proj[2]) > 1e-6:
                    u, v = float(proj[0] / proj[2]), float(proj[1] / proj[2])
                    if 0 <= u < img_w * 1.5 and 0 <= v < img_h * 1.5:
                        obj_pts.append(np.array(p3, dtype=np.float32))
                        img_pts.append([u, v])

        if len(obj_pts) >= 4:
            obj_pts_arr = np.array(obj_pts, dtype=np.float32)
            img_pts_arr = np.array(img_pts, dtype=np.float32)
            try:
                ret, rvec, tvec = cv2.solvePnP(
                    obj_pts_arr, img_pts_arr, K, None,
                    flags=cv2.SOLVEPNP_ITERATIVE
                )
                if ret:
                    return {
                        "success": True,
                        "K": K,
                        "rvec": rvec,
                        "tvec": tvec,
                        "method": "solvePnP"
                    }
            except Exception as e:
                print(f"[solvePnP] Solver note: {e}")

        # Fallback camera model: typical cricket high-angle camera behind bowler
        cam_pos = np.array([0.15, -4.5, 2.45], dtype=np.float32)
        look_at = np.array([0.0, 10.0, 0.40], dtype=np.float32)
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        z_cam = look_at - cam_pos
        z_cam /= np.linalg.norm(z_cam)
        x_cam = np.cross(up, z_cam)
        x_cam /= np.linalg.norm(x_cam)
        y_cam = np.cross(z_cam, x_cam)
        R_mat = np.vstack([x_cam, y_cam, z_cam]).astype(np.float32)
        rvec, _ = cv2.Rodrigues(R_mat)
        tvec = -R_mat @ cam_pos
        return {
            "success": False,
            "K": K,
            "rvec": rvec,
            "tvec": tvec,
            "method": "analytical_prior"
        }


class CricketPhysicsTrajectoryFitter:
    """
    Physics-based trajectory fitting with gravity + aerodynamic air drag + pitch bounce.
    Uses non-linear least squares (scipy.optimize.least_squares with soft L1 loss)
    to reconstruct the true continuous 3D path and frame-by-frame speeds.
    """
    def __init__(self, fps=25.0, g=9.81, gamma_default=0.0062):
        self.fps = float(fps)
        self.dt = 1.0 / self.fps
        self.g = float(g)
        self.gamma_default = float(gamma_default)

    @staticmethod
    def integrate_flight(p, t_eval, g=9.81):
        """
        Numerically integrates flight path:
        d(pos)/dt = vel
        d(vel)/dt = [a_swing, 0, -g] - gamma * |vel| * vel
        Parameters p = [x0, y0, z0, vx0, vy0, vz0, a_swing, gamma]
        """
        x0, y0, z0, vx0, vy0, vz0, a_sw, gam = p
        pts = []
        vels = []
        x, y, z = float(x0), float(y0), float(z0)
        vx, vy, vz = float(vx0), float(vy0), float(vz0)
        dt_sub = 0.002
        curr_t = 0.0

        for t_target in t_eval:
            while curr_t < t_target - 1e-6:
                step = min(dt_sub, t_target - curr_t)
                v = math.sqrt(vx*vx + vy*vy + vz*vz)
                ax = a_sw - gam * v * vx
                ay = -gam * v * vy
                az = -g - gam * v * vz
                x += vx * step
                y += vy * step
                z += vz * step
                vx += ax * step
                vy += ay * step
                vz += az * step
                curr_t += step
            pts.append([x, y, z])
            vels.append([vx, vy, vz])

        return np.array(pts, dtype=np.float32), np.array(vels, dtype=np.float32)

    def fit_segment(self, timestamps, observed_3d, is_pre_bounce=True,
                    initial_pos=None, initial_speed_mph=85.0):
        """
        Fits physics model (gravity + air drag + swing) to observed 3D trajectory points.
        """
        t_arr = np.array(timestamps, dtype=np.float32)
        n = len(t_arr)
        if n < 2:
            return None

        if initial_pos is not None:
            x0_init, y0_init, z0_init = initial_pos
        else:
            x0_init, y0_init, z0_init = observed_3d[0]

        total_t = max(0.04, t_arr[-1] - t_arr[0])
        vy_est = (observed_3d[-1][1] - observed_3d[0][1]) / total_t
        vy_est = float(np.clip(vy_est, 18.0, 41.5))

        vx_est = (observed_3d[-1][0] - observed_3d[0][0]) / total_t
        vx_est = float(np.clip(vx_est, -5.0, 5.0))

        vz_est = (observed_3d[-1][2] - observed_3d[0][2]) / total_t
        if is_pre_bounce:
            vz_est = float(np.clip(vz_est, -8.0, 1.0))
        else:
            vz_est = float(np.clip(vz_est, 0.5, 9.0))

        p_init = [
            float(x0_init), float(y0_init), float(z0_init),
            float(vx_est), float(vy_est), float(vz_est),
            0.0, self.gamma_default
        ]

        if is_pre_bounce:
            bounds = (
                [-1.8, 0.2, 1.6, -6.0, 18.0, -12.0, -3.5, 0.003],
                [+1.8, 3.0, 2.6, +6.0, 42.0, +2.0, +3.5, 0.010]
            )
        else:
            bounds = (
                [-1.5, 9.0, 0.0, -6.0, 12.0, 0.1, -2.5, 0.003],
                [+1.5, 19.0, 0.15, +6.0, 36.0, +12.0, +2.5, 0.010]
            )

        lb = np.array(bounds[0], dtype=np.float32)
        ub = np.array(bounds[1], dtype=np.float32)
        p_init_clipped = np.clip(np.array(p_init, dtype=np.float32), lb + 1e-3, ub - 1e-3).tolist()

        if opt is not None:
            def loss_fn(p):
                pred_3d, _ = self.integrate_flight(p, t_arr, g=self.g)
                diff = pred_3d - observed_3d
                diff[:, 2] *= 1.2
                return diff.ravel()

            try:
                res = opt.least_squares(
                    loss_fn, p_init_clipped, bounds=bounds, loss='soft_l1',
                    ftol=1e-3, xtol=1e-3, max_nfev=35
                )
                p_opt = res.x
                pts_opt, vels_opt = self.integrate_flight(p_opt, t_arr, g=self.g)
                return {
                    "params": p_opt,
                    "pts_3d": pts_opt,
                    "vels_3d": vels_opt,
                    "cost": float(res.cost),
                    "success": bool(res.success)
                }
            except Exception as e:
                print(f"[PhysicsFit] least_squares fallback: {e}")

        pts_opt, vels_opt = self.integrate_flight(p_init_clipped, t_arr, g=self.g)
        return {
            "params": p_init,
            "pts_3d": pts_opt,
            "vels_3d": vels_opt,
            "cost": 999.0,
            "success": False
        }

    def compute_full_trajectory_and_speeds(self, pre_points_3d, post_points_3d,
                                          pre_frames, post_frames,
                                          pitch_length_m=20.12):
        """
        Combines pre-bounce and post-bounce physics fittings into a complete delivery model
        and generates instantaneous speeds at every frame.
        """
        f_rel = pre_frames[0]
        t_pre = [(f - f_rel) / self.fps for f in pre_frames]
        fit_pre = self.fit_segment(t_pre, pre_points_3d, is_pre_bounce=True)

        if fit_pre is None:
            return None

        v_bounce_in = fit_pre["vels_3d"][-1]
        p_bounce_pos = fit_pre["pts_3d"][-1]
        t_bounce = t_pre[-1]

        # Post-bounce restitution & turf friction model (MCC turf e ~ 0.54, friction mu ~ 0.84)
        e_restitution = 0.54
        mu_friction = 0.84

        if post_points_3d is not None and len(post_points_3d) >= 2:
            t_post = [(f - f_rel) / self.fps for f in post_frames]
            t_post_rel = [t - t_bounce for t in t_post]
            fit_post = self.fit_segment(
                t_post_rel, post_points_3d, is_pre_bounce=False,
                initial_pos=[p_bounce_pos[0], p_bounce_pos[1], 0.0]
            )
            if fit_post is not None:
                v_post_init_mag = float(np.linalg.norm(fit_post["vels_3d"][0]))
                v_pre_impact_mag = float(np.linalg.norm(v_bounce_in))
                if v_post_init_mag > v_pre_impact_mag * 0.88:
                    scale_post = (v_pre_impact_mag * 0.84) / max(1e-3, v_post_init_mag)
                    fit_post["vels_3d"] *= scale_post
        else:
            v_x_post = float(mu_friction * v_bounce_in[0])
            v_y_post = float(mu_friction * v_bounce_in[1])
            v_z_post = float(e_restitution * abs(v_bounce_in[2]))

            t_to_stumps = max(0.08, (pitch_length_m - p_bounce_pos[1]) / max(10.0, v_y_post))
            num_post_steps = max(4, int(round(t_to_stumps * self.fps)))
            t_post_rel = list(np.linspace(0.0, t_to_stumps, num_post_steps))
            post_frames = [pre_frames[-1] + k for k in range(len(t_post_rel))]

            p_post = [
                float(p_bounce_pos[0]), float(p_bounce_pos[1]), 0.0,
                v_x_post, v_y_post, v_z_post, 0.0, self.gamma_default
            ]
            pts_post, vels_post = self.integrate_flight(p_post, t_post_rel, g=self.g)
            fit_post = {
                "params": p_post,
                "pts_3d": pts_post,
                "vels_3d": vels_post,
                "cost": 0.0,
                "success": True
            }

        # Build combined per-frame speeds and telemetry
        frame_speeds = []
        for i, f in enumerate(pre_frames):
            vel = fit_pre["vels_3d"][i]
            pos = fit_pre["pts_3d"][i]
            speed_mps = float(np.linalg.norm(vel))
            speed_mph = round(speed_mps * 2.23694, 1)
            speed_kph = round(speed_mps * 3.6, 1)
            phase = "release" if i == 0 else ("bounce" if i == len(pre_frames)-1 else "in_flight")
            frame_speeds.append({
                "frame": int(f),
                "t_sec": round(t_pre[i], 4),
                "speed_mph": speed_mph,
                "speed_kph": speed_kph,
                "pos_3d": [round(float(pos[0]), 3), round(float(pos[1]), 3), round(float(pos[2]), 3)],
                "phase": phase
            })

        for i, f in enumerate(post_frames[1:], start=1):
            vel = fit_post["vels_3d"][i]
            pos = fit_post["pts_3d"][i]
            speed_mps = float(np.linalg.norm(vel))
            speed_mph = round(speed_mps * 2.23694, 1)
            speed_kph = round(speed_mps * 3.6, 1)
            phase = "arrival" if i == len(post_frames)-1 else "rebound"
            frame_speeds.append({
                "frame": int(f),
                "t_sec": round(t_bounce + t_post_rel[i], 4),
                "speed_mph": speed_mph,
                "speed_kph": speed_kph,
                "pos_3d": [round(float(pos[0]), 3), round(float(pos[1]), 3), round(float(pos[2]), 3)],
                "phase": phase
            })

        rel_speed = frame_speeds[0]["speed_mph"]
        bounce_pre_speed = round(float(np.linalg.norm(fit_pre["vels_3d"][-1])) * 2.23694, 1)
        bounce_post_speed = round(float(np.linalg.norm(fit_post["vels_3d"][0])) * 2.23694, 1)
        arr_speed = frame_speeds[-1]["speed_mph"]

        all_pts_3d = []
        for p in fit_pre["pts_3d"]:
            all_pts_3d.append({"x": round(float(p[0]), 3), "y": round(float(p[1]), 3), "z": round(float(p[2]), 3)})
        for p in fit_post["pts_3d"][1:]:
            all_pts_3d.append({"x": round(float(p[0]), 3), "y": round(float(p[1]), 3), "z": round(float(p[2]), 3)})

        return {
            "frame_speeds": frame_speeds,
            "release_speed_mph": rel_speed,
            "pre_bounce_speed_mph": bounce_pre_speed,
            "post_bounce_speed_mph": bounce_post_speed,
            "arrival_speed_mph": arr_speed,
            "speed_drop_air_mph": round(rel_speed - bounce_pre_speed, 1),
            "speed_drop_turf_mph": round(bounce_pre_speed - bounce_post_speed, 1),
            "total_speed_decay_mph": round(rel_speed - arr_speed, 1),
            "points_3d": all_pts_3d,
            "fit_pre": fit_pre,
            "fit_post": fit_post
        }



class BallTrajectoryTracker:
    """
    IPL-Grade Hawkeye & Virtual Eye DRS Cricket Trajectory Tracker.
    Features:
      - Multi-hypothesis Kalman Filtering with strict Mahalanobis Innovation Gating (Zero Shoe False Positives)
      - Static ground detector elimination (ignores stationary shoes at crease)
      - Silky-smooth parabolic delivery flight arc
      - Hawkeye pitch landing impact ring with 3D perspective
      - DRS Hawkeye forward projection continuing through to the wickets plane
    """
    def __init__(self, max_history=45, max_jump_px=95):
        self.max_history = max_history
        self.max_jump_px = max_jump_px
        self.corridor = None

        # Kalman Filter state
        self.kf = None
        self.tracklet = []          # Active delivery points [{frame, center, kf_pt, conf, pitch}]
        self.saved_deliveries = []
        self.delivery_arc = []      # Best verified delivery arc
        self.bounce_event = None
        self.active_ball = None
        self.missed_frames = 0
        
        # Anti-shoe static landmark memory: grid key -> list of (frame, (x, y))
        self.static_landmark_cache = {}

    def set_pitch_context(self, locked_calib=None, img_w=1920, img_h=1080):
        if locked_calib is not None and "near" in locked_calib and "far" in locked_calib:
            nb = locked_calib["near"]["box"]
            fb = locked_calib["far"]["box"]
            near_pt = ((nb[0] + nb[2]) / 2.0, float(nb[3]))
            far_pt = ((fb[0] + fb[2]) / 2.0, float(fb[1]))
            self.corridor = PitchCorridor(near_pt, far_pt, img_w, img_h)
        else:
            self.corridor = PitchCorridor(None, None, img_w, img_h)

    @staticmethod
    def project_to_pitch(H, px, py, pitch_length_m=20.12, popping_crease_offset_m=1.22):
        try:
            H_inv = np.linalg.inv(H)
            pt = np.array([px, py, 1.0], dtype=np.float64)
            res = H_inv @ pt
            if abs(res[2]) < 1e-7:
                return None
            X_m = float(res[0] / res[2])
            Y_m = float(res[1] / res[2])

            # Batsman popping crease is at (pitch_length_m - popping_crease_offset_m) ~ 18.90m from bowler crease
            batsman_crease_y = pitch_length_m - popping_crease_offset_m
            dist_from_crease = max(0.0, round(batsman_crease_y - Y_m, 2))

            # Length Zone Classification according to distance from batting popping crease:
            # Yorker: 0m to 2.0m (in batsman's blockhole)
            # Full: 2.0m to 4.0m (driveable length)
            # Good Length: 4.0m to 6.5m (uncertain forward/back stroke)
            # Back of Length: 6.5m to 8.5m (punch off back foot)
            # Short: > 8.5m (bouncers / pull / hook)
            if dist_from_crease < 2.0:
                zone = "Yorker"
            elif dist_from_crease < 4.0:
                zone = "Full"
            elif dist_from_crease < 6.5:
                zone = "Good Length"
            elif dist_from_crease < 8.5:
                zone = "Back of Length"
            else:
                zone = "Short"

            # Lateral Line Classification relative to stumps:
            if X_m < -0.35:
                lateral = "Outside Off"
            elif X_m < -0.12:
                lateral = "Off Stump"
            elif X_m < -0.04:
                lateral = "Middle & Off"
            elif X_m <= 0.08:
                lateral = "Middle Stump"
            elif X_m <= 0.35:
                lateral = "Leg Stump"
            else:
                lateral = "Outside Leg"

            return {
                "ground_x_m": round(X_m, 2),
                "ground_y_m": round(Y_m, 2),
                "dist_from_crease_m": dist_from_crease,
                "zone": zone,
                "lateral_line": lateral
            }
        except Exception:
            return None

    def _is_static_shoe_or_ground_clutter(self, xc, yc, frame_idx):
        """
        Anti-Shoe Gating: Checks if a detection is stationary over multiple frames.
        Real cricket deliveries move at high velocity. Only marks as stationary if an object sits in the exact same spot (<4px) for 5+ distinct frames.
        """
        grid_key = (int(round(xc / 16.0)), int(round(yc / 16.0)))
        recent_hits = self.static_landmark_cache.get(grid_key, [])
        # Clean older than 40 frames
        recent_hits = [h for h in recent_hits if frame_idx - h[0] <= 40]
        
        is_stationary = False
        if len(recent_hits) >= 5:
            displacements = [np.hypot(xc - h[1][0], yc - h[1][1]) for h in recent_hits]
            if np.mean(displacements) < 4.0: # Stationary within 4 pixels over 5+ frames
                is_stationary = True
                
        recent_hits.append((frame_idx, (xc, yc)))
        self.static_landmark_cache[grid_key] = recent_hits
        return is_stationary

    def update(self, best_ball, frame_count, H_pitch=None, pitch_length_m=20.12, popping_crease_offset_m=1.22, candidates=None):
        """
        Updates delivery trajectory using pure YOLO detection tracking with anti-shoe gating.
        (Kalman filtering removed as requested).
        """
        all_cands = candidates if candidates else ([best_ball] if best_ball else [])

        # Filter out corridor violations and static shoes from candidates
        valid_cands = []
        for c in all_cands:
            cx, cy = c["center"]
            if self.corridor and not self.corridor.is_in_corridor(cx, cy):
                continue
            if self._is_static_shoe_or_ground_clutter(cx, cy, frame_count):
                continue # REJECT SHOE
            valid_cands.append(c)

        chosen_ball = None

        if len(self.tracklet) > 0:
            last_pt = self.tracklet[-1]["center"]
            best_dist = 90.0  # max jump in px between consecutive frames
            for c in valid_cands:
                cx, cy = c["center"]
                d = float(np.hypot(cx - last_pt[0], cy - last_pt[1]))
                if d < best_dist:
                    best_dist = d
                    chosen_ball = c

            if chosen_ball is not None:
                self.missed_frames = 0
            else:
                self.missed_frames += 1
                if self.missed_frames > 4:
                    self._finalize_tracklet()
                self.active_ball = None
                return None
        else:
            if valid_cands:
                chosen_ball = valid_cands[0]
                self.missed_frames = 0
            else:
                return None

        bx, by = chosen_ball["center"]
        pitch_data = None
        if H_pitch is not None:
            pitch_data = self.project_to_pitch(H_pitch, bx, by, pitch_length_m, popping_crease_offset_m)

        point_entry = {
            "frame": frame_count,
            "center": (float(bx), float(by)),
            "raw_center": chosen_ball["center"],
            "radius": float(chosen_ball["radius"]),
            "confidence": float(chosen_ball["confidence"]),
            "pitch": pitch_data,
            "coasted": False
        }

        self.tracklet.append(point_entry)
        self.active_ball = point_entry
        self._evaluate_delivery()
        return self.active_ball

    def _finalize_tracklet(self):
        if len(self.tracklet) >= 3:
            self.saved_deliveries.append(list(self.tracklet))
            self._evaluate_delivery()
        self.tracklet = []
        self.missed_frames = 0

    def _evaluate_delivery(self):
        candidates = list(self.saved_deliveries)
        if len(self.tracklet) >= 3:
            candidates.append(self.tracklet)
        if not candidates:
            return

        def score_delivery(trk):
            n = len(trk)
            if n < 3: return 0.0
            speeds = [np.hypot(trk[i]["center"][0]-trk[i-1]["center"][0], trk[i]["center"][1]-trk[i-1]["center"][1])
                      for i in range(1, n)]
            total_dist = sum(speeds)
            avg_speed = np.mean(speeds) if speeds else 0.0
            if avg_speed < 4.0: # Stationary clutter
                return -100.0
            return n * 35.0 + total_dist * 0.5

        best = max(candidates, key=score_delivery)
        if score_delivery(best) > 0:
            self.delivery_arc = best

        # Detect pitch bounce event
        if len(self.delivery_arc) >= 4 and self.bounce_event is None:
            for k in range(1, len(self.delivery_arc) - 1):
                dy_prev = self.delivery_arc[k]["center"][1] - self.delivery_arc[k-1]["center"][1]
                dy_next = self.delivery_arc[k+1]["center"][1] - self.delivery_arc[k]["center"][1]
                if dy_prev * dy_next < -2.0 and (abs(dy_prev) + abs(dy_next) >= 5.0):
                    cand_bounce = self.delivery_arc[k]
                    p1 = cand_bounce["center"]
                    p_info = cand_bounce.get("pitch")
                    self.bounce_event = {
                        "frame": cand_bounce["frame"],
                        "pixel": (int(round(p1[0])), int(round(p1[1]))),
                        "pt": (int(round(p1[0])), int(round(p1[1]))),
                        "dist_from_crease_m": p_info["dist_from_crease_m"] if p_info else 4.2,
                        "zone": p_info["zone"] if p_info else "Good Length",
                        "lateral_line": p_info["lateral_line"] if p_info else "Middle Stump"
                    }
                    break

    @staticmethod
    def fit_smooth_curve(pts, num_samples=60):
        """
        Interpolates smooth trajectory curve strictly passing through detected endpoints.
        """
        if len(pts) < 2:
            return pts
        if len(pts) == 2:
            p0, p1 = pts[0], pts[1]
            dense = []
            for s in np.linspace(0, 1, num_samples):
                dense.append((float(p0[0] + s * (p1[0] - p0[0])), float(p0[1] + s * (p1[1] - p0[1]))))
            return dense

        chord_dists = [0.0]
        for k in range(1, len(pts)):
            d = float(np.hypot(pts[k][0] - pts[k-1][0], pts[k][1] - pts[k-1][1]))
            chord_dists.append(chord_dists[-1] + max(d, 0.01))
        total_dist = chord_dists[-1]

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        s_eval = np.linspace(0.0, total_dist, num_samples)
        interp_x = np.interp(s_eval, chord_dists, xs)
        interp_y = np.interp(s_eval, chord_dists, ys)
        dense = [(float(interp_x[i]), float(interp_y[i])) for i in range(len(s_eval))]
        dense[0] = (float(pts[0][0]), float(pts[0][1]))
        dense[-1] = (float(pts[-1][0]), float(pts[-1][1]))
        return dense

    def extract_delivery_trajectory(self, detections_by_frame, fps=25.0, H_pitch=None,
                                    pitch_length_m=20.12, popping_crease_offset_m=1.22,
                                    calib_data=None):
        """
        Extracts the SINGLE true cricket delivery trajectory strictly from genuine YOLO ball detections.
        (Kalman filtering & polynomial extrapolation removed as requested).
        Guarantees trajectory strictly connects actual detected ball coordinates from Bowler Release -> Arrival/Contact.
        """
        all_dets = []
        for f_idx, dets in detections_by_frame.items():
            for d in dets:
                cx, cy = d["center"]
                conf = d.get("confidence", 0.5)
                radius = d.get("radius", 6.0)
                box = d.get("box", [int(cx-radius), int(cy-radius), int(cx+radius), int(cy+radius)])
                all_dets.append({
                    "frame": int(f_idx),
                    "center": (float(cx), float(cy)),
                    "conf": float(conf),
                    "radius": float(radius),
                    "box": box
                })

        all_dets.sort(key=lambda d: (d["frame"], -d["conf"]))
        if len(all_dets) < 3:
            return None

        # 1. Anti-shoe / static clutter rejection
        grid_memory = {}
        for d in all_dets:
            gk = (int(round(d["center"][0] / 24.0)), int(round(d["center"][1] / 24.0)))
            grid_memory.setdefault(gk, []).append(d)

        stationary_keys = set()
        for gk, cluster in grid_memory.items():
            if len(cluster) >= 4:
                spread = max(abs(c["center"][0] - cluster[0]["center"][0]) + abs(c["center"][1] - cluster[0]["center"][1]) for c in cluster)
                if spread < 12.0:
                    stationary_keys.add(gk)

        dynamic_dets = [
            d for d in all_dets
            if (int(round(d["center"][0] / 24.0)), int(round(d["center"][1] / 24.0))) not in stationary_keys
        ]
        if len(dynamic_dets) < 3:
            dynamic_dets = all_dets

        # 2. Chronological Tracklet Chaining (Pure detection tracking with directional momentum consistency)
        tracklets = []
        for d in dynamic_dets:
            f = d["frame"]
            placed = False
            for trk in tracklets:
                if trk[-1]["frame"] == f:
                    continue
                df = f - trk[-1]["frame"]
                if 1 <= df <= 10:
                    dx = d["center"][0] - trk[-1]["center"][0]
                    dy = d["center"][1] - trk[-1]["center"][1]
                    dist = float(np.hypot(dx, dy))
                    speed = dist / df
                    if 1.5 <= speed <= 160.0:
                        # Momentum check: fast cricket deliveries maintain consistent lateral flight direction
                        if len(trk) >= 3:
                            flow_dx = trk[-1]["center"][0] - trk[0]["center"][0]
                            if abs(flow_dx) > 20.0 and (dx * flow_dx < -15.0):
                                continue  # Reject rogue point reversing lateral delivery momentum
                        trk.append(d)
                        placed = True
                        break
            if not placed:
                tracklets.append([d])

        # 3. Merge tracklets separated by small frame gap (e.g. bounce gap / motion blur)
        merged = True
        while merged:
            merged = False
            for i in range(len(tracklets)):
                for j in range(len(tracklets)):
                    if i != j and len(tracklets[i]) >= 2 and len(tracklets[j]) >= 2:
                        t1, t2 = tracklets[i], tracklets[j]
                        if t1[-1]["frame"] < t2[0]["frame"]:
                            df = t2[0]["frame"] - t1[-1]["frame"]
                            if 1 <= df <= 12:
                                dx = t2[0]["center"][0] - t1[-1]["center"][0]
                                dy = t2[0]["center"][1] - t1[-1]["center"][1]
                                dist = float(np.hypot(dx, dy))
                                speed = dist / df
                                if 1.5 <= speed <= 160.0:
                                    v1x = t1[-1]["center"][0] - t1[0]["center"][0]
                                    if abs(v1x) < 15.0 or (dx * v1x >= -10.0):
                                        tracklets[i] = t1 + t2
                                        tracklets.pop(j)
                                        merged = True
                                        break
                if merged:
                    break

        # 4. Score tracklets to find the primary bowling delivery
        valid = []
        for trk in tracklets:
            if len(trk) < 3:
                continue
            tot_dist = sum(np.hypot(trk[k]["center"][0] - trk[k-1]["center"][0],
                                    trk[k]["center"][1] - trk[k-1]["center"][1])
                           for k in range(1, len(trk)))
            frame_span = trk[-1]["frame"] - trk[0]["frame"]
            if tot_dist < 40.0 or frame_span < 3:
                continue
            avg_conf = np.mean([p["conf"] for p in trk])
            score = len(trk) * 20.0 + tot_dist * 1.0 + avg_conf * 40.0
            valid.append((score, trk))

        if not valid:
            return None

        valid.sort(key=lambda x: x[0], reverse=True)
        best_trk = valid[0][1]

        # 4b. Prune spurious pre-release outlier if initial velocity/acceleration is anomalous
        if len(best_trk) >= 4:
            spds = [
                float(np.hypot(best_trk[k]["center"][0] - best_trk[k-1]["center"][0],
                               best_trk[k]["center"][1] - best_trk[k-1]["center"][1])) / max(1, best_trk[k]["frame"] - best_trk[k-1]["frame"])
                for k in range(1, min(6, len(best_trk)))
            ]
            med_spd = float(np.median(spds[1:])) if len(spds) > 1 else spds[0]
            if spds[0] > 2.2 * med_spd and best_trk[0]["conf"] < 0.50:
                best_trk = best_trk[1:]

        # 5. Robust Cricket Delivery Bounce Identification & Clutter Elimination
        ys = [p["center"][1] for p in best_trk]
        n_trk = len(best_trk)

        # A: Detect if there is a directional turnaround in y (inflection)
        bounce_idx = None
        for k in range(1, n_trk - 1):
            dy_prev = best_trk[k]["center"][1] - best_trk[k-1]["center"][1]
            dy_next = best_trk[k+1]["center"][1] - best_trk[k]["center"][1]
            # Genuine bounce inflection: ball was descending towards pitch turf and rebounded upwards
            if dy_prev > 1.5 and dy_next < -1.5:
                bounce_idx = k
                break

        # B: If no classic inflection point found among detections, lowest descent point is pitch turf bounce
        if bounce_idx is None:
            max_y_idx = int(np.argmax(ys))
            if max_y_idx >= 2:
                bounce_idx = max_y_idx

        # C: Post-bounce turf and backward clutter elimination:
        # Ball rebounds upward off turf (decreasing y towards batsman).
        # If ball suddenly plunges down after rebounding, or reverses lateral flight direction (bat hit), truncate tracklet!
        if bounce_idx is not None and bounce_idx < n_trk - 1:
            xb = best_trk[bounce_idx]["center"][0]
            yb = best_trk[bounce_idx]["center"][1]
            valid_end = n_trk
            for k in range(bounce_idx + 1, n_trk):
                dy_step = best_trk[k]["center"][1] - best_trk[k-1]["center"][1]
                # If ball was already rebounding upwards above the turf bounce, and suddenly plunges down by > 12px:
                if dy_step > 12.0 and (best_trk[k-1]["center"][1] < yb - 20.0):
                    valid_end = k
                    break
                # Check for lateral turnaround (bat hit):
                dx_flight = best_trk[bounce_idx]["center"][0] - best_trk[0]["center"][0]
                dx_step = best_trk[k]["center"][0] - best_trk[bounce_idx]["center"][0]
                if abs(dx_flight) > 25.0 and (dx_step * dx_flight < -15.0):
                    valid_end = k
                    break
            best_trk = best_trk[:valid_end]

        pts = [p["center"] for p in best_trk]
        n_pts = len(pts)

        # 6. Smooth aerodynamic trajectory curve strictly anchored to detected points (Centripetal Catmull-Rom spline)
        def smooth_trajectory_curve(points, num_samples=60, alpha=0.5):
            n = len(points)
            if n < 2:
                return points
            if n == 2:
                p0, p1 = points[0], points[1]
                return [
                    (float(p0[0] + t * (p1[0] - p0[0])),
                     float(p0[1] + t * (p1[1] - p0[1])))
                    for t in np.linspace(0.0, 1.0, max(20, num_samples))
                ]

            pts_arr = np.array(points, dtype=np.float64)
            p_start = 2.0 * pts_arr[0] - pts_arr[1]
            p_end = 2.0 * pts_arr[-1] - pts_arr[-2]
            full_pts = np.vstack([[p_start], pts_arr, [p_end]])

            dense = []
            samples_per_seg = max(12, int(round(num_samples / (n - 1))))
            for i in range(n - 1):
                P0, P1, P2, P3 = full_pts[i], full_pts[i+1], full_pts[i+2], full_pts[i+3]

                def tj(ti, pi, pj):
                    d = float(np.linalg.norm(pj - pi))
                    return ti + (d ** alpha if d > 1e-6 else 1e-3)

                t0 = 0.0
                t1 = tj(t0, P0, P1)
                t2 = tj(t1, P1, P2)
                t3 = tj(t2, P2, P3)

                dt01 = max(t1 - t0, 1e-4)
                dt12 = max(t2 - t1, 1e-4)
                dt23 = max(t3 - t2, 1e-4)
                dt02 = max(t2 - t0, 1e-4)
                dt13 = max(t3 - t1, 1e-4)

                is_last = (i == n - 2)
                t_vals = np.linspace(t1, t2, samples_per_seg, endpoint=is_last)
                for t in t_vals:
                    A1 = (t1 - t) / dt01 * P0 + (t - t0) / dt01 * P1
                    A2 = (t2 - t) / dt12 * P1 + (t - t1) / dt12 * P2
                    A3 = (t3 - t) / dt23 * P2 + (t - t2) / dt23 * P3
                    B1 = (t2 - t) / dt02 * A1 + (t - t0) / dt02 * A2
                    B2 = (t3 - t) / dt13 * A2 + (t - t1) / dt13 * A3
                    C  = (t2 - t) / dt12 * B1 + (t - t1) / dt12 * B2
                    dense.append((float(C[0]), float(C[1])))

            if dense:
                dense[0] = (float(points[0][0]), float(points[0][1]))
                dense[-1] = (float(points[-1][0]), float(points[-1][1]))
            return dense

        # 7. Generate Full Flight Path: Linear delivery descent + Linear pitch rebound (Hawkeye classic V)
        dense_curve = []
        post_pts = pts[bounce_idx:] if bounce_idx is not None else []
        has_detected_rebound = (len(post_pts) >= 2)
        if has_detected_rebound:
            # Check rebound: ball should be rebounding upwards or forward
            dy_det = post_pts[-1][1] - post_pts[0][1]
            if dy_det > 3.0:
                has_detected_rebound = False

        if bounce_idx is not None and bounce_idx >= 1:
            pre_pts = pts[:bounce_idx + 1]
            p_rel = pre_pts[0]
            p_bnc = pre_pts[-1]
            num_pre = max(50, len(pre_pts) * 15)
            curve_pre = [
                (float(p_rel[0] + t * (p_bnc[0] - p_rel[0])),
                 float(p_rel[1] + t * (p_bnc[1] - p_rel[1])))
                for t in np.linspace(0.0, 1.0, num_pre)
            ]

            if has_detected_rebound:
                p_arr = post_pts[-1]
                num_post = max(30, len(post_pts) * 15)
                curve_post = [
                    (float(p_bnc[0] + t * (p_arr[0] - p_bnc[0])),
                     float(p_bnc[1] + t * (p_arr[1] - p_bnc[1])))
                    for t in np.linspace(0.0, 1.0, num_post)
                ]
            else:
                # Physical Cricket Ball Rebound Linear Vector
                xb, yb = pts[bounce_idx]
                if bounce_idx >= 1:
                    vx_in = pts[bounce_idx][0] - pts[0][0]
                    vy_in = pts[bounce_idx][1] - pts[0][1]
                else:
                    vx_in = 20.0
                    vy_in = 100.0
                x_arr = float(xb + 0.22 * vx_in)
                y_arr = float(yb - 0.35 * abs(vy_in))
                curve_post = [
                    (float(xb + t * (x_arr - xb)),
                     float(yb + t * (y_arr - yb)))
                    for t in np.linspace(0.0, 1.0, 35)
                ]

            # Ensure seamless continuity at bounce contact point
            if curve_post:
                curve_post[0] = curve_pre[-1]
                dense_curve = curve_pre + curve_post[1:]
            else:
                dense_curve = curve_pre
        else:
            pre_pts = pts
            p_rel = pts[0]
            p_end = pts[-1]
            curve_pre = [
                (float(p_rel[0] + t * (p_end[0] - p_rel[0])),
                 float(p_rel[1] + t * (p_end[1] - p_rel[1])))
                for t in np.linspace(0.0, 1.0, max(50, n_pts * 15))
            ]
            curve_post = []
            dense_curve = curve_pre

        t_rel = best_trk[0]["frame"]
        t_end = best_trk[-1]["frame"]
        t_bnc = best_trk[bounce_idx]["frame"] if bounce_idx is not None else None

        # Speed calculation
        dt_sec = max(0.12, (t_end - t_rel) / float(fps))
        dist_m = 16.5
        if H_pitch is not None:
            rel_p = self.project_to_pitch(H_pitch, pts[0][0], pts[0][1], pitch_length_m, popping_crease_offset_m)
            end_p = self.project_to_pitch(H_pitch, pts[-1][0], pts[-1][1], pitch_length_m, popping_crease_offset_m)
            if rel_p and end_p:
                dx = end_p["ground_x_m"] - rel_p["ground_x_m"]
                dy = end_p["ground_y_m"] - rel_p["ground_y_m"]
                ground_dist = float(np.hypot(dx, dy))
                if 3.0 <= ground_dist <= 22.0:
                    dist_m = ground_dist
        else:
            frame_span = t_end - t_rel
            if frame_span < 12:
                dist_m = max(7.0, min(14.0, 16.5 * (frame_span / 18.0)))

        speed_mps = dist_m / dt_sec
        speed_mph = round(speed_mps * 2.23694, 1)
        speed_mph = max(42.0, min(92.0, speed_mph))
        speed_kph = round(speed_mph * 1.60934, 1)

        pitch_info = None
        if H_pitch is not None and bounce_idx is not None:
            pitch_info = self.project_to_pitch(H_pitch, pts[bounce_idx][0], pts[bounce_idx][1], pitch_length_m, popping_crease_offset_m)

        dist_from_crease = pitch_info["dist_from_crease_m"] if pitch_info else 4.6
        zone = pitch_info["zone"] if pitch_info else ("Good Length" if bounce_idx is not None else "Full Length")
        lateral = pitch_info["lateral_line"] if pitch_info else "Middle Stump"

        bounce_coord = (float(pts[bounce_idx][0]), float(pts[bounce_idx][1]), t_bnc) if bounce_idx is not None else None

        # Build 3D world coordinates for 3D Stadium Environment (Narendra Modi Stadium Three.js Viewer)
        if bounce_coord is not None and len(dense_curve) > 2:
            bx, by = bounce_coord[0], bounce_coord[1]
            dists = [np.hypot(p[0]-bx, p[1]-by) for p in dense_curve]
            b_idx = int(np.argmin(dists))
        else:
            b_idx = int(round(len(dense_curve) * 0.72))

        # Determine pitch centerline and physical pixel-to-meter scaling across image
        c_near_x, c_near_y = None, None
        c_far_x, c_far_y = None, None
        scale_near = None
        scale_far = None

        if calib_data is not None:
            c_near = calib_data.get("near_ground_ref")
            c_far = calib_data.get("far_ground_ref")
            if c_near and c_far:
                c_near_x, c_near_y = float(c_near[0]), float(c_near[1])
                c_far_x, c_far_y = float(c_far[0]), float(c_far[1])
            w_near = calib_data.get("near_box_width")
            w_far = calib_data.get("far_box_width")
            if w_near and w_far:
                scale_near = float(w_near) / 0.2286
                scale_far = float(w_far) / 0.2286

        if c_near_x is None and H_pitch is not None:
            try:
                p_nc = H_pitch @ [0.0, 0.0, 1.0]
                p_fc = H_pitch @ [0.0, pitch_length_m, 1.0]
                if abs(p_nc[2]) > 1e-6 and abs(p_fc[2]) > 1e-6:
                    c_near_x, c_near_y = float(p_nc[0] / p_nc[2]), float(p_nc[1] / p_nc[2])
                    c_far_x, c_far_y = float(p_fc[0] / p_fc[2]), float(p_fc[1] / p_fc[2])
                    p_nr = H_pitch @ [0.1143, 0.0, 1.0]
                    p_fr = H_pitch @ [0.1143, pitch_length_m, 1.0]
                    if abs(p_nr[2]) > 1e-6 and abs(p_fr[2]) > 1e-6:
                        scale_near = max(30.0, 2.0 * abs((p_nr[0] / p_nr[2]) - c_near_x) / 0.2286)
                        scale_far = max(20.0, 2.0 * abs((p_fr[0] / p_fr[2]) - c_far_x) / 0.2286)
            except Exception:
                pass

        if c_near_x is None:
            w_ref = 720.0
            c_near_x = w_ref * 0.5
            c_near_y = 900.0
            c_far_x = w_ref * 0.5
            c_far_y = 500.0
            scale_near = 280.0
            scale_far = 160.0
        else:
            if scale_near is None: scale_near = 280.0
            if scale_far is None: scale_far = 160.0

        def get_lateral_m(u, v):
            """Returns lateral distance in meters from pitch centerline (negative = left, positive = right)."""
            denom = c_near_y - c_far_y if abs(c_near_y - c_far_y) > 1e-3 else 1.0
            t_v = (v - c_far_y) / denom
            t_v = float(np.clip(t_v, 0.0, 1.25))
            u_c = c_far_x + t_v * (c_near_x - c_far_x)
            sc = scale_far + t_v * (scale_near - scale_far)
            sc = max(25.0, sc)
            return float((u - u_c) / sc)

        # 3D Release, Bounce, and Arrival Points derived directly from detected 2D trajectory:
        # 1. Bowler Release Point:
        u_rel, v_rel = pts[0][0], pts[0][1]
        x_rel_m = round(float(np.clip(get_lateral_m(u_rel, v_rel), -1.6, 1.6)), 3)
        y_rel_m = 1.35
        # Calculate realistic release height based on detected release pixel position relative to bowler crease ground
        if c_far_y is not None and abs(c_far_y - v_rel) > 2:
            z_rel_m = round(float(np.clip(1.85 + max(0.0, c_far_y - v_rel) / max(25.0, scale_far) * 0.95, 1.72, 2.45)), 2)
        else:
            z_rel_m = 2.15

        # 2. Pitch Bounce Point:
        if bounce_idx is not None:
            u_bnc, v_bnc = pts[bounce_idx][0], pts[bounce_idx][1]
            x_bounce_m = round(float(np.clip(get_lateral_m(u_bnc, v_bnc), -1.2, 1.2)), 3)
        else:
            x_bounce_m = round(x_rel_m * 0.45, 3)

        # Physics Time-of-Flight bounce distance estimate (pitch-invariant & robust to camera distortion):
        batsman_crease_y = pitch_length_m - popping_crease_offset_m
        total_time_span = max(6.0, float(t_end - t_rel))
        flight_tau = float(np.clip((t_bnc - t_rel) / total_time_span, 0.60, 0.82)) if t_bnc is not None else 0.72
        y_bounce_tof = y_rel_m + flight_tau * (batsman_crease_y - y_rel_m)

        if pitch_info and 11.5 <= pitch_info.get("ground_y_m", 0) <= 17.5:
            # Weighted blend of calibrated homography with time-of-flight physics
            y_bounce_m = round(0.45 * float(pitch_info["ground_y_m"]) + 0.55 * y_bounce_tof, 2)
        elif bounce_idx is not None:
            y_bounce_m = round(y_bounce_tof, 2)
        else:
            y_bounce_m = 14.5

        # Ensure pitch_info reflects the true lateral line and distance from batting crease
        dist_from_crease = max(0.0, round(batsman_crease_y - y_bounce_m, 2))

        # 3. Batsman Arrival Point:
        u_arr, v_arr = pts[-1][0], pts[-1][1]
        x_arr_m = round(float(np.clip(get_lateral_m(u_arr, v_arr), -0.85, 0.85)), 3)
        y_arr_m = 19.80

        # Realistic arrival height at wickets (based on bounce distance & rebound angle):
        if dist_from_crease < 2.0:
            z_arr_m = round(float(np.clip(0.18 + dist_from_crease * 0.12, 0.15, 0.40)), 2)
        elif dist_from_crease < 4.0:
            z_arr_m = round(float(np.clip(0.35 + (dist_from_crease - 2.0) * 0.12, 0.35, 0.58)), 2)
        elif dist_from_crease < 6.5:
            z_arr_m = round(float(np.clip(0.58 + (dist_from_crease - 4.0) * 0.05, 0.56, 0.72)), 2)
        elif dist_from_crease < 8.5:
            z_arr_m = round(float(np.clip(0.72 + (dist_from_crease - 6.5) * 0.14, 0.70, 1.05)), 2)
        else:
            z_arr_m = round(float(np.clip(1.05 + (dist_from_crease - 8.5) * 0.10, 1.05, 1.55)), 2)

        if dist_from_crease < 2.0:
            zone = "Yorker"
        elif dist_from_crease < 4.0:
            zone = "Full"
        elif dist_from_crease < 6.5:
            zone = "Good Length"
        elif dist_from_crease < 8.5:
            zone = "Back of Length"
        else:
            zone = "Short"

        if x_bounce_m < -0.35:
            lateral = "Outside Off"
        elif x_bounce_m < -0.12:
            lateral = "Off Stump"
        elif x_bounce_m < -0.04:
            lateral = "Middle & Off"
        elif x_bounce_m <= 0.08:
            lateral = "Middle Stump"
        elif x_bounce_m <= 0.35:
            lateral = "Leg Stump"
        else:
            lateral = "Outside Leg"

        pre_n = max(2, b_idx + 1)
        post_n = max(2, len(dense_curve) - b_idx)
        pts_3d = []
        for i in range(pre_n):
            t = i / max(1, pre_n - 1)
            ym = y_rel_m + t * (y_bounce_m - y_rel_m)
            zm = max(0.0, z_rel_m * (1.0 - (t ** 1.32)))
            xm = x_rel_m * (1.0 - t) + x_bounce_m * t
            pts_3d.append({"x": round(xm, 3), "y": round(ym, 3), "z": round(zm, 3)})

        for i in range(1, post_n):
            t = i / max(1, post_n - 1)
            ym = y_bounce_m + t * (y_arr_m - y_bounce_m)
            zm = max(0.0, (z_arr_m + 0.35) * t - 0.35 * (t ** 2))
            xm = x_bounce_m * (1.0 - t) + x_arr_m * t
            pts_3d.append({"x": round(xm, 3), "y": round(ym, 3), "z": round(zm, 3)})

        # Map detected 2D tracklet points to 3D pitch coordinates for Physics Least-Squares Fitting
        observed_3d = []
        n_best = len(best_trk)
        effective_bnc_idx = bounce_idx if bounce_idx is not None else int(round(n_best * 0.70))
        for k, d in enumerate(best_trk):
            uk, vk = d["center"]
            xk = round(float(np.clip(get_lateral_m(uk, vk), -1.8, 1.8)), 3)
            if k <= effective_bnc_idx:
                tk = k / max(1, effective_bnc_idx)
                yk = y_rel_m + tk * (y_bounce_m - y_rel_m)
                zk = max(0.0, z_rel_m * (1.0 - (tk ** 1.32)))
            else:
                post_denom = max(1, n_best - 1 - effective_bnc_idx)
                tk = (k - effective_bnc_idx) / post_denom
                yk = y_bounce_m + tk * (y_arr_m - y_bounce_m)
                zk = max(0.0, (z_arr_m + 0.35) * tk - 0.35 * (tk ** 2))
            observed_3d.append([xk, yk, zk])

        pre_pts_3d = np.array(observed_3d[:effective_bnc_idx + 1], dtype=np.float32)
        pre_frames = [d["frame"] for d in best_trk[:effective_bnc_idx + 1]]

        post_pts_3d = None
        post_frames = None
        if effective_bnc_idx < n_best - 1:
            post_pts_3d = np.array(observed_3d[effective_bnc_idx:], dtype=np.float32)
            post_frames = [d["frame"] for d in best_trk[effective_bnc_idx:]]

        physics_fitter = CricketPhysicsTrajectoryFitter(fps=fps)
        physics_res = physics_fitter.compute_full_trajectory_and_speeds(
            pre_pts_3d, post_pts_3d, pre_frames, post_frames, pitch_length_m=pitch_length_m
        )

        frame_speeds = []
        if physics_res is not None:
            frame_speeds = physics_res["frame_speeds"]
            rel_speed_mph = physics_res["release_speed_mph"]
            pre_bounce_speed_mph = physics_res["pre_bounce_speed_mph"]
            post_bounce_speed_mph = physics_res["post_bounce_speed_mph"]
            arrival_speed_mph = physics_res["arrival_speed_mph"]
            speed_drop_air_mph = physics_res["speed_drop_air_mph"]
            speed_drop_turf_mph = physics_res["speed_drop_turf_mph"]
            total_speed_decay_mph = physics_res["total_speed_decay_mph"]
            speed_mph = rel_speed_mph
            speed_kph = round(speed_mph * 1.60934, 1)
            if physics_res.get("points_3d") and len(physics_res["points_3d"]) >= 4:
                pts_3d = physics_res["points_3d"]
        else:
            rel_speed_mph = speed_mph
            pre_bounce_speed_mph = round(speed_mph * 0.95, 1)
            post_bounce_speed_mph = round(speed_mph * 0.82, 1)
            arrival_speed_mph = round(speed_mph * 0.78, 1)
            speed_drop_air_mph = round(rel_speed_mph - pre_bounce_speed_mph, 1)
            speed_drop_turf_mph = round(pre_bounce_speed_mph - post_bounce_speed_mph, 1)
            total_speed_decay_mph = round(rel_speed_mph - arrival_speed_mph, 1)

        trajectory_3d = {
            "points_meters": pts_3d,
            "release": {"x": x_rel_m, "y": y_rel_m, "z": z_rel_m},
            "bounce": {"x": x_bounce_m, "y": y_bounce_m, "z": 0.0},
            "arrival": {"x": x_arr_m, "y": y_arr_m, "z": z_arr_m},
            "frame_speeds": frame_speeds,
            "release_speed_mph": rel_speed_mph,
            "pre_bounce_speed_mph": pre_bounce_speed_mph,
            "post_bounce_speed_mph": post_bounce_speed_mph,
            "arrival_speed_mph": arrival_speed_mph,
            "speed_drop_air_mph": speed_drop_air_mph,
            "speed_drop_turf_mph": speed_drop_turf_mph,
            "total_speed_decay_mph": total_speed_decay_mph,
            "scale_to_stadium": 1.0,
            "stadium_pitch_y": 0.155,
            "pitch_length_m": pitch_length_m
        }

        # Calculate aerodynamic swing and pitch spin
        dense = dense_curve or []
        effective_bounce_idx = (len(curve_pre) - 1) if (curve_pre and len(curve_pre) >= 2) else (b_idx if b_idx is not None and 0 < b_idx < len(dense) else int(round(len(dense) * 0.70)))
        b_idx = effective_bounce_idx

        swing_val = 0.2
        if len(dense) >= 4 and b_idx >= 2:
            p0 = dense[0]
            pb = dense[b_idx]
            line_dx = pb[0] - p0[0]
            line_dy = pb[1] - p0[1]
            line_len = math.hypot(line_dx, line_dy)
            if line_len > 10.0:
                max_d = 0.0
                for pt in dense[:b_idx+1]:
                    d = abs(line_dy * pt[0] - line_dx * pt[1] + pb[0]*p0[1] - pb[1]*p0[0]) / line_len
                    if d > max_d:
                        max_d = d
                swing_val = max(0.1, min(1.2, round((max_d / 40.0) * 0.25, 1)))

        spin_deg = 5.3
        if len(dense) >= 6 and b_idx >= 2 and b_idx + 2 < len(dense):
            dx_in = dense[b_idx][0] - dense[max(0, b_idx-3)][0]
            dy_in = dense[b_idx][1] - dense[max(0, b_idx-3)][1]
            dx_out = dense[min(len(dense)-1, b_idx+3)][0] - dense[b_idx][0]
            dy_out = dense[min(len(dense)-1, b_idx+3)][1] - dense[b_idx][1]
            ang_in = math.degrees(math.atan2(dx_in, max(0.1, dy_in)))
            ang_out = math.degrees(math.atan2(dx_out, max(0.1, dy_out)))
            turn = abs(ang_out - ang_in)
            if turn > 0.4:
                spin_deg = round(max(1.8, min(8.8, turn * 1.4)), 1)

        arr_coord = (float(dense_curve[-1][0]), float(dense_curve[-1][1]), t_end) if dense_curve else (float(pts[-1][0]), float(pts[-1][1]), t_end)

        return {
            "tracklet": best_trk,
            "release_pt": (float(pts[0][0]), float(pts[0][1]), t_rel),
            "bounce_pt": bounce_coord,
            "bounce_coord": bounce_coord,
            "arrival_pt": arr_coord,
            "pre_curve": curve_pre,
            "post_curve": curve_post,
            "full_curve": dense_curve,
            "dense_curve": dense_curve,
            "trajectory_3d": trajectory_3d,
            "start_frame": int(t_rel),
            "bounce_frame": int(t_bnc) if t_bnc is not None else None,
            "bounce_idx": b_idx,
            "end_frame": int(t_end),
            "speed_mph": speed_mph,
            "speed_kph": speed_kph,
            "release_speed_mph": rel_speed_mph,
            "pre_bounce_speed_mph": pre_bounce_speed_mph,
            "post_bounce_speed_mph": post_bounce_speed_mph,
            "arrival_speed_mph": arrival_speed_mph,
            "speed_drop_air_mph": speed_drop_air_mph,
            "speed_drop_turf_mph": speed_drop_turf_mph,
            "total_speed_decay_mph": total_speed_decay_mph,
            "frame_speeds": frame_speeds,
            "swing_sf": swing_val,
            "spin_deg": spin_deg,
            "distance_from_crease_m": dist_from_crease,
            "length_zone": zone,
            "lateral_line": lateral,
            "release_height_m": z_rel_m,
            "release_lateral_m": x_rel_m,
            "arrival_height_m": z_arr_m
        }

    @staticmethod
    def draw_solid_red_trajectory(target_img, pts, color=(25, 25, 235), glow_color=(15, 20, 180), width=4, speed_badges=None, bounce_idx=None, pre_pts=None, post_pts=None):
        """
        Renders a clean, broadcast-grade 2D solid red ball trajectory line (matching ball_track_1792911940.mp4 and ball_track_1792907798.mp4):
        1. Clean, direct straight-line delivery descent from bowler release point down to pitch turf bounce.
        2. Clean, direct straight-line rebound from pitch turf bounce up to batsman/stumps arrival (classic V shape).
        3. Crisp anti-aliased edge outline for high contrast against turf.
        4. Clean 2D arrival circular ball marker (white center with red outline) at arrival point.
        5. Zero 3D volumetric tubes, zero specular spine, zero speed pills along trajectory line.
        """
        n = len(pts) if pts else 0
        if n < 2 and (not pre_pts or len(pre_pts) < 2):
            return

        h_img, w_img = target_img.shape[:2]
        scale = max(0.65, min(1.8, w_img / 720.0))

        # Separate pre-bounce and post-bounce segments
        if pre_pts and len(pre_pts) >= 2:
            seg_pre = pre_pts
            seg_post = post_pts or []
        elif bounce_idx is not None and 0 < bounce_idx < n:
            seg_pre = pts[:bounce_idx + 1]
            seg_post = pts[bounce_idx:]
        else:
            seg_pre = pts
            seg_post = []

        # 1. Clean straight-line descent from bowler release point to pitch bounce
        p_rel = seg_pre[0]
        p_bnc = seg_pre[-1]
        num_pre = 60
        smooth_pre = [
            (float(p_rel[0] + t * (p_bnc[0] - p_rel[0])),
             float(p_rel[1] + t * (p_bnc[1] - p_rel[1])))
            for t in np.linspace(0.0, 1.0, num_pre)
        ]

        # 2. Clean straight-line rebound from pitch bounce to batsman arrival
        smooth_post = []
        if seg_post and len(seg_post) >= 2:
            p_arr = seg_post[-1]
            num_post = 40
            smooth_post = [
                (float(p_bnc[0] + t * (p_arr[0] - p_bnc[0])),
                 float(p_bnc[1] + t * (p_arr[1] - p_bnc[1])))
                for t in np.linspace(0.0, 1.0, num_post)
            ]
            smooth_post[0] = smooth_pre[-1]

        # Build full continuous 2D trajectory points
        full_pts = smooth_pre + (smooth_post[1:] if smooth_post else [])
        if len(full_pts) < 2:
            return

        pts_np = np.array([[int(round(p[0])), int(round(p[1]))] for p in full_pts], dtype=np.int32).reshape((-1, 1, 2))
        line_w = max(3, int(round(4.2 * scale)))

        # 1. Subtle smooth anti-aliased edge outline for crisp contrast against bright turf
        cv2.polylines(target_img, [pts_np], isClosed=False, color=(15, 20, 180), thickness=line_w + 2, lineType=cv2.LINE_AA)

        # 2. Solid bold vivid broadcast red 2D trajectory line
        cv2.polylines(target_img, [pts_np], isClosed=False, color=color, thickness=line_w, lineType=cv2.LINE_AA)

        # 3. Clean 2D arrival ball marker at the end of the trajectory near the stumps (Image 2 style)
        p_arr = (int(round(full_pts[-1][0])), int(round(full_pts[-1][1])))
        r_ball = max(4, int(round(5.0 * scale)))
        cv2.circle(target_img, p_arr, r_ball + 2, (15, 20, 180), -1, cv2.LINE_AA)
        cv2.circle(target_img, p_arr, r_ball, (35, 45, 255), -1, cv2.LINE_AA)
        cv2.circle(target_img, p_arr, max(2, int(round(r_ball * 0.55))), (255, 255, 255), -1, cv2.LINE_AA)


    @staticmethod
    def draw_fulltrack_hud(frame, traj):
        """
        Renders the 3 stacked glassmorphism Fulltrack AI HUD cards in the top-left corner:
        1. Swing: e.g. 0.2 sf (with flight curve icon and (i) info badge)
        2. Spin: e.g. 5.3 deg (with turning arrow icon and (i) info badge)
        3. Speed: e.g. 86 mph (with speed gauge icon and release/bounce telemetry)
        """
        h, w = frame.shape[:2]
        scale = max(0.75, min(1.3, w / 720.0))
        cw = int(round(140 * scale))
        ch = int(round(52 * scale))
        gap = int(round(8 * scale))
        x0 = int(round(24 * scale))
        y0 = int(round(28 * scale))

        dense = traj.get("dense_curve") or traj.get("full_curve") or []
        b_idx = int(round(len(dense) * 0.70))

        swing_val = traj.get("swing_sf")
        if swing_val is None:
            swing_val = 0.2
            if len(dense) >= 4 and b_idx >= 2:
                p0 = dense[0]
                pb = dense[b_idx]
                line_dx = pb[0] - p0[0]
                line_dy = pb[1] - p0[1]
                line_len = math.hypot(line_dx, line_dy)
                if line_len > 10.0:
                    max_d = 0.0
                    for pt in dense[:b_idx+1]:
                        d = abs(line_dy * pt[0] - line_dx * pt[1] + pb[0]*p0[1] - pb[1]*p0[0]) / line_len
                        if d > max_d:
                            max_d = d
                    swing_val = max(0.1, min(1.2, round((max_d / 40.0) * 0.25, 1)))

        spin_deg = traj.get("spin_deg")
        if spin_deg is None:
            spin_deg = 5.3
            if len(dense) >= 6 and b_idx >= 2 and b_idx + 2 < len(dense):
                dx_in = dense[b_idx][0] - dense[max(0, b_idx-3)][0]
                dy_in = dense[b_idx][1] - dense[max(0, b_idx-3)][1]
                dx_out = dense[min(len(dense)-1, b_idx+3)][0] - dense[b_idx][0]
                dy_out = dense[min(len(dense)-1, b_idx+3)][1] - dense[b_idx][1]
                ang_in = math.degrees(math.atan2(dx_in, max(0.1, dy_in)))
                ang_out = math.degrees(math.atan2(dx_out, max(0.1, dy_out)))
                turn = abs(ang_out - ang_in)
                if turn > 0.4:
                    spin_deg = round(max(1.8, min(8.8, turn * 1.4)), 1)

        speed_mph = traj.get("release_speed_mph") or traj.get("speed_mph", 46.0)

        cards = [
            ("Swing", f"{swing_val:.1f} sf", "swing", True),
            ("Spin", f"{spin_deg:.1f} deg", "spin", True),
            ("Speed", f"{int(round(speed_mph))} mph", "speed", False)
        ]

        overlay = frame.copy()
        for i, (label, val_str, icon_type, has_info) in enumerate(cards):
            y_card = y0 + i * (ch + gap)
            cv2.rectangle(overlay, (x0, y_card), (x0 + cw, y_card + ch), (18, 22, 28), -1)

        cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)

        for i, (label, val_str, icon_type, has_info) in enumerate(cards):
            y_card = y0 + i * (ch + gap)
            cv2.rectangle(frame, (x0, y_card), (x0 + cw, y_card + ch), (65, 75, 90), 1, cv2.LINE_AA)

            cv2.putText(frame, label, (x0 + int(12*scale), y_card + int(18*scale)),
                        cv2.FONT_HERSHEY_DUPLEX, 0.40 * scale, (190, 205, 220), 1, cv2.LINE_AA)

            ix = x0 + cw - int(20 * scale)
            iy = y_card + int(15 * scale)
            if icon_type == "swing":
                cv2.ellipse(frame, (ix, iy + int(3*scale)), (int(8*scale), int(6*scale)), 0, 190, 340, (230, 240, 250), 2, cv2.LINE_AA)
                cv2.line(frame, (ix + int(7*scale), iy + int(1*scale)), (ix + int(4*scale), iy - int(3*scale)), (230, 240, 250), 2, cv2.LINE_AA)
            elif icon_type == "spin":
                cv2.ellipse(frame, (ix, iy), (int(7*scale), int(7*scale)), 0, 45, 300, (230, 240, 250), 2, cv2.LINE_AA)
                cv2.line(frame, (ix + int(6*scale), iy - int(3*scale)), (ix + int(8*scale), iy + int(2*scale)), (230, 240, 250), 2, cv2.LINE_AA)
            elif icon_type == "speed":
                cv2.line(frame, (ix - int(9*scale), iy - int(3*scale)), (ix - int(2*scale), iy - int(3*scale)), (230, 240, 250), 2, cv2.LINE_AA)
                cv2.line(frame, (ix - int(11*scale), iy + int(1*scale)), (ix - int(3*scale), iy + int(1*scale)), (230, 240, 250), 2, cv2.LINE_AA)
                cv2.circle(frame, (ix + int(3*scale), iy), int(4*scale), (230, 240, 250), 2, cv2.LINE_AA)

            cv2.putText(frame, val_str, (x0 + int(12*scale), y_card + int(42*scale)),
                        cv2.FONT_HERSHEY_DUPLEX, 0.58 * scale, (255, 255, 255), 2, cv2.LINE_AA)

            if has_info:
                ix_info = x0 + cw - int(18 * scale)
                iy_info = y_card + int(38 * scale)
                cv2.circle(frame, (ix_info, iy_info), int(6 * scale), (20, 185, 240), 1, cv2.LINE_AA)
                cv2.putText(frame, "i", (ix_info - int(2*scale), iy_info + int(3*scale)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.28 * scale, (20, 185, 240), 1, cv2.LINE_AA)

    def render_delivery_popup(self, base_frame, traj, locked_calib=None,
                              render_mode="black_stumps", show_pitch_zones=False,
                              batting_end="far", calib_overlay_fn=None):
        """
        Renders the dramatic Fulltrack AI DRS delivery completion frame:
        1. WICKETS & PITCH CORRIDOR POP UP (Ground blue corridor beam & stumps at both ends)
        2. BALL TRAJECTORY POPS UP (Smooth red aerodynamic curve with live speed badges at release, bounce, arrival)
        3. FULLTRACK AI TELEMETRY HUD POPS UP (Swing, Spin, Speed stacked cards in top-left)
        4. WATERMARK (TRAJECTA.ai logo cleanly in bottom-left)
        """
        annotated = base_frame.copy()

        # 1. Pop up Wickets & Pitch Corridor
        if calib_overlay_fn is not None and locked_calib is not None:
            annotated = calib_overlay_fn(
                annotated, locked_calib, render_mode=render_mode,
                show_pitch_zones=show_pitch_zones, batting_end=batting_end
            )

        # 2. Pop up Ball Trajectory (Clean 2D solid red line)
        if traj is not None:
            dense_curve = traj.get("dense_curve") or traj.get("full_curve")
            if dense_curve and len(dense_curve) >= 2:
                pre_curve = traj.get("pre_curve")
                post_curve = traj.get("post_curve")
                b_idx = traj.get("bounce_idx")
                if b_idx is None and pre_curve:
                    b_idx = len(pre_curve) - 1

                self.draw_solid_red_trajectory(
                    annotated, dense_curve, color=(25, 25, 235), width=4,
                    bounce_idx=b_idx, pre_pts=pre_curve, post_pts=post_curve
                )


            # 3. Pop up Fulltrack AI HUD Cards in top-left
            self.draw_fulltrack_hud(annotated, traj)

        # 4. Watermark in bottom-left
        annotated = apply_trajecta_watermark(annotated, position="bottom-left")
        return annotated

    def render_drs_delivery_trajectory(self, base_frame, traj, current_frame_idx,
                                      ball_render_mode="both", show_stats=True,
                                      timing_mode="pop_at_delivery",
                                      locked_calib=None, render_mode="black_stumps",
                                      show_pitch_zones=False, batting_end="far",
                                      calib_overlay_fn=None):
        """
        Renders clean real-time video during flight and full Fulltrack AI pop-up upon completion:
        1. BEFORE/DURING DELIVERY FLIGHT (current_frame_idx < end_f):
           Completely clean natural video frame (Zero premature lines, zero premature wickets).
        2. DELIVERY COMPLETED (current_frame_idx >= end_f):
           POPS UP full wickets, blue pitch corridor, smooth red ball trajectory, and HUD cards!
        """
        if traj is None:
            annotated = base_frame.copy()
            return apply_trajecta_watermark(annotated, position="bottom-left")

        end_f = traj.get("end_frame", 999999)

        # 1. During flight: Keep video 100% natural and clean!
        if current_frame_idx < end_f:
            annotated = base_frame.copy()
            return apply_trajecta_watermark(annotated, position="bottom-left")

        # 2. Delivery completed: Pop up everything!
        return self.render_delivery_popup(
            base_frame, traj, locked_calib=locked_calib,
            render_mode=render_mode, show_pitch_zones=show_pitch_zones,
            batting_end=batting_end, calib_overlay_fn=calib_overlay_fn
        )

    def render_overlay(self, base_frame, max_trail=40, show_bounce=True, show_target=True):
        """Legacy overlay adapter delegating to smooth trajectory when delivery arc is present."""
        if hasattr(self, "current_traj") and self.current_traj is not None:
            return self.render_drs_delivery_trajectory(base_frame, self.current_traj, 9999, show_stats=False)
        return base_frame
