-- Rating distribution with percentage — consumed by the Dash pie chart.
select
    rating,
    count(*)                                                        as count,
    round(
        100.0 * count(*) / sum(count(*)) over (),
        2
    )                                                               as pct
from {{ ref('stg_feedback') }}
group by rating
order by count desc
