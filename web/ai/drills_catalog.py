"""
TRAJECTA.AI — Cricket Bowling Drills Library
Deterministic drill catalog mapped to bowling mechanics, release kinematics, and pitch dispersion.
"""

from typing import Dict, List, Any

DRILLS_CATALOG: Dict[str, Dict[str, Any]] = {
    "corridor_accuracy": {
        "id": "drill_corridor_accuracy",
        "name": "Corridor of Uncertainty Target Cones",
        "category": "Line & Length Precision",
        "target_attribute": "Good Length 4th-Stump Corridor",
        "description": "Place two flat saucer cones 6 to 8 meters from the stumps, spaced 35 cm apart in the 4th-to-5th stump channel. Bowler aims to land 5 out of 6 deliveries between the cones.",
        "difficulty": "Intermediate",
        "equipment": ["2x Flat Saucer Cones", "Measuring Tape", "6x Cricket Balls"],
        "reps_sets": "4 sets of 6 balls (24 deliveries total)",
        "success_metric": ">= 65% balls pitched in the designated good length channel",
        "focus_cues": ["Lock non-bowling arm toward off-stump bail", "Maintain upright wrist presentation through release"]
    },
    "yorker_execution": {
        "id": "drill_yorker_execution",
        "name": "Death-Overs Base Target Shoes / Discs",
        "category": "Yorker Execution",
        "target_attribute": "Full / Yorker Length (0-2m from popping crease)",
        "description": "Position a batting glove or rubber disc 30 cm inside the batting crease directly in line with off and leg stumps. Bowler runs in at 90% match speed to strike the target on the full or at base.",
        "difficulty": "Advanced",
        "equipment": ["Rubber target disc or target cone", "Full bowling run-up"],
        "reps_sets": "3 sets of 6 deliveries with 2-minute recovery intervals",
        "success_metric": ">= 50% deliveries within 0.8m of bowling crease at stump height <= 0.3m",
        "focus_cues": ["Snap bowling wrist forward late", "Delay head drop until release point is fully cleared"]
    },
    "back_of_length_enforcer": {
        "id": "drill_back_of_length",
        "name": "Heavy-Length Rib-Cage Bouncer Ladder",
        "category": "Hit-the-Deck Discipline",
        "target_attribute": "Back of a Length (7.5m - 9.5m from batting stumps)",
        "description": "Mark a 2m x 1m chalk box on the pitch 8 meters from the batsman's stumps. Aim to strike the deck hard with vertical seam to generate 1.1m+ shoulder-height bounce.",
        "difficulty": "Intermediate to Advanced",
        "equipment": ["Chalk pitch box", "Stump sensor"],
        "reps_sets": "4 sets of 5 deliveries",
        "success_metric": ">= 70% deliveries pitching in 7.5m-9.5m range with bounce >= 1.05m",
        "focus_cues": ["Pull down hard through front knee brace", "Tall gather at jump release"]
    },
    "pace_retention": {
        "id": "drill_pace_retention",
        "name": "Energy Transfer & Run-Up Tempo Pyramids",
        "category": "Pace Maintenance",
        "target_attribute": "Speed Consistency across 20+ balls",
        "description": "Run-up rhythm pacing drill using acceleration markers at 15m, 10m, and 5m before the crease. Ensures kinetic chain momentum transfer does not decelerate in overs 3 and 4.",
        "difficulty": "All Levels",
        "equipment": ["3x Run-up distance markers", "Radar / Telemetry Speed Trap"],
        "reps_sets": "6 overs simulated spell (36 deliveries) with spell pacing analysis",
        "success_metric": "Speed standard deviation < 3.0 km/h across entire session",
        "focus_cues": ["Smooth acceleration curve into delivery stride", "Maintain momentum through follow-through path"]
    },
    "arm_slot_consistency": {
        "id": "drill_arm_slot_consistency",
        "name": "Release Height Gate & Visual Feedback",
        "category": "Release Mechanics",
        "target_attribute": "Arm Slot & Release Point Variation",
        "description": "Suspend an overhead guide pole or use video playback to keep the release point window within a 10 cm variance box across all balls in the spell.",
        "difficulty": "Intermediate",
        "equipment": ["Trajecta AI High-speed Camera", "Overhead reference gauge"],
        "reps_sets": "3 sets of 8 deliveries",
        "success_metric": "Release height variance < 8 cm across the session",
        "focus_cues": ["Fix eye line on top of off-stump", "Strong front-arm pull down to left hip (for RHB bowler)"]
    },
    "drift_and_swing": {
        "id": "drill_drift_and_swing",
        "name": "Upright Seam & Angular Deviation Channel",
        "category": "Swing & Seam Movement",
        "target_attribute": "Late Swing / Seam Angle Stability",
        "description": "Bowler uses two-tone practice balls with a high seam. Deliveries are tracked for degrees of lateral deviation in the final 6 meters before pitch impact.",
        "difficulty": "Intermediate",
        "equipment": ["Two-tone cricket balls", "Pitch track sensors"],
        "reps_sets": "4 sets of 6 deliveries (focus on outswinger and inswinger alternating)",
        "success_metric": "Lateral deviation >= 1.8 degrees with seam tilt between 15-20 degrees",
        "focus_cues": ["Index and middle finger relaxed across seam", "Thumb resting lightly on underneath seam"]
    }
}

def get_recommended_drills_for_weaknesses(weakness_keys: List[str]) -> List[Dict[str, Any]]:
    """Return matching drills for identified weaknesses."""
    recommended = []
    seen = set()
    for w in weakness_keys:
        drill = DRILLS_CATALOG.get(w)
        if drill and drill["id"] not in seen:
            recommended.append(drill)
            seen.add(drill["id"])
    
    # Fallback to general accuracy if none matched
    if not recommended:
        recommended.append(DRILLS_CATALOG["corridor_accuracy"])
    return recommended
