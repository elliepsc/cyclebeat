---
description: Audit complet du repo — sécurité, bugs, best practices data. Rapport uniquement, aucune modification.
---

Scope: $ARGUMENTS (if empty, audit the entire repo).

# Codebase Review Brief — Security, Bugs & Best Practices

You are performing a full-codebase audit: security vulnerabilities, bugs, and best-practice violations. Assume a data stack (Python, SQL/dbt, possibly GCP/BigQuery, CI via GitHub Actions or similar), but audit whatever is actually present.

## Ground Rules

- **Report, don't fix.** This is an audit. Propose fixes in the findings; change nothing unless explicitly asked after the report.
- **Evidence or it doesn't count.** Every finding cites file + line + the offending snippet. No finding based on assumption; if you can't verify something (e.g. IAM config not in the repo), list it under "Unable to verify — check manually", don't guess.
- **No false reassurance.** "I found nothing" is only acceptable per category after showing what you searched (commands + patterns). Absence of evidence ≠ evidence of absence.
- **Read before judging.** Start by mapping the repo (languages, entry points, CI config, dependency files, dbt project structure) and state your inventory before findings.

## Required Output Format

1. **Executive summary** — 5 lines max: overall risk level, count of findings by severity, the single most urgent action.
2. **CRITICAL findings first** — anything exploitable or actively leaking. For each: What / Where (file:line) / Evidence / Impact / Fix / Effort (S/M/L).
3. **All other findings**, grouped by severity (High / Medium / Low), same format.
4. **Unable to verify** — what needs manual/console checking (IAM, bucket ACLs, branch protection, secret store contents).
5. **Prioritized action plan** — ordered list: quick wins first within each severity.

Severity rubric:
- **Critical**: exposed secret (even in git history), injection reachable from external input, PII publicly exposed or committed, destructive operation without guard, auth bypass.
- **High**: known-CVE dependency in a reachable path, PII in logs/fixtures, SQL built by string concatenation (even internal), non-idempotent pipeline that corrupts on retry, missing access control on sensitive data.
- **Medium**: unpinned dependencies, missing tests on critical logic, swallowed exceptions, hardcoded config, incremental models without unique_key.
- **Low**: style/convention violations, dead code, missing docs.

## Pass 1 — Secrets & Credentials (do this first)

Run and report the output of:
- `gitleaks detect --source . -v` (or `trufflehog filesystem .` if gitleaks unavailable; if neither installable, use the grep patterns below)
- Grep patterns: `(api[_-]?key|secret|passw(or)?d|token|private[_-]?key|BEGIN (RSA|EC|OPENSSH) PRIVATE)` case-insensitive, plus provider-specific: `AKIA[0-9A-Z]{16}` (AWS), `"type": "service_account"` (GCP SA JSON), `ghp_`, `xox[bap]-` (Slack), connection strings `://.*:.*@`.

Check:
- **Git history, not just working tree**: `git log -p` scan or gitleaks default mode. A secret deleted in HEAD but present in history is a Critical finding (rotation required).
- `.env` committed? `.env.example` present with dummy values? `.gitignore` covers `.env`, `*.json` keys, `target/`, `logs/`, data files (`*.csv`, `*.parquet`, dumps)?
- Secrets in CI workflows (`.github/workflows/*.yml`): inline values, `echo` of secrets into logs, secrets passed as CLI args (visible in process lists).
- dbt `profiles.yml` committed with credentials instead of `env_var()`.
- Notebook outputs (`.ipynb`) embedding query results, tokens, or connection strings.
- Dockerfiles/compose files with baked-in credentials; `ARG`/`ENV` leaking secrets into image layers.

## Pass 2 — Injection & Unsafe Input Handling

- **SQL injection**: any SQL built via f-string/`%`/`+` with a variable — `f"WHERE id = {x}"` — even for "internal" values. Parameterized queries or safe templating required. In dbt, check Jinja that interpolates unvalidated `var()`/env into SQL.
- `subprocess` with `shell=True` and variable input; `os.system` anywhere.
- `eval`/`exec` on any non-literal input.
- Unsafe deserialization: `pickle.load` on external data, `yaml.load` without `SafeLoader`, `torch.load` on untrusted files.
- Path traversal: file paths built from user/external input without normalization.
- For any API/web layer present: standard OWASP checks (authz on every route, no verbose error leakage, CORS wildcard, missing rate limits).

