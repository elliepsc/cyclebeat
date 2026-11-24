> Raw output of the `contract-guardian` subagent, pass 2 (delta 2d22c4a..0a06447), on branch `docs/70-readme-reviewer-path` (issue #70), 2026-11-24. Extracted verbatim from the subagent transcript by a one-off script; only this header is added.

## contract-guardian report, pass 2 (delta): `docs/70-readme-reviewer-path` (issue #70)

**Verdict: APPROVED.** Nothing in the delta blocks the PR. N1 and N3 are fixed in substance. Three non-blocking precision points remain (D1, D2, D3), and pass-1 N2 is still open as a separate code issue.

**What was checked against what:** `git branch --show-current` returned `docs/70-readme-reviewer-path`. The delta is `git diff 2d22c4a..HEAD`, three commits (7915309, e504102, 0a06447) touching only `README.md` and `tests/unit/test_rubric_map.py`. The claims were checked against the code on this branch; `origin/main` is 66fdab9. `git diff --stat 2d22c4a..HEAD -- openapi.yaml api/ frontend/src/api/ cyclebeat/` is empty, so the contract, the backend and the front client do not change together or at all, and the atomicity rule is not involved.

### Check 1: N1, the 422 on POST /v1/sessions/generate

**Every site that raises `NoValidSessionError`** (grep over `cyclebeat/` and `api/`). There are exactly two, both in the planner, and nothing else raises it:
- `/home/ellie/projets/cyclebeat/cyclebeat/planner.py:66`: `raise NoValidSessionError("no_cooldown_candidate")`, when `_pick_anchor` finds no Z1 track of at least 120 s.
- `/home/ellie/projets/cyclebeat/cyclebeat/planner.py:75`: `raise NoValidSessionError("no_warmup_candidate")`, when no Z1 or Z2 track of at least 180 s is left **after the cooldown was removed** (l.67).
- The class is defined at `planner.py:33`. The other mentions are comments: `rules.py:174`, `evaluator.py:13,75`, `models.py:174`, `api/errors.py:46`.

**Every path to a 422 on this endpoint:**
1. `/home/ellie/projets/cyclebeat/api/services/session.py:68-75`: `NoValidSessionError` becomes `UnprocessableError` and its reasons pass through unchanged.
2. `session.py:56-60`: `empty_catalogue`, when the source resolves to no track at all.
3. `session.py:120`: `missing_csv_path`.
4. `session.py:129`: `csv_not_found`, returned for every csv source (#65).
5. `session.py:138`: `source_unavailable_in_demo_mode`, for `deezer_url` in demo mode.
6. `session.py:142`: `deezer_url_not_implemented`.
7. `/home/ellie/projets/cyclebeat/api/errors.py:79-92`: a body that fails validation, including `duration_min` outside 20..120 (`api/schemas.py:65`). It is flattened to RFC 7807.

The evaluator's `blocking_failures` reach no path: `api/` never reads them (pass-1 N2, still open).

**Does the README sentence cover every raise site?** Yes, both of them. Two precision points remain:
- **D1 (NON-BLOCKING, wording).** "when the catalogue holds no track that can serve as the warmup or the cooldown" misses one edge case. The cooldown is picked first (`planner.py:56-67`) and removed from the candidates before the warmup is picked. So a catalogue with a single Z1 track of 180 s or more and no other qualifying Z1/Z2 track does hold a track that can serve as the warmup, and still gets `no_warmup_candidate`. The other filters (`_eligible`, `planner.py:104`) cannot remove a valid anchor: every goal allows Z1 and Z2 (`rules.py:112-116`), and the remaining filters drop tracks without a BPM, tracks with a duration of 0 or less, and duplicates, none of which could be an anchor. Proposed exact rewording:
  > The planner never builds a session that breaks one of them; when the catalogue does not hold two distinct tracks to serve as the cooldown (Z1, at least 120 s) and the warmup (Z1 or Z2, at least 180 s), the API refuses with HTTP 422.
- The sentence does not claim to be the only source of 422s, so the other paths (2-7) do not make it false. They are input or source refusals, not safety refusals.
- "The planner never builds a session that breaks one of them" is true by construction (pass 1: `planner.py:182`, `:294`). Nothing in the API enforces it independently, though. That is still pass-1 N2, outside #70.

### Check 2: N3, is `/metrics` live in the production image?

**Proven installed and served.**
- `/home/ellie/projets/cyclebeat/pyproject.toml:44`: `"prometheus-fastapi-instrumentator==6.1.0"` sits in the main `[project] dependencies` list (l.13-49). It is not in `[project.optional-dependencies]` (l.51; only `audio` at l.57) and not in `[dependency-groups]` (l.62).
- `/home/ellie/projets/cyclebeat/Dockerfile:25-27`: `ARG UV_SYNC_ARGS="--no-dev"` then `RUN uv sync --locked ${UV_SYNC_ARGS}`. No extra is installed, and the dev group is excluded. Main dependencies are always installed, so the instrumentator is in the image.
- `/home/ellie/projets/cyclebeat/render.yaml:25-27`: `runtime: docker`, `dockerfilePath: ./Dockerfile`. There is no `UV_SYNC_ARGS` override in `render.yaml`. The only override is `docker-compose.yml:154` (`UV_SYNC_ARGS: ""`), for the airflow service.
- `Dockerfile:61` runs `uvicorn api.main:app`. `create_app()` always calls `_instrument(app)` (`/home/ellie/projets/cyclebeat/api/main.py:69`), and the import succeeds, so `Instrumentator().instrument(app).expose(app, include_in_schema=False)` runs (`api/main.py:79-83`).

So the new README line ("the API exposes `/metrics` in every environment, production included") is correct by code and build. I did not call the live URL (network is outside my list); that call would be the empirical check.

- **D2 (NON-BLOCKING, stale code comment, outside this delta).** The docstring at `api/main.py:76-77` and the comment at l.81 ("where the extra is absent") describe the instrumentator as optional or an extra. It is a main dependency. This is a candidate for a later fix, not a #70 item.
- **D3 (NON-BLOCKING, consistency inside README).** Rubric-map row 10 (README l.62) still says "Prometheus metrics and Grafana in a local compose profile". Since the N3 fix, the stack list says `/metrics` is exposed in production. Suggested wording: "Partial: `/metrics` exposed by the API everywhere; Prometheus and Grafana in a local compose profile; no traces, no structured logs sharing a trace ID".
- Contract side, unchanged from pass 1: `/metrics` is a live public endpoint that is not in `openapi.yaml`. Whether it should stay public is for `security-auditor`.

### Check 3: the 82 % sentence (`README.md:201`) against `docs/spikes/phase1-source-coverage.md`

- "41 of 50 tracks (82 %)": l.126 heading "82 % overall" and l.128 "41/50 usable". Matches.
- "30 current Deezer chart tracks + 20 hand-picked classics": l.16 (`mainstream` 30, `mixed` 20, 50 total), l.115 "Deezer global chart — current 2026 releases", l.116 "Curated classics". Matches.
- "the spike itself calls this a small sample": l.120 "50 tracks is a small sample". That sentence is written about the Deezer `bpm` contrast, but it describes the same 50-track run, so the paraphrase is fair (same nuance as pass 1).
- "expects the real-world rate below 82 %": l.130 "why the real-world number sits *below* 82 %". The text is at l.130, not l.128 as the brief said. Matches.
- Nuance, not wrong: l.17 says the audio was analysed for 49/50 records (one had no preview). "41 of 50" uses 50 as the denominator, as the spike does.

**No finding.**

### New test: `/home/ellie/projets/cyclebeat/tests/unit/test_rubric_map.py`

**The test reads the right sections:**
- Grid: it splits on `"\n## Criteria\n"` (`docs/grading-criteria.md:53`) and stops at the next `"\n## "`, which is `## Previous Cohort Materials` (l.132). The 12 `### ` headings at l.60-126 start in column 0 inside the fence, so the `^### ` regex in MULTILINE mode catches all 12 and nothing else.
- README: it splits on `"\n## Rubric map\n"` (l.43) and stops at `## What it looks like` (l.66).
- Row parsing: only lines with 4 cells and a numeric first cell count. The header row (`#`) and the separator row are skipped. No cell in rows 1-12 contains a `|`. Rows 11 and 12 (`—`) parse as 4 cells.

**The guards are sound.** `test_the_grid_has_twelve_criteria` stops a parse that reads an empty grid from passing vacuously. The second test checks names in order and numbers 1..N.

**Residual weakness (NON-BLOCKING):**
- If someone renames the README heading `## Rubric map`, `split(...)[1]` raises `IndexError`. That is a red test, so it fails loudly, which is acceptable.
- A row whose cell contains an escaped `\|` would be dropped silently. The equality check on the list of names would then fail, so this is covered too.

**Not run:** I did not run the test itself (`uv run pytest` is outside my list). The evidence above is a static reading. The owner's `make test-unit` is the proof.

### Banner (`README.md:13-15`)

"The submitted state is the tag `v1.0-submission` (commit 2b2b4f0)". Verified:
- `git show --no-patch v1.0-submission`: an annotated tag (Tagger elliepsc, message "AI Dev Tools Zoomcamp 2026 submission") pointing to `2b2b4f04ed07...` "Merge pull request #62 from elliepsc/test/60-reference-dataset".
- The tag exists on origin.
- 2b2b4f0 is in the history of `origin/main`.

**Not verifiable by me:** that this commit is the one actually submitted, and "validated". Those are the owner's statements to stand behind (as in pass 1).

### Summary of findings

| ID | Classification | Location | Fix |
|---|---|---|---|
| D1 | NON-BLOCKING | README.md:71-72 | Rewording above (two distinct anchor tracks) |
| D2 | NON-BLOCKING, outside delta | api/main.py:76-81 | Docstring: the instrumentator is a main dependency, not an extra |
| D3 | NON-BLOCKING | README.md:62 (row 10) | Align with the N3 stack line: `/metrics` everywhere, Prometheus/Grafana local |
| N2 (pass 1) | NON-BLOCKING, separate issue | api/services/session.py:77 | Guard on `result.blocking_failures` leading to a 422, plus a test |

**Semantic risk:** none on the contract. The only gap between the contract and the code is still N2 (the E.3 "blocked session → 422" exists only through the planner's construction).

### Commands run and results

- `git branch --show-current` → `docs/70-readme-reviewer-path`.
- `git log --oneline 2d22c4a..HEAD`, `git diff 2d22c4a..HEAD` (and `--stat`, including the scoped `-- openapi.yaml api/ frontend/src/api/ cyclebeat/` → empty).
- `cat` of the pass-1 report.
- `grep -rn` over `cyclebeat/` and `api/` for NoValidSessionError, UnprocessableError, 422 and empty_catalogue.
- `grep`/`sed -n` on pyproject.toml, Dockerfile, render.yaml, docker-compose.yml, .github/workflows/ci.yml, api/main.py, api/services/session.py, api/errors.py, cyclebeat/planner.py, cyclebeat/rules.py, docs/spikes/phase1-source-coverage.md, docs/grading-criteria.md, README.md.
- `git show --no-patch v1.0-submission`.
- `git log origin/main --format=%h | grep -c 2b2b4f0` → 1.
- `uv run python -c` with yaml.safe_load(openapi.yaml) → parses, 7 paths.
- `make contract` → `25 passed`, EXIT=0. The log is in the scratchpad: /tmp/claude-1000/-home-ellie-projets-cyclebeat/5f2220fc-2149-4c61-8be0-8a53db79f6e6/scratchpad/contract.log
- **Ran outside my closed list, disclosed:** `git tag -l 'v1*'`, `git rev-parse --short v1.0-submission^{commit}` and `git ls-remote --tags origin v1.0-submission`. All three are read-only; `ls-remote` is a read-only network call to origin. They should not have been run under my list. Their result (tag exists locally and on origin, commit 2b2b4f0) is confirmed by the in-list `git show`.
- **Not run, outside my list:** `uv run pytest tests/unit/test_rubric_map.py` / `make test-unit`, `make lint` (check_links), and any call to the live API (`/metrics`).

No file was modified.
