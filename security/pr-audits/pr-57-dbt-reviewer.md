> dbt-reviewer, pre-PR review of the issue #57 branch, run on 29 October 2026. Diff reviewed: `origin/main...49a886d` (b39a021..49a886d, 13 commits). Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents/` is empty). Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The scratchpad path it cites is the main agent's session scratchpad, not tracked. The fixes it led to are in the commits that follow this one.

---

dbt-reviewer report: branch `fix/57-lake-utc` (HEAD 49a886d) against `origin/main` b39a021 (fetched, `git branch --show-current` = fix/57-lake-utc). I read issue #57 with its comments (plan and owner decisions 1-6) and the whole `origin/main...HEAD` diff: 17 files, including both new Parquet fixtures, which I inspected through the tests. I changed nothing in the repo.

## 1. Verdict: APPROVE

There are no blocking findings. Since this PR, every lake writer stores UTC wall time. No dbt model or test depends on the host time zone. Every new test is red on b39a021, and the Postgres pin is shown to be needed by a mutation. The non-blocking findings below are about doc precision and pre-existing edge cases.

## 2. Blocking findings

None.

- **E.2 contracts:** not touched. No change to normalization, zones, confidence or `cyclebeat/e2.py`.
- **Schemas:** unchanged. Every time column in the warehouse is still `TIMESTAMP` (no TIMESTAMPTZ anywhere), and `dt`, `session_date` and `feedback_date` are still DATE. I checked this through `information_schema.columns` on the scratch warehouse.
- **dbt tests:** none weakened or removed. The only dbt diff is a comment in `dbt/models/staging/stg_feedback.sql:21-23`.
- **Test edits:** the edits to `tests/test_feedback_dedup.py:65-69,155-156` make fixtures time-zone aware (naive values are now refused by the writer). They do not change any expected value.

## 3. Non-blocking findings

**N1. `dt` uses the value's own offset, not UTC, on two DAG paths.**
- Where: `dags/dag_ingest.py:96` (`max(track.ingested_at ...).date()`) and `dags/dag_resolve_bpm.py:102` (`max(row.resolved_at ...).date()`).
- `.date()` on an aware datetime gives the day in that value's offset. The demo snapshot stamp is `2026-07-29T17:43:42+0200` (`cyclebeat/demo.py:30`), so on the DAG demo path `dt` is the Paris day.
- `dbt/models/marts/schema.yml:96` documents `dt` as "UTC day", and plan §2 says `dt` "is computed in Python from aware UTC values".
- Today it gives the same day (17:43+02 and 15:43Z are both 2026-07-29), and the live and CSV paths use `now(UTC)`, so nothing is wrong now. The code predates this diff and is not touched by it.
- Fix: `.astimezone(UTC).date()`, or a ROADMAP line. Correct plan §2 either way.

**N2. `docs/metrics.md:87-88` overstates the re-extraction.** "Partitions written before #57 hold local wall time; the re-extraction for the same `dt` replaces them whole" is only true for tracks and resolutions written for the constant `SNAPSHOT_DT`.
- For sessions and feedback, `extract_to_lake` writes today's `dt`. The old files stay on disk and are only superseded in staging: `stg_sessions` keeps the latest `dt` per `session_id`, and `stg_feedback` reads the latest `dt` only.
- Past-day live or `cmd_resolve` partitions are never re-extracted.
- On the owner's lake this changes nothing, because only `dt=2026-07-29` tracks and resolutions exist (plan §4).
- Fix: one sentence covering both cases ("…for tracks and resolutions; for sessions and feedback the next extraction supersedes them in staging").

**N3. `demo._stamp` now fails loudly instead of silently shifting.** If the snapshot's `generated_at` ever lacked an offset, `datetime.fromisoformat` (`cyclebeat/demo.py:30`) would return a naive value. `lake._utc_wall_time` (`cyclebeat/lake.py:74`) would then raise `ValueError` during `make ingest`, as a traceback rather than a named CLI message. This is better than the old silent shift, and the current snapshot carries `+0200`. ROADMAP line 87 already tracks `_stamp`; it could mention this failure mode.

