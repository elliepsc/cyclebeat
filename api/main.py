"""
CycleBeat — FastAPI REST API
Exposes session generation, demo access, feedback endpoints, and Prometheus metrics.
"""

import json
import logging
import os
import sys
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _root)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CycleBeat API",
    version="1.0.0",
    description=(
        "REST API for CycleBeat — serves cycling coaching sessions, demo "
        "content and feedback. Session generation is being rebuilt on the V3 "
        "BPM resolver; the contract-first rewrite lands in phase 4."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
DEMO_PATH = os.path.join(DATA_DIR, "demo_session.json")
GENERATED_PATH = os.path.join(DATA_DIR, "generated_session.json")
FEEDBACK_PATH = os.path.join(DATA_DIR, "feedback.json")


# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class SessionRequest(BaseModel):
    playlist_url: str
    use_llm: bool = True


class FeedbackRequest(BaseModel):
    session_title: str
    rating: str  # "Great", "Okay", "Hard"
    note: str | None = ""


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_feedback() -> list:
    if not os.path.exists(FEEDBACK_PATH):
        return []
    return _load_json(FEEDBACK_PATH)


def _save_feedback(entry: dict):
    """Persist one feedback entry to the JSON file and to the warehouse.

    The DuckDB write used to be `try/except: pass`, which silently dropped every row when
    the warehouse was locked or missing — the E.2 debt recorded in the appendix. It now
    logs the failure instead of swallowing it, so a broken feedback chain is visible rather
    than showing up later as an empty `mart_feedback_summary`.

    The JSON file stays the primary store and the exception is not re-raised: losing a
    warehouse row must not fail the user's request. Making DuckDB the primary store is
    phase 4's job, together with moving this SQL into `api/repositories/`.
    """
    feedback = _load_feedback()
    feedback.append(entry)
    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)
    try:
        from db.runtime import save_feedback as _db_save
        _db_save(entry["session"], entry["rating"], entry.get("note", ""))
    except Exception:
        logger.exception("feedback warehouse write failed; JSON copy kept as primary")


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe — returns 200 when the API is up."""
    return {"status": "ok", "service": "cyclebeat-api"}


@app.get("/session/demo")
def get_demo_session():
    """Return the pre-generated demo session (no Spotify credentials needed)."""
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


@app.post("/session/generate", status_code=501)
def generate_session(req: SessionRequest):
    """
    Not implemented — session generation is being rebuilt.

    The V1 implementation (Spotify playlist fetch -> Qdrant hybrid RAG ->
    LangGraph orchestrator) was removed by the phase 0 purge (ADR-001). The
    replacement is the V3 BPM resolver (phase 2) exposed through a
    contract-first endpoint (phase 4). Until then this endpoint fails
    explicitly rather than silently serving demo data as if it were generated.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Session generation is not implemented yet: the V1 pipeline was "
            "purged (ADR-001) and the V3 BPM resolver is not built. "
            "Use GET /session/demo for a pre-generated session."
        ),
    )


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
