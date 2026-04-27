"""
Coach Planner Agent — CycleBeat
RAG sur Qdrant (sentence-transformers) + génération coaching via Groq.
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

# Clients
llm_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
)
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST", "localhost"),
    port=int(os.getenv("QDRANT_PORT", 6333))
)

# Embedding model local — pas de clé API requise
_embedder = SentenceTransformer("all-MiniLM-L6-v2")


def embed_text(text: str) -> List[float]:
    return _embedder.encode(text).tolist()


# ─── INGESTION ───────────────────────────────────────────────────────────────

def ingest_patterns():
    """Charge les patterns dans Qdrant. Idempotent."""
    with open(PATTERNS_PATH, encoding="utf-8") as f:
        patterns = json.load(f)

    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME in existing:
        print("   Knowledge base déjà présente, skip ingestion.")
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
    print(f"✅ {len(points)} patterns ingérés dans Qdrant.")


# ─── RETRIEVAL ───────────────────────────────────────────────────────────────

def build_query(section: dict) -> str:
    tempo = section["tempo"]
    loudness = section["loudness"]
    effort = "repos" if loudness < -14 else "modéré" if loudness < -7 else "intense"
    speed = "lent" if tempo < 100 else "modéré" if tempo < 140 else "rapide"
    return f"Séquence cycling {effort} tempo {speed} {tempo:.0f} BPM loudness {loudness:.1f}dB"


def retrieve_patterns(query: str, top_k: int = 3) -> List[dict]:
    results = qdrant.search(
        collection_name=COLLECTION_NAME,
        query_vector=embed_text(query),
        limit=top_k
    )
    return [r.payload for r in results]


def rerank(candidates: List[dict], section: dict) -> dict:
    """Reranking par BPM range + loudness range."""
    scored = []
    for p in candidates:
        bpm_ok = p["bpm_range"][0] <= section["tempo"] <= p["bpm_range"][1]
        loud_ok = p["loudness_range"][0] <= section["loudness"] <= p["loudness_range"][1]
        scored.append((int(bpm_ok) + int(loud_ok), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


# ─── GÉNÉRATION LLM ──────────────────────────────────────────────────────────

COACH_PROMPT = """Tu es un instructeur de cycling indoor professionnel.
Génère une instruction de coaching courte (max 2 phrases), en tutoiement, énergique et précise.

Pattern : {pattern}
Morceau : {track_name} ({tempo:.0f} BPM)
Position : {position}

Réponds uniquement avec l'instruction, rien d'autre."""


def generate_cue(pattern: dict, section: dict, track_name: str, position: str) -> str:
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


# ─── AGENT PRINCIPAL ─────────────────────────────────────────────────────────

EMOJI_MAP = {
    "warm_up": "🌀", "steady": "🚴", "build": "📈",
    "sprint": "🔥", "climb": "🏔️", "interval": "⚡",
    "recovery": "💨", "cool_down": "✨"
}


def run_coach_planner(playlist_data: dict, use_llm: bool = True) -> dict:
    total = playlist_data["total_duration_s"]
    session_tracks = []

    for track in playlist_data["tracks"]:
        track_cues = []
        track_start = track["session_start_s"]

        for section in track["sections"]:
            abs_start = track_start + section["start_s"]
            position = f"{abs_start/60:.1f}min/{total/60:.1f}min"

            query = build_query(section)
            candidates = retrieve_patterns(query)
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
            "generated_by": "CycleBeat Coach Agent (Groq)"
        },
        "tracks": session_tracks
    }


if __name__ == "__main__":
    ingest_patterns()
    print("✅ Knowledge base prête.")
