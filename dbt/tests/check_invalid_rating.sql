-- Fail if any feedback row carries a rating neither vocabulary recognises.
--
-- The gate that matters for the two-scale design (ADR-009): `stg_feedback` accepts E.3's
-- up/down AND the v1 Great/Okay/Hard, and everything else lands on 'Unknown'/'unknown'.
-- Testing `rating_scale` rather than only `rating` is what makes a NEW third vocabulary fail
-- loudly instead of being absorbed as a fifth rating value.
select
    session_id,
    session_title,
    rating_raw,
    rating,
    rating_scale
from {{ ref('stg_feedback') }}
where rating = 'Unknown'
   or rating_scale = 'unknown'
