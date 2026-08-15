"""
Ingestion Pipeline — CycleBeat
Stages the cycling patterns knowledge base into DuckDB via dlt.

Phase 0 purge: the Qdrant vector loading step is gone (ADR-001). What remains is
the dlt staging plus the mirror into the runtime DuckDB that dbt reads. The V3
multi-source ingestion (Deezer/CSV → lake) replaces this in phase 2.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dlt  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from db.runtime import save_patterns  # noqa: E402

load_dotenv()

PATTERNS_PATH = os.path.join(os.path.dirname(__file__), "../data/cycling_patterns.json")
PIPELINE_NAME = "cyclebeat_ingestion"
DATASET_NAME = "cycling_data"


def load_patterns(patterns_path: str = PATTERNS_PATH) -> list[dict]:
    """Read the cycling patterns knowledge base from disk."""
    with open(patterns_path, encoding="utf-8") as f:
        return json.load(f)


@dlt.source
def cycling_patterns_source(patterns_path: str = PATTERNS_PATH):
    """dlt source that yields all cycling patterns from the JSON knowledge base."""
    @dlt.resource(name="cycling_patterns", write_disposition="replace")
    def patterns():
        yield from load_patterns(patterns_path)
    return patterns()


def run(patterns_path: str = PATTERNS_PATH) -> int:
    """Run the ingestion pipeline: dlt staging, then mirror into the runtime DuckDB.

    Returns the number of patterns ingested.
    """
    print("CycleBeat ingestion pipeline...")

    # Step 1 — dlt staging into DuckDB
    pipeline = dlt.pipeline(
        pipeline_name=PIPELINE_NAME,
        destination="duckdb",
        dataset_name=DATASET_NAME,
    )
    pipeline.run(cycling_patterns_source(patterns_path))
    print("   dlt: staging OK")

    # Step 2 — Mirror patterns into the runtime DuckDB read by dbt
    patterns = load_patterns(patterns_path)
    save_patterns(patterns)
    print(f"   duckdb: {len(patterns)} patterns mirrored OK")

    print("Pipeline complete. Knowledge base ready.")
    return len(patterns)


if __name__ == "__main__":
    run()
