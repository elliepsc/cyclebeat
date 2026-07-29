# ADR-004 — BPM resolution floor: librosa on CC audio, APIs as enrichment

- **Status**: Accepted (principle) · coverage figures pending the phase-1 source spike
- **Date**: 2026-07-28
- **Owner**: Ellie

## Context

The V3 pipeline resolves each track's BPM from multiple sources cross-validated by the
confidence rule (E.2). ADR-001 already purged Spotify (audio-features / audio-analysis
**and** 30 s previews are dead for new apps since 2024-11-27, still no replacement as of
2026-07). Two live third-party sources remain candidates:

- **Deezer** — exposes a per-track `bpm` field (`fetchDetails=true`), but it is frequently
  `0`/null on large catalogue slices, and access terms can tighten unilaterally (the exact
  failure mode Spotify just demonstrated).
- **GetSongBPM** — free BPM database (CC BY 4.0), but requires a mandatory backlink and can
  suspend keys; a third-party dependency all the same.

The current `docs-notes/cyclebeat_backlog.md` (items 1.2 / 8.1 / notes) frames **librosa as
an "opportunistic, not primary" source, ~70-80 % coverage, unreliable alone**. That framing
was written for **librosa on a 30 s Spotify preview**. It no longer holds: the player audio
in V3 is **Jamendo**, whose Creative Commons tracks are legally streamable/downloadable
**in full**. librosa run on a full CC track is materially more reliable than on a 30 s clip,
and depends on **no gate-kept API and no permission**.

## Options

1. **Deezer/GetSongBPM as the primary sources, librosa as fallback** (status quo of the
   backlog). Risk: the backbone depends on APIs that can restrict access at any time — the
   Spotify lesson, unlearned.
2. **librosa-on-full-CC-audio (Jamendo) + CSV as the guaranteed floor; Deezer + GetSongBPM
   as enrichment only.** The pipeline can produce a full, defensible BPM resolution with
   **zero external BPM API**. Third-party sources raise confidence when present but are never
   load-bearing.

## Decision

**Option 2.** The **guaranteed floor** of BPM resolution is `librosa` computed locally on
**full Creative-Commons Jamendo audio** (or any legally-held local audio), plus **CSV** input.
This path needs no API key and no permission, so no upstream deprecation can break the core.

`Deezer.bpm` and `GetSongBPM` become **enrichment sources**: they participate in the
cross-validation (and raise confidence to `cross_validated` when they agree within ±3 BPM),
but their absence never blocks a resolution. The `raw.resolutions.source` enum
(`deezer|librosa|getsongbpm|manual`) and the E.2 confidence rule are unchanged — this ADR
only fixes **which source is the backbone vs. which is optional**.

## Consequences

- **Anti-deprecation robustness.** A Deezer/GetSongBPM restriction degrades confidence, not
  availability. This is the concrete answer to "can we be sure to have an API before
  building?": the floor depends on **no** third-party API.
- **Phase-1 spike is still mandatory** and its rule is refined: it measures, on 3 real
  playlists, (a) % tracks with usable `Deezer.bpm`, (b) % resolvable by librosa on full CC
  audio, (c) % via GetSongBPM, and the resulting confidence distribution. Opening condition
  for enrichment weighting: the librosa-on-CC floor must reach the coverage the spike reports;
  the exact enrichment gain is set from those numbers, not assumed here.
- **Backlog reconciliation.** `cyclebeat_backlog.md` items describing librosa as
  "opportunistic / preview-based / unreliable alone" are **superseded by this ADR** — the
  distinction is preview-clip (old) vs. full-CC-track (V3). Update or annotate on next touch.
- **Product caveat (unchanged, restated).** The audio *played* in the app is Jamendo CC, not
  the mainstream track a rider might expect; Deezer/CSV drive the *plan* metadata. This split
  (metadata source ≠ playback source) is intentional and documented in the plan (§ player).
- **Cost**: 0 € — librosa is local; Jamendo CC is free and legal; no managed audio service.

## References

- `docs-notes/CYCLEBEAT_PLAN_V3.md` §2, §12 (API risks), phase-1 spike; E.2 confidence rule.
- `docs/adr/adr-001-v3-repositioning.md` (Spotify purge, source substitution).
- `docs-notes/DECISIONS_SESSION_2026-07.md` (audit + session decisions that produced this ADR).
