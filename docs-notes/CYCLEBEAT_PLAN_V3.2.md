# CYCLEBEAT V3.2 — ULTRAPLAN (BONUS layer on top of V3.1)
## DE pipeline + agentic layer — "depth & portfolio" extension (blind spots + 3 priorities)

> Version: 3.2 — July 2026
> **Extends** CYCLEBEAT_PLAN_V3.1.md (does not replace it). V3.1 is kept **in full**, including D1–D8.
> V3.2 adds **no** change to the *core*: it adds an **optional bonus layer** (modules B1–B6), activated
> **after** the core is submitted.
> Goal: fill the identified blind spots and execute the 3 priorities, for a strong
> **Data Engineer / Analytics Engineer with LLM & agentic** signal — without breaking the zero-cost
> constraint or the scope control that saved the project from the v1 trap.

---

## EXECUTION STATUS — updated 2026-07-29

> **Mutable state, not plan content.** This section records where execution actually stands; the
> rest of this file is the bonus specification and does not change with it. It sits here because
> §0 rule 3 gates every bonus module on core progress — in particular 3(b), *"the source spike
> (phase 1) is green"*. Verified against `origin/main` = `6e8039f`, not from memory.

### 🔴 Bonus gate: CLOSED — no B-module may start

| §0 rule 3 condition | State |
|---|---|
| (a) V3.1 core deployed, live, tested from a clean clone | ❌ Not started — phases 2–11 are untouched |
| (b) Source spike (phase 1) green | ❌ **Tooling shipped, measurement not run** — see below |
| (c) `homebarista Track 1` closed | ❓ Out of this repo's scope, not verifiable here |

### Done

| Phase | State | Evidence |
|---|---|---|
| **0. Purge & setup** | ✅ **DONE**, exit criteria met | v1 bricks purged (Spotify/Qdrant/LangGraph/Dash); `spotipy\|qdrant\|langgraph` grep over `api db ingest` empty on `origin/main`; secret hygiene verified, not assumed (`.env` never tracked); CI `build` **success** on `main`; ADR-001/002/003 committed. PRs #3, #4. |
| **1. Source spike** | 🟡 **OPEN** — tooling merged, **measurement not run** | PR #7 merged: `tools/spike/` (PEP 723 script + stdlib-only E.2 core), 46 unit tests, 3 committed fixtures, runbook, report skeleton. **§15 exit criterion — "rapport chiffré" — is NOT met.** |

Cross-cutting, outside the phase numbering:

