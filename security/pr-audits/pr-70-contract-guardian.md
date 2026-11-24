> Raw output of the `contract-guardian` subagent, pass 1, on branch `docs/70-readme-reviewer-path` at c4fd004 (issue #70), 2026-11-24. Extracted verbatim from the subagent transcript by a one-off script; only this header is added.

## contract-guardian report: `docs/70-readme-reviewer-path` (issue #70)

**Verdict: APPROVED.** Nothing blocks, and four points are worth a follow-up. One of them (N1) is a sentence in the new README text that overstates how the 422 is produced.

**What was checked:** current branch `docs/70-readme-reviewer-path`, diff `origin/main...HEAD` (one commit, c4fd004). `origin/main` is 66fdab9, which is also `HEAD~1`, so the claims in the docs that they were "checked against `main` at 66fdab9" name the right base. Only `README.md` and `docs/architecture.md` change. `git diff --stat origin/main...HEAD -- openapi.yaml api/ frontend/src/api/` is empty, so the rule that the contract, backend and front client change together is not involved.

### 1. `file:line` pointers in `/home/ellie/projets/cyclebeat/docs/architecture.md`
I opened every pointer in the table (rows at lines 12-40) with `sed -n` on the branch. Each one lands on the thing its row describes.
- **The six refreshed pointers are all correct:**
  - `api/services/session.py:67` is `plan = plan_session(catalogue, params)` and `:77` is `result = evaluate(plan, params)`.
  - `cyclebeat/cli.py:123` is `counts = extract_to_lake(root=root)`.
  - `cyclebeat/app_store.py:176` is `def extract_to_lake(...)`.
  - `cyclebeat/lake.py:27` is `LAKE_ROOT = Path("lake")` and `:109` is `def write_partition(`.
- **The pointers that were not refreshed are also still correct:**
  - `ci.yml`: 27/119/157/182 are the `build`/`frontend`/`integration`/`security` jobs; 198-200 is `deploy` with its `needs` and the main-only `if`; 221-226 is the `tools.deploy` step.
  - `tools/deploy.py`: 115 is `trigger`; 245-266 is `smoke_test` with health, generate, cors and web.
  - `render.yaml`: 23-26 (api service), 30/48 (`autoDeployTrigger: "off"`), 31-37, 42-47 and 55-56 (`VITE_API_URL`).
  - `Dockerfile`: 40-45 (the build `RUN`) and 61 (`CMD exec uvicorn`). `frontend/Dockerfile:24-28` is the nginx stage. `frontend/src/api/client.ts:6` is `API_URL`.
  - `database.py`: 106-107 is `is_postgres`; 153-167 and 153-158 are `_connect`. `warehouse.py:38-42` is the read-only open and its fallback. `track.py:27` is `readable(...)`.
  - `docker-compose.yml`: 40-47 (postgres), 58-59 (the no-mount comment), 60-61, 65, 69 (`DATABASE_URL`), 76, 86-92 and 90 (web `VITE_API_URL`), 106-138 (ingest/dbt) and 148-191 (airflow).
  - `Makefile`: 81-82 (`dbt`) and 92-96 (`ingest`, with 93/94/95/96 each on the right command).
  - `cli.py`: 48-67, 69 and 106. `ingest_pipeline.py`: 43, 51-56 and 59-61. `db/runtime.py`: 21-23 and 63. `dbt/profiles.yml:8`. `warehouse.py:122`.
  - DAGs: `dag_ingest` 36/84, `dag_resolve_bpm` 34/94, `dag_build_warehouse` 32 and 44-77.
- **NON-BLOCKING, already on `main`, not changed by this PR:**
  - The A11 row "built from the same `Dockerfile`" cites `docker-compose.yml:76`, which is the `command: uvicorn ...` line. The evidence is really `:61` (`build: .`).
  - `app_store.py:64-68` is `_sqlite_path`, not the code that picks the engine. Acceptable as supporting evidence.

### 2. Links and anchors
- I extracted every relative link from both files. All 45 targets in `README.md` are tracked (`git ls-files` finds each one).
- **README anchors all match a heading** (`README.md` heading list):
  - `#reviewer...` is not linked anywhere.
  - `#quality-gates` → l.218.
  - `#roadmap` → l.348.
  - `#run-it-locally` → l.235.
  - `#security--ops` → "Security & ops", l.366.
  - `#the-full-system-one-command-docker` → l.237.
  - `#why-this-project` → l.95.
  - `#end-to-end-tests` → l.281.
  - `docs/metrics.md#where-the-data-comes-from-and-which-window-it-covers` → `docs/metrics.md:40`.
- **`docs/architecture.md:4`** links to `../README.md#architecture`, and `## Architecture` is still at `README.md:102`.
- **`backend/README.md:11`** still links to `../README.md#architecture`, so it still lands.
- I did not run `tools.check_links`: it is outside my command list. Running `make lint` is still part of the definition of done.

### 3. API table and quick-path curl against `openapi.yaml`
- **The table matches the contract.** The API table (`README.md` l.340-346, unchanged by this PR) lists the same seven operations as `openapi.yaml`: `/health` GET, `/v1/sessions/generate` POST, `/v1/sessions` GET, `/v1/sessions/{session_id}` GET, `/v1/sessions/{session_id}/feedback` POST, `/v1/quality/coverage` GET and `/v1/quality/summary` GET. The README writes `{id}` where the contract says `{session_id}`; that is cosmetic.
- **The curl body is valid.** `GenerateSessionRequest` requires `source`, `level`, `goal` and `duration_min`. `TrackSource` requires `type` and `value`. `demo` is in the type enum, and the description says `value` is `""` for demo. `beginner` is in `Level`, `endurance` is in `Goal`, and 30 is inside 20..120.

### 4. Factual claims in the new README text

**"What safe means"** (`README.md` l.67-74)
- **Correct:**
  - safe = every check passes: `cyclebeat/evaluator.py:76`, `verdict="safe" if not failed else "review"`.
  - Four checks are blocking: `cyclebeat/rules.py:177-184`.
  - The warmup is Z1 or Z2 and at least 180 s, the cooldown is Z1 and at least 120 s, and no Z5 may start in the first 300 s: `rules.py:24-32`.
  - Duration tolerance 120 s, `MAX_CONSECUTIVE_HIGH = 2`, recovery within 2 positions, coverage threshold 0.60: `rules.py:37-47`.
  - The thresholds' provenance: the v1 note, "ordinary indoor-cycling practice" (`docs/adr/adr-007-session-construction-rules.md:27-30`).
- **N1 (NON-BLOCKING, wording): "When one of those fails, no session is served at all (HTTP 422)" overstates how it works.**
  - The 422 comes from the planner, not the evaluator. `plan_session` raises `NoValidSessionError` only when it cannot place a cooldown or a warmup (`cyclebeat/planner.py:66` `no_cooldown_candidate`, `:75` `no_warmup_candidate`). `api/services/session.py:68-75` turns that into the 422. The other 422 is `empty_catalogue` (`session.py:56-60`).
  - The other two blocking rules (no cold sprint, a BPM on every track) never produce a 422. The planner enforces them as it builds the session (`planner.py:182`, `:294`), and tracks without a BPM are excluded up front.
  - `api/services/session.py` never reads `result.blocking_failures`. No grep hit under `api/`.
  - Suggested wording: "The planner never builds a session that breaks one of them; when it cannot place a valid warmup or cooldown it refuses with HTTP 422."
- **N2 (NON-BLOCKING, contract risk; the code gap predates this PR): the evaluator's `blocking_failures` are not wired to the 422.**
  - E.3 and ADR-007 say a blocked session becomes a 422. The comments in the code say so too: `evaluator.py:12-13` ("which phase 4 turns into the E.3 422") and `models.py:174`.
  - In fact, if the planner's guarantee ever broke, the API would serve the session with verdict `review` instead of returning a 422.
  - This is a separate issue, not part of #70: a guard in `SessionService` that raises `UnprocessableError(reasons=result.blocking_failures)` when the list is not empty, plus a test.

**Stack list** (`README.md` l.169-187)
- **Correct:**
  - dbt and dlt run once, when the image is built: `Dockerfile:40-45`.
  - DuckDB is opened read-only in production: `warehouse.py:39`.
  - SQLite in production, Postgres in compose and in CI: `render.yaml` sets no `DATABASE_URL`; `docker-compose.yml:69`; `ci.yml:36-37,90`.
  - librosa is the optional `audio` extra and not in the image: `pyproject.toml:51-59`, `Dockerfile:25-27` `--no-dev`.
  - Airflow runs under the compose `pipeline` profile and Prometheus/Grafana under `monitoring`: `docker-compose.yml:108,201,212`.
  - Semgrep and gitleaks run in CI as blocking jobs. Semgrep blocks on ERROR severity only (`ci.yml:178`).
  - The MCP server is local only: the `Makefile:183` target, and nothing about it in `render.yaml` or `Dockerfile`.
- **N3 (NON-BLOCKING, precision): the Prometheus line says "not in production", but production does expose `/metrics`.**
  - `prometheus-fastapi-instrumentator==6.1.0` is a main dependency (`pyproject.toml:44`). It is therefore installed in the `--no-dev` image, and `api/main.py:80-83` serves `/metrics` (`include_in_schema=False`).
  - So the live API probably serves `/metrics` publicly. Only the Prometheus server and Grafana are local.
  - Suggested wording: "the API exposes `/metrics` everywhere; Prometheus and Grafana run only locally".
  - On the contract side, `/metrics` is a live endpoint that is not in `openapi.yaml`. That may be deliberate, but it is undocumented. Whether it should be public is a question for `security-auditor`.

**Rubric map** (`README.md` l.42-63)
- **Names and order match the grid.** The 12 criterion names are character-for-character identical to the `###` headings of `docs/grading-criteria.md` (l.60-126), in the same order.
- **Rows agree with `docs/quality-bar.md`:**
  - Row 9 CI/CD: no dev environment and no manual production step. This is quality-bar's "official level 3" gap, and it matches the grid text at `grading-criteria.md:112`.
  - Row 10: metrics plus Grafana, no traces and no shared trace ID.
  - Rows 11 and 12: ABSENT.
  - Row 3, "four subagents": `git ls-files .claude/agents` lists four files.
  - Row 7, chained healthchecks: postgres → api → web in `docker-compose.yml`.
  - The "22 October 2026" date matches `quality-bar.md:14`.
- **N4 (NON-BLOCKING, traceability):** the README says the grid was "re-checked against the course repository on 24 November 2026: unchanged since commit 526d9c1". That re-check is not recorded anywhere I can see: the header of `docs/grading-criteria.md:9` still says "Retrieved: 2026-10-22". I could not verify it (no network command in my list). Suggestion: record the 24 Nov re-check, with how it was done, in the `grading-criteria.md` header or in the `ai-workflow.md` entry, so the claim has evidence behind it.

**The 82 % sentence** (`README.md` l.199)
- Every part of it matches `docs/spikes/phase1-source-coverage.md`:
  - 41/50 usable and 82 %: l.126-128.
  - 30 chart tracks plus 20 curated classics: l.16 and the table at l.115-116.
  - "a small sample": l.120.
  - Real-world rate expected below 82 %: l.128.
- A minor nuance: the "small sample" sentence at l.120 is written about the Deezer `bpm` contrast, but it describes the same 50-track sample, so the paraphrase is fair.

**Other new sentence**
- "the planner never reads [feedback]" (`README.md` l.362): `grep` finds no feedback or rating in `cyclebeat/planner.py` or `cyclebeat/rules.py`. `mart_feedback_summary.sql` exists. Consistent.
- Not verified: "submitted ... and validated" (`README.md` l.13). I have no evidence source for it, so it is the owner's statement to stand behind.

### Semantic risks
- The changed README does not touch the contract. The only risk to the contract's position as source of truth is N2: the docs and the code comments promise a 422 for blocking failures, and the API does not enforce it independently of the planner. If you open an issue for it, the fix belongs on a separate branch.

### Commands run and results
- `git branch --show-current` → `docs/70-readme-reviewer-path`. `git diff --stat origin/main...HEAD` → 2 files. `git log origin/main..HEAD` → c4fd004.
- `sed -n` on every cited file and line → all as described above.
- Link and anchor extraction plus a `git ls-files` loop → every target tracked.
- `uv run python -c` with `yaml.safe_load(open('openapi.yaml'))` → parses; `GenerateSessionRequest`, `TrackSource`, `Level` and `Goal` inspected.
- `make contract` → `25 passed`, EXIT=0 (schemathesis against the app; RFC 7807 shape test green).
- **Hook refusal:** one `grep -rn ... .` was refused by `agent-hooks/pre_tool_use.py` because a search over `.` reaches `.env`. I did not retry it in that form; I re-ran the search over the explicit paths `api/`, `pyproject.toml`, `render.yaml`, `Dockerfile` and `Makefile`.
- **Not run, outside my list:** `make lint` / `tools.check_links`, and any network call to the course repository or the live API.

No file was modified.
