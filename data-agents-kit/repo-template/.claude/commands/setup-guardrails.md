---
description: Détecte les guardrails manquants (matrice P0-P2) puis les implémente par tiers, sur validation.
---

Scope: $ARGUMENTS (if empty, run detection on the entire repo).
Run Part 1 (detection) first and present the filled matrix BEFORE implementing anything from Part 2.

# Data Quality & CI Guardrails — Detection & Setup

Two parts: (1) how to DETECT which guardrails are missing in a repo, (2) how to IMPLEMENT them, in priority order. Give this to the model working in the repo, after (or with) the audit brief.

## Part 1 — Detection Matrix

For each guardrail: how to check it exists, and the risk if absent.

| # | Guardrail | How to detect absence | Risk if absent | Priority |
|---|-----------|----------------------|----------------|----------|
| 1 | Secret scanning (pre-commit + CI) | No `.pre-commit-config.yaml` with gitleaks/trufflehog; no scan step in CI workflows | Leaked credentials, silent for months | P0 |
| 2 | `.gitignore` covers env + data + artifacts | Inspect `.gitignore` for `.env`, `*.csv`, `*.parquet`, `target/`, `logs/`, `__pycache__`, `.ipynb_checkpoints` | Secrets & data in git history | P0 |
| 3 | Branch protection | `gh api repos/{owner}/{repo}/branches/main/protection` (403/404 = none); merge commits direct to main in `git log` | Unreviewed code in prod | P0 |
| 4 | CI runs tests at all | Workflows exist AND contain a test step that can fail the build (not `|| true`) | Broken code merges green | P0 |
| 5 | Lint enforced (sqlfluff/ruff) | Configs present (`.sqlfluff`, `ruff.toml`) AND wired in pre-commit/CI — config alone ≠ guardrail | Drift, unreviewable diffs | P1 |
| 6 | PK tests on every model | `dbt ls` vs models with `unique`+`not_null` on PK in schema YAML; or run dbt-project-evaluator | Silent duplicates → wrong numbers | P0 |
| 7 | Source freshness | `sources:` blocks lack `freshness:`/`loaded_at_field`; no `dbt source freshness` in scheduled jobs | Stale data served as current | P1 |
| 8 | Incremental safety | Incremental models without `unique_key`; no lookback logic; no `full_refresh: false` on big ones | Duplicates on rerun; accidental $$$ rebuild | P1 |
| 9 | Slim CI + preview schema | CI does full `dbt build` (or none) instead of `state:modified+ --defer`; no PR schema | Slow CI nobody waits for → bypassed | P1 |
| 10 | Data diff on PR | No recce/datafold/custom diff step posting to PRs | "Tests pass" but numbers changed | P1 |
| 11 | Cost guardrails | No `maximum_bytes_billed` in profiles/target configs; no billing alerts in IaC; unpartitioned big tables (`INFORMATION_SCHEMA.TABLES`) | One typo = one budget | P1 |
| 12 | Test results persisted | No elementary/`store_failures`/audit dataset; run_results discarded | Failures uninvestigable, no quality trend | P2 |
| 13 | Anomaly detection on marts | No volume/null-rate/metric anomaly checks (elementary or custom) scheduled | Schema tests pass, business numbers absurd | P2 |
| 14 | Freshness/failure alerting | Scheduler jobs without alert routing to a human channel | Failures discovered by stakeholders | P0 |
| 15 | Dependency pinning + audit | No lockfile; `packages.yml` with ranges; no pip-audit/dependabot config | Supply chain, surprise breakage | P2 |
| 16 | Close gate (if official reporting) | Published figures recomputed from live models; no as-reported snapshot table; no blocking check before publication | Restated history nobody approved | P2 |
| 17 | WAP (write-audit-publish) | Prod jobs write directly to consumed tables | Consumers read half-built tables | P2 |
| 18 | Destructive-op guards | Scripts with DROP/DELETE/TRUNCATE reachable without confirmation flag | One command, one restore drill | P1 |

Deliverable of the detection pass: this table filled with FOUND / MISSING / PARTIAL per row + evidence, before implementing anything.

## Part 2 — Implementation, in Order

### Tier 0 — Day one (hours, no infrastructure)