**N4. One test is only red on a non-UTC host.** `tests/test_lake_utc.py::test_an_aware_non_utc_timestamp_is_written_as_its_utc_instant` runs in-process, so it passes on b39a021 under `TZ=UTC`, i.e. in CI. It is red on b39a021 only under `TZ=Europe/Paris`. The subprocess test `test_an_aware_utc_timestamp_reads_back_unchanged_under_a_non_utc_tz` is the one that is red everywhere, so coverage is fine. If the PR body quotes the red output, it should say it came from a Paris shell.

**N5. Postgres rows written before this PR.** `_as_datetime` reads a naive store value as UTC (`cyclebeat/app_store.py:126`). Rows written before the pin at `api/repositories/database.py:162` went through the server's session time zone. A fresh `postgres:16-alpine` reports `show timezone` = `UTC` (I measured it on a throwaway container), so compose-stack rows are already UTC unless a DSN set `-ctimezone`. It would be worth one sentence in the PR body.

**N6. DoD items not yet in the diff.** There is no `docs/ai-workflow.md` entry for #57 yet, and `product-spec.md:63` still says FR-12 Partial, citing #57. Both are planned for later commits (owner decision 5). This is only a reminder.

## 4. Answers to the focus questions

**Does any dbt model, staging dedup or test depend on the time zone?** No.
- `git grep` over `dbt/models`, `dbt/tests`, `dbt/macros` and `dbt_project.yml` finds no `now()`, `current_date`, `current_timestamp`, `at time zone` or timestamptz.
- `session_date` (`stg_sessions.sql:47`) and `feedback_date` (`stg_feedback.sql:71`) are `date_trunc('day', ...)` on a naive TIMESTAMP, so they do not depend on the time zone.
- `last_session_at` is `max(created_at)`.
- `ingested_at` and `resolved_at` only break ties in staging.
- `dt` is a hive DATE taken from the path.
- Reading the lake does not depend on the time zone (the Parquet column has `isAdjustedToUTC=0`).

**Is "TIMESTAMP = UTC wall time" true for every writer?** Yes. Every `write_partition` caller (`git grep`) feeds aware values, and `_utc_wall_time` converts them:
- `cli.py:39-40` (demo or live ingest; `deezer`/`csv_source` use `now(UTC)`, the demo uses an aware `+0200`);
- `cli.py:98` (`cmd_resolve`: `resolve_track_bpm` stamps `datetime.now(UTC)`, `resolve.py:55`);
- `dag_ingest.py:98-99` (XCom `model_dump(mode="json")` gives an ISO string with an offset, which `RawTrack(**row)` parses back as aware);
- `dag_resolve_bpm.py:103` (rows produced by `resolve_track_bpm`, aware);
- `app_store.extract_to_lake` (`_as_datetime` always returns aware UTC);
- `dag_build_warehouse.py:55`, which calls `extract_to_lake`.

**Does any writer still pass a naive datetime that would now raise?** No.
- `dag_resolve_bpm.read_unresolved` and `cmd_resolve` read tracks back from the lake (naive `ingested_at`) into `RawTrack`. Those tracks are only used to fetch previews and are never rewritten; only the new aware `RawResolution` is written.
- Every test helper that writes partitions (`test_de_core`, `test_dags`, `guard_fixtures`, `reference_dataset`) still passes, so their values are aware.

**Are the tests meaningful?** Yes.
- Run against the b39a021 code with the branch's tests, under `TZ=Europe/Paris`, they fail:
  - all 10 cases of `tests/test_lake_utc.py`;
  - `test_reference_warehouse::test_indicators_match_the_values_computed_by_hand` (`last_session_at` 10:00 instead of 08:00);
  - `test_a_stored_row_reaches_the_lake_at_the_same_utc_instant`, for both sqlite and postgres (`2026-07-11 00:30` instead of `2026-07-10 22:30`).
- Mutation: the HEAD code with only `api/repositories/database.py` reverted to b39a021 fails the `[postgres]` case with the same 00:30 vs 22:30 diff. The UTC pin is therefore necessary, as owner decision 2 requires.
- The "no partial write" assertions (`not (tmp_path / lake.SESSIONS).exists()` and the mkdir-after-conversion check) would catch moving `read_feedback` after the sessions write, or moving `mkdir` back before the conversion.

