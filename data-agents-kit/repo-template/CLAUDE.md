# CLAUDE.md — Analytics & Data Engineering

Behavioral guidelines for working on data code: ingestion, pipelines, dbt models, SQL, analytics, BI, tracking. Merge with project-specific instructions as needed.

Tradeoff: these rules bias toward caution over speed. A wrong number shipped to a stakeholder costs more than a slow answer.

Stack: likely GCP + dbt. GCP-specific rules are marked [GCP] — apply on BigQuery, translate the principle otherwise.

## 0. Project Context — Read First

Tribal knowledge lives in `.claude/skills/analytics-engineer/references/` and takes precedence over any generic rule below:

- `warehouse.md` — stack, schemas, key tables with grain and freshness SLAs, upstream sources.
- `metrics.md` — the ONLY source of truth for business definitions. A metric not defined there does not exist: ask the business owner, get it added, then build. Never invent a definition.
- `conventions.md` — naming, layer structure, SQL style, minimum tests.
- `pitfalls.md` — known traps (duplicates, timezones, dead tables, flaky jobs). Check it BEFORE debugging; add to it after every incident or reusable human correction.

If these files are empty or missing for the topic at hand, say so explicitly and ask before doing non-trivial work.

## 1. Think Before Coding

- State your assumptions explicitly (grain, filters, time window, timezone, dedup logic). If uncertain, ask.
- If multiple interpretations of a metric or request exist, present them — don't pick one silently.
- Read the existing models/queries before writing new ones. Reuse existing definitions; don't create a parallel version of a metric that already exists.
- If a simpler approach exists, say so. Push back when warranted.

## 2. Simplicity First

- Minimum code that solves the problem. No speculative features, abstractions, or configurability.
- No new dependencies or tools when SQL, the stdlib, or an existing package does the job.
- SQL before Python: if a transformation can live in the warehouse, it lives in the warehouse.
- Batch before streaming: streaming only for a demonstrated latency need, not because it's modern.
- Match the existing project structure and naming conventions instead of inventing your own.

## 3. Surgical Changes

- Touch only what the request requires. Don't refactor, reformat, or "improve" adjacent models.
- Every changed line should trace directly to the user's request.
- Remove orphans YOUR change created; leave pre-existing dead code alone (mention it instead).

## 4. Data Contracts

Schemas are interfaces. Treat them like APIs.

- Never rename, retype, or drop a column consumed downstream without identifying the consumers first. Assume every exposed column has a consumer.
- Breaking changes require: impact analysis (who reads this?), a migration path, and explicit sign-off. Not a silent edit.
- Validate at boundaries: incoming data gets schema/type/nullability checks at ingestion, not deep inside transformations.
- Grain is part of the contract. State the grain of every model in one sentence. If you can't, the model isn't done.
- Enforce contracts on marts consumed outside the team (dbt model contracts: enforced types + constraints).

## 5. Reliability of Numbers

A query that runs is not a query that's right. Never present a figure you haven't challenged.

- Reconcile against a known reference: source system, certified dashboard, previous period, back-of-envelope estimate. Unexplained gaps block delivery.
- Run sanity checks: row counts before/after joins (fan-out kills silently), duplicate rate on the primary key, null rate on key columns, totals vs. sum of segments, order of magnitude.
- State the definition with the number: filters, period, timezone, inclusion/exclusion rules. A number without its definition is not a result.
- Distinguish explicitly: observed in the data / interpreted / assumed / uncertain.
- If the data can't answer reliably (missing history, broken tracking, small sample), say so. Don't fill the gap with a plausible-looking number.

