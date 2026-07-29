# Spike fixture — Profile 3: Indie / Creative Commons

**Role.** The decisive test of the ADR-004 floor: librosa BPM computed on **full, legally
streamable Creative-Commons audio** (Jamendo). This is the guaranteed path that depends on no
gate-kept third-party BPM API.

**Source (real endpoint — resolve LIVE, requires a free Jamendo `client_id`).**

```
GET https://api.jamendo.com/v3.0/tracks/?client_id={ID}&format=json&limit=30&order=popularity_total&tags=electronic&audioformat=mp32&include=musicinfo
```

Run it for a few workout-relevant tags to get variety, e.g. `electronic`, `rock`, `pop`,
`energetic`. The response gives a full-track `audio` URL (CC-licensed) that librosa can analyse
end to end.

**Target size.** ~30 tracks total across the tags.

**What to measure on this set.**
- % of tracks where librosa returns a stable BPM on the FULL CC track (the floor)
- Jamendo `musicinfo` may expose speed/tempo tags — record if present, but treat librosa as truth
- confidence distribution when librosa is the only source (single_source per E.2)

**Why this set matters.** If the floor holds here (high librosa coverage on full CC audio), the
project can resolve BPM with zero external BPM API — the anti-deprecation guarantee of ADR-004.
The other two profiles then only add confidence, never availability.
