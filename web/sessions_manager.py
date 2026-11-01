import os
import json
import time
import math
from datetime import datetime

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "data", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

def _get_session_path(session_id: str) -> str:
    # Sanitize session_id
    safe_id = "".join([c for c in session_id if c.isalnum() or c in ("-", "_")])
    return os.path.join(SESSIONS_DIR, f"{safe_id}.json")

def create_session(name: str, bowler_name: str = "", bowling_type: str = "Right-arm Fast", target_balls: int = 5, has_wickets: bool = True, player_id: str = None, team_id: str = None, squad_id: str = None) -> dict:
    session_id = f"sess_{int(time.time())}_{os.urandom(3).hex()}"
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Auto-link to Coastal Warriors and player SS (Admin / Captain)
    norm_name = (bowler_name or "").lower().strip()
    if not player_id or player_id in ["player_ss", "player_srinivas"]:
        if norm_name in ["ss", "s.s", "s. s.", "srinivas", "t. srinivas", "thalada", "admin", "captain"] or not norm_name or norm_name == "bowler":
            player_id = "player_ss"
            team_id = "team_trajecta_squad"
            squad_id = "squad_pace_battery"
            bowler_name = bowler_name or "ss"
        else:
            try:
                from web.teams_manager import list_players
                for p in list_players():
                    if p["name"].lower() == norm_name or p.get("display_name", "").lower() == norm_name:
                        player_id = p["id"]
                        team_id = p.get("team_id", "team_trajecta_squad")
                        squad_id = p.get("squad_id", "squad_pace_battery")
                        break
            except Exception:
                pass
            if not player_id:
                player_id = "player_ss"
                team_id = "team_trajecta_squad"
                squad_id = "squad_pace_battery"

    if not team_id:
        team_id = "team_trajecta_squad"

    session_data = {
        "id": session_id,
        "name": name.strip() or f"Training Session - {datetime.utcnow().strftime('%b %d')}",
        "bowler_name": bowler_name.strip() or "Bowler",
        "bowling_type": bowling_type,
        "target_balls": target_balls,
        "has_wickets": has_wickets,
        "player_id": player_id,
        "team_id": team_id,
        "squad_id": squad_id,
        "created_at": created_at,
        "updated_at": created_at,
        "deliveries": [],
        "stats": {
            "total_balls": 0,
            "avg_speed_mph": 0.0,
            "max_speed_mph": 0.0,
            "min_speed_mph": 0.0,
            "avg_speed_kph": 0.0,
            "avg_swing_sf": 0.0,
            "avg_spin_deg": 0.0,
            "length_distribution": {},
            "line_distribution": {},
            "consistency_score": 0.0
        }
    }

    with open(_get_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2)

    return session_data