**.pre-commit-config.yaml**
```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks: [{id: gitleaks}]
  - repo: https://github.com/sqlfluff/sqlfluff
    rev: 3.1.0
    hooks: [{id: sqlfluff-lint, additional_dependencies: [sqlfluff-templater-dbt]}]
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks: [{id: ruff}, {id: ruff-format}]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks: [{id: check-added-large-files, args: [--maxkb=500]}, {id: check-yaml}, {id: detect-private-key}]
```

- `.gitignore`: add `.env`, `*.csv`, `*.parquet`, `*.db`, `target/`, `logs/`, `__pycache__/`, `.ipynb_checkpoints/`, `*.json` service-account patterns. Commit `.env.example`.
- If secrets found in history: **rotate first**, clean history second (filter-repo/BFG).
- Branch protection on main: required review + required CI check, include admins.
- Alert routing: pipeline failures → a channel humans read, today. Even a plain webhook beats silence.

### Tier 1 — Week one (CI backbone)

**GitHub Actions skeleton (`.github/workflows/ci.yml`)**
```yaml
on: pull_request
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pipx run pre-commit run --all-files
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}          # full history for gitleaks
      - uses: gitleaks/gitleaks-action@v2
      - run: pipx run pip-audit -r requirements.txt
  dbt-slim-ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install dbt-bigquery
      - run: gcloud storage cp gs://<artifacts-bucket>/prod/manifest.json ./state/
      - run: >
          dbt build --select state:modified+ --defer --state ./state
          --target preview --vars '{schema_suffix: pr_${{ github.event.number }}}'
      # auth via Workload Identity Federation — no JSON keys in secrets
```

- dbt targets in `profiles.yml`: `dev` (personal schema, sampled days via var), `preview` (PR schema), `prod` — credentials via `env_var()` only.
- Cost guardrail: `maximum_bytes_billed` on dev/preview targets (e.g. 100 GB) — a typo errors instead of scanning the lake.
- PK tests: add `unique` + `not_null` on every model's key. Enforce structurally with **dbt-project-evaluator** in CI (fails on untested/undocumented models) so the rule survives you.
- Nightly prod job = `dbt build` (not run-only) + `dbt source freshness`, artifacts uploaded to the bucket (they're next CI run's state).

### Tier 2 — Month one (quality depth)

- **Persist results**: install **elementary** (or equivalent) → audit dataset with test results, run durations, failed rows (`store_failures: true` on critical tests, with retention). Build the "quality of the data platform" dashboard from it: failure rate by model, close duration, flakiest tests.
- **Anomaly detection**: elementary volume/freshness/null-rate anomaly tests on the top ~10 marts; one custom singular test per certified KPI encoding a business invariant (rate ≤ 1, totals reconcile to source ±ε).
- **Data diff on PRs**: recce or custom (row counts + key aggregates, modified models vs prod, posted as PR comment). This is the single highest-leverage review aid: it turns "LGTM" into an informed decision.
- **Scheduled reconciliation**: daily source-vs-warehouse counts/sums on critical flows; alert on drift. Schema tests cannot catch a silently missing day.
- **Destructive-op guard**: wrap maintenance scripts behind an explicit `--yes-i-mean-it` flag + dry-run default.

### Tier 3 — When official reporting exists

- **WAP publish**: prod jobs build into `<table>__staging`, run the audit suite, then atomically swap (or use dbt blue/green pattern). Consumers never see intermediate state.
- **Close gate**: scheduled close job at D+N runs the reconciliation suite; on green, snapshots period KPIs into an immutable `as_reported` table; on red, blocks and pages the owner. Post-close corrections go through a restatement entry (old + new value, reason, date), never an overwrite.

## Anti-patterns to refuse while implementing

- A guardrail that can be skipped silently (`|| true`, `continue-on-error`, warn-only forever) is decoration, not a guardrail.
- Adding every possible test at once: start with PK + freshness + the 10 marts that matter. A wall of noisy checks gets muted within a month — then you have zero guardrails plus false confidence.
- CI slower than ~10 min: people will merge around it. Slim CI is a prerequisite for enforcement, not an optimization.
- Guardrails without an owner: every alert/check added must state who acts when it fires.
