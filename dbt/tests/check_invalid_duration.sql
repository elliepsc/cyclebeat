-- Fail if any session has a nonsensical duration (≤0 or >2 hours).
select *
from {{ ref('stg_sessions') }}
where duration_s <= 0
   or duration_s > 7200
