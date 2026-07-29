# FUTURE_WORK — CycleBeat

Exploratory directions that are **out of the current V3.1/V3.2 scope**. Nothing here is built or
started; recording it so ideas aren't lost. Gating (V3.2 §0) is unchanged: nothing starts before
the core V3.1 is deployed, live, and tested from a clean clone.

---

## Live audio-capture tempo mode (source-agnostic) — decision pending

### The idea

Instead of querying a metadata API for BPM, the app **captures the audio playing on the machine**
(system output / loopback) and detects tempo & beats **in real time** to drive live coaching cues.
The music source becomes irrelevant — Spotify, YouTube, Deezer, a local file, anything audible works,
because we analyse the waveform, not a catalogue.

### Why it's attractive

- **Bypasses every API problem.** No dead Spotify endpoints, no rate limits, no licensing on
  metadata. Analysing your own audio stream for personal use raises no redistribution issue.
- **Truly source-agnostic** — the user's real "peu importe la source" wish.

### The two hard costs (why it is not the core project)

1. **Reactive, not anticipatory.** A live stream only exposes the **past**. We can say "tempo just
   jumped into the sprint zone" but not "sprint in 10 s" — the structured-session promise and the
   −10 s pre-change alert **break**, because they assume the track structure is known ahead of time.
   Live tempo detection is also noisier and laggier (a few seconds to lock) than reading a `bpm` field.
2. **Orthogonal to the DE grid / portfolio.** The whole V3 story is Data Engineering
   (sources → lake → DuckDB → dbt → warehouse → copilot). A real-time DSP desktop capture app
   **throws that away** — dlt, the lake, dbt, Airflow, the copilot — i.e. exactly what earns the
   target grid and the DE/AE interview narrative. Cool demo, wrong project to host it.

### Optional sophisticated variant — restore look-ahead

Capture system audio → **fingerprint** the current track (Chromaprint / AcoustID, free & OSS) →
fetch its known structure/BPM (MusicBrainz + AcousticBrainz dumps). The source stays irrelevant
(whatever plays gets identified) **and** anticipation returns via metadata. Caveats: still a desktop
capture app (out-of-grid), and AcousticBrainz is frozen since 2022 (coverage gaps).

### Tech stack (0 € — respects E.8)

- **Loopback capture**: Windows = WASAPI (`pyaudiowpatch` / `soundcard`); macOS = virtual device
  required (BlackHole); Linux = PulseAudio/PipeWire monitor source. OS-dependent, manual setup on Mac.
- **Real-time beat/tempo**: `aubio` (light, real-time, GPL) or `madmom` / `BeatNet` (more accurate,
  heavier).
- **Optional fingerprint**: Chromaprint + AcoustID; MusicBrainz / AcousticBrainz for metadata.

### Three options — to be defined later

1. **Future feature ("Live mode")** added **after** the DE core ships. *Recommended* — keeps the
   30/30 DE core intact, adds a strong product demo on top later.
2. **Separate standalone project** — a real-time DSP tempo coach, owned as a signal-processing piece,
   not as DE. Good for portfolio variety, but a second build.
3. **Full pivot** — abandon the DE grid and the V3/V3.2 plan to make this the main project. Only if
   the career target shifts toward DSP / real-time rather than data engineering.

### Decision status

**PENDING.** To be chosen once the core is live. Cross-referenced from
`docs-notes/CYCLEBEAT_PLAN_V3.2.md` §7. Default lean: **Option 1**.
