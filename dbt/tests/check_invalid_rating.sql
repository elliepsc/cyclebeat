-- Fail if any feedback entry has an unrecognised rating (data quality gate).
select *
from {{ ref('stg_feedback') }}
where rating = 'Unknown'
