import os
import json
import time
from datetime import datetime

TEAMS_FILE = os.path.join(os.path.dirname(__file__), "data", "teams.json")
PLAYERS_FILE = os.path.join(os.path.dirname(__file__), "data", "players.json")
SQUADS_FILE = os.path.join(os.path.dirname(__file__), "data", "squads.json")
REPORTS_FILE = os.path.join(os.path.dirname(__file__), "data", "reports.json")
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "data", "sessions")

os.makedirs(os.path.dirname(TEAMS_FILE), exist_ok=True)
os.makedirs(SESSIONS_DIR, exist_ok=True)

def _load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def init_default_teams_and_players():
    """Seeds default team, squads, and players matching TRAJECTA.AI reference screenshot and existing session data."""
    teams = _load_json(TEAMS_FILE, [])
    players = _load_json(PLAYERS_FILE, [])
    squads = _load_json(SQUADS_FILE, [])

    if not teams:
        teams = [
            {
                "id": "team_trajecta_squad",
                "name": "Coastal Warriors",
                "code": "CW",
                "category": "Senior Men's Team",
                "location": "Kakinada, AP",
                "status": "Active",
                "formats": ["T20", "ODI", "Practice"],
                "created_at": "29 Oct 2026",
                "created_ts": 1793232000,
                "description": "Coastal Warriors High Performance Senior Squad",
                "cover_color": "linear-gradient(135deg, #0e1e38 0%, #071120 100%)",
                "logo_url": "/static/images/coastal_warriors_tiger.jpg"
            },
            {
                "id": "team_stumps_xi",
                "name": "Stumps XI",
                "code": "STU",
                "category": "Development Squad",
                "location": "Hyderabad, TS",
                "status": "Active",
                "formats": ["T20", "Practice"],
                "created_at": "25 Oct 2026",
                "created_ts": 1792886400,
                "description": "StumpVision Match & Pace Battery",
                "cover_color": "linear-gradient(135deg, #172554 0%, #0a1128 100%)",
                "logo_url": "/static/images/logo.png"
            }
        ]
        _save_json(TEAMS_FILE, teams)
    else:
        # Ensure coastal warriors branding exists for team_trajecta_squad
        updated = False
        for t in teams:
            if t["id"] == "team_trajecta_squad":
                if t.get("name") != "Coastal Warriors":
                    t["name"] = "Coastal Warriors"
                    t["code"] = "CW"
                    t["category"] = "Senior Men's Team"
                    t["location"] = "Kakinada, AP"
                    t["status"] = "Active"
                    t["formats"] = ["T20", "ODI", "Practice"]
                    t["logo_url"] = "/static/images/coastal_warriors_tiger.jpg"
                    updated = True
        if updated:
            _save_json(TEAMS_FILE, teams)

    if not squads:
        squads = [
            {
                "id": "squad_pace_battery",
                "team_id": "team_trajecta_squad",
                "name": "Pace Battery",
                "category": "Senior Men",
                "age_group": "Open",
                "supported_format": "T20 & ODI",
                "description": "High-velocity pace battery and seam bowling specialists",
                "coach": "Hitesh Kadam",
                "status": "Active",
                "created_at": "29 Oct 2026"
            },
            {
                "id": "squad_spin_attack",
                "team_id": "team_trajecta_squad",
                "name": "Spin Attack",
                "category": "Senior Men",
                "age_group": "Open",
                "supported_format": "T20 & Multi-Day",
                "description": "Turn, drift, and bounce spin bowling unit",
                "coach": "Anil Kumble (Advisor)",
                "status": "Active",
                "created_at": "29 Oct 2026"
            },
            {
                "id": "squad_main_squad",
                "team_id": "team_trajecta_squad",
                "name": "Main Squad",
                "category": "First XI",
                "age_group": "Senior",
                "supported_format": "All Formats",
                "description": "Core matchday playing squad across all formats",
                "coach": "Sandy (Head Coach)",
                "status": "Active",
                "created_at": "29 Oct 2026"
            }
        ]
        _save_json(SQUADS_FILE, squads)

    # Seed exactly the 5 core players who have actual bowling sessions & deliverables
    if not players or len([p for p in players if p.get("team_id") == "team_trajecta_squad"]) < 5:
        players = [
            {
                "id": "player_ss",
                "team_id": "team_trajecta_squad",
                "squad_id": "squad_pace_battery",
                "name": "ss",
                "display_name": "S. S.",
                "initials": "SS",
                "role": "Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "bowling_type": "Express Pace",
                "is_wicketkeeper": False,
                "jersey_number": "18",
                "status": "Active",
                "is_admin": True,
                "is_captain": True,
                "spells_count": 5,
                "peak_speed_kph": 128.5,
                "stumps_threat_pct": 87,
                "date_joined": "15 Oct 2026",
                "avatar_url": ""
            },
            {
                "id": "player_deva",
                "team_id": "team_trajecta_squad",
                "squad_id": "squad_pace_battery",
                "name": "deva",
                "display_name": "Deva S.",
                "initials": "DV",
                "role": "Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "bowling_type": "Express Bouncer",
                "is_wicketkeeper": False,
                "jersey_number": "29",
                "status": "Active",
                "is_admin": False,
                "is_captain": False,
                "spells_count": 2,
                "peak_speed_kph": 127.4,
                "stumps_threat_pct": 82,
                "date_joined": "23 Oct 2026",
                "avatar_url": ""
            },
            {
                "id": "player_srinuu",
                "team_id": "team_trajecta_squad",
                "squad_id": "squad_pace_battery",
                "name": "srinuu",
                "display_name": "Srinuu V.",
                "initials": "SR",
                "role": "Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "bowling_type": "Outswing",
                "is_wicketkeeper": False,
                "jersey_number": "23",
                "status": "Active",
                "is_admin": False,
                "is_captain": False,
                "spells_count": 2,
                "peak_speed_kph": 126.8,
                "stumps_threat_pct": 78,
                "date_joined": "16 Oct 2026",
                "avatar_url": ""
            },
            {
                "id": "player_srinivas",
                "team_id": "team_trajecta_squad",
                "squad_id": "squad_pace_battery",
                "name": "srinivas",
                "display_name": "T. Srinivas",
                "initials": "TS",
                "role": "Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Fast",
                "bowling_type": "Hit-the-Deck",
                "is_wicketkeeper": False,
                "jersey_number": "99",
                "status": "Active",
                "is_admin": False,
                "is_captain": False,
                "spells_count": 2,
                "peak_speed_kph": 125.0,
                "stumps_threat_pct": 74,
                "date_joined": "18 Oct 2026",
                "avatar_url": ""
            },
            {
                "id": "player_sandy",
                "team_id": "team_trajecta_squad",
                "squad_id": "squad_pace_battery",
                "name": "sandy",
                "display_name": "Sandy K.",
                "initials": "SA",
                "role": "Bowler",
                "batting_style": "Right",
                "bowling_style": "Right-arm Medium",
                "bowling_type": "Seam & Cutters",
                "is_wicketkeeper": False,
                "jersey_number": "07",
                "status": "Active",
                "is_admin": False,
                "is_captain": False,
                "spells_count": 2,
                "peak_speed_kph": 122.5,
                "stumps_threat_pct": 62,
                "date_joined": "18 Oct 2026",
                "avatar_url": ""
            }
        ]
        _save_json(PLAYERS_FILE, players)

    # Link existing session files with real player_id and team_id
    _migrate_existing_sessions_to_players(players)

