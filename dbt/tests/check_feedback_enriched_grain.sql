-- Fail if `int_feedback_enriched` holds the same feedback twice.
--
-- Same key as `check_stg_feedback_grain.sql` (`created_at` is exposed here as `feedback_at`).
-- Beyond a duplicate already in `stg_feedback` (which `check_stg_feedback_grain` catches), a
-- duplicate here comes from the session join fanning out, e.g. `stg_sessions` keeping two rows
-- for one `session_id`.
-- Singular, because `session_id` is NULL on v1 rows and GROUP BY compares NULLs as equal.
select
    session_id,
    session_title,
    feedback_at,
    count(*) as n_rows
from {{ ref('int_feedback_enriched') }}
group by session_id, session_title, feedback_at
having count(*) > 1
