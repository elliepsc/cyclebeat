-- Fail if `mart_recent_activity` holds the same feedback twice.
--
-- The grain is one feedback (one insert into the app-store `feedback` table). That table has
-- no key, so the key is the rated session and the instant: `session_id` for API rows,
-- `session_title` for v1 rows (NULL `session_id`), and `feedback_at`.
--
-- The key ASSUMES that two inserts on one session never share a timestamp:
-- - API rows: `datetime.now(UTC)` at µs, taken per insert;
-- - v1 rows: DuckDB `now()`, the transaction start, so two v1 rows written in one transaction
--   would share it and fail this test. No current code path writes v1 rows (#54).
--
-- `rating`, `rating_scale` and `note` stay out. An exact duplicate is identical in every
-- column, so adding them would catch nothing more. Leaving them out makes the test stricter:
-- a (session, instant) collision between two different ratings is flagged too, because under
-- the assumption above it cannot be two genuine inserts.
--
-- A singular test rather than `unique` on a concatenation: GROUP BY compares NULLs as equal,
-- so a duplicated v1 row still collides.
select
    session_id,
    session_title,
    feedback_at,
    count(*) as n_rows
from {{ ref('mart_recent_activity') }}
group by session_id, session_title, feedback_at
having count(*) > 1
