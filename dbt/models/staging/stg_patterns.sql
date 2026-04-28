with source as (
    select * from {{ source('raw', 'patterns') }}
),

cleaned as (
    select
        id,
        pattern_type,
        phase,
        label,
        bpm_min,
        bpm_max,
        round((bpm_min + bpm_max) / 2.0, 1)        as bpm_mid,
        energy_min,
        energy_max,
        loudness_min,
        loudness_max,
        resistance,
        cadence_target,
        effort,
        duration_min_s,
        duration_max_s,
        instruction,
        coach_tone,
        tags,
        case
            when effort in ('easy', 'light')           then 'low'
            when effort in ('moderate', 'tempo')       then 'medium'
            when effort in ('hard', 'max', 'explosive') then 'high'
            else 'medium'
        end                                          as effort_bucket
    from source
    where id is not null
)

select * from cleaned
