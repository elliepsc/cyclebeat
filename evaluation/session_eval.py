"""
Session-Level Evaluation — CycleBeat
Primary metric: effort/recovery ratio. Secondary: phase diversity, transition coherence.
Compares two sessions (baseline rules-only vs full RAG+LLM system).
"""

import json
import os
from typing import List

EFFORT_PHASES = {"sprint", "climb", "interval", "build"}
RECOVERY_PHASES = {"recovery", "cool_down", "warm_up"}
NEUTRAL_PHASES = {"steady"}

IDEAL_EFFORT_RATIO_MIN = 0.35   # at least 35% effort time
IDEAL_EFFORT_RATIO_MAX = 0.65   # no more than 65% effort time

# Incoherent transitions: jumping directly between two max-effort phases
BAD_TRANSITIONS = {
    ("sprint", "climb"),
    ("climb", "sprint"),
    ("sprint", "sprint"),
    ("climb", "climb"),
}


def extract_cues(session: dict) -> List[dict]:
    """Flatten all cues from all tracks into a single time-sorted list."""
    cues = []
    for track in session["tracks"]:
        cues.extend(track["cues"])
    cues.sort(key=lambda c: c["start_s"])
    return cues


def effort_recovery_ratio(cues: List[dict]) -> dict:
    """Compute effort/recovery balance. Ideal range: 35%–65% effort."""
    total_s = sum(c["duration_s"] for c in cues)
    effort_s = sum(c["duration_s"] for c in cues if c["phase"] in EFFORT_PHASES)
    recovery_s = sum(c["duration_s"] for c in cues if c["phase"] in RECOVERY_PHASES)
    neutral_s = sum(c["duration_s"] for c in cues if c["phase"] in NEUTRAL_PHASES)

    effort_ratio = effort_s / total_s if total_s > 0 else 0
    is_balanced = IDEAL_EFFORT_RATIO_MIN <= effort_ratio <= IDEAL_EFFORT_RATIO_MAX

    return {
        "total_s": round(total_s, 1),
        "effort_s": round(effort_s, 1),
        "recovery_s": round(recovery_s, 1),
        "neutral_s": round(neutral_s, 1),
        "effort_ratio": round(effort_ratio, 3),
        "is_balanced": is_balanced,
        "verdict": "✅ Balanced" if is_balanced else (
            "⚠️ Too intense" if effort_ratio > IDEAL_EFFORT_RATIO_MAX else "⚠️ Too easy"
        )
    }


def phase_diversity(cues: List[dict]) -> dict:
    """Count distinct phases used. A well-designed session should use at least 4."""
    phases = {c["phase"] for c in cues}
    return {
        "unique_phases": len(phases),
        "phases_used": sorted(list(phases)),
        "is_diverse": len(phases) >= 4
    }


def transition_coherence(cues: List[dict]) -> dict:
    """Count incoherent phase transitions (e.g. sprint → climb with no recovery)."""
    bad_count = 0
    bad_examples = []

    for i in range(len(cues) - 1):
        current_phase = cues[i]["phase"]
        next_phase = cues[i + 1]["phase"]
        pair = (current_phase, next_phase)
        if pair in BAD_TRANSITIONS:
            bad_count += 1
            bad_examples.append(f"{current_phase} → {next_phase} at {cues[i+1]['start_s']:.0f}s")

    total_transitions = len(cues) - 1
    bad_ratio = bad_count / total_transitions if total_transitions > 0 else 0

    return {
        "total_transitions": total_transitions,
        "bad_transitions": bad_count,
        "bad_ratio": round(bad_ratio, 3),
        "examples": bad_examples[:5],
        "is_coherent": bad_ratio < 0.15
    }


def score_session(session: dict) -> dict:
    """Compute a weighted global session quality score (0–100)."""
    cues = extract_cues(session)

    er = effort_recovery_ratio(cues)
    pd = phase_diversity(cues)
    tc = transition_coherence(cues)

    # Weighted scoring: balance 40pts, diversity 30pts, coherence 30pts
    score = 0
    score += 40 if er["is_balanced"] else max(0, 40 - abs(er["effort_ratio"] - 0.5) * 100)
    score += 30 if pd["is_diverse"] else pd["unique_phases"] * 7
    score += 30 if tc["is_coherent"] else max(0, 30 - tc["bad_ratio"] * 100)

    return {
        "session_title": session["session"]["title"],
        "effort_recovery": er,
        "phase_diversity": pd,
        "transition_coherence": tc,
        "global_score": round(score, 1)
    }


def compare_sessions(session_a: dict, session_b: dict):
    """Compare two sessions side-by-side and save results to disk."""
    score_a = score_session(session_a)
    score_b = score_session(session_b)

    print("\n📊 Session-Level Evaluation — CycleBeat")
    print("=" * 60)

    for label, score in [("BASELINE (rules-only)", score_a), ("FULL SYSTEM (RAG + LLM)", score_b)]:
        er = score["effort_recovery"]
        pd = score["phase_diversity"]
        tc = score["transition_coherence"]

        print(f"\n  {label}")
        print(f"  {'─' * 45}")
        print(f"  Effort/Recovery  : {er['effort_ratio']*100:.1f}% effort — {er['verdict']}")
        print(f"  Unique phases    : {pd['unique_phases']} — {'✅' if pd['is_diverse'] else '⚠️ not diverse enough'}")
        print(f"  Bad transitions  : {tc['bad_transitions']}/{tc['total_transitions']} — {'✅' if tc['is_coherent'] else '⚠️ incoherent transitions'}")
        if tc["examples"]:
            for ex in tc["examples"]:
                print(f"    ↳ {ex}")
        print(f"  Global score     : {score['global_score']}/100")

    winner = "FULL SYSTEM" if score_b["global_score"] >= score_a["global_score"] else "BASELINE"
    diff = abs(score_b["global_score"] - score_a["global_score"])
    print(f"\n  ✅ Better session: {winner} (+{diff:.1f} pts)")

    os.makedirs("evaluation", exist_ok=True)
    with open("evaluation/session_eval_results.json", "w", encoding="utf-8") as f:
        json.dump({"baseline": score_a, "full_system": score_b}, f, ensure_ascii=False, indent=2)
    print("  💾 Results saved → evaluation/session_eval_results.json")


if __name__ == "__main__":
    demo_path = os.path.join(os.path.dirname(__file__), "../data/demo_session.json")

    with open(demo_path) as f:
        demo_session = json.load(f)

    score = score_session(demo_session)
    er = score["effort_recovery"]
    print(f"\n📊 Session: {score['session_title']}")
    print(f"   Effort ratio    : {er['effort_ratio']*100:.1f}% — {er['verdict']}")
    print(f"   Unique phases   : {score['phase_diversity']['unique_phases']}")
    print(f"   Bad transitions : {score['transition_coherence']['bad_transitions']}")
    print(f"   Global score    : {score['global_score']}/100")
