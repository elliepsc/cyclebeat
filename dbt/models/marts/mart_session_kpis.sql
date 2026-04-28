-- Global KPIs consumed by the Dash dashboard.
select
    count(*)                                        as total_sessions,
    round(avg(duration_min), 1)                     as avg_duration_min,
    sum(track_count)                                as total_tracks_used,
    count(distinct playlist_url)                    as unique_playlists,
    max(created_at)                                 as last_session_at,
    round(avg(satisfaction_pct), 1)                 as avg_satisfaction_pct
from {{ ref('int_session_summary') }}
