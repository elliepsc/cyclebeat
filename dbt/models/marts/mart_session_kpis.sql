-- Global session KPIs.
--
-- `unique_playlists` is gone: it counted `distinct playlist_url`, a v1 column that the
-- contract-first API does not produce and E.3 never declared. Replaced by figures the new
-- shape actually carries — how many sessions the evaluator flagged for review, and how far
-- from their target they landed. Both say something about engine quality; a playlist-URL
-- count said nothing at all.
--
-- One row, always. A count is 0 on an empty history, so the two `sum()` counters are
-- coalesced; an average, an extremum or a date stays NULL — there is no value to report,
-- and 0 would be a false one (docs/metrics.md). Guarded by the unit tests in unit_tests.yml.
select
    count(*)                                        as total_sessions,
    round(avg(duration_min), 1)                     as avg_duration_min,
    coalesce(sum(track_count), 0)                   as total_tracks_used,
    count(*) filter (where verdict = 'review')      as sessions_flagged_review,
    round(avg(abs(duration_gap_s)), 1)              as avg_abs_duration_gap_s,
    max(created_at)                                 as last_session_at,
    round(avg(satisfaction_pct), 1)                 as avg_satisfaction_pct
from {{ ref('int_session_summary') }}
