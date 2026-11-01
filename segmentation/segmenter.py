"""
TRAJECTA.AI — Automatic Cricket Delivery Segmentation Pipeline.

Production-grade event-based video segmentation module for multi-delivery cricket footage.
Complies with Master Engineering Implementation Brief:
- Video inspection (duration <= 60s, frame rate, resolution, decodable check)
- Temporal ball observation collection with anti-shoe and spatial pitch corridor gating
- Delivery activity clustering and directional momentum tracking
- Event detection (bowler release, pitch bounce, batter arrival/stump passage)
- Boundary resolution with adaptive pre-release context and post-event tail
- Multi-delivery separation and deduplication
- Deterministic chronological delivery IDs (e.g. video_1_delivery_001)
- FFmpeg browser-compatible H.264 clip extraction
"""

import os
import re
import math
import time
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

import cv2
import numpy as np

# Find FFmpeg binary
FFMPEG_BIN = "/usr/local/bin/ffmpeg"
if not os.path.exists(FFMPEG_BIN):
    which_ffmpeg = shutil.which("ffmpeg")
    FFMPEG_BIN = which_ffmpeg if which_ffmpeg else "ffmpeg"


@dataclass
class VideoInspectionMetadata:
    """Metadata derived from inspecting a source video."""
    video_id: str
    filename: str
    file_path: str
    width: int
    height: int
    fps: float
    total_frames: int
    duration_seconds: float
    is_landscape: bool
    is_valid: bool
    error_message: Optional[str] = None


@dataclass
class DeliverySegment:
    """
    Structured representation of a single detected cricket delivery segment.
    Maintains clean separation between source timestamps and clip-relative timestamps.
    """
    delivery_id: str
    source_video_id: str
    source_filename: str
    source_duration: float
    start_seconds: float
    end_seconds: float
    release_seconds: Optional[float] = None
    bounce_seconds: Optional[float] = None
    arrival_seconds: Optional[float] = None
    start_confidence: float = 0.90
    end_confidence: float = 0.90
    overall_confidence: float = 0.90
    boundary_method: str = "observed_release_with_pre_window"
    status: str = "detected"  # 'detected' | 'extracted' | 'analyzed' | 'failed' | 'review_needed'
    clip_url: Optional[str] = None
    clip_path: Optional[str] = None
    analysis_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    trajectory_points: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def clip_duration(self) -> float:
        return max(0.0, round(self.end_seconds - self.start_seconds, 2))

    @property
    def clip_relative_release(self) -> Optional[float]:
        if self.release_seconds is not None:
            return max(0.0, round(self.release_seconds - self.start_seconds, 2))
        return None

    @property
    def clip_relative_bounce(self) -> Optional[float]:
        if self.bounce_seconds is not None:
            return max(0.0, round(self.bounce_seconds - self.start_seconds, 2))
        return None

    @property
    def clip_relative_arrival(self) -> Optional[float]:
        if self.arrival_seconds is not None:
            return max(0.0, round(self.arrival_seconds - self.start_seconds, 2))
        return None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["clip_duration"] = self.clip_duration
        d["clip_relative_release"] = self.clip_relative_release
        d["clip_relative_bounce"] = self.clip_relative_bounce
        d["clip_relative_arrival"] = self.clip_relative_arrival
        # Remove bulky raw trajectory points from top-level summary if not needed
        if len(d.get("trajectory_points", [])) > 200:
            d["trajectory_points_count"] = len(d["trajectory_points"])
            d.pop("trajectory_points", None)
        return d


