-- Fail if `mart_recent_activity` holds the same feedback twice.
--
-- The grain is one feedback (one insert into the app-store `feedback` table). That table has
-- no key, so the identity is what tells two inserts apart: the rated session and the instant.
-- `session_id` for API rows, `session_title` for v1 rows (NULL `session_id`); `feedback_at` is
-- `datetime.now(UTC)` at µs for API rows, DuckDB `now()` for v1 rows. `rating`,
-- `rating_scale` and `note` are left out: they describe a feedback, they do not identify it,
-- and a key that includes them would let two different ratings at the same instant on the
-- same session pass as two rows. A singular test rather than `unique` on a concatenation:
-- GROUP BY compares NULLs as equal, so a duplicated v1 row (NULL `session_id`) still collides.
select
    session_id,
    session_title,
    feedback_at,
    count(*) as n_rows
from {{ ref('mart_recent_activity') }}
group by session_id, session_title, feedback_at
having count(*) > 1
