# Phase-1 source spike — runbook

Measures the **real** BPM coverage of the free sources on three curated sets, before the
phase-2 resolver is built on top of the assumption. Produces the figures ADR-004 is waiting
for (`Status: Accepted (principle) · coverage figures pending the phase-1 source spike`).

**The steps below need accounts that only you can create.** Per E.7, phase 1 contains human
actions: the tooling is prepared and stops here. No result is ever simulated — a figure in
the report that did not come from your run would make the whole go/no-go worthless.

## 1. Credentials to obtain (human, one-off, free)

| Source | Needed | Where | Notes |
|---|---|---|---|
| **Deezer** | nothing | — | The public API needs no key for `/chart` and `/track/{id}`. |
| **Jamendo** | `client_id` | <https://devportal.jamendo.com/> | Free account → create an app → copy the Client ID. This is the one that matters: it unlocks the full CC audio the ADR-004 floor is measured on. |
| **GetSongBPM** | `api_key` | <https://getsongbpm.com/api> | Free key on request. **Carries a mandatory backlink obligation** — if the project ships this source, the attribution has to appear in the UI. Factor that in before adopting it. |

The spike degrades rather than fails: without `GETSONGBPM_API_KEY` that column is recorded as
an error per track and simply reported as not measured; without `JAMENDO_CLIENT_ID` the
`indie_cc` set is skipped — **but that set is the decisive test**, so the run is not
conclusive without it.

## 2. Declare them locally

Put them in `.env` (gitignored, never committed) or export them in the shell:

```bash
export JAMENDO_CLIENT_ID="..."
export GETSONGBPM_API_KEY="..."
```

`.env.example` lists both, empty. **Never commit a real value** (E.0.5).

Confirm the GetSongBPM base URL against your dashboard when the key is issued — the one
compiled in has not been exercised, since no key was held when this was written. Override it
without touching the code:

```bash
uv run --script tools/spike/source_coverage.py --fetch --getsongbpm-base "https://.../search/"
```

## 3. Run the measurement

From WSL, after `cyclebeat` (see the README's "Development environment"):

```bash
uv run --script tools/spike/source_coverage.py --fetch --set all
```

`--script` builds a throwaway environment from the PEP 723 header at the top of the file, so
librosa is never installed into the project. The first run downloads it — a few minutes.

Expect roughly 80 tracks (30 mainstream + 20 mixed + ~30 CC) and, with audio analysis, on the
order of 15-30 minutes. It writes `data/spike/raw_output.json`.

Useful flags:

| Flag | Effect |
|---|---|
| `--set indie_cc` | Only the decisive set, if you want the ADR-004 answer first |
| `--limit 10` | Smaller sample — start here to confirm the credentials work |
| `--skip-audio` | Metadata only, no download, no librosa (fast sanity check) |

**Start with `--set indie_cc --limit 5`.** It is the E.8 rule for any live run: a 5-case
sample before a full sweep, so a broken key costs seconds rather than a full fetch.

Everything is cached under `data/spike/.cache/` (gitignored), so re-running re-fetches
nothing. Calls are read-only and paced at 0.3 s. Cost: 0 €.

## 4. Read the summary

```bash
uv run --script tools/spike/source_coverage.py --report
```

Recomputes every figure from `raw_output.json` with **no network**, which is what makes the
report reproducible. It prints per-set coverage, the librosa breakdown
(`usable` / `unstable` / `too_short`), the confidence distribution, median latency, and
applies the §15 decision rule.

## 5. Hand back

Commit `data/spike/raw_output.json` and paste the `--report` output. Every figure in
`docs/spikes/phase1-source-coverage.md` is then filled from it, so each number stays traceable
to raw evidence rather than asserted.

## What the numbers mean

- **`librosa usable` on `indie_cc`** — the decisive one. High here means BPM resolution works
  with **zero third-party BPM API**, which is exactly the anti-deprecation guarantee ADR-004
  claims. The other two sets then only add confidence, never availability.
- **`Deezer bpm usable` on `mainstream`** — the §15 rule: **below 50 %, the report explicitly
  recommends the CSV + Jamendo + librosa pivot**.
- **`unstable`** is a real result, not a failure. It says librosa cannot lock a stable tempo on
  that track, and a resolver must treat it as absent rather than trust it.