- **Truth-source chain repaired** (PR #5). `CLAUDE.md` named `docs-notes/CYCLEBEAT_PLAN_V3.md` as
  truth-source #2 while `.gitignore` excluded it: anyone cloning got the rules without the source.
  The plans, this file and `DECISIONS_SESSION_2026-07.md` are now tracked.
- **Safety net made immutable.** Annotated tag `v1-llm-zoomcamp-archive` → `c7bb63a`, pushed and
  verified on origin. The `archive/*` branch must never be swept: it reports `0 commits not on
  main` while being the only named pointer to the pre-purge tree.
- **Development environment and contributing workflow documented in the README** (PR #6).
  `make lint && make test-unit` was not runnable out of the box: Windows and WSL cannot share
  `.venv/` (`Scripts/` vs `bin/`, `os error 5` on drvfs), and the branch → PR → merge procedure
  lived only in a gitignored local note.

### Remaining — in order

1. **Close phase 1. Blocking, and it needs a human.** Per E.7 the model prepares and stops; a
   spike result is never simulated.
   - Create a free Jamendo `client_id` (**the decisive one** — it unlocks the full CC audio the
     ADR-004 floor is measured on). Optionally a GetSongBPM key, which carries a **mandatory
     backlink obligation**. Deezer needs no key.
   - Run `tools/spike/source_coverage.py` (start with a 5-case sample, E.8), commit
     `data/spike/raw_output.json`, fill `docs/spikes/phase1-source-coverage.md` from it.
   - Apply the §15 rule: **Deezer usable < 50 % → recommend the CSV + Jamendo + librosa pivot**.
     Promote ADR-004 from `Accepted (principle)` to `Accepted` with figures, or write ADR-005 if
     librosa disappoints.
2. **Phases 2–11: not started.** Nothing may start before 1 closes — §15's blocking rule.
3. **Debts to settle** (below).

### Open debts and flagged conflicts

| # | Item | Why it matters |
|---|---|---|
| 1 | **`docs/ai-workflow.md` entries missing for PR #6 and #7** | `CLAUDE.md` requires one entry per PR; it is grid criterion 2, the one most often lost by being written after the fact. Backfilled in the same PR as this status. |
| 2 | **Language conflict, unresolved** | §E.6 of V3 says *"docs en français"*; `CLAUDE.md` says *"repo docs in English"*. Resolved toward English by truth-source order (the repo as it is — 12 ADRs, README, ai-workflow are English). **The plan text was deliberately not edited**: amending a truth-source is not a side effect. Needs a decision. |
| 3 | **Truth-source #4 does not exist** | `CLAUDE.md` names `docs-notes/CYCLEBEAT_PLAN_V2.md §6-9` as truth-source #4 and E.2 says *"reprendre V2 §6 comme spec normative"*. **That file is not in the repository.** E.2 is self-sufficient, so nothing was invented — but the reference is unverifiable. |
| 4 | **Two E.2 disambiguations** carried by `tools/spike/e2.py` | E.2 is written for integers; the code handles floats. Zones are assigned on the rounded BPM (no float falls between bands), and since E.2 fixes confidence *scores* but not which value becomes `bpm_effective`, the spike takes the mean of agreeing sources and reports librosa arbitration as its own bucket rather than inventing a score. **The phase-2 resolver must settle this properly.** |
| 5 | **Merged branches not swept** | `chore/dev-env-setup`, `docs/session-2026-07-sync`, `phase-1/source-spike` all report `0` commits not on `main` and can be deleted. `archive/v1-llm-zoomcamp` reports `0` too and must **never** be deleted. |

---

## 0. NATURE OF V3.2 — READ FIRST

Three non-negotiable rules, in the senior-lead reviewer spirit:

1. **The V3.1 core (30/30) remains the absolute priority and is not touched.** V3.2 does not modify a single
   line of phases 0–11. A bonus module that would require changing the core is **rejected**.
2. **Bonuses add ZERO points to the zoomcamp** (the grid is already 30/30). They add **portfolio depth** and
   **interview signal**. So we **never** do them at the expense of submission: do them for the CV/interview, not
   for the grade.
3. **Strict gating (anti-scope-creep — the v1 lesson).** No bonus module starts until:
   (a) the V3.1 core is **deployed, live, and tested from a clean clone**; (b) the source spike (phase 1) is
   green; (c) `homebarista Track 1` is done (cross-project arbitration, V3.1 §0.4). Each bonus is
   **independent**: take 0, 1 or N depending on the job target, never "all or nothing".

Inherited execution discipline (V3.1 E.0, applies as-is to V3.2): one module = one branch + one PR; every
behavior ships its test in the same commit; one ADR per structural decision; a `docs/ai-workflow.md` entry per
session; **any paid brick = automatic rejection** (E.8).

### 0.1 What V3.2 addresses (recap of blind spots + 3 priorities)

| Gap / priority (source: course mapping) | Bonus module | Priority for your goal |
|---|---|---|
| **Priority 1 — multi-agent / orchestration** (CycleBeat gap #1, your explicit interest) | **B1** | 🎯 high |
| **Priority 2 — DE at scale: distributed batch (Spark)** (blind spot) | **B2** | 🎯 high |
| **Priority 2 — DE at scale: streaming (Kafka)** (blind spot) | **B3** | 🎯 high |
| Blind spot — **managed cloud warehouse + IaC** (BigQuery/MotherDuck, Terraform) | **B4** | ➕ medium |
| **Priority 3 — deeper eval + observability** (cross-model judge, tracing, drift) | **B5** | ➕ medium (cheap, high ROI) |
| Blind spot — **Kubernetes / ops** (K8s, K8sGPT) | **B6** | ⚪ low (only if DevOps target) |
| **More DataOps** — data reliability: quality gates, observability, freshness/anomaly, alerting, incident runbook | **B7** | ➕ medium-high (cheap, strong DataOps signal) |
| Blind spot — **orchestration *in prod*** (backfills, SLA, data contracts) | folded into **B4** / **B7** | ➕ medium |

> **Closing note.** Your very first question — *"for multi-agent orchestration, which project?"* — finds its own
> answer here: **CycleBeat, via module B1**, as a bonus *after* the core. The V3.1 single-agent copilot
> (deliberately bounded) becomes the foundation of a supervised multi-agent system.

---

## 1. BONUS TRACK OVERVIEW

| # | Module | Fills | Adds (depth) | Tools (0 €) | Effort | Mapped course |
|---|---|---|---|---|---|---|
| B1 | Multi-agent orchestration | multi-agent gap · P1 | supervisor/router, orchestrator-worker, hand-off, thread memory, per-agent tracing | LangGraph (ADR) or lightweight supervisor; same LLM | 4–6 d | Blent Agentic AI · Maven Agent Eng · Alexey |
| B2 | Distributed batch (Spark) | distributed gap · P2 | DataFrame API, joins/groupBy, partitions, shuffles, DuckDB parity | local PySpark | 3–4 d | Blent DE · DE Zoomcamp M6 |
| B3 | Streaming (Kafka) | streaming gap · P2 | producer→topic→consumer, real-time mart, Avro schemas/registry | Redpanda (compose) | 3–4 d | Blent DE · DE Zoomcamp M7 |
| B4 | Cloud warehouse + IaC | cloud gap + IaC + prod orchestration | multi-adapter dbt (BigQuery/MotherDuck), Terraform, backfills/SLA/data contracts | BigQuery free / MotherDuck free · Terraform CLI | 3–4 d | DE Zoomcamp M1/M3/M4 · Blent DE · GDE Arch |
| B5 | Eval + observability | P3 | **cross-model judge**, agent tracing, cost/latency dashboard, drift | Langfuse self-host · OpenTelemetry · Grafana · Evidently | 2–3 d | Alexey · Blent Agentic AI · GDE |
| B6 | Kubernetes + K8sGPT | K8s/ops gap | kind deploy, AI operational diagnosis | kind · Helm · K8sGPT | 2–3 d | Blent DevOps · GDE DevOps/Arch |
| B7 | DataOps / data reliability | DataOps depth · prod orchestration | blocking quality gates, observability, freshness/anomaly, alerting, slim CI, env promotion, incident runbook | Elementary · dbt · GitHub Actions | 3–4 d | Blent DE · DE Zoomcamp M4 · Alexey · GDE |

Bonus total: **~20–28 d** on top of the core's 32–40 d. **Never in parallel with the core.** Spread
post-submission, by career priority (§3).

---

## 2. BONUS MODULES — SPECIFICATIONS

Each module follows the V3.1 E.7 template (Objective / Inputs / Deliverables / Validation / Out of scope) and
inherits the D1–D8 guardrails whenever it touches the agent, the data, or the deployment.

### B1 — Multi-agent orchestration (Warehouse Copilot → supervised system) 🎯

**Objective.** Turn the single-agent copilot (V3.1 §9) into a **supervised multi-agent system**, without
sacrificing a single D1/D2/D5 guardrail.

**What it demonstrates.** Supervisor/routing · orchestrator-worker · hand-off · shared thread memory ·
termination control (caps) · **per-agent tracing modeled in the warehouse** — exactly Blent Agentic AI's
multi-agent module and Maven's orchestrator-worker/A2A patterns.

**Normative design.**
- **Supervisor** (router) receives the question, picks ONE worker, aggregates, terminates. It never runs SQL.
- **Specialized workers**, each bounded: (1) `warehouse-analyst` = the current copilot (SELECT-only, sandboxed
  connection D1); (2) `lineage-explainer` = deep `explain_track`; (3) `coaching-agent` = session generation/
  explanation. Each worker **keeps** its guardrails — security *composes*, it doesn't dilute.
- **No perimeter merging**: a worker cannot call another's tools. `trigger_resolve` stays subject to the
  out-of-band confirmation D2, **at both supervisor and worker level**.
- **Framework**: decision by ADR. Option A (pedagogically recommended) = **LangGraph**, reintroduced here
  *for good reason* (real graph: branching + shared state + N agents — which the v1 linear 3 nodes did not
  justify; ADR-B1 documents "when a graph framework becomes legitimate"). Option B = lightweight supervisor
  (function-calling) if you want to stay dependency-free. **Pick one, argue it in the ADR.**
- **Observability**: extend `fct_agent_runs` with `agent_name`, `role` (supervisor|worker), `parent_run_id`,
  `handoff_reason`. New mart `mart_agent_topology` (who calls whom, cost per agent).

**Eval & exit criteria (anti-circular, V2 §9 spirit).**
- Golden set of **12 routing questions** with the expected target worker; the supervisor routes ≥ 11/12.
- **Trajectory eval**: no unnecessary hand-offs; cost/latency vs single-agent baseline **measured and
  documented** (a multi-agent costing 3× with no gain = anti-pattern to own or fix).
- **Anti-bypass test**: a trap question must not let a worker skip its guardrails via the supervisor
  (`test_supervisor_cannot_bypass_worker_guards`).
- Runs in CI on Ollama. Output: green evals + a "single vs multi-agent: when it's justified" decision note.

**Interview pitch.** *"Supervised multi-agent system over a warehouse: a router dispatches to bounded specialist
agents, each hardened against direct AND indirect injection, with per-agent tracing modeled in SQL in the
warehouse — and a trajectory eval that proves the multi-agent brings real gain vs single-agent, not just
complexity."*

**Out of scope.** No inter-process A2A, no voice, no autonomous write agents (D2 holds).

### B2 — Distributed batch with Spark 🎯

**Objective.** Prove **distributed computing** skills — the most visible DE market gap.

**Normative design.**
- Reimplement `dag_build_warehouse` (or the heaviest aggregation) in **local PySpark** (free), writing Parquet
  the warehouse reads back — **same output contract** as the DuckDB path.
- **Scale honesty (mandatory, ADR-B2).** 40 patterns = trivial volume → Spark is *unjustified* there. So:
  generate a **large synthetic dataset** (10–50M play events / simulated resolutions) to make Spark relevant.
  The ADR sets the rule: "DuckDB by default; the Spark path is a *scale spike* proving distributed mastery,
  warranted above ~X GB". **Never claim Spark is required at the real volume** — a reviewer would see it.
- Demonstrate: DataFrame API, groupBy/join, partitioning, broadcast join, understanding of shuffles.
- Makefile target `spark-build`; optional `spark` compose profile.

**Exit criteria.** Spark job processes the synthetic 10M-row dataset; **parity test** (Spark vs DuckDB on the
small set → identical results); documented benchmark; ADR-B2 written.

**Maps** Blent DE (Spark/Hadoop), DE Zoomcamp M6.

### B3 — Streaming with Kafka/Redpanda 🎯

**Objective.** Prove **real-time** skills — the second major DE gap.

**Normative design.**
- Streaming path: a **producer** simulates live events (session telemetry / "now playing") → **Kafka topic**
  (Redpanda in compose, free, Kafka-compatible + schema registry) → **consumer** landing to the lake and
  updating a **real-time mart** (e.g. `mart_live_session` or rolling feedback).
- **Schema management**: Avro + Redpanda schema registry; a non-conforming message is rejected and counted.
- `streaming` compose profile, opt-in (the app runs without it). Kafka Streams optional; a Python consumer suffices.

**Exit criteria.** End-to-end producer→topic→consumer→mart green; Avro schema enforced (non-conforming message
rejected test); 1 `@streaming` integration test; documented (README + ADR-B3: batch vs streaming, when).

**Maps** Blent DE (Kafka + Spark Streaming), DE Zoomcamp M7.

### B4 — Managed cloud warehouse + IaC + prod orchestration ➕

**Objective.** Fill "managed cloud", "IaC" and "orchestration *in prod*" at once — all on free tier.

**Normative design.**
- **Multi-adapter dbt**: add **BigQuery** (free tier: 1 TB queries/month free) *or* **MotherDuck** (free tier)
  as an alternative target, selected by env `WAREHOUSE_TARGET`. The same dbt models build on both (this is
  precisely DE Zoomcamp M4: dbt on DuckDB **and** BigQuery). Demonstrate **partitioning/clustering** (BigQuery)
  and **query-cost awareness** (partition pruning, free-tier cap).
- **Terraform IaC** (free CLI): provision the BigQuery dataset + service account/IAM (or MotherDuck resources).
  Small, honest → fills DE Zoomcamp M1 (IaC).
- **Prod orchestration (0 € — deepen Airflow, don't add infra)**: backfills (catchup + date-partitioned runs),
  **SLA**, **cross-DAG data contracts** (freshness/row-count assertions between `resolve`→`build`).

**Exit criteria.** `WAREHOUSE_TARGET=bigquery make dbt` builds the same models on the cloud; `terraform apply`
provisions the dataset (and `terraform destroy` removes it — no residual cost); a backfill demonstrated; cost
guardrail documented. ADR-B4: local DuckDB vs cloud, when to switch.

**Maps** DE Zoomcamp M1/M3/M4, Blent DE, GDE Software Architecture (cloud, DR).

### B5 — Deeper eval & observability ➕ (cheap, high ROI)

**Objective.** Professionalize the eval/monitoring layer — priority 3, and fix a real bias.

**Normative design.**
- **Cross-model LLM-as-judge**: the judge runs on a model **different** from the generator (removes
  self-judging bias — the same flaw I flagged on homebarista). E.g. generation on Groq `qwen3-32b`, judge on a
  second free model. Methodology footnote in the README.
- **Tracing**: Langfuse (free self-host in compose) *or* OpenTelemetry + export; instrument each agent step
  (especially the B1 multi-agent).
- **Dashboard**: Grafana (free) over `fct_llm_calls` / `fct_agent_runs` (export DuckDB→Parquet/Postgres, or
  CSV/Infinity connector) → cost, latency, tool usage, cost per agent.
- **Drift**: Evidently (free) on data-quality metrics + LLM output metrics over time.
- Extend the golden set + wire B1's trajectory eval.

**Exit criteria.** Judge on a distinct model; Langfuse traces visible; **1 live Grafana dashboard**; **1
Evidently report** committed. ADR-B5: why a cross-model judge.

**Maps** Alexey (judge, Grafana, Logfire/OpenTelemetry, Evidently, LangWatch), Blent Agentic AI (eval/golden/
traces), GDE (token cost / inference profiling / data drift).

### B6 — Kubernetes deployment + K8sGPT ⚪ (optional, DevOps target)

**Objective.** The only module off your core trajectory; do it **only** if you target DevOps-adjacent roles.
V3.1 already mentioned it as "optional if time permits" — here it is scoped.

**Normative design.** Deploy the compose stack on a **local kind cluster** (free): manifests/Helm; then
**K8sGPT** for operational diagnosis (improves the crit. 13 "operational diagnosis" artifact).

**Exit criteria.** Stack runs on kind; K8sGPT diagnosis of an injected failure documented. ADR-B6.

**Maps** Blent DevOps (K8s), GDE DevOps, GDE Software Architecture (AI security/ops).

### B7 — DataOps / data reliability engineering ➕ (cheap, strong DataOps signal)

**Objective.** Make the pipeline's *reliability* first-class — the "more DataOps" you asked for.
Consolidate the DataOps threads already in the core (dbt tests, CI, mutation check, data-quality marts, B4
backfills/SLA/contracts) into an explicit, demonstrable layer, and add what's missing: blocking quality gates,
observability, anomaly monitoring, alerting, and a data-incident runbook.

**What it demonstrates.** Data reliability engineering — the discipline DE/AE roles increasingly expect:
"how do you *know* the pipeline is healthy, and what happens when it isn't?"

**Normative design.**
- **Blocking quality gates in CI** (not just warnings): beyond dbt tests, add dbt `source freshness` +
  volume-anomaly + schema-change checks that **fail** the build. Tool: Elementary Data (OSS, dbt-native) or
  custom dbt tests. A stale/anomalous source stops the pipeline, it doesn't ship silently.
- **Data observability**: Elementary produces a data-quality report (test results, freshness, volume, anomalies
  over time) + lineage, committed as an artifact (and/or surfaced in the Data Quality screen).
- **Slim CI for dbt**: state-based selection (`dbt build --select state:modified+`) so a PR rebuilds only the
  changed models — the real analytics-engineering DataOps move.
- **Environment promotion**: dbt targets `dev` (local DuckDB) / `ci` / `prod`, documented promotion flow; a
  feature branch never writes to prod.
- **Alerting (0 €)**: pipeline-failure + data-anomaly alerts via GitHub Actions notification / Airflow SLA-miss
  callback — no paid SaaS.
- **Data-incident runbook**: `docs/runbooks/data-incident.md` — triage → rollback of the warehouse image → DAG
  re-run → communication. Ties directly to the crit. 13 "operational diagnosis" artifact.

**Exit criteria.** A broken freshness/quality gate **fails CI** (proven with a deliberately stale/anomalous
fixture); Elementary report committed; slim-CI selection working on a PR; runbook written. ADR-B7.

**Interview pitch.** *"The pipeline has data-reliability SLOs: blocking freshness/volume/schema gates in CI,
an Elementary observability report, anomaly alerting, and a data-incident runbook — so a bad upstream batch
fails loudly instead of poisoning the marts silently."*

**Maps** DataOps practices (Blent DE, DE Zoomcamp M4 testing/deploy), Alexey (monitoring/observability),
GDE Software Architecture (data drift).

---

## 3. RECOMMENDED SEQUENCING (aligned with DE/AE + LLM/agentic)

Order by decreasing ROI **for your target**. Each module is an independent milestone, shipped on its branch.

1. **B1 — multi-agent.** Your #1 interest, and the agentic differentiator. Start with it.
2. **B5 — eval/observability.** Cheap, high signal, and it *tools* B1 (trajectory eval, per-agent tracing).
   B1 then B5 forms a coherent "serious agentic" block.
3. **B2 then B3 — Spark then Kafka.** The "DE at scale" gap that neither CycleBeat nor homebarista carries.
   These are what open senior DE roles.
4. **B7 — DataOps.** Cheap and high-signal; it deepens the DE core's reliability story. Do it alongside/after
   B4 (it reuses the same warehouse + dbt + Airflow). Strong interview material for AE/DE-with-reliability roles.
5. **B4 — cloud + IaC.** Rounds out the DE/AE cloud signal (BigQuery, Terraform, backfills).
6. **B6 — K8s.** Only if you pivot toward DevOps. Otherwise, skip it.

Cut rule: if time is short, **B1 + B5 + B7 + (B2 or B3)** is already a "DE/AE + agentic + DataOps" portfolio well
above average. B4/B6 are comfort.

---

## 4. GRID IMPACT & RISKS (reviewer lucidity)

- **Zoomcamp grid: +0 points.** The core is at 30/30; bonuses don't count toward the grade. Their value is 100%
  **interview/portfolio**. Never delay submission for a bonus.
- **"CV-padding" risk (Spark/Kafka).** On 40 patterns, distributed and streaming are *architecturally
  unjustified*. Without a large synthetic dataset + honest ADR, a senior reviewer reads name-dropping. → B2/B3
  **require** synthetic data and the "when it's justified" ADR. Better an honest Spark on inflated data than a
  cosmetic Spark.
- **"Gratuitous multi-agent" risk.** V3.1 itself states "orchestrated by default, agent by exception". B1 must
  **prove a gain** (trajectory eval, cost vs single-agent), otherwise it's complexity for show.
- **Scope-creep risk (the v1 trap).** Strict gating §0: nothing starts before core deployed + spike green. A
  bonus module that overflows gets **cut**, it never pushes the submission back.
- **Security preserved.** Any module touching the agent (B1) or the data (B3) **inherits D1/D2/D5**; no
  shortcut. B1 *composes* guardrails per worker — that's one more argument, not debt.

---

## 5. ZERO COST — VERIFICATION PER MODULE (extension of E.8)

| Module | Brick | Cost | Condition |
|---|---|---|---|
| B1 | Multi-agent LLM | 0 € | same Groq free / Ollama stack; per-agent caps inherited from E.4; per-caller LiteLLM budgets |
| B2 | Spark | 0 € | local PySpark; synthetic dataset generated locally; no managed cluster |
| B3 | Kafka | 0 € | Redpanda in a container (Apache-2.0); opt-in compose profile |
| B4 | Cloud warehouse | 0 € | BigQuery free tier (1 TB/month) **or** MotherDuck free; free Terraform CLI; `destroy` after demo; query-cap guardrail |
| B4 | IaC | 0 € | open-source Terraform; local state (no paid backend) |
| B5 | Tracing/dashboard/drift | 0 € | Langfuse self-host · OpenTelemetry · Grafana · Evidently — all OSS |
| B6 | Kubernetes | 0 € | local kind; OSS K8sGPT (local Ollama LLM mode or optional key never required) |
| B7 | DataOps (Elementary, gates, alerting) | 0 € | Elementary OSS dbt package; GitHub Actions notifications; Airflow SLA callbacks — no paid observability SaaS |

E.8 rule maintained: **any brick introducing a cost = automatic rejection**, free alternative or question to the
owner. The BigQuery/MotherDuck free tier is capped and `terraform destroy` documented so no billable resource is
left behind.

---

## 6. VERDICT

**V3.1 (core): unchanged, priority, to ship first.** V3.2 does not weaken it — it waits for it to be live.

**V3.2 (bonus): defensible and high career-ROI, under two conditions** — (1) strict gating (nothing before core
deployed + spike green); (2) scale honesty on B2/B3 (synthetic data + ADR, never a necessity claim). Done in
this order — **B1 → B5 → B2/B3 → B7 → B4 → (B6)** — it turns CycleBeat from "a good AI Dev Tools capstone" into a
**complete DE/AE-with-agentic-and-DataOps portfolio**: supervised and evaluated multi-agent, distributed batch,
streaming, data-reliability engineering (blocking gates + observability + incident runbook), cloud warehouse +
IaC, production observability.

Final reminder (priority zero, unchanged since the first review): **the deliverable that matters is not this
plan, it's the built repo.** V3.2 is worth nothing until V3.1 is online. Build the core, submit, deploy — *then*
open the bonus track.

---

## 7. EXPLORATORY — Live audio-capture tempo mode (out-of-grid · decision pending)

Added 2026-07-28. **Not a bonus module** (B1-B7 are DE/portfolio); this is a **product/DSP idea**
whose fate is explicitly undecided. Full write-up in root `FUTURE_WORK.md`.

**Idea.** Capture the audio playing on the machine (system loopback) and detect tempo/beats in real
time, so coaching works with **any** source (Spotify/YouTube/Deezer/local) — the source becomes
irrelevant because we analyse the waveform, not a catalogue. Sidesteps every API-deprecation and
licensing problem.

**Why it is not the core.** (1) It is **reactive, not anticipatory** — a live stream exposes only the
past, so the structured session + the −10 s pre-change alert break unless combined with a
fingerprint→metadata lookup (Chromaprint/AcoustID → MusicBrainz/AcousticBrainz). (2) It is
**orthogonal to the DE grid**: a real-time DSP capture app throws away dlt / lake / dbt / Airflow /
copilot — the very things that earn 30/30 and the DE/AE narrative.

**Stack (0 €):** loopback (`pyaudiowpatch`/`soundcard` Win · BlackHole Mac · PulseAudio Linux) +
`aubio`/`madmom`/`BeatNet`; optional Chromaprint/AcoustID.

**Three options — to be defined later (default lean = 1):**
1. **Future feature** ("Live mode") added *after* the DE core ships — keeps 30/30 intact.
2. **Separate standalone project** — a real-time DSP tempo coach, owned as DSP, not DE.
3. **Full pivot** — abandon the DE grid/plan to make this the main project; only if the career
   target shifts toward DSP/real-time.

**Gating unchanged:** nothing starts before the core V3.1 is deployed + the source spike is green.

---

## APPENDIX — ADRs to produce for V3.2

- `adr-b1-multi-agent-framework.md` — LangGraph vs lightweight supervisor; when a graph framework is legitimate.
- `adr-b2-spark-scale-threshold.md` — DuckDB by default, Spark as a scale spike; volume threshold; synthetic data.
- `adr-b3-batch-vs-streaming.md` — when streaming is warranted; Redpanda vs Kafka.
- `adr-b4-cloud-warehouse.md` — local DuckDB vs BigQuery/MotherDuck; Terraform IaC; free-tier cost guardrails.
- `adr-b5-cross-model-judge.md` — why the judge must differ from the generator.
- `adr-b6-k8s-optional.md` — why K8s is outside the core track (do only if DevOps target).
- `adr-b7-dataops.md` — data-reliability layer: blocking gates, Elementary observability, alerting, incident runbook.

*CycleBeat plan v3.2 — bonus layer — Ellie Pascaud — July 2026.*
*References: CYCLEBEAT_PLAN_V3.1.md (core, preserved), MAPPING_FORMATIONS_CYCLEBEAT.md (blind spots & priorities).*
