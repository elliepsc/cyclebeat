# Phase-1 spike — real BPM coverage of the free sources

> ## FINAL — complete for the backbone that was retained (ADR-005)
>
> This report is closed. It measures the path the project actually builds on: **`librosa` computed
> locally on the Deezer public 30 s preview**, with the Deezer `bpm` field as cross-validation
> enrichment. Both sets that exercise that path ran and are reported below.
>
> **`indie_cc` (librosa on full Creative-Commons Jamendo audio) is not "pending" — it is moot.**
> It was the decisive test of **ADR-004**, which [ADR-005](../adr/adr-005-deezer-preview-backbone.md)
> supersedes: the CC catalogue is the wrong one for the product and the Jamendo dependency was
> dropped. GetSongBPM was not measured either (no key); it remains an unadopted optional source.
> Those rows read `NOT MEASURED` throughout and are never counted as zero.

- **Date of run**: 2026-07-29 · **report finalized**: 2026-08-15 under ADR-005
- **Sets measured**: `mainstream` (30 tracks), `mixed` (20 tracks) — 50 records total
- **Audio analysed**: Deezer 30 s preview for 49/50 records (1 track had no preview)
- **Raw evidence**: `data/spike/raw_output.json` (committed)
- **Reproduce offline**: `uv run --script tools/spike/source_coverage.py --report`

## Why this spike exists

§15 makes the phase-1 exit criterion blocking, with a quantified decision rule:
*"Rapport chiffré ; si Deezer < 50 % exploitable → pivot assumé"*. The spike had to establish,
on real playlists and before the phase-2 resolver was built on top of an assumption, how much BPM
the free sources actually deliver.

It was designed under ADR-004, which made **librosa on full CC audio the guaranteed floor**. The
figures below triggered the §15 rule, and the pivot that followed is ADR-005: **Deezer `bpm` is
demoted from candidate backbone to enrichment, and the backbone becomes librosa on the Deezer
preview** — real mainstream catalogue, no gate-kept account.

## Method

| Set | Source | Size | Audio analysed |
|---|---|---|---|
| `mainstream` | `GET https://api.deezer.com/chart/0/tracks?limit=30` then `/track/{id}` | 30 | Deezer 30 s preview |
| `mixed` | `data/spike/playlist_mixed.csv` → `/search` → `/track/{id}` | 20 | Deezer 30 s preview |

A Deezer `bpm` counts only when present **and** `!= 0`. E.2 normalization
(`while bpm > 180: /= 2`, `while bpm < 70: *= 2`) is applied before any comparison, so a
half-time source still cross-validates. A librosa estimate counts as **usable** only when two
disjoint windows of the same track agree within ±3 BPM — the tolerance E.2 already fixes for
cross-source agreement, reused rather than invented.

## Results

### Coverage per source and per set

| Set | Tracks | Deezer `bpm` usable | GetSongBPM hit | librosa usable | Cross-source agreement (±3) |
|---|---:|---:|---:|---:|---:|
| `mainstream` | 30 | **7 — 23.3 %** | NOT MEASURED | 26 — 86.7 % | 5/6 — 83.3 % |
| `mixed` | 20 | **13 — 65.0 %** | NOT MEASURED | 15 — 75.0 % | 8/11 — 72.7 % |
| **Total** | **50** | **20 — 40.0 %** | NOT MEASURED | **41 — 82.0 %** | 13/17 — 76.5 % |

### librosa breakdown

| Set | `usable` | `unstable` | `too_short` |
|---|---:|---:|---:|
| `mainstream` | 26 | 4 | 0 |
| `mixed` | 15 | 4 | 1 |
| **Total** | **41** | **8** | **1** |

### Latency

Median latency is **null in the committed raw output**: that run was served entirely from
cache (0 HTTP calls, 119 cache hits), which is the E.8 caching behaviour working as intended.
Observed during the live fetch earlier the same day — **not reproducible from the committed
artifact, and recorded as an observation only**: ≈ 63 ms median (`mainstream`), ≈ 78 ms
(`mixed`). Deezer latency is not a constraint at this scale.

