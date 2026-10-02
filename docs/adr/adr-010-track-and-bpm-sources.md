# ADR-010 — Track and BPM sources: three roles, Spotify and YouTube for identity only

- **Status**: Accepted — **supersedes the "Spotify import" section and the "cache previews permanently" mitigation of ADR-005** (the rest of ADR-005, the BPM backbone, stays in force)
- **Date**: 2026-10-02
- **Owner**: Ellie

## Context

"Which service do we use?" bundles three different questions, and they do not need the same answer:

1. **Where does the rider listen?** (the playback surface)
2. **Where does the exact identity of a track come from?** (title, artist, ISRC)
3. **Where does the BPM come from?**

ADR-005 chose Deezer for all three in the demo path and kept an optional Spotify import (playlist →
ISRC → Deezer match → preview → librosa) as a post-core idea. This ADR re-checks the Spotify and
YouTube options against their **official** documentation (verified 2026-10-02) and separates the roles.

Convention: every external claim below carries its source URL. A claim that could not be confirmed on an
official page is marked **non vérifié** and is not relied on.

### Spotify

| Claim | Status | Source |
|---|---|---|
| Since 2024-11-27, new apps (and existing development-mode apps without a pending extension request) lose Audio Features, Audio Analysis, Related Artists, Recommendations, Featured/Category playlists, algorithmic and Spotify-owned editorial playlists, and **30-second preview URLs in multi-get responses**. Apps that already had extended mode are unaffected. | Verified | <https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api> |
| Since 2026-02-11 (new Client IDs) and 2026-03-09 (existing ones): Development Mode requires the **app owner to hold an active Premium subscription** (the app stops working if it lapses), at most **5 authorized users** per Client ID, and one Client ID per developer. | Verified | <https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security>, <https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide>, <https://developer.spotify.com/documentation/web-api/concepts/quota-modes> |
| The Client ID limit was later **raised from 1 to 25** per developer account (July 2026), and quota is now counted **per developer account**, shared by all Development Mode Client IDs; exceeding it returns `429` with `reason: QUOTA_EXCEEDED`. | Verified | <https://developer.spotify.com/blog/2026-07-23-web-api-quota-updates>, <https://developer.spotify.com/documentation/web-api/references/changes/july-2026> |
| The February 2026 changelog removed fields from Development Mode objects (Track: `available_markets`, `external_ids`, `linked_from`, `popularity`; Album and Artist similar), and the endpoint set was narrowed (batch fetches such as `GET /tracks`, browse, artist top tracks, search `limit` max 10). | Verified | <https://developer.spotify.com/documentation/web-api/references/changes/february-2026>, migration guide above |
| **`external_ids` (hence the ISRC) is NOT removed in the end**: the March 2026 changelog marks it as "previously marked as removed in the February 2026 changelog but will continue to be available" for both Track and Album. The February page and the migration guide still show it as removed with a "reverted" pointer; the March changelog is the later source. | Verified | <https://developer.spotify.com/documentation/web-api/references/changes/march-2026> |
| Postponement of the endpoint-narrowing for existing integrations (the Premium, user-cap and Client-ID changes took effect as planned). | Verified | <https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security> |
| **Expiry of user authorizations** in Development Mode, and any per-account quota figure beyond "subject to change". | **Non vérifié** — no official page found stating an expiry period; the quota page gives no numbers. | — |

Consequence: Spotify offers identity (including the ISRC, per the March changelog) but **no BPM and no
audio** for a new app, and Development Mode is a five-user, owner-Premium, allowlisted setup.

**Owner's Premium test** (the owner's account is a "Basic Famille" member; whether it satisfies the
owner-Premium requirement is unknown and is tested by the owner, not inferred):

- Result: ______________________________________________
- Date of the test: ____ / ____ / ________

### YouTube

| Claim | Status | Source |
|---|---|---|
| The IFrame Player API exposes the loaded video's URL (`player.getVideoUrl()`) and the elapsed time (`player.getCurrentTime()`). Its reference documents audio only as volume/mute control, with **no method returning audio data**. | Verified (the absence is read from the reference, not stated by it) | <https://developers.google.com/youtube/iframe_api_reference> |
| API clients must not "create, include, or promote features that play content, including audio or video components, from a background player, meaning a player that is not displayed in the page, tab, or screen that the user is viewing" (III.I.9); nor "separate, isolate, or modify the audio or video components" (III.I.7); nor "download, import, backup, cache, or store copies of YouTube audiovisual content" without prior written approval (III.E.1.a). Audio-only use of YouTube through the API is therefore **not allowed**; the player must stay displayed. | Verified | <https://developers.google.com/youtube/terms/developer-policies> |
| Embedded players need a viewport of at least 200 × 200 px, and autoplay must not start until more than half of the player is visible. | Verified | <https://developers.google.com/youtube/terms/required-minimum-functionality> |
| There is **no API to learn what is playing in the YouTube or YouTube Music app** (as opposed to an embedded player the application itself controls). | **Non vérifié** — an absence; no official page states it. Not relied on beyond "this ADR designs nothing that needs it". | — |

