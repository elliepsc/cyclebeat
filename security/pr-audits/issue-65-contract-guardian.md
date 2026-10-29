> contract-guardian, pre-PR review of the issue #65 branch, run on 29 October 2026. Diff reviewed: `origin/main...ebc1acd` (3 commits, eddc7f3, 81fe8e6, ebc1acd). Agent definition: `.claude/agents/contract-guardian.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents` is empty). Named after the issue, because the PR number does not exist yet. Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The fixes it led to are in the commits that follow this one.

---

## contract-guardian report: `origin/main...fix/65-pre-submission-audit`

I checked against `origin/main`, fetched just before the review. The branch is `fix/65-pre-submission-audit` with 3 commits (ebc1acd, 81fe8e6, eddc7f3). I changed nothing, and `git status --short` was clean at the end.

### Verdict: APPROVED

I found no blocking violation. All four claims hold. Two of them need a small correction in wording, covered in the non-blocking findings below.

### The four claims

**1. No breaking change: confirmed.**
- The `TrackSource.type` enum is still `[deezer_url, csv, demo]` (`openapi.yaml`, `TrackSource`). It matches `SourceType` in `api/schemas.py:27`.
- `/v1/sessions/generate` still declares only `200` and `422`. The 422 points to `#/components/responses/UnprocessableEntity`, which was already there.
- The `Problem` schema is untouched: `type`, `title`, `status`, `detail`, plus the extra `reasons` field.
- `reasons` is a free `array<string>` with no enum, so a reason code can never break the contract.
- `csv_not_found` already existed: it is at `origin/main:api/services/session.py:131`. `missing_csv_path` is unchanged as well.
- The error still comes from `UnprocessableError`, so it is still a 422 in the RFC 7807 shape.

**2. Atomic change, and the client matches a fresh generation: confirmed.**
- `openapi.yaml`, `api/services/session.py` and `frontend/src/api/schema.d.ts` all change in this diff.
- I regenerated the client into the scratchpad only, without `npm ci` and without touching the working tree. I used the same tool that `gen:api` calls, the locked openapi-typescript 7.13.0. The command was `frontend/node_modules/.bin/openapi-typescript openapi.yaml -o /tmp/claude-1000/-home-ellie-projets-cyclebeat/d2e163e9-2de0-429b-8404-faaa9a4041c1/scratchpad/schema.d.ts`.
- `diff` against the committed `frontend/src/api/schema.d.ts` printed IDENTICAL.
- The front never refers to `csv` outside `schema.d.ts`, so no UI code is affected.

**3. The new description matches `api/services/session.py`: confirmed, with one wording issue (finding A).**
- "No file is opened" is true. The csv branch raises before any I/O, and the `read_csv` import and `Path` usage are gone.
- The test `test_a_csv_request_opens_no_file` spies on both `builtins.open` and `io.open` over 7 kinds of path (missing, existing, `..`, symlink, directory, binary file, committed fixture).
- "422 `csv_not_found`" is true for any non-empty value.
- "Through the API it never produced a session" matches the code comment and the issue context.

**4. FR-01 in `product-spec.md` matches the contract and the code: confirmed.**
- FR-01 now requires only the `demo` source to return 200, and records the csv refusal and issue #66.
- Its pointers are correct today: `cyclebeat/cli.py:62-67` is the `args.csv` branch that calls `read_csv`, and `dags/dag_ingest.py:69-76` is `extract_csv`.

### Violations

None blocking.

### Non-blocking findings

- **A. "Whatever the path" is slightly too broad** (`openapi.yaml`, `TrackSource.value` description; the same text is in `frontend/src/api/schema.d.ts`).
  - An empty `value` with `type: csv` gets `missing_csv_path`, not `csv_not_found`. That check is still at `api/services/session.py:119-122` and is pinned by `test_a_csv_source_without_a_path_is_refused`.
  - FR-01's "one 422 whatever the path" has the same imprecision.
  - Possible fix: "`csv` is refused with 422 (`csv_not_found` for any non-empty path, `missing_csv_path` for an empty one)". Then rerun `make front-gen` in the same PR.
- **B. The reason code no longer means what its name says.** `csv_not_found` is now returned for files that do exist. The owner chose this to avoid a breaking change, and the description explains it, so the contract is honest. A client that branches on the code will still read "not found". Renaming it would be a breaking change, so it belongs in issue #66 with an impact analysis.
- **C. Dead code.** `_from_csv` at `api/services/session.py:193` has no caller left. ruff and mypy do not flag it. Either leave it on purpose for #66 with a comment saying so, or remove it there.
- **D. Fragile line-range pointers in FR-01.** `cli.py:62-67` and `dag_ingest.py:69-76` are correct now. CLAUDE.md prefers a section or function anchor (for example "`extract_csv` in `dags/dag_ingest.py`") because line numbers move when text is added above them.
- **E. Outside the contract, for your information.** The diff has no `docs/ai-workflow.md` entry, which the project's definition of done requires.

### Semantic risks

- The route description in `openapi.yaml` (`/v1/sessions/generate`) still presents 422 only as "no valid session can be built from the catalogue". The csv refusal, like the existing deezer refusals, is a source refusal rather than a planner refusal. This was already true before the diff and is documented on `TrackSource.value`, so it is acceptable.
- The front depends only on the generated types and never sends `csv`, so users of the UI see no change.

### Commands run and results

- `git fetch -q origin && git log --oneline origin/main..HEAD`: 3 commits.
- `git grep "csv_not_found\|missing_csv_path" origin/main -- openapi.yaml api frontend/src`: both codes already present on main (`api/services/session.py:125,131`).
- `uv run python -c "import yaml; yaml.safe_load(open('openapi.yaml'))"`: parses OK.
- `frontend/node_modules/.bin/openapi-typescript openapi.yaml -o <scratchpad>/schema.d.ts`, then `diff` with `frontend/src/api/schema.d.ts`: IDENTICAL.
- `uv run pytest -p no:cacheprovider tests/test_api_contract.py tests/unit/test_api_services.py`: exit 0, **50 passed**. That covers the schemathesis contract suite and the 4 new or renamed csv tests.
- `git status --short` afterwards: clean.
