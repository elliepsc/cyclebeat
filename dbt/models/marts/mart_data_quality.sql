{{ config(materialized='table') }}

-- BPM coverage and confidence distribution — the mart E.2 names for unresolved tracks, and
-- the figure phase 2's exit criterion is measured against.
--
-- One row per confidence_method so the shape survives new methods without a schema change.
-- The phase-1 spike measured, over 48 unique tracks from the committed snapshot:
--   single_source 56.2%, cross_validated 25.0%, librosa_arbitrated 8.3%, unknown 10.4%.
-- A large move here means the resolver has drifted from E.2, not that the music changed.

with tracks as (
    select * from {{ ref('int_track_resolution') }}
),

total as (
    select count(*) as n_tracks from tracks
)

select
    coalesce(t.confidence_method, 'unknown')                as confidence_method,
    count(*)                                                as n_tracks,
    round(count(*) * 100.0 / max(total.n_tracks), 1)        as pct_of_catalogue,
    round(avg(t.confidence), 3)                             as avg_confidence,
    count(*) filter (where t.bpm_effective is not null)     as n_with_bpm,
    count(*) filter (where t.has_deezer_bpm)                as n_with_deezer_bpm,
    count(*) filter (where t.has_librosa_bpm)               as n_with_librosa_bpm,
    count(*) filter (where t.review)                        as n_flagged_review
from tracks t
cross join total
group by coalesce(t.confidence_method, 'unknown')
order by n_tracks desc
