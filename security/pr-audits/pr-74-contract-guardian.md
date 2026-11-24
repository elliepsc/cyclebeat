> Raw output of the `contract-guardian` subagent, pass 1, on branch `fix/74-blocking-failures-422` at 9dd17b1 (issue #74), 2026-11-24. Extracted verbatim from the subagent transcript by a one-off script; only this header is added.

Verdict: APPROVED. There are no blocking findings. There are four non-blocking findings and one semantic risk.

**Branch and reference**
- `git branch --show-current` returns `fix/74-blocking-failures-422`.
- I checked the branch against `origin/main` at 190d55e, using `git diff origin/main...HEAD`. The branch has two commits: dee4e0a (fix) and 9dd17b1 (CLAUDE.md).
- `.claude/agents/contract-guardian.md` is identical on HEAD and `origin/main`: `git diff origin/main HEAD` on that file returns 0 lines.
- I did not run `gh issue view 74 --json title,body,comments` because it is outside my closed command list. So I have not checked issue #74's acceptance criteria or the owner's relayed decisions. You need to tick those yourself.

**Q1 — contract (`openapi.yaml`)**
- `reasons` is defined as `type: array, items: {type: string}`, with no enum and no pattern (l. 237-239). I confirmed this by parsing the file with `yaml.safe_load`.
- The four check names `warmup_present`, `cooldown_present`, `no_cold_sprint` and `all_segments_have_bpm` (`cyclebeat/rules.py:177-184`) are plain strings, so they fit with no schema change.
- On the Python side, `EvaluationResult.blocking_failures` is a `list[str]` (`cyclebeat/models.py:180`). It feeds `UnprocessableError(reasons: list[str] | None)` (`api/errors.py`) and then `Problem.reasons`, so the types line up.
- Only the `#` comment changed: l. 226-229 in the diff, one line changed and one added. The schema itself is the same.
- The generate 422 description (l. 72-75) and `responses.UnprocessableEntity` (l. 210-215) are not touched. "The engine will not return a session that skips its cooldown" is still true, and is now enforced twice.
- **Front client**: no regeneration needed. A YAML `#` comment is not part of the parsed document, and the parsed `Problem` schema is unchanged. So the generated `frontend/src/api/schema.d.ts` (`reasons?: string[]` at l. 157) cannot change.
  - Caveat: I did not run the generator (outside my list). This conclusion is reasoned, not measured.
- The front treats `reasons` as opaque strings and maps no enum, so the new values display with no front change (`frontend/src/api/sessions.ts:39-47`, `frontend/src/screens/ErrorNotice.tsx:26-30`).
- **Atomicity (E.0.5)**: satisfied. No wire shape changed anywhere, so neither the backend nor the client has to move with the contract.

**Q2 — the fix (`api/services/session.py:77-84`)**
- It is the only behaviour change in the diff. The rest is comments, docs and tests.
- The new 422 is raised only when `result.blocking_failures` is non-empty, before `self._sessions.save(...)`. A refused session is therefore never saved, which is correct.
- The `reasons` order is deterministic: `blocking_failures=sorted(blocking)` (`cyclebeat/evaluator.py:77`).
- **Can it turn a session served today (200) into a 422?** Only one with a non-empty `blocking_failures`. Those four checks are the only input to the new branch (`evaluator.py:68`).
  - With the real planner that set is empty (see Q5), so the branch cannot be reached with today's planner. It is defence in depth, and no session currently served would change.
  - Both modules get zones from `e2.zone_of(bpm_effective)` and thresholds from `rules`, and `evaluate(plan, params)` receives the same `params` the planner used. So the planner and the evaluator cannot disagree.

**Q3 — the two new tests (`tests/unit/test_api_services.py`)**
- Both go through HTTP. `_generate_over_http` builds `create_app()` and sets `app.dependency_overrides[get_session_service]`. It uses `TestClient(raise_server_exceptions=False)`, so a 500 shows up as a status code rather than an exception.
- **Test 1** (`test_a_blocking_failure_from_the_evaluator_is_a_422`):
  - It patches `api.services.session.plan_session` with `monkeypatch.setattr(session_module, "plan_session", ...)`. That is the right target, because `session.py:33` binds the name with `from cyclebeat.planner import ... plan_session`.
  - Its guard is valid. It checks `cooldown_present ∈ blocking_failures` with `advanced/intervals/45`, which are exactly the defaults of `request()` (l. 125-133). So it checks the same plan the endpoint will serve.
  - If removing the last segment ever left a Z1 segment of at least 120 s at the end, the guard would fail and name the actual cause, not a misleading one.
  - On the base branch the request would get a 200 with verdict `review`, so `assert status_code == 422` would fail with `(200, 'review')`. That is the right reason. This is reasoned: I could not check out the base and run it.
  - It also checks the `application/problem+json` content type and `reasons`.
- **Test 2** (`test_a_non_blocking_failure_is_still_a_200_with_review`):
  - It is pure HTTP and does no monkeypatching, which is correct because it pins existing behaviour.
  - The guard's parameters `advanced/intervals/60` match `request(duration_min=60)`.
  - I traced the plan by hand:
    - BPM 95 is Z1 and BPM 105 is Z2.
    - The cooldown is the Z1/200 s track and the warmup is the Z2/210 s track.
    - The main block is the Z1/240 s track, which intervals allows.
    - The total is 650 s against a 3600 s target, so `duration_accuracy` fails, `blocking_failures` is empty and the verdict is `review`. The test is consistent.
  - It would go red on the obvious wrong fix (refusing on `failed` or on `verdict == "review"`). I did not run it on such a mutation (`make test-unit` is outside my list).

**Q4 — README and CLAUDE.md**
- **README "What safe means"**: the new clause is accurate against `session.py:77-84`. Its referent is slightly loose: "one of them" means the four blocking rules, while `reasons` carries the check names. That is acceptable.
- **CLAUDE.md** (one added line, l. 45): this is a process claim, not a contract one. I partly checked it against `agent-hooks/pre_tool_use.py`:
  - `_tokens` (l. 378-391) splits the command on `\n` and catches the per-line shlex `ValueError` itself, so an unbalanced quote is not by itself what trips the fail-closed path (`main`, l. 1459).
  - This supports "cause still unknown"; I did not find the cause.
  - Whether the line widens the scope of #74 is your call.

**Q5 — "the planner never builds a session that breaks a blocking rule"**
This time I checked it line by line against `cyclebeat/planner.py` on HEAD. It holds:
- **`warmup_present`**: `placed = [warmup, *main, cooldown]` (l. 88). The warmup is picked with `zone ∈ WARMUP_ZONES` and `duration_s >= WARMUP_MIN_DURATION_S` (l. 69-75). Its zone comes from `e2.zone_of(bpm_effective)` (l. 130, 145), the same function the evaluator recomputes with (`evaluator.py:33`). `Segment.duration_s = track.duration_s` (l. 353).
- **`cooldown_present`**: the last placed track is the cooldown, picked with `zone == COOLDOWN_ZONE` and duration of at least the minimum (l. 60-66). It is removed from the candidates by `track_id` (l. 67) and duplicates are excluded (l. 121-125), so the warmup and the cooldown are always distinct.
- **`no_cold_sprint`**: the anchors are Z1/Z2, so only main segments can be Z5. `_allowed_here` refuses a Z5 with `starts_at_s < COLD_SPRINT_WINDOW_S` (l. 294-295). Its `starts_at_s = warmup_s + elapsed_s` (l. 216) equals the evaluator's running sum of the earlier segments (`_with_start_times`, l. 210-222). The earlier non-high early return at l. 288-291 never lets a Z5 through.
- **`all_segments_have_bpm`**: `_eligible` drops every track where `zone_of(bpm_effective) is None` (l. 130-133), and every placed track comes from `_eligible`. So each segment has `bpm_effective is not None`.
- **Empty plan**: impossible, since both anchors are always placed or the planner raises.
- `planner.py:182` (docstring) and `:294` (the check) are as cited in my #70 review.

**Violations**
None blocking.

**Non-blocking findings**
1. `openapi.yaml:72-75` (pre-existing, untouched): "The structured reasons are in `detail`" is wrong. They are in `reasons`, and `detail` is the prose. `planner.py:37` has the same error.
   - Fix (follow-up issue, not this PR): change the description to "in `reasons`". It is a description-only change, but it does change `schema.d.ts` l. 40 (the JSDoc copy), so it needs a client regeneration in the same PR.
2. `api/schemas.py:38-41`: the `Problem` docstring still says `reasons` carries the planner's codes only. Fix: add "and the evaluator's blocking check names", mirroring the `openapi.yaml` comment.
3. `README.md:74`: the edited line runs past the paragraph's wrap of about 100 characters. Fix: re-wrap.
4. Test 1 could also assert that nothing was saved on the 422, for example by checking the fake `SessionRepository` stays empty. Fix: optional extra assertion.

**Semantic risk**
`reasons` now mixes two vocabularies on the same 422:
- the planner's codes: `no_cooldown_candidate`, `no_warmup_candidate`, `empty_catalogue`, ...
- the evaluator's check names: `cooldown_present`, ...

A client branching on `reasons` has to know both. Neither is enumerated in the contract (open string, pre-existing), and the front only displays them. Adding an enum later would be a breaking change, so the vocabulary should be decided before anything branches on it.

**Commands run and results**
- `git branch --show-current` → `fix/74-blocking-failures-422`
- `git diff origin/main...HEAD --stat` → 5 files, +82/-2
- `git diff origin/main HEAD -- .claude/agents/contract-guardian.md | wc -l` → 0
- `git log origin/main..HEAD` → dee4e0a, 9dd17b1
- `uv run python -c` with `yaml.safe_load` → parses. `Problem.reasons = {'type': 'array', 'items': {'type': 'string'}}`. The generate 422 is still `$ref: UnprocessableEntity`.
- `make contract` (`pytest tests/test_api_contract.py`) → 25 passed, 4 deprecation warnings from schemathesis/jsonschema, exit 0.
  - This target does not check the front client against the contract, and schemathesis cannot reach the new branch with the real planner.
- Read-only `cat`, `sed -n` and `grep` on `api/services/session.py`, `api/errors.py`, `api/schemas.py`, `cyclebeat/evaluator.py`, `cyclebeat/planner.py`, `cyclebeat/rules.py`, `cyclebeat/models.py`, `tests/unit/test_api_services.py`, `README.md`, `Makefile`, `frontend/src/` and `agent-hooks/pre_tool_use.py`.
- Not run, outside my list: `gh issue view 74 ...`, `make test-unit` (including running the two new tests and showing them red on the base or on a mutation), and the front client generator.

**Relevant files**
- /home/ellie/projets/cyclebeat/openapi.yaml
- /home/ellie/projets/cyclebeat/api/services/session.py
- /home/ellie/projets/cyclebeat/api/schemas.py
- /home/ellie/projets/cyclebeat/cyclebeat/evaluator.py
- /home/ellie/projets/cyclebeat/cyclebeat/planner.py
- /home/ellie/projets/cyclebeat/cyclebeat/rules.py
- /home/ellie/projets/cyclebeat/tests/unit/test_api_services.py
- /home/ellie/projets/cyclebeat/README.md
- /home/ellie/projets/cyclebeat/CLAUDE.md
- /home/ellie/projets/cyclebeat/frontend/src/api/schema.d.ts
