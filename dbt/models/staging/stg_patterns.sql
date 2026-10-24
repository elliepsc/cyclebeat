-- The 40-pattern knowledge base, with `effort_bucket` derived from the pattern's `effort`.
--
-- Rule (#55): an `effort` outside the mapping below is never silently put into a bucket. It
-- comes out as `unknown`, and `dbt/tests/check_invalid_pattern_buckets.sql` fails on it, the
-- same pattern as `rating_scale = 'unknown'` and `check_invalid_rating.sql`. A new value is
-- mapped here explicitly, by the owner.
--
-- Criterion (owner decision, #55): resistance, on the `resistance_bucket` thresholds of
-- `int_pattern_effort_profile`: 3 or less -> low, 4 to 6 -> medium, 7 or more -> high. BPM is
-- not an effort criterion (`very_hard` is a climb at about 92 BPM, resistance 8). Two limits:
--   (i)  it is a labelling decision over 2 to 6 patterns per value, not a measurement;
--   (ii) `easy_moderate` (resistance 4) is the tightest case, and `moderate_hard` loses the
--        "hard" nuance on a 3-level scale.
-- The criterion labels values, not patterns: two patterns contradict it and keep their
-- value's bucket (`cadence_drill_high`: moderate, mapped before #55, resistance 3;
-- `steady_power`: moderate_hard, resistance 7).
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
        -- `light`, `tempo` and `explosive` were removed: absent from every version of the
        -- pattern file (`explosive` is a `coach_tone` value).
        case
            when effort in ('easy', 'very_easy')                          then 'low'
            when effort in ('moderate', 'easy_moderate', 'moderate_hard') then 'medium'
            when effort in ('hard', 'max', 'very_hard')                   then 'high'
            else 'unknown'
        end                                          as effort_bucket
    from source
    where id is not null
)

select * from cleaned
