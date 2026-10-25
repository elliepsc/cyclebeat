-- Feedback joined with session context — the decision layer for quality analysis.
--
-- Grain: one row represents one feedback of `stg_feedback`, with the context of the session it
-- rates when it carries a `session_id`. Key: (session_id, session_title, feedback_at), asserted
-- by `dbt/tests/check_feedback_enriched_grain.sql`.
--
-- Joined on `session_id` only (ADR-008), the same rule as `int_session_summary`. A title is a
-- mutable, non-unique display string; two sessions called the same thing were
-- indistinguishable, which is the defect the rekeying fixed.
--
-- v1 rows keep a NULL `session_id` (ADR-008: nothing back-fills a guess), so they have no
-- session context here. Their `session_title` is the v1 session's display title, and no
-- modelled session carries one any more: the title fallback this join used to have compared
-- it with `s.session_id`, which matches nothing by design and attached a row only by
-- coincidence (#60).

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
    on f.session_id = s.session_id