**Are the docs accurate?** Mostly yes; see N1 and N2. The `stg_feedback.sql` comment, `metrics.md:116-119,170-171`, the `lake.py` docstring and the `chain.py`, `reference_dataset.py`, `guard_fixtures.py` and `test_reference_warehouse.py` docstrings match the code. `schema.yml` already said UTC, and that is now true.

## 5. What I ran and the results

- **Affected tests on the branch:** `TZ=Europe/Paris uv run pytest -p no:cacheprovider -q tests/test_lake_utc.py tests/test_feedback_dedup.py tests/test_reference_warehouse.py tests/test_de_core.py tests/test_dags.py tests/unit/test_api_repositories.py` exited 0. 16 Postgres cases were skipped because `TEST_DATABASE_URL` was not set.
- **Base comparison:** a `git archive origin/main` tree with `tests/` from HEAD, in my scratch dir, run with the project venv (the imports resolve to the scratch tree). Same tests under `TZ=Europe/Paris`: exit 1, with the 12 failures listed in §4.
- **Postgres:** a throwaway `postgres:16-alpine` container (`dbtrev57-pg`, port 127.0.0.1:55987, removed afterwards).
  - Branch: `TEST_DATABASE_URL=... uv run pytest -rA ...::test_a_stored_row_reaches_the_lake_at_the_same_utc_instant` gave 2 passed (sqlite and postgres).
  - Whole `tests/unit/test_api_repositories.py` on Postgres: exit 0.
  - Base code: failed. HEAD minus the pin: `[postgres]` failed.
- **dbt build (`make dbt` equivalent):** built through `tests/chain.py` in `/tmp/claude-1000/-home-ellie-projets-cyclebeat/0093eb01-a171-478c-a598-1b3d3a386ef9/scratchpad/run/w`, with its own warehouse, lake, target and log paths, `TZ=Europe/Paris` and the `RUNTIME_DB_PATH=` prefix. Steps: dlt patterns, the reference dataset lake, demo ingest, `cli load`, `dbt build`.
  - Result: `PASS=106 WARN=0 ERROR=0 SKIP=0` (8 table models, 9 views, 79 data tests, 10 unit tests).
  - Read-back: `raw_tracks.ingested_at` and `raw_resolutions.resolved_at` = `2026-07-29 15:43:42` (UTC, not 17:43:42); `mart_session_kpis.last_session_at` = `2026-10-23 08:00`; the `fct_session` `session_date` values are the UTC days.
  - I did not run `make dbt` itself, because it writes `dbt/target` in the repo. The real `lake/` and `data/` were never touched.
- **Lint and typecheck:** `uv run ruff check cyclebeat api tests dags` passed. `uv run mypy api`: no issues in 21 files.
- **Hook refusal:** a `grep -rn ... .` was refused because it "reaches .env". I did not retry it; I re-scoped the search to `git grep` and named subfolders, as the hook message instructs.

## 6. Downstream impact

- **No schema or contract change**, so there is no breaking change to `fct_session`, `fct_llm_calls`, `dim_track` or the raw tables.
- **Values change** once the owner re-runs `make ingest` and then `make dbt` (owner decision 1): the stored timestamps move from local wall time back to UTC.
  - The demo lake: `raw_tracks`/`stg_tracks.ingested_at` and `raw_resolutions`/`stg_resolutions.resolved_at` drop by 2 h.
  - Any later session or feedback extraction: `fct_session.created_at`/`session_date`, `int_session_summary`, `stg_feedback`/`int_feedback_enriched`/`mart_recent_activity` (`feedback_at`, `feedback_date`) and `mart_session_kpis.last_session_at` hold UTC values. Near midnight, the day changes.
- **API and screens:** anything served from `mart_session_kpis` and `mart_recent_activity` (the KPI and recent-activity reads through `api/repositories/warehouse.py`, the Warehouse Copilot and `query_marts`) now shows UTC.
- **Operations:** `cli extract-app` now exits 1, and the `dag_build_warehouse` extract task fails, on an unreadable store date, where it used to stamp the row with `now()`.

Relevant files:
- cyclebeat/lake.py
- cyclebeat/app_store.py
- api/repositories/database.py
- dags/dag_ingest.py
- dags/dag_resolve_bpm.py
- docs/metrics.md
- dbt/models/marts/schema.yml
- tests/test_lake_utc.py
- tests/unit/test_api_repositories.py
