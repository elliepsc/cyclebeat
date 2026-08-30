# ADR-009 — Postgres transactional (Neon) beside DuckDB analytical

- **Status**: Accepted — **supersedes ADR-008**
- **Date**: 2026-08-30
- **Owner**: Ellie

> **Numbering note.** The phase-4 brief calls this decision "ADR-006 (Postgres=Neon)". `006` was
> already taken by `adr-006-e2-open-points.md`, Accepted 2026-08-15, and `007` / `008` are taken
> too. The convention in `docs/adr/README.md` is that an `Accepted` ADR is immutable, so this
> decision takes the next free number, **009**, rather than overwriting one.

## Context

**ADR-008 got the store wrong, and this ADR corrects it.** ADR-008 decided that sessions and
feedback are persisted in **DuckDB**, with the API writing `fct_session` directly. That decision
was taken from E.2, E.3 and §7 — and **without reading `CYCLEBEAT_ROADMAP.md` §2.7**, which is
where the database split actually lives and which assigns transactional persistence to
**Postgres, in phase 4**:

> **Postgres** = transactionnel : `sessions`, `feedback`, état app (écriture fiable, fin de
> l'actuel best-effort `try/except pass`). **DuckDB** = entrepôt analytique : lake → DuckDB →
> dbt (staging→marts), copilote warehouse. Le pipeline ingère les données transactionnelles
> Postgres dans l'entrepôt pour l'analytique (`fct_session`, `mart_feedback_summary`).
> **Impact phases :** Postgres transactionnel s'ajoute en **phase 4**.

The two systems answer different questions and ADR-008 collapsed them into one:

- **OLTP** — a session was generated, a rider rated it. Small, frequent, transactional writes
  that must not be lost. DuckDB is a poor fit: it is single-writer by design, which is why the
  DAGs already carry `max_active_runs=1` and why the API and `make dbt` contend for the file.
- **OLAP** — how much of the catalogue resolved, which source has the worst coverage, what the
  confidence distribution is. That is the lake → dbt → marts → copilot chain, and it is the
  differentiator of this project. It stays on DuckDB.

Course context, since criterion 7 grades this: Module 3 teaches SQLite → **Postgres** as the
application's transactional store. Having both, with an ingest from one into the other, is the
realistic OLTP+OLAP architecture rather than a compromise.

## Options

| Option | Behaviour | Cost |
|---|---|---|
| **A — separate the roles** (chosen) | Postgres for `sessions` / `feedback` / app state; DuckDB stays the analytical warehouse; the pipeline ingests Postgres into the warehouse | +1-2 days, two stores to run |
| B — replace DuckDB with Postgres | One store, simplest ops | **Destroys the DE differentiator**: the lake → dbt → marts → copilot chain and every phase-2 deliverable would have to be rebuilt, and the warehouse story that criterion 7 and the copilot rest on disappears |
| C — DuckDB only, multi-env documented | No new dependency; what ADR-008 shipped | §2.7 calls this the "alternative minimale": it *passes* criterion 7 on the generic 2026 wording, but tells a weaker story, and it leaves the single-writer contention between the API and `make dbt` unresolved |

Option A, as §2.7 recommends. Option C is what ADR-008 chose, and it is defensible in isolation —
it is only wrong because §2.7 had already decided otherwise.

### Provider: Neon, not Render

§2.7 writes "free tier **Render**" while the phase-4 and phase-9 briefs both write **Neon**
(phase 9: "secrets Render/**Neon**"). Reading them together: **Render hosts the API, Neon hosts
Postgres.** Neon is chosen — its free tier is a managed Postgres that does not expire, whereas
Render's free Postgres is time-limited, which would break the §18 condition that the deployed
URL must be live for at least a week before submission. §2.7 is corrected in the same PR.

## Decision

1. **Postgres is the transactional store.** `sessions` and `feedback` live there. Writes are
   reliable and raise on failure — this finally closes the `try/except pass` debt E.2 recorded
   on 2026-07-28.
2. **DuckDB remains the analytical warehouse.** Lake → DuckDB → dbt (staging → intermediate →
   marts) → copilot. Unchanged by this ADR.
3. **The warehouse ingests from Postgres.** `fct_session` becomes a **warehouse** table fed from
   Postgres by the pipeline, not a table the API writes. `raw.feedback` likewise. The API owns
   no DuckDB table.
4. **Local = a `postgres` container in compose. Production = Neon free tier.** The connection
   string is a secret: `.env` only, never committed (E.0.5), with `.env.example` documenting the
   variable.
5. **Zero cost is preserved** (E.8): a container locally, Neon's free tier in production.

## Consequences

- **ADR-008 is superseded, not deleted.** Its `session_id` rekeying of feedback and its rule that
  all SQL lives in `api/repositories/` both survive — only the *store* changes. Its migration
  note about the v1 `feedback` table becomes historical, since that table stops being the API's
  concern.
- **`DEMO_MODE` must still work with no Postgres running.** E.8 requires the project to run with
  no key and no service on a clean clone, and criterion 14 is tested from one. The repository
  layer therefore needs a degraded path — a clear failure or an in-memory store — rather than
  making a database a hard prerequisite for reading the demo. **This is the main risk this ADR
  introduces** and phase 4 must answer it explicitly.
- **The feedback rating vocabulary needs a mapping, and now has a place for it.** The API speaks
  E.3's `up`/`down`; the normative dbt chain (`stg_feedback` → `int_feedback_enriched` →
  `mart_feedback_summary`) classifies `Great`/`Okay`/`Hard` and its `check_invalid_rating` test
  fails on anything else. With the API writing Postgres and the pipeline ingesting into the
  warehouse, the **ingestion boundary** is where that translation belongs — instead of the API
  writing a vocabulary the warehouse rejects, which is what ADR-008 shipped.
- **Two stores to run**, and a second connection to configure in compose, CI and Render. The
  integration suite (phase 8) gains a Postgres service.
- **ADR-003 is reinforced.** "No Render disk" was already the rule; moving transactional state to
  a managed Postgres removes the last reason to want one.
- **A new dependency** (`psycopg`) enters the backend, justified by this ADR per E.0.5.
- **Reversible at a cost.** The warehouse side is untouched, so reverting means pointing the
  repositories back at DuckDB — which is precisely ADR-008, and precisely why that ADR is
  superseded rather than erased.

## References

- `docs-notes/CYCLEBEAT_ROADMAP.md` §2.7 (the decision this ADR formalizes), §2.3 (the
  single-writer hardening, now scoped to the analytical store), §2.6 (criterion 7).
- `docs-notes/CYCLEBEAT_PLAN_V3.md` E.2 (the `try/except pass` debt and the `raw.feedback`
  contract), E.3 (the session endpoints), E.8 (zero cost), §15 phases 4, 8 and 9.
- `docs/adr/adr-008-session-persistence.md` (superseded).
- `docs/adr/adr-003-render-no-disk.md` (no persistent disk in production).
