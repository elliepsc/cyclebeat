-- Last 20 feedback entries with session context.
--
-- Carries `rating_scale` so a consumer can tell a satisfaction rating from an effort one.
-- Without it the column would mix `up` and `Hard` in one list and read as a single scale,
-- which is the conflation ADR-009 exists to prevent.
select
    feedback_date,
    session_id,
    session_title,
    rating,
    rating_scale,
    note,
    level,
    goal,
    duration_min,
    track_count
from {{ ref('int_feedback_enriched') }}
order by feedback_at desc
limit 20
