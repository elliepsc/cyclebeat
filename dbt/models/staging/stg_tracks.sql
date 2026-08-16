-- One row per track, latest ingestion wins.
--
-- The lake is partitioned by ingestion date, so the same track re-ingested on a later `dt`
-- appears more than once here. `dim_track` needs one row per track, so the newest partition
-- is selected rather than deduplicated arbitrarily — re-ingesting must refresh metadata,
-- not multiply it.

with source as (
    select * from {{ source('raw', 'raw_tracks') }}
),

ranked as (
    select
        track_id,
        source_platform,
        title,
        artist,
        duration_s,
        preview_url,
        ingested_at,
        dt,
        row_number() over (partition by track_id order by dt desc, ingested_at desc) as recency
    from source
    where track_id is not null
)

select
    track_id,
    source_platform,
    title,
    artist,
    duration_s,
    preview_url,
    ingested_at,
    dt
from ranked
where recency = 1
