-- Fail if the confidence distribution does not account for the whole catalogue.
--
-- Every track lands in exactly one E.2 branch, so the shares must sum to 100 % and the
-- track counts must equal `dim_track`. A drift here means tracks are being dropped or
-- double-counted somewhere between the lake and the mart — the kind of silent loss a
-- coverage report is supposed to expose rather than hide.
with totals as (
    select
        sum(n_tracks)         as counted_tracks,
        sum(pct_of_catalogue) as counted_share
    from {{ ref('mart_data_quality') }}
),

expected as (
    select count(*) as n_tracks from {{ ref('dim_track') }}
)

select
    totals.counted_tracks,
    expected.n_tracks,
    totals.counted_share
from totals
cross join expected
where totals.counted_tracks != expected.n_tracks
   or abs(totals.counted_share - 100.0) > 0.5
