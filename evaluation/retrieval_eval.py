"""
Retrieval Evaluation — CycleBeat
Compares vector search vs text search vs hybrid search on Hit Rate and MRR.
Embeddings: sentence-transformers all-MiniLM-L6-v2.
"""

import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST", "localhost"),
    port=int(os.getenv("QDRANT_PORT", 6333))
)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
COLLECTION_NAME = "cycling_patterns"

# Ground-truth test set: query → expected phase
TEST_SET = [
    {"query": "intense high-energy drop 170 BPM sprint sequence", "expected_phase": "sprint"},
    {"query": "session start gentle warm-up slow legs awakening", "expected_phase": "warm_up"},
    {"query": "standing climb max resistance extreme effort", "expected_phase": "climb"},
    {"query": "recovery after sprint catch breath", "expected_phase": "recovery"},
    {"query": "steady cadence moderate rhythm base pace", "expected_phase": "steady"},
    {"query": "30-second all-out sprint interval max power", "expected_phase": "interval"},
    {"query": "end of session cool down easy stretch", "expected_phase": "cool_down"},
    {"query": "seated powerful slow climb crush the pedals", "expected_phase": "climb"},
    {"query": "progressive acceleration building power", "expected_phase": "build"},
    {"query": "long recovery easy spin light pedals", "expected_phase": "recovery"},
]


def vector_search(query: str, top_k: int = 5) -> list:
    """Run dense vector search using sentence-transformer embeddings."""
    vector = embedder.encode(query).tolist()
    results = qdrant.search(collection_name=COLLECTION_NAME, query_vector=vector, limit=top_k)
    return [r.payload for r in results]


def text_search(query: str, top_k: int = 5) -> list:
    """Run keyword-based search by scoring patterns on query term overlap."""
    keywords = query.lower().split()
    records, _ = qdrant.scroll(collection_name=COLLECTION_NAME, limit=200,
                                with_payload=True, with_vectors=False)
    scored = []
    for r in records:
        p = r.payload
        text = f"{p['label']} {p['instruction']} {' '.join(p['tags'])} {p['phase']}".lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def hybrid_search(query: str, top_k: int = 5, alpha: float = 0.7) -> list:
    """Combine vector and keyword reciprocal-rank scores (alpha controls vector weight)."""
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


def hit_rate(results: list, expected: str) -> int:
    """Return 1 if the expected phase appears in top-k results, 0 otherwise."""
    return int(any(r["phase"] == expected for r in results))


def mrr(results: list, expected: str) -> float:
    """Compute Mean Reciprocal Rank for the expected phase in the result list."""
    for i, r in enumerate(results):
        if r["phase"] == expected:
            return 1.0 / (i + 1)
    return 0.0


def evaluate(fn, label: str) -> dict:
    """Evaluate a retrieval function over the full test set and print per-query results."""
    hits, rrs = [], []
    print(f"\n  {label}")
    print("  " + "─" * 55)
    for t in TEST_SET:
        results = fn(t["query"])
        h = hit_rate(results, t["expected_phase"])
        r = mrr(results, t["expected_phase"])
        hits.append(h)
        rrs.append(r)
        print(f"  {'✅' if h else '❌'} [{t['expected_phase']:12s}] {t['query'][:50]}")
    return {"approach": label, "hit_rate": round(np.mean(hits), 3), "mrr": round(np.mean(rrs), 3)}


def run_evaluation():
    """Run all retrieval approaches and save results to disk."""
    print("\n🔬 Retrieval Evaluation — CycleBeat")
    r_vec = evaluate(vector_search, "Vector Search (sentence-transformers)")
    r_txt = evaluate(text_search, "Text Search (keyword)")
    r_hyb = evaluate(hybrid_search, "Hybrid Search (vector + keyword, alpha=0.7)")

    print(f"\n{'Approach':<45} {'Hit Rate':>10} {'MRR':>8}")
    print("─" * 63)
    for r in [r_vec, r_txt, r_hyb]:
        print(f"{r['approach']:<45} {r['hit_rate']:>10.3f} {r['mrr']:>8.3f}")

    winner = max([r_vec, r_txt, r_hyb], key=lambda x: x["hit_rate"])
    print(f"\n✅ Best approach: {winner['approach']}")

    os.makedirs("evaluation", exist_ok=True)
    with open("evaluation/retrieval_results.json", "w") as f:
        json.dump([r_vec, r_txt, r_hyb], f, indent=2)
    print("💾 Results saved → evaluation/retrieval_results.json")


if __name__ == "__main__":
    run_evaluation()
