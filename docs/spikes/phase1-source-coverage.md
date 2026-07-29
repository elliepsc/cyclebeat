# Phase-1 spike — real BPM coverage of the free sources

> ## ⚠️ PARTIAL RUN — Deezer measured, the decisive ADR-004 test was NOT
>
> Two of the three sets ran. **`indie_cc` — librosa on full Creative-Commons audio, the
> decisive test of the ADR-004 floor — was not measured**, because the owner chose not to
> create a Jamendo account. GetSongBPM was not measured either (no key). Those rows read
> `NOT MEASURED` throughout and are never counted as zero.
>
> The §15 go/no-go below is therefore **decidable for Deezer and undecided for the floor**.

- **Date of run**: 2026-07-29
- **Sets measured**: `mainstream` (30 tracks), `mixed` (20 tracks) — `indie_cc` skipped
- **Raw evidence**: `data/spike/raw_output.json` (committed)
- **Reproduce offline**: `uv run --script tools/spike/source_coverage.py --report`

## Why this spike exists

ADR-004 decided the *shape* of BPM resolution — `librosa` on full Creative-Commons audio plus
CSV as the **guaranteed floor**, `Deezer.bpm` and `GetSongBPM` as **enrichment** that raises
confidence but never blocks — and deferred its coverage figures to this spike. §15 makes the
exit criterion blocking: *"Rapport chiffré ; si Deezer < 50% exploitable → pivot CSV+Jamendo
assumé"*.

## Method

| Set | Source | Size | Audio analysed |
|---|---|---|---|
| `mainstream` | `GET https://api.deezer.com/chart/0/tracks?limit=30` then `/track/{id}` | 30 | Deezer 30 s preview |
| `mixed` | `data/spike/playlist_mixed.csv` → `/search` → `/track/{id}` | 20 | Deezer 30 s preview |
| `indie_cc` | `GET https://api.jamendo.com/v3.0/tracks/` | **0 — NOT MEASURED** | would have been full CC track |

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
| `indie_cc` | — | NOT MEASURED | NOT MEASURED | **NOT MEASURED** | NOT MEASURED |

### librosa breakdown

| Set | `usable` | `unstable` | `too_short` |
|---|---:|---:|---:|
| `mainstream` | 26 | 4 | 0 |
| `mixed` | 15 | 4 | 1 |

### Confidence distribution (E.2)

| Set | `cross_validated` 0.9 | `single_source` 0.6 | `librosa_arbitrated` | `review` 0.3 | `unknown` (NULL) |
|---|---:|---:|---:|---:|---:|
| `mainstream` | 5 | 21 | 1 | 0 | 3 |
| `mixed` | 8 | 6 | 3 | 0 | 3 |

With only two effective sources (Deezer + librosa), most tracks land on `single_source` 0.6.
`cross_validated` 0.9 requires two sources that agree, so it is capped by Deezer's coverage.

### Latency

Median latency is **null in the committed raw output**: that run was served entirely from
cache (0 HTTP calls, 119 cache hits), which is the E.8 caching behaviour working as intended.
Observed during the live fetch earlier the same day — **not reproducible from the committed
artifact, and recorded as an observation only**: ≈ 63 ms median (`mainstream`), ≈ 78 ms
(`mixed`). Deezer latency is not a constraint at this scale.

## Verdict

### §15 rule: **PIVOT triggered** — Deezer 23.3 % on `mainstream`, well below 50 %

The rule is met literally on the set it was written for. Taken alone, **Deezer is not a
viable backbone.**

### The finding that matters most: Deezer's coverage splits by catalogue age

| Set | Composition | Deezer `bpm` usable |
|---|---|---:|
| `mainstream` | Deezer global chart — current 2026 releases | **23.3 %** (7/30) |
| `mixed` | Curated classics: Queen 1978, MJ 1982, Bill Withers 1971, Daft Punk 2013… | **65.0 %** (13/20) |

Nearly a threefold gap on the same field, same API, same run. The observed contrast is
catalogue age; **that is a hypothesis, not a proven cause** — genre, popularity and region
were not controlled for, and 50 tracks is a small sample. But the direction is unambiguous and
it is the operationally relevant one: **BPM is sparsest exactly on the new releases a user
would build a playlist from today.** A demo on classics would look far healthier than the
product actually is.

### librosa on 30 s previews: high, but weaker evidence than it looks

86.7 % / 75 % usable is well above the "70-80 %, unreliable alone" framing ADR-004 supersedes.
**Two caveats keep this from settling the question:**

1. **The two windows are not really independent.** On a 30 s preview they are two adjacent
   15 s halves of the same clip. On a full track they would be 30-90 s and 90-150 s — genuinely
   disjoint musical passages. Agreement between adjacent halves is a weaker claim than the
   ADR-004 floor test would produce.
2. **A preview is a curated 30 s excerpt**, usually the most rhythmically stable part of the
   track. It flatters a tempo estimator.

So this number supports the ADR-004 direction — librosa is not the weak link — but it **does
not substitute for the unmeasured full-CC-audio test**.

### Cross-validation works when it has something to cross-validate

Where Deezer and librosa both produced a value, they agreed within ±3 BPM after normalization
in 83.3 % / 72.7 % of cases. The E.2 design is sound; it is starved of sources, not broken.

## Consequences

1. **ADR-004 is not contradicted; it is reinforced on its weakest premise.** Deezer as
   enrichment rather than backbone is exactly what these numbers describe.
2. **ADR-004 cannot yet be promoted** from `Accepted (principle)` to `Accepted` with figures:
   its central claim — the floor holds on full CC audio with no third-party API — remains
   **unmeasured**.
3. **Dropping the CC source has a measured cost.** Deezer + librosa-on-preview leaves most
   tracks at `single_source` 0.6, and on current chart music Deezer contributes to barely a
   quarter of them. A decision to stay Deezer-only should be taken against these numbers, and
   recorded in an ADR-005 superseding ADR-004 — not by default.
4. **Phase 2 has an open input**: E.2 fixes confidence *scores* but not which value becomes
   `bpm_effective`, nor the score after librosa arbitration (1 and 3 tracks here). The resolver
   must settle it.

## What would close this spike

Measuring `indie_cc`: a free Jamendo `client_id`, then
`uv run --script tools/spike/source_coverage.py --fetch --set indie_cc`. Roughly ten minutes,
and it is the only missing number. Any legally-held local audio works too — ADR-004 says *"full
Creative-Commons Jamendo audio (or any legally-held local audio)"*.

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
   *"repo docs in English"*. Resolved toward English by truth-source order. The plan text was
   deliberately not edited — amending a truth-source is not a side effect. Needs a decision.
2. **Truth-source #4 does not exist.** `CLAUDE.md` names `docs-notes/CYCLEBEAT_PLAN_V2.md
   §6-9`; the file is not in the repository. E.2 is self-sufficient, so nothing was invented,
   but the reference is unverifiable.
3. **Two E.2 disambiguations** are carried by `tools/spike/e2.py`, both marked in the code:
   zones assigned on the rounded BPM, and the mean of agreeing sources as `bpm_effective`.
4. **GetSongBPM carries a mandatory backlink obligation** — to weigh if it is ever adopted.
