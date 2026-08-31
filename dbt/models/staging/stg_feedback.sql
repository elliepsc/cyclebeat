-- Feedback, cleaned. Carries TWO rating scales side by side, and translates neither.
--
-- E.3 fixes the API's vocabulary to `up` / `down` — a **satisfaction** judgement. The v1 rows
-- already in the warehouse use `Great` / `Okay` / `Hard` — a **perceived effort** judgement.
-- These are different axes: a session can be very hard and very much enjoyed, so `down` is not
-- `Hard` and no mapping between them is measurable. Inventing one is what E.0.2 forbids, so
-- `rating_scale` says which axis a row is on and both are kept.
--
-- This is the defect that made `make dbt` red: the previous version mapped anything outside
-- Great/Okay/Hard to 'Unknown', and `check_invalid_rating` fails on 'Unknown' — so the first
-- `POST /v1/sessions/{id}/feedback` turned the next `dbt build` red. CI missed it because it
-- runs `make dbt` before any POST, against an empty table.

with source as (
    select * from {{ source('raw', 'feedback') }}
),

cleaned as (
    select
        session_id,
        session_title,
        rating                                       as rating_raw,

        -- Which axis this row is on. `unknown` is the only failure mode left, and
        -- `dbt/tests/check_invalid_rating.sql` fails on it.
        case
            when lower(rating) in ('up', 'down')     then 'satisfaction'
            when rating like '%Great%'
              or rating like '%Okay%'
              or rating like '%Hard%'                then 'effort'
            else 'unknown'
        end                                          as rating_scale,

        -- Normalized within its own scale. Never across scales.
        case
            when lower(rating) = 'up'                then 'up'
            when lower(rating) = 'down'              then 'down'
            when rating like '%Great%'               then 'Great'
            when rating like '%Okay%'                then 'Okay'
            when rating like '%Hard%'                then 'Hard'
            else 'Unknown'
        end                                          as rating,

        note,
        created_at,
        cast(date_trunc('day', created_at) as date)  as feedback_date
    from source
    -- A row needs one of the two keys to be attachable to anything. `session_id` is the real
    -- key (ADR-008); `session_title` is what the v1 rows have.
    where session_id is not null
       or session_title is not null
)

select * from cleaned
