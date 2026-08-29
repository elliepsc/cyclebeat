-- mart_bpm_coverage must stay internally coherent.
--
-- A singular test rather than a package generic, matching the convention the other tests in
-- this folder already follow — the repo installs no dbt package, so `dbt build` works on a
-- clean clone with no `dbt deps` step.
--
-- Two ways this mart can lie:
--   1. `n_usable > n_tracks` — more usable opinions than opinions, which means the filter and
--      the count drifted apart.
--   2. `pct_of_catalogue > 100` — the denominator stopped being the whole catalogue, the exact
--      bug that would make a source resolving 1 track of 50 report full coverage.

select
    source,
    n_tracks,
    n_usable,
    pct_of_catalogue
from {{ ref('mart_bpm_coverage') }}
where n_usable > n_tracks
   or n_usable < 0
   or pct_of_catalogue < 0
   or pct_of_catalogue > 100
