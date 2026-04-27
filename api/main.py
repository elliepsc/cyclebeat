"""
CycleBeat — FastAPI REST API
Production-ready backend decoupled from the Streamlit UI.
Exposes session generation, demo access, and feedback endpoints.
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

app = FastAPI(
    title="CycleBeat API",
    version="1.0.0",
    description=(
        "REST API for CycleBeat — generates timestamped cycling coaching sessions "
        "from a Spotify playlist using hybrid RAG + LLM."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
DEMO_PATH = os.path.join(DATA_DIR, "demo_session.json")
GENERATED_PATH = os.path.join(DATA_DIR, "generated_session.json")
FEEDBACK_PATH = os.path.join(DATA_DIR, "feedback.json")


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class SessionRequest(BaseModel):
    playlist_url: str
    use_llm: bool = True
    use_hybrid: bool = True


class FeedbackRequest(BaseModel):
    session_title: str
    rating: str  # "Great", "Okay", "Hard"
    note: Optional[str] = ""


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_feedback() -> list:
    if not os.path.exists(FEEDBACK_PATH):
        return []
    return _load_json(FEEDBACK_PATH)


def _save_feedback(entry: dict):
    feedback = _load_feedback()
    feedback.append(entry)
    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe — returns 200 when the API is up."""
    return {"status": "ok", "service": "cyclebeat-api"}


@app.get("/session/demo")
def get_demo_session():
    """Return the pre-generated demo session (no Spotify credentials required)."""
    if not os.path.exists(DEMO_PATH):
        raise HTTPException(status_code=404, detail="Demo session not found.")
    return _load_json(DEMO_PATH)


@app.get("/session/generated")
def get_generated_session():
    """Return the last session generated from a Spotify playlist."""
    if not os.path.exists(GENERATED_PATH):
        raise HTTPException(
            status_code=404,
            detail="No generated session yet. POST /session/generate first."
        )
    return _load_json(GENERATED_PATH)


@app.post("/session/generate", status_code=201)
def generate_session(req: SessionRequest):
    """
    Generate a full coaching session from a Spotify playlist URL.
    Runs the complete pipeline: playlist fetch -> RAG -> LLM generation.
    Saves the result to data/generated_session.json and returns it.
    """
    try:
        from agents.orchestrator import generate_session as _generate
        session = _generate(
            req.playlist_url,
            use_llm=req.use_llm,
            use_hybrid=req.use_hybrid,
        )
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback", status_code=201)
def submit_feedback(req: FeedbackRequest):
    """Append a user feedback entry to the feedback log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session": req.session_title,
        "rating": req.rating,
        "note": req.note or "",
    }
    _save_feedback(entry)
    return {"status": "saved", "entry": entry}


@app.get("/feedback")
def get_feedback():
    """Return all collected feedback entries."""
    return _load_feedback()


@app.get("/feedback/stats")
def get_feedback_stats():
    """Return aggregated feedback stats: total sessions, satisfaction rate."""
    feedback = _load_feedback()
    if not feedback:
        return {"total": 0, "satisfaction_pct": None, "ratings": {}}
    ratings = {}
    for f in feedback:
        r = f.get("rating", "Unknown")
        ratings[r] = ratings.get(r, 0) + 1
    great = sum(v for k, v in ratings.items() if "Great" in k)
    return {
        "total": len(feedback),
        "satisfaction_pct": round(great / len(feedback) * 100, 1),
        "ratings": ratings,
    }


# ─── ENTRYPOINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
