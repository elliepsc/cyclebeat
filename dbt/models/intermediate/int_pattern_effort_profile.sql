-- Pattern effort profile: one row per pattern of `stg_patterns` (`id`), with its BPM and
-- resistance buckets, for coach decision analysis.
with patterns as (
    select * from {{ ref('stg_patterns') }}
)

select
    id,
    phase,
    label,
    effort,
    effort_bucket,
    coach_tone,
    bpm_min,
    bpm_max,
    bpm_mid,
    resistance,
    cadence_target,
    -- A NULL bpm_mid or resistance is `unknown`, never the CASE's last bucket: same rule as
    -- `stg_patterns.effort_bucket` (#55), failed by `check_invalid_pattern_buckets.sql`.
    case
        when bpm_mid is null                    then 'unknown'
        when bpm_mid < 100                      then 'slow'
        when bpm_mid between 100 and 130        then 'moderate'
        when bpm_mid between 130 and 155        then 'fast'
        else                                         'very_fast'
    end                                         as bpm_bucket,
    case
        when resistance is null                 then 'unknown'
        when resistance <= 3                    then 'light'
        when resistance <= 6                    then 'moderate'
        when resistance <= 8                    then 'hard'
        else                                         'max'
    end                                         as resistance_bucket,
    pattern_type,
    tags
from patterns
