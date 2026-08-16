{{ config(materialized='table') }}

-- The E.2 track dimension: one row per track, carrying the resolved BPM and its confidence.
--
-- E.2 shape: + bpm_effective DOUBLE, zone TEXT (Z1..Z5), confidence DOUBLE,
--            confidence_method TEXT, n_sources_agree INTEGER
--
-- `planner_eligible` is the operational reading of E.2's "no source -> bpm NULL, excluded
-- from the planner": a track with no BPM cannot be placed in a session. It is exposed as a
-- column so the planner (phase 3) filters on a contract rather than re-deriving the rule.

with resolution as (
    select * from {{ ref('int_track_resolution') }}
)

select
    track_id,
    title,
    artist,
    source_platform,
    duration_s,
    preview_url,
    bpm_effective,
    zone,
    confidence,
    confidence_method,
    n_sources_agree,
    review,
    has_deezer_bpm,
    has_librosa_bpm,
    has_manual_bpm,
    bpm_effective is not null as planner_eligible,
    dt as ingested_dt
from resolution