### Deezer — risk on the backbone

| Claim | Status | Source |
|---|---|---|
| Full-length recordings are only for Premium+ users; otherwise access is limited to 30 seconds. | Verified | <https://developers.deezer.com/termsofuse> |
| Use of the services is "strictly limited for a non-commercial purpose and in a non-commercial environment". | Verified | <https://developers.deezer.com/termsofuse> |
| "Local Storage/Offline Storage of audio data is strictly forbidden"; the application must not make audio data downloadable; the app "can be blocked by Deezer at any time" if it does not respect the terms. | Verified | <https://developers.deezer.com/guidelines> |
| **Automated analysis** (BPM estimation by a script) of the 30-second extract: the terms and guidelines read contain **no clause that permits or forbids it**. | **Not clearly authorized.** | both pages above |

**This is a risk on the backbone, stated plainly.** The pipeline downloads the 30-second preview and
analyses it with librosa (`cyclebeat/resolve.py`), and it keeps the MP3 in `data/audio_cache/`
(gitignored and `.dockerignore`d, never committed or served). Whether that cache counts as the
"local storage of audio data" the guidelines forbid is **not decided here**: the Decision below removes
the question by dropping persistent audio storage, until the code catches up;
ADR-005's "cache previews permanently" mitigation rested on it. What the repo does publish is derived
values only (BPM, confidence), not audio. A written reading from Deezer was not obtained.

## Options

1. **Keep the ADR-005 Spotify import** (playlist → ISRC → Deezer match → librosa). Rejected, for three
   reasons: Development Mode **requires the app owner to hold Premium**; it allows **at most five
   authorized users**; and the feature would therefore be **unusable by the project's reviewers**, who
   cannot be added to an allowlist of five. The ISRC is **not** a reason: `external_ids` remains available
   (March 2026 changelog above). The import would also not reduce the Deezer dependency, since the BPM
   would still come from the Deezer preview.
2. **Use Spotify or YouTube for BPM.** Rejected: Spotify audio endpoints are closed to new apps, and the
   YouTube policies above forbid isolating or audio-only use of the audio.
3. **Separate the three roles; Deezer for BPM, Spotify/YouTube (if ever) for identity only.** Chosen.

## Decision

- **Deezer (30 s preview analysed by librosa) remains the BPM source of the demo mode**, as in ADR-005,
  with the Deezer `bpm` field as cross-validation and CSV as the manual floor.
- **Spotify and YouTube are only ever a source of the identity of the track being played, never of
  BPM.**
- **The Spotify import via ISRC planned in ADR-005 is abandoned.** The ADR-005 status line is updated to
  point here; its text is not rewritten.
- **"Idea 2"** — an observation table of BPM (tap tempo, microphone, YouTube then Spotify as identity
  sources) — is **deferred to a design ADR, ADR-011**, to be written after the `v1.0-submission` tag.
  Nothing in it is designed here. **Note for that ADR**: since the ISRC stays available from Spotify,
  it will allow an **exact Spotify → Deezer track match** in Idea 2 (identity by ISRC, not by fuzzy
  title/artist matching).
- **No persistent storage of audio.** The 30-second preview is downloaded to a **temporary file, analysed,
  and deleted immediately**; only the derived numbers (BPM, confidence, window figures) are kept. This
  replaces ADR-005's mitigation "cache previews permanently in the lake" and resolves the Deezer
  local-storage question below by not storing audio at all. The code change (today `cyclebeat/resolve.py`
  and `cyclebeat/http.py` cache the MP3 in `data/audio_cache/`) is **not part of this ADR's PR**: it is a
  separate branch `fix/no-audio-cache`, after phase 5.

## Consequences

- No Spotify code or credential enters the core. The "People are on Spotify" caveat in ADR-005 stays a
  product note, not a feature.
- The Deezer analysis question (above) stays open and is the largest unresolved risk on the backbone;
  the mitigations that carry it are the CSV floor, the committed demo snapshot and no audio in CI. The
  "cache previews permanently" mitigation is withdrawn: re-resolving after a change to the confidence
  rule will re-download previews instead of reading a local audio cache (the lake keeps the numbers, so
  replays that only change the rule stay offline). Until `fix/no-audio-cache` lands, the code still
  caches audio, which this ADR treats as a known gap.
- A future identity-only source must respect the rules in the tables: Spotify Development Mode limits;
  a displayed YouTube player, no audio extraction.
- Cost: unchanged, 0 €.

## References

- `docs/adr/adr-005-deezer-preview-backbone.md` (backbone; Spotify import section superseded here).
- `docs/adr/adr-001-v3-repositioning.md`.
- `cyclebeat/resolve.py`, `cyclebeat/http.py` (preview download and local cache).

Note (2026-10-02): the known gap above is corrected on branch `fix/no-audio-cache`. `cyclebeat/http.py` now downloads a preview into a temporary file removed in a `finally` (success, failed analysis or failed download), `cyclebeat/resolve.py` and `tools/spike/source_coverage.py` use that same API, and no code path writes audio durably. The JSON metadata cache is unchanged.
