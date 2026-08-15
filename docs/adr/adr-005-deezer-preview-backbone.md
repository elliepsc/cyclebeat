# ADR-005 — BPM backbone: Deezer source + librosa on preview; CC/Jamendo floor dropped

- **Status**: Accepted — **supersedes ADR-004**
- **Date**: 2026-08-14
- **Owner**: Ellie

## Context

ADR-004 chose `librosa` on **full Creative-Commons Jamendo audio** (+ CSV) as the *guaranteed BPM
floor*, precisely so the backbone would depend on **no gate-kept API**. Two problems surfaced:

1. **Wrong catalogue for the product.** The owner wants CycleBeat to run on the **mainstream music
   people actually listen to** (Deezer/Spotify catalogues), not obscure CC Jamendo tracks a rider
   would never build a playlist from. ADR-004 also introduced a **Jamendo account/dependency** the
   owner does not want.
2. **Phase-1 stayed blocked.** The phase-1 spike (2026-07-29) measured Deezer + librosa-on-Deezer-
   preview, but the **decisive test of ADR-004** — librosa on full CC audio — was **never run** (no
   Jamendo account). So ADR-004 could not be promoted from `principle` to figures, and phase 1 could
   not close.

Measured facts from the spike (already in the repo, `docs/spikes/phase1-source-coverage.md`):

- Deezer `bpm` field usable: **23.3 %** on the current chart, **65 %** on classics (sparse exactly on
  the new releases a user builds a playlist from → §15 pivot rule triggered).
- librosa on the Deezer **30 s preview**: **75–87 %** usable — **but** the preview *flatters* the
  estimator (two adjacent 15 s windows, not independent; a preview is the most rhythmically stable
  excerpt), so the true field figure is somewhat lower.

**Spotify status (re-verified 2026-08).** Dead for new apps (extended-quota cutoff 2024-11-27):
`audio-features`/`audio-analysis` (tempo/BPM), recommendations, related artists, featured/category
playlists, **and 30 s preview URLs**. **Still available** for new apps: track/album/artist metadata
incl. **ISRC**, search, **user playlist read/create/edit**, playback control, OAuth. → Spotify can be a
**playlist source** (tracklist + ISRC) but provides **no audio and no BPM**.

## Options

1. **Keep ADR-004** (librosa-on-full-CC-Jamendo floor). Rejected: obscure catalogue, unwanted Jamendo
   dependency, and the decisive test remains unmeasured → phase 1 stays blocked.
2. **Deezer source + librosa on the Deezer 30 s preview as backbone; Deezer `bpm` as enrichment; CSV as
   manual floor.** Real mainstream music, no Jamendo, self-sufficient on publicly-served preview audio.
   **Chosen.**
3. **Spotify as the primary source.** Rejected: no audio, no BPM — metadata only; not a viable BPM path.

## Decision

**Option 2.** The BPM backbone becomes **`librosa` computed locally on the Deezer public 30 s preview**.

- **Enrichment**: the Deezer `bpm` field participates in cross-validation and raises confidence to
  `cross_validated` (0.9) when it agrees with librosa within ±3 BPM after E.2 normalization.
- **Manual floor**: CSV import (owner-supplied BPM) remains the always-available override.
- **Dropped**: the Jamendo/CC catalogue and the `extract_jamendo` ingestion branch.
- **Unchanged**: the `raw.resolutions.source` enum (`deezer|librosa|getsongbpm|manual` — minus the
  Jamendo catalogue) and the **E.2 confidence rule**. This ADR only re-fixes *which source is the
  backbone*.

**Spotify import — OPTIONAL enrichment, explicitly OUT of core scope.** A post-core candidate feature:
`Spotify playlist → per-track ISRC → match to Deezer by ISRC → Deezer preview → librosa`. It honours
"people are on Spotify (incl. the owner)" **without any dead endpoint**, but adds an **OAuth flow** and
**cross-catalogue matching** with its own failure modes. Treated like a bonus module (gated after the
core ships), never a core dependency.

## Consequences

- **Phase 1 is UNBLOCKED without Jamendo.** The decisive test is no longer "librosa on full CC audio"
  but "librosa on the Deezer preview" — **already measured** (75–87 %). Phase 1 closes by **formalizing
  this decision** and finalizing the spike report from the two already-measured sets. **No new account.**
- **Honest costs (documented, not hidden):**
  - The preview flatters the estimator → real-world coverage sits **below** the 75–87 % figure.
  - Without the Deezer `bpm` field (most current tracks), confidence lands at `single_source` **0.6**,
    not `cross_validated` 0.9.
  - A 30 s preview yields a **per-track BPM only** (tempo ≈ constant); the full track duration comes
    from metadata. Documented.
- **Robustness tradeoff vs ADR-004 (accepted deliberately).** We trade ADR-004's *zero-third-party-API*
  floor for a **dependency on Deezer public preview URLs** — which Deezer could tighten (the Spotify
  lesson). Mitigation: cache previews **permanently in the lake** (E.8), keep CSV + the Deezer `bpm`
  field as independent signals; if Deezer previews die, **CSV + manual remains the floor**. Lower
  robustness than ADR-004 — the price of a real, recognizable catalogue.
- **Product caveat RESOLVED in the good direction.** Under ADR-004, playback (Jamendo) ≠ the expected
  track. Now **metadata source = playback source = the actual Deezer track/preview** — the rider hears
  the real song.
- **Legal note (owner is not a lawyer — document the basis).** Analyzing a publicly-served Deezer 30 s
  preview for a **transient BPM value**, no redistribution, portfolio/personal use → low risk; store no
  redistributable audio. A future Spotify import reads only the user's **own** playlists under their
  OAuth consent, stores **no** Spotify audio (there is none), and matches via ISRC/metadata only.
- **Cost**: 0 € — librosa local; Deezer public API/preview free; no managed audio service; Spotify (if
  built) uses a free dev app + user OAuth.
- **Reconciliation to do on next touch**: mark ADR-004 `Superseded by ADR-005`; drop `extract_jamendo`
  from `dag_ingest` (E.5); update the phase-1 spike report + `CYCLEBEAT_ROADMAP.md` §1/§6 (no Jamendo);
  the E.2 source enum keeps `deezer|librosa`.

## References

- `docs/adr/adr-004-bpm-resolution-floor.md` (**superseded**).
- `docs/adr/adr-001-v3-repositioning.md` (Spotify purge, source substitution).
- `docs/spikes/phase1-source-coverage.md` (measured Deezer + librosa-on-preview figures).
- `docs-notes/CYCLEBEAT_PLAN_V3.md` §2, §12 (API risks), E.2 (confidence rule), E.5 (`dag_ingest`).
- `docs-notes/CYCLEBEAT_ROADMAP.md` §1, §6 (phase-1 status).
