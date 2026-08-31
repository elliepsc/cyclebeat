-- Rating distribution, per scale.
--
-- Grouped on (rating_scale, rating), not on rating alone: the two vocabularies coexist
-- (ADR-009), and a percentage computed across both would divide satisfaction counts by an
-- effort denominator. The share is therefore within each scale.
select
    rating_scale,
    rating,
    count(*)                                                        as count,
    round(
        100.0 * count(*) / sum(count(*)) over (partition by rating_scale),
        2
    )                                                               as pct
from {{ ref('stg_feedback') }}
group by rating_scale, rating
order by rating_scale, count desc
