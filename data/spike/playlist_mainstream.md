# Spike fixture — Profile 1: Mainstream

**Role.** High Deezer catalogue coverage, popular tracks. Stresses the reliability of the
Deezer `bpm` field on mainstream music (often 0/null) — i.e. measures how load-bearing the
enrichment source really is.

**Source (real endpoint — resolve LIVE, do not hardcode a fabricated playlist ID).**

```
GET https://api.deezer.com/chart/0/tracks?limit=30
```

Returns the current global top tracks. For each track, the spike then calls:

```
GET https://api.deezer.com/track/{id}          # bpm field (fetchDetails), preview_url
```

**Target size.** ~30 tracks.

**What to measure on this set.**
- % of tracks where Deezer `bpm` is present AND != 0
- % resolvable by librosa on the Deezer 30s preview_url (fallback, less reliable than full audio)
- % hit on GetSongBPM by (artist, title)
- cross-source agreement within +/-3 BPM after E.2 normalization

**Note.** Optionally pin a specific national chart instead of global (e.g. a country playlist)
if you want a stable, repeatable set across runs — record the exact URL used in the report.
