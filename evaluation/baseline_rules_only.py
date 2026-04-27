"""
Baseline Rules-Only — CycleBeat
Génère un script de coaching par règles simples (sans RAG, sans LLM).
Sert de baseline pour prouver que le RAG + LLM apportent une vraie valeur.

Règles :
  loudness > -6  AND tempo > 140  → sprint
  loudness > -6  AND tempo <= 140 → climb
  loudness > -10 AND tempo > 120  → steady
  loudness <= -14                 → recovery
  sinon                           → steady
"""

import json
import os

RULES = [
    {"cond": lambda l, t: l > -6  and t > 140,  "phase": "sprint",   "resistance": 8, "cadence": "105-115 RPM", "instruction": "SPRINT ! Résistance 8, cadence max."},
    {"cond": lambda l, t: l > -6  and t <= 140, "phase": "climb",    "resistance": 9, "cadence": "65-75 RPM",  "instruction": "MONTÉE. Résistance 9, pousse fort."},
    {"cond": lambda l, t: l > -10 and t > 120,  "phase": "steady",   "resistance": 5, "cadence": "90-100 RPM", "instruction": "Cadence. Résistance 5, maintiens."},
    {"cond": lambda l, t: l <= -14,              "phase": "recovery", "resistance": 2, "cadence": "70-80 RPM",  "instruction": "Récup. Résistance 2, souffle."},
]
DEFAULT = {"phase": "steady", "resistance": 5, "cadence": "85-95 RPM", "instruction": "Cadence régulière. Résistance 5."}

EMOJI_MAP = {"sprint": "🔥", "climb": "🏔️", "steady": "🚴", "recovery": "💨"}


def apply_rules(section: dict) -> dict:
    loudness = section["loudness"]
    tempo = section["tempo"]
    for rule in RULES:
        if rule["cond"](loudness, tempo):
            return rule
    return DEFAULT


def generate_baseline_session(playlist_data: dict) -> dict:
    """Génère un script de coaching par règles pures. Aucun LLM, aucun RAG."""
    session_tracks = []

    for track in playlist_data["tracks"]:
        track_cues = []
        track_start = track["session_start_s"]

        for section in track["sections"]:
            rule = apply_rules(section)
            phase = rule["phase"]
            track_cues.append({
                "start_s": round(track_start + section["start_s"], 1),
                "duration_s": round(section["duration_s"], 1),
                "phase": phase,
                "instruction": rule["instruction"],
                "resistance": rule["resistance"],
                "cadence": rule["cadence"],
                "emoji": EMOJI_MAP.get(phase, "🚴"),
                "bpm": section["tempo"],
                "method": "rules_only"
            })

        session_tracks.append({
            "track_name": track["track_name"],
            "artist": track["artist"],
            "start_s": track_start,
            "duration_s": track["duration_s"],
            "cues": track_cues
        })

    return {
        "session": {
            "title": f"[BASELINE] {playlist_data['playlist_name']}",
            "total_duration_s": playlist_data["total_duration_s"],
            "generated_by": "rules_only"
        },
        "tracks": session_tracks
    }


if __name__ == "__main__":
    # Test avec le demo dataset
    demo_path = os.path.join(os.path.dirname(__file__), "../data/demo_session.json")

    # Simule un playlist_data depuis la démo
    with open(demo_path) as f:
        demo = json.load(f)

    # Reformate demo_session → format playlist_data pour compatibilité
    fake_playlist = {
        "playlist_name": demo["session"]["title"],
        "total_duration_s": demo["session"]["total_duration_s"],
        "tracks": [
            {
                "track_name": t["track_name"],
                "artist": t["artist"],
                "session_start_s": t["start_s"],
                "duration_s": t["duration_s"],
                "sections": [
                    {"start_s": c["start_s"] - t["start_s"], "duration_s": c["duration_s"],
                     "loudness": -8.0, "tempo": c.get("bpm", 128.0)}
                    for c in t["cues"]
                ]
            }
            for t in demo["tracks"]
        ]
    }

    baseline = generate_baseline_session(fake_playlist)
    print(f"✅ Baseline généré : {len(baseline['tracks'])} tracks")
    for track in baseline["tracks"]:
        print(f"\n  {track['track_name']}")
        for cue in track["cues"]:
            print(f"    {cue['emoji']} {cue['phase']:10s} | {cue['instruction']}")
