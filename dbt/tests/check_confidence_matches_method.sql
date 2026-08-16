-- Fail if a track's confidence score does not match the E.2 branch that produced it.
--
-- This is the contract test for the confidence rule: E.2 allows no other formula, and
-- ADR-006 fixes the one value E.2 left open (arbitration scores 0.6). A mismatch here means
-- the Python resolver and the appendix have diverged — a breaking data-contract change, not
-- a tuning issue.
--
-- Pairing asserted:
--   cross_validated     -> 0.9
--   single_source       -> 0.6
--   librosa_arbitrated  -> 0.6   (ADR-006)
--   review              -> 0.3
--   unknown             -> NULL, and bpm_effective NULL

select
    track_id,
    confidence_method,
    confidence,
    bpm_effective
from {{ ref('dim_track') }}
where
    (confidence_method = 'cross_validated'    and confidence is distinct from 0.9)
 or (confidence_method = 'single_source'      and confidence is distinct from 0.6)
 or (confidence_method = 'librosa_arbitrated' and confidence is distinct from 0.6)
 or (confidence_method = 'review'             and confidence is distinct from 0.3)
 or (confidence_method = 'unknown'            and (confidence is not null
                                                   or bpm_effective is not null))