## Expected confidence distribution under the ADR-005 backbone (E.2)

This is the figure the phase-2 resolver plans against. Recomputed from
`data/spike/raw_output.json` over the two measured sets (50 tracks), applying the E.2 rule
unchanged:

| Set | `cross_validated` 0.9 | `single_source` 0.6 | `librosa_arbitrated` | `review` 0.3 | `unknown` (NULL) |
|---|---:|---:|---:|---:|---:|
| `mainstream` | 5 | 21 | 1 | 0 | 3 |
| `mixed` | 8 | 6 | 3 | 0 | 3 |
| **Total** | **13** | **27** | **4** | **0** | **6** |

| Method | Tracks | Share of the catalogue |
|---|---:|---:|
| **`single_source` 0.6** | **27** | **54 %** |
| `cross_validated` 0.9 | 13 | 26 % |
| `unknown` — bpm NULL, excluded from the planner | 6 | 12 % |
| librosa-arbitrated (score unfixed by E.2) | 4 | 8 % |
| `review` 0.3 | 0 | 0 % |

**`single_source` 0.6 is the dominant regime, and that is a structural property of the ADR-005
backbone, not an accident of this sample.** With two effective sources, a track reaches
`cross_validated` 0.9 only when Deezer *also* carries a usable `bpm` — so 0.9 is capped by the
Deezer field's own coverage, which is **23.3 % on current chart releases** against **65 % on
classics**. The practical consequence for phase 2 and for the product: **confidence is lowest
exactly on the new music a rider builds a playlist from today**, and any demo assembled from
classics will overstate the confidence the product actually achieves.

Two figures the planner must be dimensioned for: **12 % of tracks resolve to no BPM at all**
(bpm NULL → excluded, counted in `mart_data_quality`), and **8 % land in librosa arbitration**,
whose score E.2 does not fix — see open point 3.

## Verdict

### §15 rule: **PIVOT triggered** — Deezer 23.3 % on `mainstream`, well below 50 %

The rule is met literally on the set it was written for. Taken alone, **Deezer is not a viable
backbone.** ADR-005 is that pivot, taken against these numbers rather than by default.

### The finding that drove the pivot: Deezer's coverage splits by catalogue age

| Set | Composition | Deezer `bpm` usable |
|---|---|---:|
| `mainstream` | Deezer global chart — current 2026 releases | **23.3 %** (7/30) |
| `mixed` | Curated classics: Queen 1978, MJ 1982, Bill Withers 1971, Daft Punk 2013… | **65.0 %** (13/20) |

Nearly a threefold gap on the same field, same API, same run. The observed contrast is
catalogue age; **that is a hypothesis, not a proven cause** — genre, popularity and region
were not controlled for, and 50 tracks is a small sample. But the direction is unambiguous and
it is the operationally relevant one: **BPM is sparsest exactly on the new releases a user
would build a playlist from today.**

### librosa on 30 s previews: 82 % overall, with a documented error bar

41/50 usable (86.7 % / 75.0 % per set) is well above the "70-80 %, unreliable alone" framing the
v1 backlog carried. Under ADR-005 this is the backbone figure, so its two weaknesses are stated
as **accepted costs, not as blockers** — they are why the real-world number sits *below* 82 %:

1. **The two windows are not really independent.** On a 30 s preview they are two adjacent
   15 s halves of the same clip. On a full track they would be genuinely disjoint musical
   passages, and agreement between them would be a stronger claim than what is measured here.
2. **A preview is a curated 30 s excerpt**, usually the most rhythmically stable part of the
   track. It flatters a tempo estimator.

Neither is fixable within the ADR-005 backbone — the preview *is* the audio the project is
allowed to analyse — so both are carried forward as known bias, in ADR-005 "Honest costs".
A third, structural: a 30 s preview yields a **per-track BPM only** (tempo assumed ≈ constant);
the full track duration comes from Deezer metadata.

### Cross-validation works when it has something to cross-validate

