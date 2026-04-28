-- Pattern effort profile — maps each pattern to a BPM bucket for coach decision analysis.
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
    case
        when bpm_mid < 100                      then 'slow'
        when bpm_mid between 100 and 130        then 'moderate'
        when bpm_mid between 130 and 155        then 'fast'
        else                                         'very_fast'
    end                                         as bpm_bucket,
    case
        when resistance <= 3                    then 'light'
        when resistance <= 6                    then 'moderate'
        when resistance <= 8                    then 'hard'
        else                                         'max'
    end                                         as resistance_bucket,
    pattern_type,
    tags
from patterns
