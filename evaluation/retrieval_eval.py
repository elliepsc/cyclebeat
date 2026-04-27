"""
Retrieval Evaluation — CycleBeat
Vector search vs Text search — Hit Rate + MRR
Embeddings : sentence-transformers all-MiniLM-L6-v2
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

TEST_SET = [
    {"query": "séquence intense drop énergie haute 170 BPM", "expected_phase": "sprint"},
    {"query": "début de séance réveil des jambes lent", "expected_phase": "warm_up"},
    {"query": "montée debout résistance max effort extrême", "expected_phase": "climb"},
    {"query": "récupération après sprint souffle", "expected_phase": "recovery"},
    {"query": "cadence régulière base rythme modéré", "expected_phase": "steady"},
    {"query": "intervalle on sprint 30 secondes tout donner", "expected_phase": "interval"},
    {"query": "fin de séance retour calme détente", "expected_phase": "cool_down"},
    {"query": "montée puissante lente assis écraser pédales", "expected_phase": "climb"},
    {"query": "accélération progressive montée en puissance", "expected_phase": "build"},
    {"query": "repos pédale légère récupération longue", "expected_phase": "recovery"},
]


def vector_search(query: str, top_k: int = 5) -> list:
    vector = embedder.encode(query).tolist()
    results = qdrant.search(collection_name=COLLECTION_NAME, query_vector=vector, limit=top_k)
    return [r.payload for r in results]


def text_search(query: str, top_k: int = 5) -> list:
    keywords = query.lower().split()
    records, _ = qdrant.scroll(collection_name=COLLECTION_NAME, limit=100,
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


def hit_rate(results: list, expected: str) -> int:
    return int(any(r["phase"] == expected for r in results))


def mrr(results: list, expected: str) -> float:
    for i, r in enumerate(results):
        if r["phase"] == expected:
            return 1.0 / (i + 1)
    return 0.0


def evaluate(fn, label: str) -> dict:
    hits, rrs = [], []
    print(f"\n  {label}")
    print("  " + "─" * 45)
    for t in TEST_SET:
        results = fn(t["query"])
        h = hit_rate(results, t["expected_phase"])
        r = mrr(results, t["expected_phase"])
        hits.append(h)
        rrs.append(r)
        print(f"  {'✅' if h else '❌'} [{t['expected_phase']:12s}] {t['query'][:45]}")
    return {"approach": label, "hit_rate": round(np.mean(hits), 3), "mrr": round(np.mean(rrs), 3)}


def run_evaluation():
    print("\n🔬 Retrieval Evaluation — CycleBeat")
    r_vec = evaluate(vector_search, "Vector Search (sentence-transformers)")
    r_txt = evaluate(text_search, "Text Search (keyword)")

    print(f"\n{'Approche':<40} {'Hit Rate':>10} {'MRR':>8}")
    print("─" * 58)
    for r in [r_vec, r_txt]:
        print(f"{r['approach']:<40} {r['hit_rate']:>10.3f} {r['mrr']:>8.3f}")

    winner = r_vec if r_vec["hit_rate"] >= r_txt["hit_rate"] else r_txt
    print(f"\n✅ Meilleure approche : {winner['approach']}")

    os.makedirs("evaluation", exist_ok=True)
    with open("evaluation/retrieval_results.json", "w") as f:
        json.dump([r_vec, r_txt], f, indent=2)
    print("💾 Résultats → evaluation/retrieval_results.json")


if __name__ == "__main__":
    run_evaluation()