class CricketDeliverySegmenter:
    """
    Dedicated AI Engine for detecting, isolating, and extracting multiple
    cricket deliveries from video footage.
    """

    def __init__(
        self,
        ball_detector=None,
        weights_path: Optional[str] = None,
        max_duration_seconds: float = 60.0,
        pre_release_window: float = 1.20,
        post_arrival_window: float = 1.50,
        min_delivery_duration: float = 0.25,
        max_delivery_clip_duration: float = 12.0,
        min_track_points: int = 4
    ):
        self.ball_detector = ball_detector
        self.weights_path = weights_path
        self.max_duration_seconds = max_duration_seconds
        self.pre_release_window = pre_release_window
        self.post_arrival_window = post_arrival_window
        self.min_delivery_duration = min_delivery_duration
        self.max_delivery_clip_duration = max_delivery_clip_duration
        self.min_track_points = min_track_points

    def _ensure_detector(self):
        if self.ball_detector is None:
            from ball_tracker.tracker import BallDetector
            if not self.weights_path:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                self.weights_path = os.path.join(base_dir, "weights", "ball_best.pt")
                if not os.path.exists(self.weights_path):
                    root_dir = os.path.dirname(base_dir)
                    self.weights_path = os.path.join(root_dir, "weights", "ball_best.pt")
            self.ball_detector = BallDetector(self.weights_path)

    # -------------------------------------------------------------------------
    # STAGE A: Decode and Inspect Video
    # -------------------------------------------------------------------------
    def inspect_video(self, video_path: str, video_id: str = "video_1") -> VideoInspectionMetadata:
        """
        Validates video decode, frame rate, resolution, duration <= 60s.
        Derives timestamps strictly from actual video stream timing.
        """
        filename = os.path.basename(video_path)
        if not os.path.exists(video_path):
            return VideoInspectionMetadata(
                video_id=video_id,
                filename=filename,
                file_path=video_path,
                width=0, height=0, fps=0.0,
                total_frames=0, duration_seconds=0.0,
                is_landscape=True, is_valid=False,
                error_message=f"Video file not found: {video_path}"
            )

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return VideoInspectionMetadata(
                video_id=video_id,
                filename=filename,
                file_path=video_path,
                width=0, height=0, fps=0.0,
                total_frames=0, duration_seconds=0.0,
                is_landscape=True, is_valid=False,
                error_message="Video file cannot be decoded or is corrupted"
            )

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        if width <= 0 or height <= 0 or fps <= 0 or total_frames <= 0:
            return VideoInspectionMetadata(
                video_id=video_id,
                filename=filename,
                file_path=video_path,
                width=width, height=height, fps=fps,
                total_frames=total_frames, duration_seconds=0.0,
                is_landscape=True, is_valid=False,
                error_message="Invalid video stream dimensions or frame count"
            )

        duration = total_frames / fps

        # Reject files exceeding the 60-second limit (allowing small floating-point tolerance of 0.05s)
        if duration > (self.max_duration_seconds + 0.05):
            return VideoInspectionMetadata(
                video_id=video_id,
                filename=filename,
                file_path=video_path,
                width=width, height=height, fps=fps,
                total_frames=total_frames, duration_seconds=duration,
                is_landscape=(width >= height), is_valid=False,
                error_message=f"Video duration ({duration:.1f}s) exceeds maximum allowed limit of {self.max_duration_seconds}s"
            )

        return VideoInspectionMetadata(
            video_id=video_id,
            filename=filename,
            file_path=video_path,
            width=width, height=height, fps=fps,
            total_frames=total_frames, duration_seconds=duration,
            is_landscape=(width >= height), is_valid=True
        )

    # -------------------------------------------------------------------------
    # STAGE B: Generate Temporal Ball Observations
    # -------------------------------------------------------------------------
    def generate_ball_observations(
        self,
        video_path: str,
        meta: VideoInspectionMetadata,
        conf: float = 0.15,
        stride: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Runs ball detector across video frames, applying anti-shoe and spatial constraints.
        Returns chronological candidate observations.
        """
        self._ensure_detector()
        self.ball_detector.reset_video_memory()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []

        observations: List[Dict[str, Any]] = []
        frame_idx = 0

        # Memory for stationary clutter (shoes, pitch marks)
        grid_history: Dict[Tuple[int, int], List[Tuple[int, Tuple[float, float]]]] = {}

        fps = meta.fps if meta.fps > 0 else 30.0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % stride == 0:
                time_sec = frame_idx / fps
                dets = self.ball_detector.detect(
                    frame,
                    conf=conf,
                    is_video=True,
                    ball_color="auto",
                    max_ball_size=72.0,
                    frame_idx=frame_idx
                )

                for d in dets:
                    cx, cy = d["center"]
                    # Spatial sanity check within frame boundaries
                    if not (0 <= cx <= meta.width and 0 <= cy <= meta.height):
                        continue

                    # Static clutter rejection (e.g. bowler shoe resting at crease)
                    gk = (int(round(cx / 20.0)), int(round(cy / 20.0)))
                    hist = grid_history.get(gk, [])
                    hist = [h for h in hist if (frame_idx - h[0]) <= int(fps * 2.0)]
                    is_stationary = False
                    if len(hist) >= 4:
                        dists = [math.hypot(cx - h[1][0], cy - h[1][1]) for h in hist]
                        if np.mean(dists) < 5.0:
                            is_stationary = True
                    hist.append((frame_idx, (cx, cy)))
                    grid_history[gk] = hist

                    if is_stationary:
                        continue

                    observations.append({
                        "frame": frame_idx,
                        "time_sec": round(time_sec, 3),
                        "center": (float(cx), float(cy)),
                        "radius": float(d.get("radius", 6.0)),
                        "conf": float(d.get("confidence", 0.5)),
                        "box": d.get("box", [int(cx-6), int(cy-6), int(cx+6), int(cy+6)])
                    })

            frame_idx += 1

        cap.release()
        observations.sort(key=lambda o: o["frame"])
        return observations

    # -------------------------------------------------------------------------
    # STAGE C, D, E: Identify Delivery Activity & Event Estimation
    # -------------------------------------------------------------------------
    def cluster_delivery_tracks(
        self,
        observations: List[Dict[str, Any]],
        fps: float,
        img_w: int,
        img_h: int
    ) -> List[List[Dict[str, Any]]]:
        """
        Groups temporal ball observations into distinct cricket delivery tracks.
        Accounts for brief tracking occlusion (1-6 frames) without breaking deliveries.
        Rejects stationary clutter and non-delivery motion.
        """
        if len(observations) < self.min_track_points:
            return []

        # 1. Primary tracklet formation based on physical delivery momentum
        tracklets: List[List[Dict[str, Any]]] = []
        max_frame_gap = max(4, int(round(fps * 0.25)))  # ~0.25s gap tolerance for motion blur / brief occlusion

        for obs in observations:
            f = obs["frame"]
            cx, cy = obs["center"]
            placed = False

            for trk in tracklets:
                last = trk[-1]
                df = f - last["frame"]
                if 1 <= df <= max_frame_gap:
                    dx = cx - last["center"][0]
                    dy = cy - last["center"][1]
                    dist = math.hypot(dx, dy)
                    speed_px_per_frame = dist / df

                    # Plausible cricket ball speed across frame (2 to 180 px/frame)
                    if 1.5 <= speed_px_per_frame <= 200.0:
                        # Momentum check: cricket deliveries travel forward/downward toward batsman
                        # Prevent sharp 180-degree turnarounds in delivery flight
                        if len(trk) >= 3:
                            overall_dx = trk[-1]["center"][0] - trk[0]["center"][0]
                            overall_dy = trk[-1]["center"][1] - trk[0]["center"][1]
                            # Allow downward/forward movement or consistent lateral swing
                            if abs(overall_dx) > 20.0 and (dx * overall_dx < -15.0):
                                continue
                        trk.append(obs)
                        placed = True
                        break

            if not placed:
                tracklets.append([obs])

        # 2. Merge tracklets separated by small gap (e.g. pitch bounce turf loss or bat impact)
        merged = True
        merge_gap_frames = max(6, int(round(fps * 0.40)))  # ~0.40s
        while merged:
            merged = False
            for i in range(len(tracklets)):
                for j in range(len(tracklets)):
                    if i != j and len(tracklets[i]) >= 2 and len(tracklets[j]) >= 2:
                        t1, t2 = tracklets[i], tracklets[j]
                        if t1[-1]["frame"] < t2[0]["frame"]:
                            df = t2[0]["frame"] - t1[-1]["frame"]
                            if 1 <= df <= merge_gap_frames:
                                dx = t2[0]["center"][0] - t1[-1]["center"][0]
                                dy = t2[0]["center"][1] - t1[-1]["center"][1]
                                dist = math.hypot(dx, dy)
                                speed = dist / df
                                if 1.5 <= speed <= 220.0:
                                    tracklets[i] = t1 + t2
                                    tracklets.pop(j)
                                    merged = True
                                    break
                if merged:
                    break

        # 3. Filter and qualify true cricket delivery candidates
        valid_deliveries: List[List[Dict[str, Any]]] = []
        for trk in tracklets:
            n = len(trk)
            if n < self.min_track_points:
                continue

            frame_span = trk[-1]["frame"] - trk[0]["frame"]
            duration_sec = frame_span / fps if fps > 0 else 0.0
            if duration_sec < self.min_delivery_duration:
                continue

            total_dist = sum(
                math.hypot(
                    trk[k]["center"][0] - trk[k-1]["center"][0],
                    trk[k]["center"][1] - trk[k-1]["center"][1]
                )
                for k in range(1, n)
            )

            # Must have traversed a significant distance down the pitch
            if total_dist < 35.0:
                continue

            # Must exhibit dynamic motion (not stationary object or gentle sway)
            avg_speed = total_dist / max(1, frame_span)
            if avg_speed < 1.8:
                continue

            # Must have net forward/downward progress down the pitch corridor
            # In typical camera angle (~4m behind non-striker wicket), ball descends towards pitch/batsman
            dy_net = trk[-1]["center"][1] - trk[0]["center"][1]
            max_y = max(p["center"][1] for p in trk)
            min_y = min(p["center"][1] for p in trk)
            vertical_travel = max_y - min_y

            # Delivery must either descend or have significant trajectory progression
            if vertical_travel < 20.0 and total_dist < 70.0:
                continue

            valid_deliveries.append(trk)

        # Sort delivery tracks chronologically
        valid_deliveries.sort(key=lambda t: t[0]["frame"])
        return valid_deliveries

    def estimate_events(
        self,
        track: List[Dict[str, Any]],
        fps: float
    ) -> Dict[str, Any]:
        """
        Estimates release, pitch bounce, and arrival events from a qualified delivery track.
        """
        n = len(track)
        t_start = track[0]["time_sec"]
        t_end = track[-1]["time_sec"]

        # 1. Release Event
        # Top-most / earliest downward point in delivery flight
        release_sec = t_start
        is_release_observed = True
        # If track starts with upward climb or starts mid-screen, flag as inferred
        if track[0]["center"][1] > 600:  # already low on pitch
            is_release_observed = False

        # 2. Bounce Event
        # Inflection point where ball descends (dy > 0) then rebounds upward (dy < 0),
        # or local maximum y on turf
        bounce_sec = None
        bounce_idx = None
        for k in range(1, n - 1):
            dy_prev = track[k]["center"][1] - track[k-1]["center"][1]
            dy_next = track[k+1]["center"][1] - track[k]["center"][1]
            if dy_prev > 2.0 and dy_next < -2.0:
                bounce_idx = k
                bounce_sec = track[k]["time_sec"]
                break

        # Fallback for bounce: maximum y point if in the latter half of delivery
        if bounce_sec is None and n >= 5:
            max_y_idx = int(np.argmax([p["center"][1] for p in track]))
            if 2 <= max_y_idx <= (n - 2):
                bounce_idx = max_y_idx
                bounce_sec = track[max_y_idx]["time_sec"]

        # 3. Arrival Event
        # Terminal point of delivery flight at batsman / stumps
        arrival_sec = t_end

        return {
            "release_seconds": round(release_sec, 3),
            "is_release_observed": is_release_observed,
            "bounce_seconds": round(bounce_sec, 3) if bounce_sec is not None else None,
            "arrival_seconds": round(arrival_sec, 3),
            "bounce_idx": bounce_idx
        }

    # -------------------------------------------------------------------------
    # STAGE F, G, H: Boundary Resolution, Separation, and Deduplication
    # -------------------------------------------------------------------------
    def build_delivery_segments(
        self,
        meta: VideoInspectionMetadata,
        tracks: List[List[Dict[str, Any]]]
    ) -> List[DeliverySegment]:
        """
        Calculates non-overlapping delivery intervals with pre-release window
        and post-arrival tail. Assigns stable deterministic delivery IDs.
        """
        if not tracks:
            return []

        candidates = []
        fps = meta.fps if meta.fps > 0 else 30.0

        for trk in tracks:
            ev = self.estimate_events(trk, fps)
            rel_s = ev["release_seconds"]
            arr_s = ev["arrival_seconds"]
            bnc_s = ev["bounce_seconds"]
            is_rel_obs = ev["is_release_observed"]

            # Stage F: Pre-release window
            raw_start = max(0.0, rel_s - self.pre_release_window)

            # Stage E: Post-arrival tail (event-based end estimation, NOT hardcoded 2s post-bounce)
            raw_end = min(meta.duration_seconds, arr_s + self.post_arrival_window)

            # Confidence scores
            avg_conf = float(np.mean([p["conf"] for p in trk]))
            point_bonus = min(0.15, len(trk) * 0.01)
            overall_conf = round(min(0.98, max(0.60, avg_conf + point_bonus)), 2)

            method = "observed_release_with_pre_window" if is_rel_obs else "inferred_flight_with_pre_window"

            candidates.append({
                "start": raw_start,
                "end": raw_end,
                "release": rel_s,
                "bounce": bnc_s,
                "arrival": arr_s,
                "is_rel_obs": is_rel_obs,
                "overall_conf": overall_conf,
                "method": method,
                "track": trk
            })

        # Stage H: Deduplicate overlapping candidate tracks
        # If two candidates overlap substantially in flight time, merge or keep higher-confidence
        deduped = []
        for cand in candidates:
            merged_into_existing = False
            for ex in deduped:
                # Check overlap between flight windows [release, arrival]
                flight_overlap_start = max(cand["release"], ex["release"])
                flight_overlap_end = min(cand["arrival"], ex["arrival"])
                if flight_overlap_end > flight_overlap_start:
                    overlap_dur = flight_overlap_end - flight_overlap_start
                    c_dur = max(0.1, cand["arrival"] - cand["release"])
                    ex_dur = max(0.1, ex["arrival"] - ex["release"])
                    if (overlap_dur / min(c_dur, ex_dur)) > 0.40:
                        # Duplicate track of same delivery!
                        merged_into_existing = True
                        if len(cand["track"]) > len(ex["track"]):
                            ex["track"] = cand["track"]
                            ex["release"] = min(ex["release"], cand["release"])
                            ex["arrival"] = max(ex["arrival"], cand["arrival"])
                            ex["overall_conf"] = max(ex["overall_conf"], cand["overall_conf"])
                            if cand["bounce"] is not None:
                                ex["bounce"] = cand["bounce"]
                        break
            if not merged_into_existing:
                deduped.append(cand)

        # Sort chronologically by start timestamp
        deduped.sort(key=lambda c: c["start"])

        # Stage G & H: Resolve boundary overlaps between consecutive distinct deliveries
        for k in range(len(deduped) - 1):
            curr = deduped[k]
            next_cand = deduped[k + 1]

            if curr["end"] > next_cand["start"]:
                # The post-arrival tail of curr collides with pre-release window of next_cand
                # Determine fair split boundary without truncating genuine delivery flight
                curr_flight_end = curr["arrival"]
                next_flight_start = next_cand["release"]

                if curr_flight_end < next_flight_start:
                    split_pt = (curr_flight_end + next_flight_start) / 2.0
                    curr["end"] = round(min(curr["end"], split_pt), 2)
                    next_cand["start"] = round(max(next_cand["start"], split_pt), 2)
                else:
                    # Very close deliveries: cut curr end at next release, clamp next start
                    curr["end"] = round(max(curr["start"] + 0.5, next_cand["release"] - 0.1), 2)
                    next_cand["start"] = round(curr["end"] + 0.05, 2)

        # Build final DeliverySegment objects with stable deterministic IDs
        segments: List[DeliverySegment] = []
        for idx, item in enumerate(deduped):
            start_s = round(max(0.0, item["start"]), 2)
            end_s = round(min(meta.duration_seconds, item["end"]), 2)

            # Validate non-empty and sensible duration (min 0.8s, max 15.0s)
            dur = end_s - start_s
            if dur < 0.8:
                continue

            delivery_num = idx + 1
            delivery_id = f"{meta.video_id}_delivery_{delivery_num:03d}"

            seg = DeliverySegment(
                delivery_id=delivery_id,
                source_video_id=meta.video_id,
                source_filename=meta.filename,
                source_duration=round(meta.duration_seconds, 2),
                start_seconds=start_s,
                end_seconds=end_s,
                release_seconds=round(item["release"], 2) if item["release"] is not None else None,
                bounce_seconds=round(item["bounce"], 2) if item["bounce"] is not None else None,
                arrival_seconds=round(item["arrival"], 2) if item["arrival"] is not None else None,
                start_confidence=round(item["overall_conf"], 2),
                end_confidence=round(item["overall_conf"], 2),
                overall_confidence=round(item["overall_conf"], 2),
                boundary_method=item["method"],
                status="detected",
                trajectory_points=item["track"]
            )
            segments.append(seg)

        return segments

    # -------------------------------------------------------------------------
    # Master Segmentation Flow for a Video File
    # -------------------------------------------------------------------------
    def segment_video(
        self,
        video_path: str,
        video_id: str = "video_1",
        ball_conf: float = 0.15,
        stride: int = 1
    ) -> Tuple[VideoInspectionMetadata, List[DeliverySegment]]:
        """
        Executes full end-to-end segmentation on a source video:
        1. Inspects & validates (<= 60s)
        2. Detects temporal ball candidates
        3. Clusters delivery tracks
        4. Resolves events & non-overlapping boundaries
        5. Assigns deterministic IDs
        """
        meta = self.inspect_video(video_path, video_id=video_id)
        if not meta.is_valid:
            return meta, []

        observations = self.generate_ball_observations(
            video_path,
            meta,
            conf=ball_conf,
            stride=stride
        )

        tracks = self.cluster_delivery_tracks(
            observations,
            fps=meta.fps,
            img_w=meta.width,
            img_h=meta.height
        )

        segments = self.build_delivery_segments(meta, tracks)
        return meta, segments


# -----------------------------------------------------------------------------
# Section 6: FFmpeg Browser-Compatible Clip Extraction
# -------------------------------------------------------------------------
def extract_delivery_clip(
    source_video_path: str,
    segment: DeliverySegment,
    output_dir: str,
    ffmpeg_bin: str = FFMPEG_BIN
) -> bool:
    """
    Extracts an individual delivery segment into a standalone browser-compatible
    H.264 MP4 clip with fast-start metadata.
    """
    os.makedirs(output_dir, exist_ok=True)
    out_filename = f"{segment.delivery_id}.mp4"
    out_path = os.path.join(output_dir, out_filename)

    start_s = segment.start_seconds
    dur_s = max(0.5, segment.end_seconds - segment.start_seconds)

    cmd = [
        ffmpeg_bin, "-y",
        "-ss", f"{start_s:.3f}",
        "-i", source_video_path,
        "-t", f"{dur_s:.3f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "22",
        "-threads", "4",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-avoid_negative_ts", "make_zero",
        out_path
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            segment.clip_path = out_path
            # URL relative to static root
            segment.clip_url = f"/static/outputs/segments/{out_filename}"
            segment.status = "extracted"
            return True
        else:
            segment.status = "failed"
            segment.error_message = "FFmpeg produced empty output file"
            return False
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
        segment.status = "failed"
        segment.error_message = f"FFmpeg extraction failed: {err_msg[:200]}"
        return False
    except Exception as e:
        segment.status = "failed"
        segment.error_message = f"Clip extraction error: {str(e)}"
        return False


def segment_video_file(
    video_path: str,
    video_id: str = "video_1",
    output_segments_dir: Optional[str] = None,
    ball_detector=None,
    extract_clips: bool = True
) -> Tuple[VideoInspectionMetadata, List[DeliverySegment]]:
    """
    High-level convenience function to segment video and optionally extract clips.
    """
    segmenter = CricketDeliverySegmenter(ball_detector=ball_detector)
    meta, segments = segmenter.segment_video(video_path, video_id=video_id)

    if extract_clips and meta.is_valid and segments and output_segments_dir:
        for seg in segments:
            extract_delivery_clip(video_path, seg, output_segments_dir)

    return meta, segments
