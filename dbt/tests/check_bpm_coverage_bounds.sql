-- `mart_bpm_coverage.pct_of_catalogue` must be computed over the WHOLE catalogue.
--
-- A singular test rather than a package generic, matching the convention of the other tests
-- in this folder — the repo installs no dbt package, so `dbt build` works on a clean clone
-- with no `dbt deps` step.
--
-- The earlier version of this test asserted `pct_of_catalogue > 100` and claimed to catch "a
-- source resolving 1 track of 50 reporting full coverage". It did not: with a per-source
-- denominator that case yields exactly 100.0, which is inside the bound. The test was green
-- and the bug would have shipped. So this one PINS the denominator instead of bounding the
-- result — the arithmetic is restated here, independently of the model, and any drift in
-- either direction fails.
--
-- The `round(..., 1)` mirrors the model; comparing unrounded would fail on float noise.

with catalogue as (
    select count(*) as n_catalogue from {{ ref('stg_tracks') }}
),

expected as (
    select
        c.source,
        c.n_tracks,
        c.n_usable,
        c.pct_of_catalogue,
        round(100.0 * c.n_usable / nullif(t.n_catalogue, 0), 1) as pct_expected
    from {{ ref('mart_bpm_coverage') }} c
    cross join catalogue t
)

select *
from expected
where pct_of_catalogue is distinct from pct_expected
   -- Structural sanity, kept because they are cheap and one of them is reachable: an orphan
   -- track_id present in stg_resolutions but absent from stg_tracks would push a share above
   -- the catalogue size.
   or n_usable > n_tracks
   or n_usable < 0
   or pct_of_catalogue < 0
   or pct_of_catalogue > 100
