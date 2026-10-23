-- Last 20 feedback entries with session context.
--
-- Carries `rating_scale` so a consumer can tell a satisfaction rating from an effort one.
-- Without it the column would mix `up` and `Hard` in one list and read as a single scale,
-- which is the conflation ADR-009 exists to prevent.
--
-- Grain: one row represents one feedback, as held by the latest lake extraction (one insert
-- into the app-store `feedback` table, deduplicated across `dt` by `stg_feedback`, #54), among
-- the 20 most recent by `feedback_at`, with the context of the session it rates. Its key is
-- (session_id, session_title, feedback_at), checked by `dbt/tests/check_recent_activity_grain.sql`.
--
-- The tie-break after `feedback_at desc` makes the 20 rows deterministic: once the key holds,
-- (feedback_at, session_id, session_title) orders every row, so equal timestamps no longer
-- leave the cut at row 20 to the engine. NULLs sort last (DuckDB's default for ascending).
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
