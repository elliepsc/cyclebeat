"""
Coach Planner Agent — CycleBeat
RAG on Qdrant (sentence-transformers) + coaching generation via Groq/OpenAI-compatible API.
"""

import json
import os
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from dotenv import load_dotenv
from typing import List

load_dotenv()

COLLECTION_NAME = "cycling_patterns"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2
PATTERNS_PATH = os.path.join(os.path.dirname(__file__), "../data/cycling_patterns.json")

# API client (Groq endpoint or any OpenAI-compatible backend)
llm_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
)
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")

# Qdrant Cloud (QDRANT_URL set) takes priority over local host/port
_qdrant_url = os.getenv("QDRANT_URL")
if _qdrant_url:
    qdrant = QdrantClient(url=_qdrant_url, api_key=os.getenv("QDRANT_API_KEY"))
else:
    qdrant = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", 6333))
    )

# Local embedding model — no API key required
_embedder = SentenceTransformer("all-MiniLM-L6-v2")


def embed_text(text: str) -> List[float]:
    """Encode a text string into a dense vector using sentence-transformers."""
    return _embedder.encode(text).tolist()


# ─── INGESTION ───────────────────────────────────────────────────────────────

def ingest_patterns():
    """Load cycling patterns into Qdrant. Idempotent — skips if collection already exists."""
    with open(PATTERNS_PATH, encoding="utf-8") as f:
        patterns = json.load(f)

    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME in existing:
        print("   Knowledge base already present, skipping ingestion.")
        return

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    )

    points = []
    for i, p in enumerate(patterns):
        text = (
            f"Phase: {p['phase']}. Label: {p['label']}. "
            f"Effort: {p['effort']}. Tags: {', '.join(p['tags'])}. "
            f"Instruction: {p['instruction']}"
        )
        points.append(PointStruct(id=i, vector=embed_text(text), payload=p))

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"✅ {len(points)} patterns ingested into Qdrant.")


# ─── QUERY REWRITING ─────────────────────────────────────────────────────────

REWRITE_PROMPT = """You are a cycling coach expert. Rewrite the following raw audio-feature description
into a natural coaching retrieval query (1 sentence, English, focused on effort and rhythm).

Raw description: {raw_query}

Respond with only the rewritten query, nothing else."""


def rewrite_query(raw_query: str) -> str:
    """Rewrite a raw audio-feature query into natural coaching language using the LLM."""
    response = llm_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": REWRITE_PROMPT.format(raw_query=raw_query)}],
        temperature=0.3,
        max_tokens=60
    )
    return response.choices[0].message.content.strip()


# ─── RETRIEVAL ───────────────────────────────────────────────────────────────

def build_raw_query(section: dict) -> str:
    """Build a raw retrieval query string from section audio features (BPM + loudness)."""
    tempo = section["tempo"]
    loudness = section["loudness"]
    effort = "rest" if loudness < -14 else "moderate" if loudness < -7 else "intense"
    speed = "slow" if tempo < 100 else "moderate" if tempo < 140 else "fast"
    return f"Cycling sequence {effort} tempo {speed} {tempo:.0f} BPM loudness {loudness:.1f}dB"


def vector_search(query: str, top_k: int = 5) -> List[dict]:
    """Run a dense vector search against the Qdrant collection."""
    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=embed_text(query),
        limit=top_k
    )
    return [r.payload for r in results]


def text_search(query: str, top_k: int = 5) -> List[dict]:
    """Keyword-based search: score patterns by query term overlap in label, instruction, tags."""
    keywords = query.lower().split()
    records, _ = qdrant.scroll(
        collection_name=COLLECTION_NAME,
        limit=200,
        with_payload=True,
        with_vectors=False
    )
    scored = []
    for r in records:
        p = r.payload
        text = f"{p['label']} {p['instruction']} {' '.join(p['tags'])} {p['phase']}".lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def hybrid_search(query: str, top_k: int = 5, alpha: float = 0.7) -> List[dict]:
    """Combine vector and keyword reciprocal-rank scores; alpha controls vector weight."""
    vec_results = vector_search(query, top_k=top_k * 2)
    txt_results = text_search(query, top_k=top_k * 2)

    scores: dict = {}
    for rank, p in enumerate(vec_results):
        pid = p["id"]
        scores.setdefault(pid, {"payload": p, "vec": 0.0, "txt": 0.0})
        scores[pid]["vec"] = 1.0 / (rank + 1)

    for rank, p in enumerate(txt_results):
        pid = p["id"]
        scores.setdefault(pid, {"payload": p, "vec": 0.0, "txt": 0.0})
        scores[pid]["txt"] = 1.0 / (rank + 1)

    fused = sorted(
        scores.values(),
        key=lambda x: alpha * x["vec"] + (1 - alpha) * x["txt"],
        reverse=True
    )
    return [item["payload"] for item in fused[:top_k]]