Where Deezer and librosa both produced a value, they agreed within ±3 BPM after normalization
in 13/17 cases — 76.5 % (83.3 % / 72.7 % per set). The E.2 design is sound; it is starved of
sources, not broken.

## Consequences

1. **ADR-004 is superseded, not refuted on librosa.** Its central claim — that librosa is not
   the weak link — is supported by these numbers. What failed is its *catalogue*: the CC/Jamendo
   floor was the wrong music for the product and required an account the owner declined, so its
   decisive test was never run and phase 1 could not close on a measurement.
2. **ADR-005 is taken against measured figures, not by default.** Deezer + librosa-on-preview
   leaves 54 % of tracks at `single_source` 0.6, and on current chart music Deezer contributes to
   barely a quarter of them. That cost is accepted knowingly, in exchange for a real, recognizable
   catalogue and a single source for metadata *and* playback.
3. **Robustness is deliberately lower than under ADR-004.** The backbone now depends on Deezer
   continuing to serve public preview URLs — the exact failure mode Spotify demonstrated in 2024.
   Mitigation is in ADR-005: permanent preview caching in the lake (E.8), CSV + manual as the
   independent floor.
4. **Phase 2 has two open inputs**, both visible in the table above: E.2 fixes confidence *scores*
   but not which value becomes `bpm_effective`, nor the score after librosa arbitration (4 tracks,
   8 %). The resolver must settle both.
5. **Phase-1 exit criterion (§15) is MET**: numbered report finalized on the retained backbone,
   ADR-005 accepted, ADR-004 superseded. Phase 2 may open.

## Cost (E.8)

0 €. Deezer's public API needs no key. librosa runs locally through a PEP 723 script, so it
enters neither `pyproject.toml`, `uv.lock` nor the image. Calls are read-only and paced at
0.3 s; the final run made **0 HTTP calls against 119 cache hits**, which is the permanent-cache
requirement demonstrated rather than asserted.

## Instrument defects found and fixed during the run

Recorded because both would have falsified the result, and neither was caught by a test:

1. **A threshold on the instrument was deciding the outcome.** The minimum window was 15 s, so
   a two-window split needed 30 s. Deezer previews measure **29.986 s** — four of the first
   five tracks were reported `too_short` over **14 milliseconds**. Lowered to 10 s, derived
   from E.2's own 70 BPM floor (~11.7 beats, enough for autocorrelation). Window planning was
   extracted into a pure `plan_windows()` with a regression test on the exact 29.986 s value.
2. **The response cache would never have been hit.** Its key used `hash()`, which
   `PYTHONHASHSEED` randomizes per process, so every run would have re-fetched every URL — an
   E.8 violation. Replaced with sha256; the 119 cache hits above are the proof it now works.

A third, cosmetic: `librosa.feature.rhythm` is not exposed as an attribute, so two successive
guesses fell through to the deprecated `librosa.beat.tempo`. Resolved by probing the installed
library instead of guessing — `librosa.feature.tempo` is the re-export that resolves.

## Open points

1. **Language conflict.** §E.6 of the V3 plan says *"docs en français"*; `CLAUDE.md` says
   *"repo docs in English"*. Resolved toward English by truth-source order. Still not arbitrated
   in the plan itself.
2. **The committed raw output predates the instrument.** `data/spike/raw_output.json` records
   `jamendo_tracks` / `jamendo_tags` in its `endpoints` provenance block, because it was written
   before the Jamendo path was pruned from `tools/spike/source_coverage.py` under ADR-005. The
   artifact is unchanged and every figure above still recomputes from it; the provenance block
   simply describes the instrument as it stood on 2026-07-29.
3. **Two E.2 disambiguations** are carried by `tools/spike/e2.py`, both marked in the code:
   zones assigned on the rounded BPM, and the mean of agreeing sources as `bpm_effective`.
   Neither is normative — the phase-2 resolver must fix them, together with the arbitration score.
4. **GetSongBPM carries a mandatory backlink obligation** — to weigh if it is ever adopted. It
   stays in the `raw.resolutions.source` enum, unmeasured and unadopted.
