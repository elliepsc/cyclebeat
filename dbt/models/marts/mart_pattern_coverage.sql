-- Pattern coverage by phase and effort bucket — shows KB composition for the README.
select
    phase,
    effort_bucket,
    bpm_bucket,
    resistance_bucket,
    pattern_type,
    count(*)                                as pattern_count,
    round(avg(bpm_mid), 1)                  as avg_bpm,
    round(avg(cast(resistance as double)), 1) as avg_resistance
from {{ ref('int_pattern_effort_profile') }}
group by phase, effort_bucket, bpm_bucket, resistance_bucket, pattern_type
order by phase, effort_bucket
