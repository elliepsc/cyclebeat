-- Fail if `stg_feedback` holds the same feedback twice.
--
-- Same key as `check_recent_activity_grain.sql` (the reasoning is there), checked over every
-- row rather than the mart's 20: a duplicate outside the 20 most recent would otherwise reach
-- `mart_feedback_summary` and `int_session_summary` unseen. Singular, because `session_id` is
-- NULL on v1 rows and GROUP BY compares NULLs as equal.
select
    session_id,
    session_title,
    created_at,
    count(*) as n_rows
from {{ ref('stg_feedback') }}
group by session_id, session_title, created_at
having count(*) > 1
