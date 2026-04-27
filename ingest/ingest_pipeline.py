"""
Ingestion Pipeline — CycleBeat
Loads cycling patterns into Qdrant via dlt staging + sentence-transformers embeddings.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dlt
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from dotenv import load_dotenv

load_dotenv()

PATTERNS_PATH = os.path.join(os.path.dirname(__file__), "../data/cycling_patterns.json")
COLLECTION_NAME = "cycling_patterns"
VECTOR_SIZE = 384

_qdrant_url = os.getenv("QDRANT_URL")
if _qdrant_url:
    qdrant = QdrantClient(url=_qdrant_url, api_key=os.getenv("QDRANT_API_KEY"))
else:
    qdrant = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", 6333))
    )
embedder = SentenceTransformer("all-MiniLM-L6-v2")


@dlt.source
def cycling_patterns_source(path: str = PATTERNS_PATH):
    """dlt source that yields all cycling patterns from the JSON knowledge base."""
    @dlt.resource(name="cycling_patterns", write_disposition="replace")
    def patterns():
        with open(path, encoding="utf-8") as f:
            for p in json.load(f):
                yield p
    return patterns()


def load_into_qdrant(patterns: list):
    """Recreate the Qdrant collection and upsert all pattern vectors."""
    existing = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION_NAME in existing:
        qdrant.delete_collection(COLLECTION_NAME)

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
        points.append(PointStruct(id=i, vector=embedder.encode(text).tolist(), payload=p))

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"✅ {len(points)} patterns ingested into Qdrant.")


def run():
    """Run the full ingestion pipeline: dlt staging then Qdrant vector loading."""
    print("🚀 CycleBeat ingestion pipeline...\n")

    # Step 1 — dlt staging into DuckDB
    pipeline = dlt.pipeline(
        pipeline_name="cyclebeat_ingestion",
        destination="duckdb",
        dataset_name="cycling_data"
    )
    pipeline.run(cycling_patterns_source())
    print("   dlt: staging OK")

    # Step 2 — Load vectors into Qdrant
    with open(PATTERNS_PATH, encoding="utf-8") as f:
        patterns = json.load(f)
    load_into_qdrant(patterns)

    print("\n✅ Pipeline complete. Knowledge base ready.")

    # Signal for docker-compose healthcheck (Linux/Docker only)
    try:
        open("/tmp/ingest_done", "w").close()
    except OSError:
        pass


if __name__ == "__main__":
    run()
