{{ config(materialized='table') }}

-- The E.2 session fact. Grain: `session_id`.
--
-- E.2 declares this table; ADR-008 had the API write it directly into DuckDB, and ADR-009
-- corrects that: the API writes the TRANSACTIONAL store, the pipeline ingests it, and the
-- fact table is modelled here like every other mart. The API owns no warehouse table.
--
-- `llm_cost_usd` and `latency_ms` are declared by E.2 and stay NULL until phase 6 wires
-- LiteLLM. They are present rather than added later so the shape matches the appendix now.

with sessions as (
    select * from {{ ref('stg_sessions') }}
)

select
    session_id,
    level,
    goal,
    duration_min,
    verdict,
    n_segments,
    duration_gap_s,
    duration_s,

    cast(null as double)  as llm_cost_usd,
    cast(null as integer) as latency_ms,

    created_at,
    session_date
from sessions
