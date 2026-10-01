-- Sessions, cleaned. Sourced from the TRANSACTIONAL store via the lake (ADR-009).
--
-- The previous version read the v1 `sessions` table (`title`, `playlist_url`, `track_count`),
-- which nothing writes any more since the contract-first rewrite — so this chain and the two
-- marts below it were quietly serving an empty table. ADR-008 noted that the table was dead
-- and deferred the consequence; this is the consequence.
--
-- The grain is `session_id`, the key E.3 routes on and ADR-008 introduced.

with source as (
    select * from {{ source('raw', 'sessions') }}
),

deduplicated as (
    -- One row per session. `dt` is the ingestion-date partition, so a session extracted on
    -- several days appears once per day in the lake; the latest partition wins, matching how
    -- `stg_resolutions` handles the same situation.
    select
        *,
        row_number() over (
            partition by session_id
            order by dt desc, created_at desc
        ) as recency
    from source
    where session_id is not null
),

cleaned as (
    select
        session_id,
        level,
        goal,
        duration_min,
        verdict,
        n_segments,
        duration_gap_s,

        -- What the session ACTUALLY lasts: the target plus the signed gap the planner
        -- reports. Not `duration_min * 60`, which is the request, not the plan.
        (duration_min * 60.0) + duration_gap_s       as duration_s,

        -- One segment is one track (ADR-007), so this is the count the old `track_count`
        -- meant. Kept under the old name because the marts downstream read it.
        n_segments                                   as track_count,

        created_at,
        cast(date_trunc('day', created_at) as date)  as session_date
    from deduplicated
    where recency = 1
      and duration_min > 0
)

select * from cleaned
