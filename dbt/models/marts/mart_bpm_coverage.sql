{{ config(materialized='table') }}

-- BPM resolution coverage, one row per source. Backs `GET /v1/quality/coverage` (E.3) and
-- sits on the copilot's read allowlist (E.4).
--
-- The question it answers is "how much of the catalogue did each source actually resolve",
-- which is what ADR-005 traded away when it made librosa the backbone and the Deezer `bpm`
-- field mere enrichment: the spike measured that field at 23.3 % on current releases, and
-- this mart is where that stays visible in production rather than only in a report.
--
-- Read from `stg_resolutions`, NOT from `dim_track`: dim_track carries the E.2 *verdict*, one
-- row per track, so a source that disagreed and lost arbitration has already vanished from
-- it. Coverage has to count opinions, including the ones that were overruled.
--
-- `n_usable` applies E.2's own definition of "had an opinion" — stg_resolutions has already
-- nulled the non-positive values Deezer uses to mean "no BPM". No normalization happens here:
-- E.2 forbids variants, and `cyclebeat.e2` is the only implementation.

with resolutions as (
    select * from {{ ref('stg_resolutions') }}
),

catalogue as (
    -- The denominator is the whole track catalogue, not the set of tracks this source
    -- touched -- otherwise a source that resolved one track out of fifty would report 100 %.
    select count(*) as n_catalogue from {{ ref('stg_tracks') }}
),

per_source as (
    select
        source,
        count(*)                                    as n_tracks,
        count(*) filter (where bpm_raw is not null) as n_usable
    from resolutions
    group by source
)

select
    p.source,
    p.n_tracks,
    p.n_usable,
    round(100.0 * p.n_usable / nullif(c.n_catalogue, 0), 1) as pct_of_catalogue
from per_source p
cross join catalogue c
order by p.source