## Pass 3 — Data Security & Privacy

- PII (emails, names, phone, IP, addresses) hardcoded in: test fixtures, dbt seeds, sample files, comments, log statements, notebook outputs.
- Real data files committed (`*.csv`, `*.parquet`, `*.db`, dumps) — flag any non-trivial data file and assess whether it contains production data.
- Logging of sensitive values: grep log calls for variables named like `email`, `user`, `token`, `password`, and full-row dumps (`logger.info(df)`, `print(row)`).
- PII selected in models that don't need it; PII columns flowing into exposed marts without masking/policy tags (check dbt YAML for meta/policy tags if used).
- GDPR: any table storing user data — is there a deletion/retention path? (If not determinable from code, put under "Unable to verify".)
- Exports to third parties (external APIs, LLM calls, webhooks) sending unminimized data.

## Pass 4 — Dependencies & Supply Chain

- Run `pip-audit` (or `safety check`) / `npm audit` as applicable; report CVEs with reachability judgment (is the vulnerable path actually used?).
- Unpinned deps: `requirements.txt` without versions, missing lockfile (`uv.lock`/`poetry.lock`/`package-lock.json`), dbt `packages.yml` with version ranges instead of exact pins.
- CI actions pinned to mutable tags (`@main`, `@v1`) instead of SHAs for third-party actions.
- Abandoned/typo-squatted packages (unusual names, last release years ago).

## Pass 5 — Bugs (data-specific logic)

- **Idempotence**: pipelines using blind `INSERT`/append — rerun = duplicates. Look for missing MERGE/upsert/partition-overwrite.
- **Retry corruption**: jobs with retries whose body isn't idempotent.
- **Timezone**: naive vs aware datetime mixing, `datetime.now()` vs UTC, date truncation across timezones, hardcoded offsets.
- **Wall-clock logic**: `CURRENT_DATE`/`yesterday` computed at runtime instead of an execution-date parameter → unbackfillable, and reruns produce different results.
- **NULL handling**: `NOT IN` with nullable subqueries, joins on nullable keys, `COALESCE(x, 0)` masking unknowns, comparisons `= NULL`.
- **Join fan-out**: joins where neither side is verified unique; `DISTINCT` used to patch duplicates.
- **Boundary bugs**: `BETWEEN` on timestamps, off-by-one on date ranges, inclusive/exclusive mismatch between models.
- **Division**: unguarded division; but also `SAFE_DIVIDE` silently hiding a data problem.
- **Swallowed errors**: bare `except:`, `except Exception: pass`, try/except that logs and continues in a pipeline (partial success reported as success).
- **Race conditions**: concurrent jobs writing the same table/partition; temp tables with static names.
- **Incremental models**: missing `unique_key`, no lookback for late data, no full-refresh guard on expensive ones.

## Pass 6 — Best-Practice Violations

SQL/dbt:
- Hardcoded table references instead of `ref()`/`source()`.
- `SELECT *` in models; undocumented models; models without any test; primary keys without unique+not_null tests.
- Business logic duplicated across models; staging models doing joins/business logic; marts reading raw.
- Sources without freshness config; exposures absent while dashboards exist.

Python:
- No tests, or tests that assert nothing; `print` debugging in prod code; config as edited constants instead of env; functions >100 lines mixing IO and logic; mutable default arguments.

CI/CD & repo hygiene:
- No CI, or CI that doesn't run tests; deploy jobs without review gates; no lint config (sqlfluff/ruff) or configs present but not enforced in CI.
- Evidence of direct-to-main commits (merge history); giant PRs; generated artifacts (`target/`, `__pycache__`, `.DS_Store`) committed.
- Destructive SQL in migrations/scripts (`DROP`, `DELETE` without `WHERE`, `TRUNCATE`) without guards or confirmation.

Infra (if IaC present):
- Terraform state committed; public buckets/datasets (`allUsers`, `publicRead`); overly broad IAM (`roles/editor`, `roles/owner` to service accounts); no quotas/`maximum_bytes_billed` on dev.

## Method Requirements

- Work pass by pass, in the order above. Announce which pass you're in.
- After all passes, do a **second review of your own findings**: remove anything you can't back with the cited evidence, and re-check the 5 most severe findings by re-reading the actual code paths (is it reachable? is it really exploitable?). False Criticals destroy trust in the whole report.
- End with the prioritized action plan. Quick wins (< 1h, high impact) explicitly marked.
