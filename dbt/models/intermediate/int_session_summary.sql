-- One row per session, enriched with feedback aggregates. Grain: `session_id`.

with sessions as (
    select * from {{ ref('stg_sessions') }}
),

feedback as (
    select * from {{ ref('stg_feedback') }}
),

aggregated as (
    select
        s.session_id,
        s.level,
        s.goal,
        s.verdict,
        s.session_date,
        s.created_at,
        s.duration_s,
        s.duration_min,
        s.duration_gap_s,
        s.track_count,

        count(f.session_id)                                          as feedback_count,

        -- Counted per scale. Mixing them would let an `effort` rating move a satisfaction
        -- figure, which is exactly the conflation ADR-009 refuses.
        sum(case when f.rating = 'up'    then 1 else 0 end)          as positive_count,
        sum(case when f.rating = 'down'  then 1 else 0 end)          as negative_count,
        sum(case when f.rating = 'Great' then 1 else 0 end)          as great_count,
        sum(case when f.rating = 'Okay'  then 1 else 0 end)          as okay_count,
        sum(case when f.rating = 'Hard'  then 1 else 0 end)          as hard_count,

        -- Satisfaction over the rows that actually express satisfaction. NULL when none do,
        -- rather than 0 %, which would read as "everyone disliked it".
        case
            when sum(case when f.rating_scale = 'satisfaction' then 1 else 0 end) = 0
                then null
            else round(
                100.0 * sum(case when f.rating = 'up' then 1 else 0 end)
                / sum(case when f.rating_scale = 'satisfaction' then 1 else 0 end), 1)
        end                                                          as satisfaction_pct

    from sessions s
    left join feedback f on s.session_id = f.session_id
    group by
        s.session_id, s.level, s.goal, s.verdict, s.session_date,
        s.created_at, s.duration_s, s.duration_min, s.duration_gap_s, s.track_count
)

select * from aggregated