Close, as-of & restatements:
- Distinguish event time from processing time. Late-arriving data means "yesterday's number" changes if recomputed — decide per report, explicitly: living metric (always recomputed) or frozen at close.
- Figures that feed official reporting (finance, board, external) get a **close**: a declared cutoff (e.g. D+3 after month-end) at which the period's numbers are snapshotted into an immutable as-reported table (`period, metric, value, published_at`). Recomputing history must never silently change what was reported.
- The close is gated: it passes only if the anomaly/reconciliation suite passes (see §11). A failed close blocks publication — no silent "provisional" numbers. Late upstream data at cutoff is an explicit decision: delay the close or close with a documented gap.
- After close, corrections are **restatements, not overwrites**: keep both versions queryable (as-reported vs as-restated), document what changed, why, and the magnitude, notify consumers, annotate the affected dashboards.

Analysis rigor:
- Before attributing a trend to a cause, rule out the usual suspects: seasonality, mix/composition effects (Simpson's paradox), selection and survivorship bias, tracking changes, volume shifts between segments.
- A published analysis is reproducible: versioned query/code, stated as-of date. "I can't rerun it" means it doesn't exist.

Experiments (A/B tests):
- Metrics, guardrails, MDE, and duration are fixed before launch. No peeking, no early stopping without a sequential method.
- Randomization unit = analysis unit (user-randomized ⇒ user-level analysis). Mismatches inflate significance.
- Every experiment gets a written readout — decision, result, confidence, surprises — especially when the result is null.

## 6. Data Security & Privacy

Secrets:
- Never commit secrets, credentials, or connection strings — in code, config, YAML, or notebook cells.
- `.env` pattern: `.env` in `.gitignore`, a committed `.env.example` with the same keys and dummy values. Code reads config from environment variables (dbt: `env_var()` in profiles, never a hardcoded password).
- Secret scanning in pre-commit AND CI (gitleaks/trufflehog). Don't rely on humans spotting a key in review.
- Git history is forever: a secret committed then deleted is still leaked. Rotate it immediately; cleaning history (BFG/filter-repo) comes second.
- CI/CD secrets live in the runner's secret store (GitHub Actions secrets, Secret Manager) — never in workflow YAML or logs. Mask them in job output.
- Prefer keyless auth over long-lived credentials. [GCP] Workload Identity Federation for CI, ADC locally, Secret Manager for the rest; exported service-account JSON keys are a last resort with rotation and expiry.
- One service account per pipeline/environment — no shared credentials, no personal accounts running prod jobs. Rotate anything long-lived; audit access regularly.

Data:
- `.gitignore` covers data files too: `*.csv`, `*.parquet`, `*.db`, dumps, dbt `target/` and `logs/` (compiled SQL can embed literals). Data in git is both a leak and a repo-size bug.
- Treat PII as radioactive: don't SELECT it unless required; keep it out of logs, exports, seeds, test fixtures, screenshots, error messages, and LLM/third-party tools. [GCP] Policy tags / column-level security and authorized views over copying "clean" subsets around.
- Notebooks leak: outputs embed query results. Strip outputs before commit (nbstripout) or keep notebooks out of the repo.
- No production data copied into dev/notebooks/local files without an explicit reason and cleanup plan. Masked or synthetic data for dev when the real values don't matter.
- Least privilege: read-only unless the task requires writes. [GCP] Scoped IAM per dataset, no project-level Editor; audit logs enabled on sensitive datasets.
- Encryption in transit and at rest everywhere (warehouse defaults cover it — the gap is usually exports: files on laptops, buckets public by mistake, unencrypted dumps).
- GDPR: deletions propagate (if you build a table with user data, ask how deletion requests reach it); retention limits declared per dataset. [GCP] Table/partition expiration where a retention rule exists.

## 7. Governance & Ownership

- Every table, model, and metric gets an owner, a description, and a documented definition. Undocumented tables are future incidents.
- No shadow metrics: if "revenue" or "active user" is already defined, use it or explicitly flag the divergence — never a third silent variant.
- Respect lineage: know what feeds your model and what it feeds. If you can't draw it, map it before changing anything.
- One-off analyses that stakeholders reuse get promoted to owned, tested models — or clearly labeled disposable. No zombie `temp_` tables serving dashboards.
- [GCP] Label datasets/tables (owner, layer, pii); separate datasets per layer.

## 8. Ingestion, Jobs & Orchestration

ELT, not ETL: land first, transform in the warehouse.

- **Raw is immutable and append-only.** Land data as-is; no cleaning, no renaming, no filtering at ingestion. Add load metadata to every row: `_loaded_at`, source identifier, batch/file id.
- **Extraction jobs are resumable and idempotent**: checkpoint progress, handle pagination and rate limits explicitly, and make retries safe (re-extracting a window must not duplicate rows downstream).
- **Schema drift is expected, not fatal**: ingestion tolerates new columns; contract tests catch and flag them. A renamed or dropped source column must fail loudly at staging, not propagate NULLs silently.
- Late and out-of-order data is the norm: design windows and dedup logic assuming it.
- CDC/incremental extraction over full reloads once volume justifies it — but keep a documented full-reload path for recovery.
- Columnar formats (Parquet/Avro) for files; no CSV as a pipeline interface if avoidable. [GCP] Prefer native/external BigQuery loads over hand-rolled loaders.
- Incremental extraction tracks an explicit, stored watermark (high-water mark) — never inferred from wall clock.
- Assume at-least-once delivery: dedupe downstream on natural keys. Never design around "exactly once".
- Bad records go to quarantine/dead-letter with a reason. Dropping them silently is data loss; blocking a whole batch for one row is an outage. Pick per pipeline, explicitly.
- Detect hard deletes in sources: a row disappearing upstream must not live forever in your warehouse.

Orchestration:
- Every job takes an execution date/window as a parameter — backfillable by design. No hardcoded `yesterday` evaluated at runtime.
- Dependencies are explicit in the DAG. No timing coupling ("B runs 2h after A and hopes").
- Retries with backoff for transient failures only — a logic error retried is still a logic error.
- Store UTC, convert at presentation. Name the timezone in every date-based definition.
- Orchestrator files stay thin: DAG definitions are config; heavy logic lives in tested code the DAG calls.
- Explicit catchup/backfill policy per DAG — an accidental catchup over a year of missed runs is an incident.
- Sensors and external waits have timeouts and a failure path. Nothing waits forever.

## 9. SQL & Modeling Standards

Layered architecture, one direction of flow:

- **raw/source**: untouched ingested data. Never queried by end users.
- **staging (`stg_`)**: 1:1 with sources — rename, cast, dedupe. No joins, no business logic.
- **intermediate (`int_`)**: reusable business-logic building blocks. Not exposed to consumers.
- **marts (`fct_`, `dim_`, `mart_`)**: consumption-ready, business-named, documented, tested. Dashboards read ONLY from here.

SQL rules:
- Business logic lives in exactly one place. Two models computing the same thing → extract it.
- CTEs over nested subqueries; one logical step per CTE, named for what it does. Import CTEs first, `final` last.
- No `SELECT *` in models. Explicit columns, or a contract you can't keep.
- Qualify every column with its table alias in joins. No implicit casts — cast explicitly.
- `DISTINCT` is not a dedup strategy — it's a symptom. Find the fan-out, fix the join or the grain.
- Deterministic outputs: same inputs → same result. No wall-clock logic buried in transformations.
- Naming: snake_case; booleans `is_`/`has_`; timestamps `_at` (UTC); dates `_date`; monetary columns carry currency (`amount_eur`).
- Currency conversions use a declared rate table with an as-of date — never a hardcoded rate. State which rate the metric uses (daily close, monthly average).
- Lint enforced (sqlfluff or project standard) — formatting is not a review topic.

Correctness footguns:
- NULL semantics are documented per column: unknown vs not-applicable vs zero. Never let `COALESCE(x, 0)` silently turn "unknown" into "zero".
- `NOT IN (subquery)` with a NULL in the subquery returns nothing — use `NOT EXISTS`.
- Guard divisions ([GCP] `SAFE_DIVIDE`) — but treat divide-by-zero occurrences as a data question, not just an error to silence.
- Half-open time intervals: `>= start AND < end`. Never `BETWEEN` on timestamps.
- Joins on nullable keys silently drop rows. Check nullability before joining.
- Published counts use exact `COUNT(DISTINCT)`; `APPROX_` variants are for exploration only, and labeled as such.

Dimensional modeling (marts):
- Facts = events/measures at a stated grain; dimensions = context. Don't let dimension attributes accumulate inside fact tables.
- Surrogate keys are deterministic hashes of the natural key (e.g. `generate_surrogate_key`); document the natural key.
- Know each measure's additivity: revenue sums; stock levels and balances don't (semi-additive — period-end or average, chosen deliberately).
- Conformed dimensions: one `dim_customer` shared across marts, not one variant per team.
- Many-to-many relationships go through a bridge table, not a fanned-out join.
- SCD handling is chosen per dimension, explicitly: type 1 (overwrite) or type 2 (history via snapshots) — and documented.

Python (pipeline code):
- Pinned, locked dependencies (uv/poetry + lockfile). A pipeline that breaks on `pip install` day is self-inflicted.
- Small pure functions for transforms, typed signatures, unit tests. Notebooks are for exploration — never a production job.
- Structured logging with context (job, batch id, row counts in/out); no bare `print`. Config from env vars, not edited constants.
- pandas is fine for small data; past memory limits, push the work back to the warehouse instead of chunking around it.

## 10. dbt Standards

- `ref()` and `source()` only. A hardcoded table name in a model is a bug.
- **Sources**: every external table is declared in a source with `loaded_at_field` and freshness thresholds. Source freshness runs in prod and alerts.
- **Materializations**: `view` by default; `table` for heavy consumption; `incremental` only for measured need. Incremental models require a `unique_key`, a late-arriving-data lookback window, and a documented full-refresh path.
- **Seeds**: only for small, static, business-owned reference data (mappings, country codes, targets/budgets). Never facts, never PII, never anything that changes often — if it changes monthly, it's a source, not a seed. Every seed has declared column types in YAML, tests on its key, and an owner.
- **Macros**: extract logic repeated 3+ times; don't macro-ify one-offs. Document arguments. A macro nobody can read is worse than duplication.
- **Snapshots** for slowly changing dimensions when history matters — don't rebuild SCD logic by hand.
- **Exposures** declared for every dashboard/app consuming marts, so impact analysis (`dbt ls --select +exposure:X`) actually works.
- **Versions pinned**: dbt version and every package in `packages.yml` pinned exactly. Upgrades are deliberate, reviewed PRs — not surprises on the next run.
- Third-party dbt packages run with YOUR warehouse permissions. Review before adding; prefer maintained, widely-used ones.
- Keep Jinja minimal: if the compiled SQL is unreadable, the model is unmaintainable. Compile and read it when in doubt.
- Protect expensive incrementals from accidental rebuilds (`full_refresh: false`) with a documented deliberate override.
- Make visibility explicit: model `access`/groups for private vs public, `meta: owner` on every mart.
- Docs are code: every model has a description; every mart column that isn't self-evident is documented. `dbt build` is the standard command (run+test interleaved, fails fast per model).

## 11. Tests — the Required Matrix

Test what protects a decision. PK tests are non-negotiable; the rest is judgment.

Minimum by layer:
- **Sources**: freshness + volume plausibility.
- **Staging**: `unique` + `not_null` on the primary key. Always. A model without a tested PK is unfinished.
- **Marts**: PK tests + `relationships` (no orphan foreign keys) + `accepted_values` on enums + at least one singular test encoding a business rule ("no negative order totals", "conversion rate ≤ 1", "daily totals match staging source").
- **Complex logic** (window functions, regex, date edge cases, currency conversion): dbt unit tests with fixed inputs/expected outputs — test the logic without touching the warehouse.

Rules:
- Severity is deliberate: `error` blocks, `warn` must be reviewed weekly. A warn nobody reads gets deleted or promoted.
- Never weaken a test, hardcode an expected value, or filter out failing rows to go green. A failing test is information.
- On every PR touching a model: data diff vs production (row counts, key aggregates, changed rows) posted in the PR. "Compiles and tests pass" ≠ "numbers unchanged where they should be".
- Scheduled cross-system reconciliation on critical flows (source counts/sums vs warehouse): schema tests can't catch a silently missing day.
- Monitor distributions, not just constraints: volume, null-rate, and metric anomaly detection on critical marts (elementary or equivalent).
- Flaky tests are bugs: a test failing intermittently gets fixed or deleted this week — not snoozed indefinitely.

Where check results live:
- Every run persists its outcomes to **audit tables in the warehouse** (dedicated `audit`/`meta` dataset): run_id, model, test, status, failed-row count, executed_at. Elementary or equivalent does this out of the box.
- `store_failures` on: the actual failing rows land in the audit schema with a retention policy — so a failure can be investigated after the fact, not just observed.
- dbt artifacts (`run_results.json`, `manifest.json`) are archived per run (bucket/GCS): they are both the state for slim CI and the raw material for quality trending.
- This history is itself data: trend it (which models fail often, is quality degrading, how long do closes take). Data quality gets a dashboard like any other domain.

## 12. Performance & Cost

Warehouses bill for what you scan. Cost is a correctness concern.

- Estimate before you run: dry-run / bytes-scanned check on anything non-trivial. `LIMIT` does NOT reduce BigQuery scan cost — partition filters do.
- [GCP] Set `maximum_bytes_billed` as a guardrail on dev and ad hoc queries: a typo should error, not scan 2 TB.
- [GCP] Partition big tables (usually by date), cluster by frequent filter/join keys, `require_partition_filter` where sensible.
- Filter early, join late: reduce rows before joining. Know the cardinality of both sides before writing a join.
- Materialize expensive reused logic once instead of recomputing it in five dashboards. [GCP] Materialized views / scheduled tables for hot paths.
- Deep view-on-view chains recompute everything at query time — measure, then materialize the bottleneck.
- Don't optimize what isn't slow or expensive. Measure first.

## 13. Environments & Targets

Four targets, strict separation. Humans never write to prod.

- **dev** — personal schema per developer (`dev_<user>`). Default working target. Limit data volume (e.g., last N days via a variable) to keep iteration fast and cheap. Disposable at any time.
- **preview** — ephemeral schema per PR, built by CI (`pr_<number>`). Only modified models + downstream, deferred to prod state for the rest. Reviewers query it to validate outputs. Dropped automatically on merge/close.
- **staging** — permanent mirror of prod: same sources, full data, prod-like scheduling. Catches what dev's sampled data can't (volume, performance, freshness). Release candidates run here before prod.
- **prod** — written ONLY by the CD pipeline / scheduler service account. No human write access, no manual runs except break-glass with a documented reason.

[GCP] Separate projects (or at minimum datasets + service accounts) per environment; dev/preview get billing quotas so a bad query can't burn the budget.

## 14. CI/CD

Pipeline, in order:

1. **Pre-commit**: sqlfluff lint/format, YAML validity, no secrets.
2. **CI on PR**: compile → `dbt build --select state:modified+ --defer --state <prod-manifest>` into the preview schema → data diff summary posted to the PR. Slim CI: never rebuild the whole project for a one-model change.
3. **Review**: small PRs with stated intent — what changed, why, what was verified, who is impacted. At least one reviewer for anything touching marts or contracts.
4. **Merge to main** → deploy to staging, full build + all tests.
5. **Release/tag** → deploy to prod via CD. Persist the run artifacts (manifest as state for slim CI, run_results to the audit store per §11).
6. **Rollback story exists before deploy**: revert the PR and redeploy, or repoint to the previous artifacts. If you can't roll back, you're not done.

Rules:
- All transformation code lives in git. No logic that exists only in a console, a saved query, or a dashboard's custom SQL.
- CD is the only path to prod. A hotfix goes through the same pipeline, just faster.
- Scheduled prod runs use `dbt build`; failures alert a human who acts (see §16).
- No destructive warehouse operations (DROP, DELETE without WHERE, overwriting prod tables) without explicit confirmation.
- Branch protection on main: no direct pushes; required review + green CI to merge. Applies to everyone, including admins.
- Prod publishes follow Write-Audit-Publish where practical: build into a staging area, run audits, then swap/publish atomically. Consumers never see a half-built table.
- Dependencies (Python packages, dbt packages, CI actions) pinned via lockfiles and updated through reviewed PRs (dependabot/renovate) — supply chain is part of the pipeline.

## 15. DataOps — Infrastructure, Cost & Lifecycle

- **Infrastructure as code**: datasets, IAM, schedules, quotas, alert policies live in Terraform (or the project's IaC), not in console clicks. A resource created by hand in prod is a bug. [GCP] That includes BigQuery datasets, scheduled queries, and service accounts.
- **Runbooks**: every production pipeline has one — what it does, how to rerun/backfill it, known failure modes, who to escalate to. If the on-call person can't fix it at 8am without the author, it's not done.
- **Cost is monitored, not discovered**: budgets + alerts per environment; queries and jobs labeled so cost is attributable (team, pipeline, dashboard). Review top costs monthly; a dashboard nobody uses that costs money gets deprecated.
- **Deprecation is a process, not a DROP**: announce with a deadline → check usage in query logs → dual-run or redirect consumers → archive, then delete. Applies to tables, dashboards, and events alike.
- **Blameless postmortems** for data incidents: timeline, root cause, action items with owners. The output is a prevented recurrence (a new test, contract, or alert), not a culprit.
- Keep the catalog true: stale documentation is worse than none — fix docs in the same PR as the change.
- **Disaster recovery is tested, not assumed**: know the restore path (time travel, snapshots, re-ingestion from raw) and its limits — and exercise it once. [GCP] BigQuery time travel is ~7 days; decide what needs snapshots/exports beyond that.
- **Raw retention IS the recovery story**: as long as raw is kept, everything downstream is rebuildable. Never let a cleanup or retention job break that assumption silently.
- Environment parity: staging differs from prod only in data volume and permissions — never in code, config, or engine version.

## 16. Observability, Freshness & Incidents

- Every production pipeline has: failure alerting to a human who acts, freshness checks on outputs, and volume anomaly detection (0 rows and 10x rows are both incidents).
- Freshness is a promise: each mart has a stated SLA ("available by 8am, data through yesterday"). Consumers can see freshness, not guess it.
- Alerts must be actionable — a muted alert channel is worse than none. If an alert fires twice with no action, fix the alert or the pipeline.
- Incident on published numbers: fix forward, backfill if needed, notify consumers of what was wrong and for how long. Silent corrections destroy trust.

## 17. Semantic Layer & BI Consumption

The last mile is where trust is won or lost.

- Metrics are defined once, centrally (semantic layer, metrics YAML, or the marts themselves) — dashboards display metrics, they don't compute them. No business logic in dashboard custom SQL or BI formulas.
- Two tiers of dashboards, visibly distinct: **certified** (owned, tested, SLA'd, connected to marts) and **exploratory** (clearly labeled, disposable). Never let an exploratory dashboard drive a recurring decision silently.
- Dashboard sprawl is debt: before building a new dashboard, check if an existing one answers the question. Audit usage quarterly; unused dashboards get deprecated (per §15).
- Use a date spine for time series — missing days must show as gaps or zeros by decision, not disappear.
- Every dashboard answers a stated question for a stated audience and has an owner. A dashboard that needs a verbal explanation to be read correctly isn't finished.
- Deliver analyses conclusion-first: the answer, the confidence level, the caveats — then the method. Stakeholders decide; they don't re-derive.
- Metric definition changes are versioned events: announce them, date them, annotate the dashboards. A KPI that silently changes definition invalidates every past decision made on it.
- Maintain a business glossary: one place where each certified metric's definition, owner, and caveats live — linked from the dashboards that display it.
- Intake discipline: every request maps to a decision — "what will you do differently depending on the answer?". No decision identified → point to the existing certified asset or timebox the exploration explicitly.

## 18. Tracking & Instrumentation

- Follow the existing event taxonomy. Don't invent event/property names ad hoc.
- Never rename or repurpose an existing event/property silently — version or add, don't mutate.
- New tracking ships with: a spec (trigger, properties, types), an owner, and verification that events arrive as specified (real-session test, volume check after release).
- Before interpreting tracked data, check instrumentation health: gaps, volume drops, duplicates, bot traffic. A trend in the data may be a trend in the tracking.

## 19. Bug Loop — Reproduce, Fix, Verify at the Data Level

Fixing data code means fixing the data, not just the code.

1. Reproduce: isolate a minimal failing case (specific rows/dates/segment). Don't fix blind.
2. Diagnose: root cause in the lineage — upstream data issue, logic bug, or contract break. Fix the cause, not the symptom.
3. Fix: with a test that would have caught it.
4. Verify at the data level: row counts, totals, affected segments before/after. Code review passing ≠ numbers correct.
5. Backfill: decide explicitly whether history must be corrected; say what stays wrong if not.
6. Communicate: if wrong numbers were consumed, notify the consumers.

## 20. Verify, Don't Claim — Fail Loudly

- Never say "done" or "correct" without evidence: tests run, checks executed, reconciliation shown. If you can't run it, say so.
- No silent fallbacks: no COALESCE/fillna/default masking missing data, no try/except letting a pipeline "succeed" with partial data. Partial success is failure.
- If you don't know, say "I don't know". Don't fabricate table names, column semantics, or business rules.


## 21. Reverse ETL & Data Activation

Data flowing back into operational tools (CRM, ad platforms, email) is a production interface.

- Export models live in `marts/exports/` and stay thin: rename, cast, filter. Business logic stays in the marts — never duplicated in an export model or in the sync tool.
- Every sync is declared as an exposure (destination, owner, criticality) so impact analysis covers operational tools, not just dashboards.
- Data minimization: sync only the columns the destination needs. PII leaves the warehouse only with a documented purpose and, where possible, masked or tokenized.
- Sync failures alert like pipeline failures. A stale audience in an ad platform or an outdated score in the CRM is an incident, not a detail.
- The warehouse stays the source of truth. Never let a destination tool "correct" values that flow back upstream.

## 22. Operating Rules for AI Agents

Applies to Claude Code, Codex, and any subagent working on this repo.

- Agents write code, not production data. Prod warehouse access is read-only; every change lands as a PR; a human merges. An agent never merges its own PR, and agent-on-agent review never replaces human review.
- One service account per agent, least privilege, every action logged and attributable. Enforce via IAM and `.claude/settings.json` permissions — instructions alone are not a guardrail.
- No closed loop anomaly → auto-fix. The chain is: detect → diagnose (cite queries) → classify the cause → human decides → fix as PR. Exception: an explicit whitelist of trivial, reversible fixes — with a circuit breaker: the same auto-fix applied 3 times in a week means stop and escalate (it is a root cause, not an incident).
- Never "fix" a model to make a failing test pass when the cause is upstream or business-side — that produces wrong data with green tests.
- Agent-triggered builds are state-aware (`dbt build --select state:modified+ --defer`). Never full project rebuilds.
- Destructive operations (DROP, DELETE without WHERE, TRUNCATE, `--full-refresh` on protected incrementals) require explicit human confirmation, enforced by deny rules/hooks — not by politeness.
- Reusable human corrections get written into `pitfalls.md`, `conventions.md` or `metrics.md` — feedback that is not capitalized is lost at the next session.
- A documented, tested kill switch exists (disable the trigger label / cron). If you cannot switch the agents off in one action, do not run them.

---

These guidelines are working if: numbers ship with definitions and checks, schema changes stop breaking consumers, every PR shows a data diff before merge, prod is written only by CD and IaC, pipelines are idempotent and backfillable, cost is attributable, dashboards trace to certified marts, bugs are verified fixed in the data — not just in the diff, and agents propose while humans decide.