def retrieve_patterns(query: str, top_k: int = 3, use_hybrid: bool = True) -> List[dict]:
    """Retrieve the top-k coaching patterns using hybrid search or vector-only search."""
    return hybrid_search(query, top_k=top_k) if use_hybrid else vector_search(query, top_k=top_k)


def rerank(candidates: List[dict], section: dict) -> dict:
    """Re-rank candidates by BPM and loudness range match with the current section."""
    scored = []
    for p in candidates:
        bpm_ok = p["bpm_range"][0] <= section["tempo"] <= p["bpm_range"][1]
        loud_ok = p["loudness_range"][0] <= section["loudness"] <= p["loudness_range"][1]
        scored.append((int(bpm_ok) + int(loud_ok), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


# ─── LLM COACHING GENERATION ─────────────────────────────────────────────────

COACH_PROMPT = """You are a professional indoor cycling instructor — energetic, precise, and motivating.
Generate a short coaching instruction (max 2 sentences). Use direct address ("you"), be specific about effort and cadence.

Pattern: {pattern}
Track: {track_name} ({tempo:.0f} BPM)
Position in session: {position}

Reply with only the instruction, nothing else."""


def generate_cue(pattern: dict, section: dict, track_name: str, position: str) -> str:
    """Generate a personalized coaching cue from a retrieved pattern using the LLM."""
    prompt = COACH_PROMPT.format(
        pattern=json.dumps(pattern, ensure_ascii=False),
        track_name=track_name,
        tempo=section["tempo"],
        position=position
    )
    response = llm_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=100
    )
    return response.choices[0].message.content.strip()


# ─── MAIN AGENT ──────────────────────────────────────────────────────────────

EMOJI_MAP = {
    "warm_up": "🌀", "steady": "🚴", "build": "📈",
    "sprint": "🔥", "climb": "🏔️", "interval": "⚡",
    "recovery": "💨", "cool_down": "✨"
}


def run_coach_planner(
    playlist_data: dict,
    use_llm: bool = True,
    use_hybrid: bool = True
) -> dict:
    """Run the full coach planning pipeline: rewrite query → retrieve → rerank → generate cue."""
    total = playlist_data["total_duration_s"]
    session_tracks = []

    for track in playlist_data["tracks"]:
        track_cues = []
        track_start = track["session_start_s"]

        for section in track["sections"]:
            abs_start = track_start + section["start_s"]
            position = f"{abs_start/60:.1f}min/{total/60:.1f}min"

            raw_query = build_raw_query(section)
            query = rewrite_query(raw_query) if use_llm else raw_query
            candidates = retrieve_patterns(query, use_hybrid=use_hybrid)
            pattern = rerank(candidates, section)

            instruction = (
                generate_cue(pattern, section, track["track_name"], position)
                if use_llm
                else pattern["instruction"]
            )

            track_cues.append({
                "start_s": round(abs_start, 1),
                "duration_s": round(section["duration_s"], 1),
                "phase": pattern["phase"],
                "instruction": instruction,
                "resistance": pattern["resistance"],
                "effort": pattern["effort"],
                "emoji": EMOJI_MAP.get(pattern["phase"], "🚴"),
                "bpm": section["tempo"],
            })

        session_tracks.append({
            "track_name": track["track_name"],
            "artist": track["artist"],
            "start_s": track_start,
            "duration_s": track["duration_s"],
            "cues": track_cues,
        })

    return {
        "session": {
            "title": f"CycleBeat — {playlist_data['playlist_name']}",
            "total_duration_s": total,
            "generated_by": "CycleBeat Coach Agent"
        },
        "tracks": session_tracks
    }


if __name__ == "__main__":
    ingest_patterns()
    print("✅ Knowledge base ready.")