def complete_session(session_id: str) -> dict:
    """Finalizes a session and synchronizes it to Coastal Warriors player profile and reports."""
    sess = get_session(session_id)
    if not sess:
        return {}

    deliveries = sess.get("deliveries", [])
    speeds_mph = [float(d["speed_mph"]) for d in deliveries if d.get("speed_mph") and float(d["speed_mph"]) > 0]
    speeds_kph = [float(d["speed_kph"]) for d in deliveries if d.get("speed_kph") and float(d["speed_kph"]) > 0]
    if not speeds_kph and speeds_mph:
        speeds_kph = [round(s * 1.60934, 1) for s in speeds_mph]

    avg_speed_kph = round(sum(speeds_kph) / len(speeds_kph), 1) if speeds_kph else 0.0
    peak_speed_kph = round(max(speeds_kph), 1) if speeds_kph else 0.0

    sess["status"] = "Completed"
    sess["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Ensure player_id and team_id are set to player_ss (Admin/Captain)
    if not sess.get("player_id") or sess.get("player_id") == "player_srinivas" or (sess.get("bowler_name") or "").lower() in ["ss", "srinivas", "t. srinivas", "admin", "captain"]:
        sess["player_id"] = "player_ss"
        sess["team_id"] = "team_trajecta_squad"
        sess["squad_id"] = "squad_pace_battery"
        sess["bowler_name"] = "ss"

    # Save session
    with open(_get_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(sess, f, indent=2)

    # Sync to player in Coastal Warriors team portal
    player_id = sess.get("player_id", "player_ss")
    from web.teams_manager import update_player_from_completed_session
    updated_player = update_player_from_completed_session(player_id, sess)
    sess["player_profile"] = updated_player

    return sess

def list_sessions(team_id: str = None, player_id: str = None) -> list:
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return []
        
    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if fname.endswith(".json"):
            fpath = os.path.join(SESSIONS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    spid = data.get("player_id")
                    stid = data.get("team_id")
                    if team_id and stid and stid != team_id:
                        continue
                    if player_id and spid and spid != player_id:
                        continue

                    # Summary for listing
                    sessions.append({
                        "id": data["id"],
                        "name": data["name"],
                        "bowler_name": data.get("bowler_name", "Bowler"),
                        "bowling_type": data.get("bowling_type", "Right-arm Fast"),
                        "avatar_url": data.get("avatar_url", ""),
                        "target_balls": data.get("target_balls", 5),
                        "total_balls": len(data.get("deliveries", [])),
                        "player_id": data.get("player_id", ""),
                        "team_id": data.get("team_id", ""),
                        "squad_id": data.get("squad_id", ""),
                        "created_at": data.get("created_at", ""),
                        "avg_speed_mph": data.get("stats", {}).get("avg_speed_mph", 0.0)
                    })
            except Exception:
                continue
                
    return sessions

def get_session(session_id: str) -> dict:
    fpath = _get_session_path(session_id)
    if not os.path.exists(fpath):
        return None
        
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def recalculate_session_stats(session_data: dict) -> dict:
    deliveries = session_data.get("deliveries", [])
    n = len(deliveries)
    if n == 0:
        session_data["stats"] = {
            "total_balls": 0,
            "avg_speed_mph": 0.0,
            "max_speed_mph": 0.0,
            "min_speed_mph": 0.0,
            "avg_speed_kph": 0.0,
            "avg_swing_sf": 0.0,
            "avg_spin_deg": 0.0,
            "length_distribution": {},
            "line_distribution": {},
            "consistency_score": 0.0
        }
        return session_data

    speeds_mph = [d.get("speed_mph", 0.0) for d in deliveries if d.get("speed_mph", 0) > 0]
    swings = [d.get("swing_sf", 0.2) for d in deliveries]
    spins = [d.get("spin_deg", 5.0) for d in deliveries]
    rel_heights = [d.get("release_height_m", 2.15) for d in deliveries if d.get("release_height_m", 0) > 0]
    
    avg_speed = round(float(sum(speeds_mph) / len(speeds_mph)), 1) if speeds_mph else 0.0
    max_speed = round(float(max(speeds_mph)), 1) if speeds_mph else 0.0
    min_speed = round(float(min(speeds_mph)), 1) if speeds_mph else 0.0
    avg_kph = round(avg_speed * 1.60934, 1)

    avg_swing = round(float(sum(swings) / len(swings)), 2) if swings else 0.2
    avg_spin = round(float(sum(spins) / len(spins)), 1) if spins else 5.0
    avg_rel_height = round(float(sum(rel_heights) / len(rel_heights)), 2) if rel_heights else 2.15

    length_dist = {}
    line_dist = {}
    good_zone_count = 0

    for d in deliveries:
        lz = d.get("length_zone", "Good Length")
        length_dist[lz] = length_dist.get(lz, 0) + 1
        if lz in ("Good Length", "Full"):
            good_zone_count += 1
            
        line = d.get("lateral_line", "Middle Stump")
        line_dist[line] = line_dist.get(line, 0) + 1

    consistency = round((good_zone_count / n) * 100.0, 1)

    session_data["stats"] = {
        "total_balls": n,
        "avg_speed_mph": avg_speed,
        "max_speed_mph": max_speed,
        "min_speed_mph": min_speed,
        "avg_speed_kph": avg_kph,
        "avg_swing_sf": avg_swing,
        "avg_spin_deg": avg_spin,
        "avg_release_height_m": avg_rel_height,
        "length_distribution": length_dist,
        "line_distribution": line_dist,
        "consistency_score": consistency
    }
    return session_data

def add_delivery_to_session(session_id: str, delivery_data: dict) -> dict:
    session = get_session(session_id)
    if session is None:
        return None

    ball_num = len(session.get("deliveries", [])) + 1
    
    # Standardize delivery entry
    ball_entry = {
        "ball_number": ball_num,
        "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
        "filename": delivery_data.get("filename", f"ball_{ball_num}.mp4"),
        "video_url": delivery_data.get("video_url", ""),
        "download_url": delivery_data.get("download_url", ""),
        "speed_mph": float(delivery_data.get("speed_mph", 0.0)),
        "speed_kph": float(delivery_data.get("speed_kph", 0.0)),
        "swing_sf": float(delivery_data.get("swing_sf", 0.2)),
        "spin_deg": float(delivery_data.get("spin_deg", 5.3)),
        "distance_from_crease_m": float(delivery_data.get("distance_from_crease_m", 4.5)),
        "length_zone": delivery_data.get("length_zone", "Good Length"),
        "lateral_line": delivery_data.get("lateral_line", "Middle Stump"),
        "bounce_coord": delivery_data.get("bounce_coord"),
        "trajectory_3d": delivery_data.get("trajectory_3d"),
        "pitch_x": float(delivery_data["pitch_x"]) if delivery_data.get("pitch_x") is not None else ((delivery_data.get("trajectory_3d") or {}).get("bounce", {}).get("x")),
        "pitch_y": float(delivery_data["pitch_y"]) if delivery_data.get("pitch_y") is not None else ((delivery_data.get("trajectory_3d") or {}).get("bounce", {}).get("y")),
        "release_height_m": float(delivery_data.get("release_height_m") or (delivery_data.get("trajectory_3d") or {}).get("release", {}).get("z", 2.15)),
        "release_lateral_m": float(delivery_data.get("release_lateral_m") or (delivery_data.get("trajectory_3d") or {}).get("release", {}).get("x", 0.0)),
        "arrival_height_m": float(delivery_data.get("arrival_height_m") or (delivery_data.get("trajectory_3d") or {}).get("arrival", {}).get("z", 0.68)),
        "release_frame": delivery_data.get("release_frame"),
        "bounce_frame": delivery_data.get("bounce_frame"),
        "end_frame": delivery_data.get("end_frame"),
        "frames_processed": delivery_data.get("frames_processed", 0)
    }

    session["deliveries"].append(ball_entry)
    session["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    recalculate_session_stats(session)

    with open(_get_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)

    return session

def delete_session(session_id: str) -> bool:
    fpath = _get_session_path(session_id)
    if os.path.exists(fpath):
        try:
            os.remove(fpath)
            return True
        except Exception:
            return False
    return False

def update_session(session_id: str, updates: dict) -> dict:
    session = get_session(session_id)
    if session is None:
        return None
    if "bowler_name" in updates and updates["bowler_name"]:
        session["bowler_name"] = str(updates["bowler_name"]).strip()
    if "bowling_type" in updates and updates["bowling_type"]:
        session["bowling_type"] = str(updates["bowling_type"]).strip()
    if "avatar_url" in updates:
        session["avatar_url"] = str(updates["avatar_url"]).strip()
    if "name" in updates and updates["name"]:
        session["name"] = str(updates["name"]).strip()
    if "target_balls" in updates and updates["target_balls"] is not None:
        try:
            session["target_balls"] = int(updates["target_balls"])
        except (ValueError, TypeError):
            pass
    if "has_wickets" in updates:
        session["has_wickets"] = bool(updates["has_wickets"])
    if "manual_wicket" in updates:
        session["manual_wicket"] = updates["manual_wicket"]
    for field in ["session_type", "venue", "pitch_type", "notes", "created_at", "recording_status", "video_status", "video_duration", "session_code"]:
        if field in updates and updates[field] is not None:
            session[field] = str(updates[field]).strip()
    session["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(_get_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    return session

def delete_delivery_from_session(session_id: str, delivery_id: str) -> dict:
    session = get_session(session_id)
    if session is None:
        return None
    deliveries = session.get("deliveries", [])
    orig_count = len(deliveries)
    # Match either by explicit id or by ball_number as string/int
    new_deliveries = []
    for d in deliveries:
        did = str(d.get("id") or d.get("ball_number"))
        if did != str(delivery_id):
            new_deliveries.append(d)
    
    if len(new_deliveries) < orig_count:
        # Re-index ball numbers
        for idx, d in enumerate(new_deliveries):
            d["ball_number"] = idx + 1
        session["deliveries"] = new_deliveries
        session["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        recalculate_session_stats(session)
        with open(_get_session_path(session_id), "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
    return session

def get_multiple_sessions(session_ids: list) -> list:
    results = []
    for sid in session_ids:
        s = get_session(sid)
        if s:
            results.append(s)
    return results

def aggregate_multiple_sessions(session_ids: list) -> dict:
    """Merges multiple session deliveries into a single unified analysis session object."""
    sessions = get_multiple_sessions(session_ids)
    if not sessions:
        return None
    
    all_deliveries = []
    bowler_name = sessions[0].get("bowler_name", "Bowler")
    bowling_type = sessions[0].get("bowling_type", "Right-arm Fast")
    team_id = sessions[0].get("team_id", "")
    player_id = sessions[0].get("player_id", "")

    ball_counter = 1
    for s in sessions:
        for d in s.get("deliveries", []):
            d_copy = dict(d)
            d_copy["original_session_id"] = s["id"]
            d_copy["original_session_name"] = s.get("name", "Session")
            d_copy["ball_number"] = ball_counter
            ball_counter += 1
            all_deliveries.append(d_copy)

    combined_session = {
        "id": f"multi_{len(sessions)}_spells",
        "name": f"Multi-Spell Analysis ({len(sessions)} Sessions)",
        "bowler_name": bowler_name,
        "bowling_type": bowling_type,
        "team_id": team_id,
        "player_id": player_id,
        "target_balls": len(all_deliveries),
        "is_multi_session": True,
        "source_session_ids": session_ids,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "deliveries": all_deliveries,
        "stats": {}
    }
    recalculate_session_stats(combined_session)
    return combined_session

