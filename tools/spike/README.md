# Phase-1 source spike — runbook

Measures the **real** BPM coverage of the free sources on two curated sets, before the phase-2
resolver is built on top of the assumption. It produced the figures in
`docs/spikes/phase1-source-coverage.md`, which closed phase 1.

> **Phase 1 is closed** ([ADR-005](../../docs/adr/adr-005-deezer-preview-backbone.md)). This
> runbook is kept because the measurement must stay reproducible — and because the resolver
> built in phase 2 will want to re-measure on a wider catalogue. The Jamendo / Creative-Commons
> `indie_cc` set that earlier versions of this file described as "the decisive test" is **gone**:
> ADR-005 dropped that catalogue, so the retained backbone is `librosa` on the **Deezer 30 s
> preview**, with the Deezer `bpm` field as enrichment.

## 1. Credentials

| Source | Needed | Where | Notes |
|---|---|---|---|
| **Deezer** | **nothing** | — | The public API needs no key for `/chart`, `/search` and `/track/{id}`, and the 30 s preview is served publicly. This is the backbone — it depends on no account. |
| **GetSongBPM** | `api_key` (optional) | <https://getsongbpm.com/api> | Free key on request. **Never measured, never adopted.** It carries a **mandatory backlink obligation** — if the project ever ships this source, the attribution has to appear in the UI. Factor that in before adopting it. |

**The spike runs end to end with no credential at all.** Without `GETSONGBPM_API_KEY` that
column is recorded as an error per track and reported as `NOT MEASURED` — never as zero.

## 2. Declare the optional key

If you do get a GetSongBPM key, put it in `.env` (gitignored, never committed) or export it:

```bash
export GETSONGBPM_API_KEY="..."
```

`.env.example` lists it, empty. **Never commit a real value** (E.0.5).

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

Expect 50 tracks (30 mainstream + 20 mixed) and, with audio analysis, on the order of 10-20
minutes. It writes `data/spike/raw_output.json`.

Useful flags:

| Flag | Effect |
|---|---|
| `--set mainstream` \| `--set mixed` | One set only |
| `--limit 10` | Smaller sample — the chart set only; `mixed` is fixed by its CSV |
| `--skip-audio` | Metadata only, no download, no librosa (fast sanity check) |

**Start with `--set mainstream --limit 5`.** It is the E.8 rule for any live run: a 5-case
sample before a full sweep, so a broken assumption costs seconds rather than a full fetch.

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
`docs/spikes/phase1-source-coverage.md` is filled from it, so each number stays traceable
to raw evidence rather than asserted.

## What the numbers mean

- **`librosa usable`** — the backbone figure under ADR-005: the share of tracks whose BPM the
  project can resolve from the Deezer preview alone, with **zero third-party BPM API**. Measured
  at **82 %** overall, with a documented upward bias (two adjacent 15 s windows of a curated
  excerpt — see the report's "librosa on 30 s previews").
- **`Deezer bpm usable`** — the §15 rule: **below 50 % on `mainstream`, Deezer cannot be the
  backbone**. It measured 23.3 %, which is exactly the pivot ADR-005 records. Deezer `bpm` is now
  read as *enrichment*: when it is present and agrees within ±3 BPM after E.2 normalization, the
  track reaches `cross_validated` 0.9 instead of `single_source` 0.6.
- **`unstable`** is a real result, not a failure. It says librosa cannot lock a stable tempo on
  that track, and a resolver must treat it as absent rather than trust it.
