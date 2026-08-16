-- One row per (track_id, source), latest partition wins — the E.5 idempotency key.
--
-- E.2 normalization is NOT applied here. It runs once, in `cyclebeat.e2`, and E.2 forbids
-- variants: a second implementation in SQL would be exactly the "local heuristic" the
-- half/double-time pitfall warns about. This model only cleans and deduplicates.
--
-- A non-positive bpm_raw is absence of a source, not a tempo: Deezer encodes "no BPM" as
-- exactly 0, and the loops in E.2's normalization do not terminate on 0. It is nulled here
-- so downstream counts of "sources that had an opinion" stay honest.

with source as (
    select * from {{ source('raw', 'raw_resolutions') }}
),

ranked as (
    select
        track_id,
        source,
        case when bpm_raw > 0 then bpm_raw end as bpm_raw,
        resolved_at,
        latency_ms,
        dt,
        row_number() over (
            partition by track_id, source
            order by dt desc, resolved_at desc
        ) as recency
    from source
    where track_id is not null
      and source is not null
)

select
    track_id,
    source,
    bpm_raw,
    resolved_at,
    latency_ms,
    dt
from ranked
where recency = 1
