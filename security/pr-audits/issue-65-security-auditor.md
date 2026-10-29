> security-auditor, pre-PR review of the issue #65 branch, run on 29 October 2026. Diff reviewed: `origin/main...ebc1acd` (3 commits, eddc7f3, 81fe8e6, ebc1acd). Agent definition: `.claude/agents/security-auditor.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents` is empty). Named after the issue, because the PR number does not exist yet. Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. When it ran, the branch had not been pushed yet, contrary to what L3 assumes. The fixes it led to are in the commits that follow this one.

---

# Security audit: `git diff origin/main...fix/65-pre-submission-audit` (issue #65, finding P1 of PR #64)

Reference branch: `fix/65-pre-submission-audit` (checked out, clean), compared with `origin/main` after `git fetch`. Commits: eddc7f3, 81fe8e6, ebc1acd. Files changed: `README.md`, `api/services/session.py`, `frontend/src/api/schema.d.ts`, `openapi.yaml`, `product-spec.md`, `tests/unit/test_api_services.py`.

## Executive summary

- **Overall risk: Low. No blocking finding.** The csv branch no longer touches the filesystem. It returns one constant 422 that never echoes the path, and the tests do prove this.
- `make audit` exit 0: Semgrep 0 findings (243 and 89 rules), gitleaks "242 commits scanned … no leaks found".
- Three non-blocking findings: one test could pass vacuously in theory, `_from_csv` is dead code, and one commit message is a little more detailed than needed.
- **Action #1 (after merge, human):** the deployed Render API keeps the old behaviour until this is deployed. After deploy, check it with a business call: `POST /v1/sessions/generate` with a csv source and two different paths should return byte-identical 422 bodies.

## Point-by-point answers

**1. Does any code under `api/` still open a caller-supplied path?** No.
- Command: `grep -rnE "open\(|read_csv|Path\(|read_text|read_bytes|os\.path|pathlib|duckdb\.connect|load_csv|sources\.csv" api/`
- Every remaining hit is configuration or a fixed path, never request data:
  - `api/repositories/warehouse.py:25-26` and `api/repositories/database.py:114-115`: env var or a path relative to the repo.
  - `api/repositories/readonly_warehouse.py:99,121,163`: the locked DuckDB connection.
  - `api/routers/sessions.py:26`: FastAPI's `Path` parameter, not pathlib.
  - `api/services/warehouse_tools.py:16` and `readonly_warehouse.py:9`: docstrings.
- `from pathlib import Path` and the lazy import of `cyclebeat.sources.csv_source.read_csv` are both gone from `api/services/session.py`.
- `request.source.value` is used in only one place, `session.py:119`, as a truthiness test.
- The deezer_url branch makes no network or file access (`session.py:136-144`).
- `mcp-server/cyclebeat_warehouse.py:21` is a `sys.path` insert from `__file__`, not request data.

**2. Is the response the same for every path, path-free, and never a 500?** Yes.
- `session.py:129-133` raises a constant `UnprocessableError` with a fixed string and `reasons=["csv_not_found"]`. Nothing in it depends on the path.
- The 422 body comes from `api/errors.py:65-69` (`title`, `status`, `detail`, `reasons`). It has no timestamp or request id, so the bodies are byte-identical, and the test compares full `response.text`.
- No code runs between the truthiness check and the raise, so a 500 cannot happen on this branch.

**3. Do the new tests prove the claims, and could they pass vacuously?** They prove them.
- Run: `uv run pytest tests/unit/test_api_services.py -v -p no:cacheprovider` gave 25 passed, exit 0.
- Against the base code I checked by reading, because the scratch mutation run was refused (see Unable to verify). Each test fails on `origin/main`:
  - `test_a_csv_request_opens_no_file`: the base `read_csv` calls `open(path, ...)` (`origin/main:cyclebeat/sources/csv_source.py:42`). That is `builtins.open`, which the spy records, so `opened == []` fails.
  - `test_every_csv_path_gets_the_same_response`: the base message was `f"CSV not found: {path}"`, so the bodies differ and contain the path.
  - `test_no_csv_path_is_a_server_error`: on the base, the `directory` path raises `IsADirectoryError` and the `unreadable` path raises `UnicodeDecodeError`. Only `FileNotFoundError` was caught, so both give 500 under `raise_server_exceptions=False`.
- The ebc1acd message says the tests were shown red on f17725c. I could not rerun that myself.
- The spy covers `builtins.open` and `io.open`, and so also `Path.open` and `Path.read_text`, which call `io.open` at call time. It does not cover `os.open` or native readers such as DuckDB or pyarrow. Since `api/` no longer contains any reading code (point 1), the grep is the stronger proof, and the spy is a regression net on top of it.

**4. Does `missing_csv_path` for an empty value leak anything?** No.
- The outcome depends only on whether the caller's own string is empty (`session.py:119-122`). No server state is involved.
- A whitespace-only value `" "` is truthy and gets `csv_not_found`, which is also harmless.

