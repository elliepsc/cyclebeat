-- Last 20 feedback entries with session context.
--
-- Carries `rating_scale` so a consumer can tell a satisfaction rating from an effort one.
-- Without it the column would mix `up` and `Hard` in one list and read as a single scale,
-- which is the conflation ADR-009 exists to prevent.
--
-- Grain: one row represents one feedback, as held by the latest lake extraction (one insert
-- into the app-store `feedback` table; `stg_feedback` reads only the latest `dt`, #54), among
-- the 20 most recent by `feedback_at`, with the context of the session it rates when it
-- carries a `session_id` (a v1 row has none, #60). Its key is
-- (session_id, session_title, feedback_at), checked by `dbt/tests/check_recent_activity_grain.sql`.
--
-- The tie-break after `feedback_at desc` makes the 20 rows deterministic: the key holds over
-- every feedback (`check_stg_feedback_grain.sql`), so (feedback_at, session_id, session_title)
-- orders every row, and equal timestamps no longer leave the cut at row 20 to the engine.
-- NULLs sort last (DuckDB's default for ascending).
select
    feedback_at,
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
order by feedback_at desc, session_id, session_title
limit 20
