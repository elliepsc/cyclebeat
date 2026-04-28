-- Last 20 feedback entries with session context — consumed by the Dash log table.
select
    feedback_date,
    session_title,
    rating,
    note,
    duration_min,
    track_count,
    playlist_url
from {{ ref('int_feedback_enriched') }}
order by feedback_at desc
limit 20
