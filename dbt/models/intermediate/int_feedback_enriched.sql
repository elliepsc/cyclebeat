-- Feedback joined with session context — the decision layer for quality analysis.
with feedback as (
    select * from {{ ref('stg_feedback') }}
),

sessions as (
    select * from {{ ref('stg_sessions') }}
)

select
    f.session_title,
    f.rating,
    f.rating_raw,
    f.note,
    f.feedback_date,
    f.created_at                              as feedback_at,
    s.duration_s,
    s.duration_min,
    s.track_count,
    s.playlist_url,
    case
        when f.rating = 'Great' then 1
        else 0
    end                                       as is_great,
    case
        when f.rating = 'Hard'  then 1
        else 0
    end                                       as is_hard

from feedback f
left join sessions s on f.session_title = s.title
