-- One row per session, enriched with feedback aggregates.
with sessions as (
    select * from {{ ref('stg_sessions') }}
),

feedback as (
    select * from {{ ref('stg_feedback') }}
),

aggregated as (
    select
        s.title,
        s.playlist_url,
        s.session_date,
        s.created_at,
        s.duration_s,
        s.duration_min,
        s.track_count,
        count(f.session_title)                                      as feedback_count,
        sum(case when f.rating = 'Great' then 1 else 0 end)         as great_count,
        sum(case when f.rating = 'Okay'  then 1 else 0 end)         as okay_count,
        sum(case when f.rating = 'Hard'  then 1 else 0 end)         as hard_count,
        case
            when count(f.session_title) = 0 then null
            else round(
                100.0 * sum(case when f.rating = 'Great' then 1 else 0 end)
                / count(f.session_title), 1)
        end                                                         as satisfaction_pct
    from sessions s
    left join feedback f on s.title = f.session_title
    group by
        s.title, s.playlist_url, s.session_date,
        s.created_at, s.duration_s, s.duration_min, s.track_count
)

select * from aggregated
