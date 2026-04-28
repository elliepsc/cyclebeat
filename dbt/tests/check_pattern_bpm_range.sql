-- Fail if any pattern has an inverted or out-of-range BPM window.
select *
from {{ ref('stg_patterns') }}
where bpm_min >= bpm_max
   or bpm_min < 40
   or bpm_max > 220
