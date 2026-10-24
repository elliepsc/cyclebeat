-- Fail if any pattern carries a bucket its CASE did not recognise (#55).
--
-- `stg_patterns.effort_bucket`, `int_pattern_effort_profile.bpm_bucket` and
-- `.resistance_bucket` put an unmapped effort, or a NULL bpm_mid or resistance, into
-- `unknown` instead of a default bucket. This test is what makes such a value fail loudly,
-- the same pattern as `rating_scale = 'unknown'` and `check_invalid_rating.sql`.
select
    id,
    effort,
    effort_bucket,
    bpm_mid,
    bpm_bucket,
    resistance,
    resistance_bucket
from {{ ref('int_pattern_effort_profile') }}
where effort_bucket = 'unknown'
   or bpm_bucket = 'unknown'
   or resistance_bucket = 'unknown'