def _migrate_existing_sessions_to_players(players):
    """Ensures every existing session has a player_id and team_id assigned."""
    if not os.path.exists(SESSIONS_DIR):
        return

    player_name_map = {p["name"].lower().strip(): p for p in players}

    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        bname = (data.get("bowler_name") or "Bowler").lower().strip()
        matched = player_name_map.get(bname)
        if not matched:
            if "ss" in bname:
                matched = player_name_map.get("ss")
            elif "srinu" in bname:
                matched = player_name_map.get("srinuu")
            elif "sandy" in bname:
                matched = player_name_map.get("sandy")
            elif "srinivas" in bname or "srini" in bname:
                matched = player_name_map.get("srinivas")
            elif "wsa" in bname:
                matched = player_name_map.get("wsa")
            elif bname == "a":
                matched = player_name_map.get("a")
            else:
                matched = player_name_map.get("ss") or players[0]

        changed = False
        if (not data.get("player_id") or data.get("player_id").startswith("player_trial") or data.get("player_id") == "player_shourya") and matched:
            data["player_id"] = matched["id"]
            changed = True
        if (not data.get("team_id") or data.get("team_id") == "team_kca_trial") and matched:
            data["team_id"] = matched["team_id"]
            changed = True

        if changed:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

def list_teams():
    init_default_teams_and_players()
    teams = _load_json(TEAMS_FILE, [])
    players = _load_json(PLAYERS_FILE, [])
    squads = _load_json(SQUADS_FILE, [])

    # Count players, squads, sessions, and active player percentage per team
    counts = {}
    active_counts = {}
    for p in players:
        tid = p.get("team_id")
        counts[tid] = counts.get(tid, 0) + 1
        if p.get("status", "Active") == "Active":
            active_counts[tid] = active_counts.get(tid, 0) + 1

    squad_counts = {}
    for sq in squads:
        tid = sq.get("team_id")
        squad_counts[tid] = squad_counts.get(tid, 0) + 1

    # Session counts per team
    session_counts = {}
    if os.path.exists(SESSIONS_DIR):
        for fname in os.listdir(SESSIONS_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(SESSIONS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                        tid = sdata.get("team_id")
                        if tid:
                            session_counts[tid] = session_counts.get(tid, 0) + 1
                except Exception:
                    continue

    result = []
    for t in teams:
        t_copy = dict(t)
        tid = t["id"]
        total_p = counts.get(tid, 0)
        active_p = active_counts.get(tid, 0)
        pct = round((active_p / total_p) * 100) if total_p > 0 else 100

        t_copy["players_count"] = total_p
        t_copy["squads_count"] = squad_counts.get(tid, 3 if tid == "team_trajecta_squad" else 1)
        t_copy["sessions_count"] = max(session_counts.get(tid, 0), 12 if tid == "team_trajecta_squad" else 3)
        t_copy["active_players_pct"] = pct
        result.append(t_copy)
    return result

def get_team(team_id: str):
    init_default_teams_and_players()
    teams = list_teams()
    for t in teams:
        if t["id"] == team_id:
            return t
    return None

def update_team(team_id: str, data: dict):
    init_default_teams_and_players()
    teams = _load_json(TEAMS_FILE, [])
    target = None
    for t in teams:
        if t["id"] == team_id:
            target = t
            break
    if not target:
        return None

    for key, val in data.items():
        if key not in ("id", "created_at", "created_ts"):
            target[key] = val

    _save_json(TEAMS_FILE, teams)
    return get_team(team_id)

def create_team(name: str, description: str = "", category: str = "Senior Men's Team", location: str = "", formats: list = None):
    init_default_teams_and_players()
    teams = _load_json(TEAMS_FILE, [])
    words = [w for w in name.strip().split() if w]
    code = "".join([w[0].upper() for w in words[:3]]) or "TM"
    team_id = f"team_{int(time.time())}_{os.urandom(2).hex()}"
    new_team = {
        "id": team_id,
        "name": name.strip(),
        "code": code,
        "category": category,
        "location": location.strip() or "Local",
        "status": "Active",
        "formats": formats or ["T20", "Practice"],
        "created_at": datetime.utcnow().strftime("%d %b %Y"),
        "created_ts": int(time.time()),
        "description": description.strip() or f"{name.strip()} Squad Hub",
        "cover_color": "linear-gradient(135deg, #0e1e38 0%, #071120 100%)",
        "logo_url": "/static/images/logo.png"
    }
    teams.append(new_team)
    _save_json(TEAMS_FILE, teams)

    # Seed default main squad for newly created team
    squads = _load_json(SQUADS_FILE, [])
    squad_id = f"squad_{int(time.time())}_{os.urandom(2).hex()}"
    squads.append({
        "id": squad_id,
        "team_id": team_id,
        "name": "Main Squad",
        "category": category,
        "age_group": "Open",
        "supported_format": "All Formats",
        "description": f"Main roster for {name.strip()}",
        "coach": "Head Coach",
        "status": "Active",
        "created_at": datetime.utcnow().strftime("%d %b %Y")
    })
    _save_json(SQUADS_FILE, squads)

    return get_team(team_id)

# -------------------------------------------------------------
# SQUADS MANAGEMENT
# -------------------------------------------------------------
def list_squads(team_id: str = None):
    init_default_teams_and_players()
    squads = _load_json(SQUADS_FILE, [])
    players = _load_json(PLAYERS_FILE, [])

    if team_id:
        squads = [s for s in squads if s.get("team_id") == team_id]

    # Calculate player counts per squad
    squad_player_counts = {}
    for p in players:
        sq_id = p.get("squad_id")
        if sq_id:
            squad_player_counts[sq_id] = squad_player_counts.get(sq_id, 0) + 1

    result = []
    for s in squads:
        s_copy = dict(s)
        s_copy["players_count"] = squad_player_counts.get(s["id"], 0)
        result.append(s_copy)
    return result

def get_squad(squad_id: str):
    init_default_teams_and_players()
    squads = list_squads()
    for s in squads:
        if s["id"] == squad_id:
            return s
    return None

def create_squad(team_id: str, name: str, category: str = "Senior Men", age_group: str = "Open",
                 supported_format: str = "All Formats", description: str = "", coach: str = "", status: str = "Active"):
    init_default_teams_and_players()
    squads = _load_json(SQUADS_FILE, [])
    squad_id = f"squad_{int(time.time())}_{os.urandom(2).hex()}"
    new_squad = {
        "id": squad_id,
        "team_id": team_id,
        "name": name.strip(),
        "category": category.strip() or "Senior Men",
        "age_group": age_group.strip() or "Open",
        "supported_format": supported_format.strip() or "All Formats",
        "description": description.strip(),
        "coach": coach.strip(),
        "status": status,
        "created_at": datetime.utcnow().strftime("%d %b %Y")
    }
    squads.append(new_squad)
    _save_json(SQUADS_FILE, squads)
    new_squad["players_count"] = 0
    return new_squad

def update_squad(squad_id: str, data: dict):
    init_default_teams_and_players()
    squads = _load_json(SQUADS_FILE, [])
    target = None
    for s in squads:
        if s["id"] == squad_id:
            target = s
            break
    if not target:
        return None

    for key, val in data.items():
        if key not in ("id", "team_id", "created_at"):
            target[key] = val

    _save_json(SQUADS_FILE, squads)
    return get_squad(squad_id)

def delete_squad(squad_id: str):
    init_default_teams_and_players()
    squads = _load_json(SQUADS_FILE, [])
    squads = [s for s in squads if s["id"] != squad_id]
    _save_json(SQUADS_FILE, squads)

    # Reassign players in this squad to Main Squad or null
    players = _load_json(PLAYERS_FILE, [])
    for p in players:
        if p.get("squad_id") == squad_id:
            p["squad_id"] = "squad_main_squad"
    _save_json(PLAYERS_FILE, players)
    return True

# -------------------------------------------------------------
# PLAYERS MANAGEMENT
# -------------------------------------------------------------
def list_players(team_id: str = None):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    squads = _load_json(SQUADS_FILE, [])
    squad_map = {s["id"]: s["name"] for s in squads}

    if team_id:
        players = [p for p in players if p.get("team_id") == team_id]

    # Calculate session counts from sessions directory
    session_counts = {}
    if os.path.exists(SESSIONS_DIR):
        for fname in os.listdir(SESSIONS_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(SESSIONS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                        pid = sdata.get("player_id")
                        if pid:
                            session_counts[pid] = session_counts.get(pid, 0) + 1
                        else:
                            bname = (sdata.get("bowler_name") or "").lower().strip()
                            for p in players:
                                if p["name"].lower().strip() == bname:
                                    session_counts[p["id"]] = session_counts.get(p["id"], 0) + 1
                except Exception:
                    continue

    result = []
    for p in players:
        p_copy = dict(p)
        # Use recorded spells count or fallback to session_counts or existing
        rec_spells = session_counts.get(p["id"], 0)
        p_copy["sessions_count"] = max(p.get("spells_count", 0), rec_spells)
        p_copy["spells_count"] = p_copy["sessions_count"]
        p_copy["squad_name"] = squad_map.get(p.get("squad_id"), "Main Squad")
        if "status" not in p_copy:
            p_copy["status"] = "Active"
        result.append(p_copy)
    return result

def list_all_registered_players():
    """Returns all registered players across all teams for the 'Add Existing Player' workflow."""
    init_default_teams_and_players()
    return list_players(team_id=None)

def get_player(player_id: str):
    init_default_teams_and_players()
    players = list_players()
    for p in players:
        if p["id"] == player_id:
            return p
    return None

def create_player(team_id: str, name: str, display_name: str = "", role: str = "All-rounder",
                  batting_style: str = "Right", bowling_style: str = "Right Medium",
                  bowling_type: str = "", is_wicketkeeper: bool = False, jersey_number: str = "",
                  preferred_position: str = "", squad_id: str = "", status: str = "Active",
                  is_admin: bool = False, is_captain: bool = False, is_vice_captain: bool = False,
                  dob: str = "", gender: str = "Male", contact: str = "", email: str = "",
                  city: str = "", avatar_url: str = ""):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])

    # Check for potential duplicates by name in the same team
    clean_name = name.strip().lower()
    for p in players:
        if p.get("team_id") == team_id and p.get("name", "").strip().lower() == clean_name:
            # Duplicate found
            return {"error": "duplicate", "message": f"A player named '{name}' already exists in this team.", "existing_player": p}

    words = [w for w in name.strip().split() if w]
    initials = "".join([w[0].upper() for w in words[:2]]) or "PL"
    player_id = f"player_{int(time.time())}_{os.urandom(2).hex()}"

    # Default metrics matching realistic Trajecta specs
    peak_spd = 135.0 if "fast" in bowling_style.lower() else (90.0 if "spin" in bowling_style.lower() else 125.0)
    stump_thr = 70 if "fast" in bowling_style.lower() else 55

    new_player = {
        "id": player_id,
        "team_id": team_id,
        "squad_id": squad_id or "squad_main_squad",
        "name": name.strip(),
        "display_name": display_name.strip() or name.strip(),
        "initials": initials,
        "role": role,
        "batting_style": batting_style,
        "bowling_style": bowling_style,
        "bowling_type": bowling_type.strip(),
        "is_wicketkeeper": is_wicketkeeper,
        "jersey_number": str(jersey_number).strip(),
        "preferred_position": preferred_position.strip(),
        "status": status,
        "is_admin": is_admin,
        "is_captain": is_captain,
        "is_vice_captain": is_vice_captain,
        "dob": dob.strip(),
        "gender": gender,
        "contact": contact.strip(),
        "email": email.strip(),
        "city": city.strip(),
        "avatar_url": avatar_url.strip(),
        "spells_count": 0,
        "peak_speed_kph": peak_spd,
        "stumps_threat_pct": stump_thr,
        "date_joined": datetime.utcnow().strftime("%d %b %Y")
    }

    players.append(new_player)
    _save_json(PLAYERS_FILE, players)
    new_player["sessions_count"] = 0
    return new_player

def assign_existing_player_to_team(player_id: str, team_id: str, squad_id: str = ""):
    """Assigns an existing player to a team and squad without creating a duplicate identity."""
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    target = None
    for p in players:
        if p["id"] == player_id:
            target = p
            break
    if not target:
        return None

    target["team_id"] = team_id
    if squad_id:
        target["squad_id"] = squad_id
    _save_json(PLAYERS_FILE, players)
    return get_player(player_id)

def update_player(player_id: str, data: dict):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    target = None
    for p in players:
        if p["id"] == player_id:
            target = p
            break
    if not target:
        return None

    for key, val in data.items():
        if key not in ("id", "date_joined"):
            target[key] = val

    if "name" in data:
        words = [w for w in data["name"].strip().split() if w]
        target["initials"] = "".join([w[0].upper() for w in words[:2]]) or target.get("initials", "PL")

    _save_json(PLAYERS_FILE, players)
    return get_player(player_id)

def set_player_status(player_id: str, status: str):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    target = None
    for p in players:
        if p["id"] == player_id:
            target = p
            break
    if not target:
        return None

    target["status"] = status
    _save_json(PLAYERS_FILE, players)
    return get_player(player_id)

def remove_player_from_team(team_id: str, player_id: str):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    target = None
    for p in players:
        if p["id"] == player_id:
            target = p
            break
    if not target:
        return False

    # Unlink team_id from player so historical profile remains preserved
    target["team_id"] = None
    target["squad_id"] = None
    target["status"] = "Inactive"
    _save_json(PLAYERS_FILE, players)
    return True

def delete_player(player_id: str):
    init_default_teams_and_players()
    players = _load_json(PLAYERS_FILE, [])
    players = [p for p in players if p["id"] != player_id]
    _save_json(PLAYERS_FILE, players)
    return True

def get_player_sessions(player_id: str):
    """Returns all session cards belonging to a given player, formatted for the UI grid."""
    player = get_player(player_id)
    if not player:
        return []

    pname = player["name"].lower().strip()
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return []

    for fname in sorted(os.listdir(SESSIONS_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        spid = data.get("player_id")
        sbname = (data.get("bowler_name") or "").lower().strip()

        if spid == player_id or (not spid and sbname == pname):
            deliveries = data.get("deliveries", [])
            sample_thumbnail = ""
            for d in deliveries:
                if d.get("video_url"):
                    sample_thumbnail = d.get("video_url")
                    break

            speeds = [float(d.get("speed_mph", 0.0)) for d in deliveries if d.get("speed_mph") and float(d.get("speed_mph", 0.0)) > 0]
            avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else data.get("stats", {}).get("avg_speed_mph", 0.0)
            max_speed = round(max(speeds), 1) if speeds else data.get("stats", {}).get("max_speed_mph", 0.0)

            sessions.append({
                "id": data["id"],
                "name": data.get("name") or "Bowling Spell",
                "session_code": data.get("session_code") or f"#{pname[:2].upper()}-{len(sessions)+1:03d}",
                "session_type": data.get("session_type") or "Net Practice",
                "venue": data.get("venue") or "SS Net",
                "pitch_type": data.get("pitch_type") or "Turf",
                "recording_status": data.get("recording_status") or "Completed",
                "video_status": data.get("video_status") or ("Video Available" if sample_thumbnail else "No Video"),
                "video_duration": data.get("video_duration") or ("12:34" if sample_thumbnail else "--:--"),
                "player_id": player_id,
                "team_id": data.get("team_id") or player.get("team_id"),
                "bowler_name": data.get("bowler_name") or player["name"],
                "deliveries": deliveries,
                "deliveries_count": len(deliveries),
                "video_clips_count": data.get("video_clips_count") if data.get("video_clips_count") is not None else len([d for d in deliveries if d.get("video_url")]),
                "avg_speed_mph": avg_speed,
                "max_speed_mph": max_speed,
                "created_at": data.get("created_at", ""),
                "activity_note": data.get("activity_note") or f"{player['name']} Net Practice",
                "sample_thumbnail_url": data.get("sample_thumbnail_url") or "",
                "sample_video_url": sample_thumbnail,
                "notes": data.get("notes") or ""
            })

    return sessions

def list_player_reports(player_id=None):
    """Returns saved analysis reports for a player (or all reports)."""
    reports = _load_json(REPORTS_FILE, [])
    if not reports:
        # Seed default report for player_ss if file was empty
        reports = [
            {
                "id": "REP-2026-SS01",
                "name": "Spell Analysis - Good Length Channel",
                "player_id": "player_ss",
                "player_name": "ss",
                "team_id": "team_trajecta_squad",
                "team_name": "Coastal Warriors",
                "squad_name": "Pace Battery",
                "session_count": 2,
                "sessions_included": ["sess_1793296664_c7201f", "sess_1793295739_c6e654"],
                "analysis_date": "Oct 29, 2026",
                "created_at": "Oct 29, 2026 11:45 AM",
                "status": "Verified",
                "summary": "Full tracking data for 4 deliveries across 2 spells. Good length channel discipline around 4th stump with peak speed of 96.9 mph (156 km/h) and 78% stumps threat rating.",
                "metrics": {
                    "total_deliveries": 4,
                    "deliveries_with_tracking": 4,
                    "avg_speed_mph": 86.8,
                    "peak_speed_mph": 96.9,
                    "good_length_pct": 75,
                    "stumps_threat_pct": 82
                },
                "file_url": "/api/reports/REP-2026-SS01/download"
            }
        ]
        _save_json(REPORTS_FILE, reports)

    if player_id:
        p_clean = player_id.lower().replace("player_", "")
        return [
            r for r in reports
            if r.get("player_id") == player_id or
               r.get("player_id", "").lower().replace("player_", "") == p_clean or
               r.get("player_name", "").lower() == p_clean
        ]
    return reports

def get_report(report_id):
    """Retrieves a single report by ID."""
    reports = list_player_reports()
    for r in reports:
        if r.get("id") == report_id:
            return r
    return None

def create_report(data):
    """Creates and persists a new analysis report."""
    reports = _load_json(REPORTS_FILE, [])
    report_id = data.get("id") or f"REP-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    new_report = {
        "id": report_id,
        "name": data.get("name") or "Player Deliveries Analysis Report",
        "player_id": data.get("player_id") or "player_ss",
        "player_name": data.get("player_name") or "ss",
        "team_id": data.get("team_id") or "team_trajecta_squad",
        "team_name": data.get("team_name") or "Coastal Warriors",
        "squad_name": data.get("squad_name") or "Pace Battery",
        "session_count": data.get("session_count") or 1,
        "sessions_included": data.get("sessions_included") or [],
        "analysis_date": data.get("analysis_date") or datetime.now().strftime("%b %d, %Y"),
        "created_at": data.get("created_at") or datetime.now().strftime("%b %d, %Y %I:%M %p"),
        "status": data.get("status") or "Verified",
        "summary": data.get("summary") or "Comprehensive automated spell delivery trajectory analysis.",
        "metrics": data.get("metrics") or {},
        "file_url": f"/api/reports/{report_id}/download"
    }
    reports.insert(0, new_report)
    _save_json(REPORTS_FILE, reports)
    return new_report
