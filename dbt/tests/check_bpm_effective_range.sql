-- Fail if any resolved BPM falls outside the plausible range.
--
-- E.2's normalization is supposed to land every value in [70, 180]; the wider [40, 220]
-- window is what the pattern knowledge base already uses (`check_pattern_bpm_range.sql`),
-- so a row here means normalization did not run at all, not that a track is unusual.
-- NULL is legitimate — E.2's "no source" case — and is excluded rather than failed.
select
    track_id,
    bpm_effective,
    confidence_method
from {{ ref('dim_track') }}
where bpm_effective is not null
  and (bpm_effective < 40 or bpm_effective > 220)
