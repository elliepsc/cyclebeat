-- Track metadata joined to its E.2 verdict and to per-source coverage flags.
--
-- The verdict comes from `raw_resolved`, materialized by `cyclebeat.warehouse` from the one
-- normative implementation of the E.2 rule. Nothing here re-derives confidence: this model
-- assembles, it does not decide.

with tracks as (
    select * from {{ ref('stg_tracks') }}
),

resolutions as (
    select * from {{ ref('stg_resolutions') }}
),

verdict as (
    select * from {{ source('raw', 'raw_resolved') }}
),

per_source as (
    select
        track_id,
        count(*) filter (where bpm_raw is not null)                       as n_sources_with_bpm,
        count(*) filter (where source = 'deezer'  and bpm_raw is not null) as has_deezer_bpm,
        count(*) filter (where source = 'librosa' and bpm_raw is not null) as has_librosa_bpm,
        count(*) filter (where source = 'manual'  and bpm_raw is not null) as has_manual_bpm
    from resolutions
    group by track_id
)

select
    t.track_id,
    t.title,
    t.artist,
    t.source_platform,
    t.duration_s,
    t.preview_url,
    t.dt,
    v.bpm_effective,
    v.zone,
    v.confidence,
    v.confidence_method,
    v.n_sources_agree,
    v.review,
    coalesce(s.n_sources_with_bpm, 0) as n_sources_with_bpm,
    coalesce(s.has_deezer_bpm, 0) > 0  as has_deezer_bpm,
    coalesce(s.has_librosa_bpm, 0) > 0 as has_librosa_bpm,
    coalesce(s.has_manual_bpm, 0) > 0  as has_manual_bpm
from tracks t
left join verdict v on v.track_id = t.track_id
left join per_source s on s.track_id = t.track_id
