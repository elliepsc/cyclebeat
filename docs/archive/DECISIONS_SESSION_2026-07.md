# Session decisions & audit — 2026-07-28

Consolidated output of a review session (senior-lead-data lens). Not a truth source by
itself: structural decisions live in `docs/adr/`, the normative plan in
`CYCLEBEAT_PLAN_V3.md`. This file records the **audit findings** and the **rationale** behind
the decisions taken in-session, so nothing is lost between the conversation and the repo.

Truth-source order (E.0.1) is unchanged: (1) repo code, (2) plan V3 appendix E, (3) plan body.

---

## 1. Grid audit — current repo vs. target

Two grids coexist in the repo history and must not be confused:

- **Old grid (LLM-Zoomcamp RAG)** — what `README.md` and `PEER_REVIEW.md` still describe.
  Superseded by ADR-001. Ignore for grading the V3 target.
- **Target grid (AI Dev Tools, 14 criteria, max 30 pts)** — what the V3.1 plan and the
  `.claude/agents` are built against.

### 1.1 Scored on the target grid — **current `main`, evidence-based**

| # | Criterion | Score | Evidence |
|---|---|---|---|
| 1 | Problem description | 2/2 | README problem statement is clear |
| 2 | AI-assisted workflow | 2/2 | `docs/ai-workflow.md`, CLAUDE.md/AGENTS.md, 4 subagents |
| 3 | Technologies & architecture | 1/2 | No CI/CD to describe; README mislabels Dash as Streamlit |
| 4 | Frontend | 1/3 | Dash works but backend calls hardcoded/scattered; no front tests |
| 5 | API contract | 0-1/2 | No committed `openapi.yaml`; FastAPI is code-first (reverse of contract-first) |
| 6 | Backend | 1/3 | 7 endpoints, decent structure, but no contract to follow, no backend tests |
| 7 | Database | 1/2 | DuckDB integrated but best-effort (`try/except`); JSON still source of truth |
| 8 | Containerization | 2/2 | Full compose, healthchecks, one command |
| 9 | Integration testing | 0/2 | None — Makefile admits it |
| 10 | Deployment | 1/2 | `render.yaml` present, no live URL / proof |
| 11 | CI/CD | 0/2 | No `.github/workflows` |
| 12 | Agent extension pack | 1/2 | Instructions + subagents, but no MCP server, no hook, no permission notes |
| 13 | Security/audit | 0/2 | `security-auditor` defined but `docs/security/` produces nothing |
| 14 | Reproducibility | 1/2 | README Option 2 points to `app/streamlit_app.py` which does not exist |

**Current `main`: ~13/30.** Not the plan's target; it is the pre-purge state.

### 1.2 Verdict

- The **V3.1/V3.2 plan, fully executed, is designed for 30/30** — the mapping is deliberate
  (subagents cite each criterion). That is a **projection**, not a result.
- The gap is **execution, not design**: the V3 core (openapi.yaml, React front + tests,
  backend/integration tests, CI/CD, `docs/security/`, MCP + hooks, live deploy) is **not built
  yet**; `pyproject.toml` itself flags "the V3 rewrite" as future.
- **Bonus track (V3.2 B1-B7) adds 0 grid points** — portfolio/interview value only. Do not
  delay submission for it.

---

## 2. Decision — BPM resolution floor

Ratified as **ADR-004**. Summary: the guaranteed backbone is **librosa on full Creative-Commons
Jamendo audio + CSV** (no gate-kept API, no permission); **Deezer.bpm** and **GetSongBPM** are
**enrichment**, never load-bearing. This reverses the backlog's "librosa = opportunistic,
preview-based, unreliable alone" framing, which assumed 30 s Spotify previews (now dead).
See `docs/adr/adr-004-bpm-resolution-floor.md`.

Music-source answer, for the record: **not Spotify, not YouTube.** Deezer/CSV = plan metadata
& BPM enrichment; Jamendo = the audio actually played (CC, legal); librosa = local BPM floor.
"Can we be sure to have an API before building?" → certainty comes from the **phase-1 spike**,
not from docs; and the floor depends on **no** third-party API.

---

## 3. Feedback telemetry — CORRECTION (chain already exists)

**Earlier claim retracted.** A prior draft said runtime feedback "never reaches the warehouse".
That is **wrong**. The chain already exists and is wired:

```
api/main.py → db/runtime.py (INSERT into DuckDB `feedback`)
           → sources.yml: raw.feedback
           → stg_feedback.sql (rating cleaned: Great/Okay/Hard, feedback_date)
           → int_feedback_enriched.sql → mart_feedback_summary.sql
```

No `fct_feedback` is needed — the existing `stg → intermediate → mart` pattern is valid.

**Real (smaller) gaps that remain:**
1. **Best-effort write.** `api/main.py` wraps the DuckDB write in `try/except: pass`, with
   `data/feedback.json` as the primary store. A silent failure means the mart under-counts.
   Make the warehouse write the source of truth (JSON = demo fallback only), or at least log
   failures instead of swallowing them.
2. **Plan/code drift.** E.2 of `CYCLEBEAT_PLAN_V3.md` lists the BPM warehouse tables
   (`raw.tracks`, `raw.resolutions`, `dim_track`, `fct_session`, `fct_llm_calls`,
   `fct_agent_runs`) but **not** the feedback tables that dbt already implements. Reconcile:
   add `raw.feedback` + the stg/int/mart lineage to the E.2 spec so contract matches code.
3. **Copilot access.** Expose `mart_feedback_summary` on the copilot allowlist so it can answer
   "which goal/level has the worst satisfaction this week?".

Note: these dbt marts model the **current** product (sessions/feedback/patterns). They are
**not** the V3 BPM warehouse (`raw.tracks`/`raw.resolutions`/`dim_track`) — that is still to be
built in the V3 core (phase 2).

---

## 4. Stale-file log (to fix at the Phase-0 README/PEER_REVIEW rewrite)

Both files still describe the **v1** product and the **old grid**. Banners added to flag this;
full rewrite is a Phase-0 deliverable (plan L403), not done here to avoid preempting the purge.

- `README.md`: says Streamlit (code is Dash), references `app/streamlit_app.py` (does not
  exist → broken run instructions), lists Spotify/Qdrant as current stack, mentions Prefect
  (decision is Airflow, ADR-002).
- `docs-notes/PEER_REVIEW.md`: scores "28/23" on the old RAG grid (Qdrant, Streamlit, LangGraph
  bonus) — contradicts the target grid and §1 above.

---

## 5. Single-ingestion invariant (no new decision, verification to add)

The current double ingestion path (`agents/coach_planner.py` vs `ingest/ingest_pipeline.py`)
is **moot**: both are deleted in Phase-0 purge (ADR-001). The durable principle — one
ingestion path, SQL only in `api/repositories/` and `dbt/` — is already E.0.5. Action: add a
CI guard (grep/test) asserting no module opens DuckDB outside a repository. No plan change.
