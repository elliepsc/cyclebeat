-- Fail if `mart_feedback_summary` holds more than one row per (rating_scale, rating).
--
-- The mart's grain is that pair. A singular test rather than `unique` on a concatenated key:
-- GROUP BY compares NULLs as equal, a concatenation would turn them into a NULL key that
-- `unique` skips.
select
    rating_scale,
    rating,
    count(*) as n_rows
from {{ ref('mart_feedback_summary') }}
group by rating_scale, rating
having count(*) > 1
