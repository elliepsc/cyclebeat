# Phase-1 spike — real BPM coverage of the free sources

> ## ⏳ STATUS: PENDING LIVE RUN — CONTAINS NO MEASUREMENTS YET
>
> Every figure below reads `PENDING`. **None of them may be filled by anything other than a
> real run of `tools/spike/source_coverage.py`.** Per E.7, phase 1 contains human actions
> (creating the Jamendo and GetSongBPM accounts): the tooling is prepared and stops here, and
> a spike result is never simulated. The runbook is `tools/spike/README.md`.
>
> No decision — the §15 go/no-go, ADR-004's promotion, the phase-2 resolver — may be taken on
> this document while this banner is present.

- **Date of run**: PENDING
- **Operator**: PENDING
- **Raw evidence**: `data/spike/raw_output.json` (committed alongside this report)
- **Reproduce offline**: `uv run --script tools/spike/source_coverage.py --report`

## Why this spike exists

ADR-004 decided the *shape* of BPM resolution — `librosa` on full Creative-Commons audio plus
CSV as the **guaranteed floor**, `Deezer.bpm` and `GetSongBPM` as **enrichment** that raises
confidence but never blocks — and explicitly deferred its coverage figures to this spike. §15
makes the exit criterion blocking: *"Rapport chiffré ; si Deezer < 50% exploitable → pivot
CSV+Jamendo assumé"*.

This is the last unobserved assumption in the plan. Phase 2 builds the resolver on top of it.

## Method

Three curated sets, committed under `data/spike/`:

| Set | Source | Size | What it stresses |
|---|---|---|---|
| `mainstream` | `GET https://api.deezer.com/chart/0/tracks` | ~30 | Reliability of the Deezer `bpm` field on popular catalogue |
| `mixed` | `data/spike/playlist_mixed.csv` | 20 | Resolution by `(artist, title)` with no platform id |
| `indie_cc` | `GET https://api.jamendo.com/v3.0/tracks/` (tags: electronic, rock, pop, energetic) | ~30 | **The decisive ADR-004 floor test**: librosa on full CC audio |

Per track: Deezer `bpm` (present **and** `!= 0`), GetSongBPM hit by `(artist, title)`, librosa
on audio (full CC track for `indie_cc`, 30 s Deezer preview otherwise), then cross-source
agreement and the E.2 confidence bucket.

### What counts as a usable librosa BPM

librosa almost always returns *a* number, so "librosa answered" would mechanically report
100 % and prove nothing. A track counts only when **two disjoint windows of the same track
agree within ±3 BPM** after E.2 normalization — the same tolerance E.2 already fixes for
cross-source agreement, reused rather than invented. Windows that cannot be cut are reported
`too_short`, never `usable`.

### Normative rules applied verbatim (E.2)

Normalization `while bpm > 180: bpm /= 2` then `while bpm < 70: bpm *= 2`; zones Z1 `<100`,
Z2 `100-115`, Z3 `116-130`, Z4 `131-145`, Z5 `>145`; confidence 0.9 `cross_validated` (2+
sources within ±3), 0.6 `single_source`, librosa arbitration else 0.3 + `review`, no source →
NULL. Guarded by 46 unit tests in `tests/test_spike_coverage.py`.

## Results — coverage per source and per set

| Set | Tracks | Deezer `bpm` usable | GetSongBPM hit | librosa usable | Cross-source agreement (±3) |
|---|---:|---:|---:|---:|---:|
| `mainstream` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `mixed` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `indie_cc` | PENDING | PENDING | PENDING | PENDING | PENDING |

### librosa breakdown

| Set | `usable` | `unstable` | `too_short` | Audio analysed |
|---|---:|---:|---:|---|
| `mainstream` | PENDING | PENDING | PENDING | Deezer 30 s preview |
| `mixed` | PENDING | PENDING | PENDING | Deezer 30 s preview |
| `indie_cc` | PENDING | PENDING | PENDING | **Full CC track** |

### Confidence distribution (E.2)

| Set | `cross_validated` 0.9 | `single_source` 0.6 | `librosa_arbitrated` | `review` 0.3 | `unknown` (NULL) |
|---|---:|---:|---:|---:|---:|
| `mainstream` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `mixed` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `indie_cc` | PENDING | PENDING | PENDING | PENDING | PENDING |

### Latency

| Source | Median (ms) | Notes |
|---|---:|---|
| Deezer | PENDING | paced at 0.3 s, cached |
| GetSongBPM | PENDING | paced at 0.3 s, cached |
| librosa | PENDING | local compute, no network |

## Verdict

**PENDING LIVE RUN.**

Decision rule, to be applied literally once the numbers exist:

- **Deezer usable < 50 % on `mainstream` → explicitly recommend the CSV + Jamendo + librosa
  pivot** (the ADR-004 floor), per §15.
- **The decisive number is `librosa usable` on `indie_cc`** — full CC audio. If it is high, the
  floor holds with **no third-party BPM API at all**, which is the anti-deprecation guarantee
  ADR-004 claims. Deezer and GetSongBPM then only add confidence, never availability.
- If librosa on full CC audio disappoints, that is a documented result too: it triggers an
  ADR-005 grounded in these measurements, not an intuition-driven engine swap.

## Cost (E.8)

0 €. Deezer, Jamendo and GetSongBPM free tiers only; librosa runs locally. Every call is
read-only and paced at ≥ 0.3 s, responses and audio are cached under `data/spike/.cache/`
(gitignored) so re-runs re-fetch nothing, and `--report` recomputes everything offline. No
paid brick was introduced.

## Open points flagged during this phase

1. **Truth-source conflict on documentation language.** Plan V3 §E.6 (l.545) says *"docs en
   français"*; `CLAUDE.md` says *"repo docs in English"*. Resolved toward English by
   truth-source order — the repo as it is (truth-source #1) has all 12 ADRs, the README and
   `ai-workflow.md` in English. **The plan text was not edited**: amending a truth-source is
   out of this phase's scope. Needs a decision.
2. **Truth-source #4 is missing from the repo.** `CLAUDE.md` names
   `docs-notes/CYCLEBEAT_PLAN_V2.md §6-9` as truth-source #4, and E.2 says *"Reprendre V2 §6
   comme spec normative"*. That file does not exist in the repository. The E.2 rules were
   therefore taken from appendix E.2 itself, which is self-sufficient — but the reference is
   currently unverifiable.
3. **Two E.2 disambiguations** were needed where the appendix is written for integers and the
   code handles floats. Neither changes a threshold; both are marked `DISAMBIGUATION` in
   `tools/spike/e2.py`: zones are assigned on the rounded BPM so no float falls between bands,
   and — since E.2 fixes confidence *scores* but not which value becomes `bpm_effective` when
   several sources agree — the spike takes the mean of agreeing sources and reports librosa
   arbitration as its own bucket with a null score rather than inventing one. **The phase-2
   resolver needs that settled properly.**
4. **GetSongBPM carries a mandatory backlink obligation.** Adopting it as a source means
   shipping the attribution in the UI. To weigh once its measured contribution is known.
