"""Executable form of the phase 0 exit criterion (runbook E.1 #3, §15).

The criterion is verified, not assumed: the application packages must not
reference any purged v1 brick, and the purged paths must stay gone. This file
is deliberately the only place in the repo where those names still appear.
"""

import ast
import importlib
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Application packages — the surface the exit-criterion grep covers.
APP_PACKAGES = ("api", "db", "ingest")

# Purged by ADR-001: Spotify client, vector DB + hybrid search, LangGraph
# orchestrator, local embeddings.
FORBIDDEN_IMPORTS = (
    "spotipy",
    "qdrant_client",
    "langgraph",
    "langchain_core",
    "sentence_transformers",
    "agents",
)

# Deleted by the purge; `evaluation/` and the UI come back as V3 rewrites.
PURGED_PATHS = (
    "agents",
    "app",
    "evaluation",
    "scripts/spotify_auth.py",
)


def _app_source_files() -> list[pathlib.Path]:
    files = []
    for package in APP_PACKAGES:
        files.extend(sorted((REPO_ROOT / package).rglob("*.py")))
    return files


def _imported_names(source: str) -> set[str]:
    """Top-level module names imported by a source file, lazy imports included."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_app_packages_have_source_files():
    """Guard the guard: an empty scan must not pass silently."""
    assert len(_app_source_files()) >= 4


@pytest.mark.parametrize("source_file", _app_source_files(), ids=lambda p: p.name)
def test_no_application_module_imports_a_purged_brick(source_file: pathlib.Path):
    imported = _imported_names(source_file.read_text(encoding="utf-8"))
    offenders = sorted(imported.intersection(FORBIDDEN_IMPORTS))
    assert not offenders, f"{source_file.relative_to(REPO_ROOT)} imports {offenders}"


@pytest.mark.parametrize("purged", PURGED_PATHS)
def test_purged_paths_are_gone(purged: str):
    assert not (REPO_ROOT / purged).exists()


def test_ingest_pipeline_has_no_vector_store_step():
    """The dlt staging survives; the vector loading step does not."""
    module = importlib.import_module("ingest.ingest_pipeline")
    assert hasattr(module, "cycling_patterns_source")
    assert not hasattr(module, "load_into_qdrant")
    assert not hasattr(module, "wait_for_qdrant")