**5. Is the unreachable `_from_csv` a security concern?** No.
- `_from_csv` (`api/services/session.py:193`) takes already-parsed objects and opens nothing.
- Its only reference is its own definition: `grep -rn "_from_csv" api tests cyclebeat mcp-server dags evals`.
- It is a hygiene question only (finding L2).

**6. Secrets, and doc text that describes the flaw too precisely?**
- Secrets: none. gitleaks found no leaks over all refs. A grep of the diff for key, token, secret, `gsk_`, `sk-`, `/etc/`, `/proc` and `.env` patterns found no secret. `.env.example` is tracked, and `.gitignore` lines 12, 13 and 16 cover `.env` and `.env.*` with `!.env.example`.
- Whether `.env` was ever tracked is an owner check. Her latest result: "no line" (`git log --all --oneline -- .env`, 13 October 2026). I did not run it.
- Doc text:
  - The code comment `session.py:123-128` ("reading a caller-supplied path exposed the server's files") stays at the "reads arbitrary server paths" level.
  - `openapi.yaml`, `schema.d.ts` and the FR-01 note in `product-spec.md` say only that csv is refused and no file is opened.
  - The fixture category names in the tests are neutral.
  - Only the ebc1acd commit message goes a little further (finding L3).

## Findings by severity

No Critical, High or Medium findings.

### L1 — `test_a_csv_request_opens_no_file` could in theory pass vacuously (Low, non-blocking)
- **Where:** `tests/unit/test_api_services.py`, `test_a_csv_request_opens_no_file`, the loop body.
- **Evidence:**
  ```python
  with contextlib.suppress(Exception):
      service.generate(request(source={"type": "csv", "value": path}))
  assert opened == []
  ```
- **Impact:** both the request building and `generate` sit inside `suppress(Exception)`. If either failed before reaching the csv branch, nothing would be opened and the test would pass without exercising the code. It does not happen today, and the HTTP tests cover the same paths, but the test proves nothing by itself.
- **Fix:** replace `suppress` with `pytest.raises(UnprocessableError) as raised`, and assert `raised.value.reasons == ["csv_not_found"]` on each iteration.
- **Effort:** 5 min.

### L2 — `_from_csv` is dead code (Low, non-blocking, not a security issue)
- **Where:** `api/services/session.py:193`.
- **Impact:** none for security. It is a maintenance trap: if issue #66 brings csv back, `_from_csv` invites wiring `read_csv(Path(value))` again.
- **Fix:** delete it now, or keep it with a note pointing to #66 that says any reintroduction must take an upload or a server-chosen id, never a path. That choice belongs to #66.
- **Effort:** 5 min.

### L3 — The ebc1acd commit message lists the tested path categories (Low/informational, non-blocking)
- **Where:** ebc1acd body: "every path category (missing, outside, parent climb, symlink, directory, unreadable, existing) gets the same response; none is a server error."
- **Impact:** small. It hints that some categories behaved differently, but does not say how. The old code was already public on `main`, and the fix lands in the same PR.
- **Fix:** none needed. Rewording would mean rewriting history on a pushed branch, which is not worth it.

### Info — the reason code `csv_not_found` is now semantically loose
- The code now also answers for files that exist. This was the owner's choice (no new reason, no enum change), and the `detail` text explains the refusal. Noted for #66; not a finding.

## Unable to verify

- **Red-on-base mutation run:** refused by the PreToolUse hook. A `git archive … | tar -x` into the scratchpad was blocked with "writes to data/ and lake/ are refused (spike)", because the archive included `data/spike/` (looks like a false positive: the target was the scratchpad). I stopped and did not retry in another form. The "fails on base" claims in point 3 come from reading the base code, plus the commit's statement that the tests were red on f17725c.
- **An earlier grep refusal:** `grep -rn … .` was refused because it reaches `.env`. I searched only named subfolders (`api tests cyclebeat mcp-server dags evals`), as the hook's message asks.
- **`openapi.yaml` and `schema.d.ts` consistency:** only the descriptions changed and the text matches. I did not run `make contract` or the client regeneration.
- **Deployed instance behaviour:** not called. Render calls are refused to agents.

## Prioritized action plan

1. **(Human, after merge)** Deploy, then call `POST /v1/sessions/generate` with a csv source and two different paths. Expect two identical 422 `csv_not_found` bodies that contain neither path.
2. **(Quick win, optional in this PR)** L1: replace `suppress(Exception)` with `pytest.raises(UnprocessableError)` and assert the reason.
3. **(Issue #66)** L2: decide what happens to `_from_csv`. Any csv revival must not accept a server path.
4. The rest of the DoD (lint, typecheck, contract, CI) is the main agent's job; it was not run here apart from `make audit` and this one test file.
