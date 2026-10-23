-- Fail unless `mart_session_kpis` holds exactly one row — its grain, empty history included.
--
-- A global aggregate with no GROUP BY returns one row even over zero sessions; a change that
-- adds a grouping, or a join that fans out, would break that silently for every consumer
-- reading "the" KPI row.
select count(*) as n_rows
from {{ ref('mart_session_kpis') }}
having count(*) <> 1
