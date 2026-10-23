-- Fail if `mart_pattern_coverage` holds more than one row per combination of its five
-- grouping columns — the mart's grain.
--
-- A singular test for the same reason as `check_feedback_summary_grain.sql`: `pattern_type`
-- is not constrained to be non-NULL, and GROUP BY keeps a NULL type as one group.
select
    phase,
    effort_bucket,
    bpm_bucket,
    resistance_bucket,
    pattern_type,
    count(*) as n_rows
from {{ ref('mart_pattern_coverage') }}
group by phase, effort_bucket, bpm_bucket, resistance_bucket, pattern_type
having count(*) > 1
