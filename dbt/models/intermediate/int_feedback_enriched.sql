-- Feedback joined with session context — the decision layer for quality analysis.
--
-- Joined on `session_id` (ADR-008), not on the title. A title is a mutable, non-unique
-- display string; two sessions called the same thing were indistinguishable, which is the
-- defect the rekeying fixed. The title join is kept as a FALLBACK for v1 rows, which predate
-- `session_id` and have nothing else to match on.

with feedback as (
    select * from {{ ref('stg_feedback') }}
),

sessions as (
    select * from {{ ref('stg_sessions') }}
)

select
    f.session_id,
    f.session_title,
    f.rating,
    f.rating_raw,
    f.rating_scale,
    f.note,
    f.feedback_date,
    f.created_at                              as feedback_at,

    s.level,
    s.goal,
    s.verdict,
    s.duration_s,
    s.duration_min,
    s.track_count,

    -- Scale-aware flags. A row on the `effort` scale has no opinion on satisfaction and vice
    -- versa, so each flag is NULL outside its own scale rather than a misleading 0 — which is
    -- what averaging them later depends on.
    case when f.rating_scale = 'satisfaction' then
        case when f.rating = 'up' then 1 else 0 end
    end                                       as is_positive,
    case when f.rating_scale = 'effort' then
        case when f.rating = 'Hard' then 1 else 0 end
    end                                       as is_hard

from feedback f
left join sessions s
    on  f.session_id = s.session_id
    or (f.session_id is null and f.session_title = s.session_id)
