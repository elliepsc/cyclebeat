# ops/ — operational diagnosis (criterion 13)

| Incident | Diagnosis | Evidence |
|---|---|---|
| Postgres stopped, API still `(healthy)`, session generation 500 (reproduced 15 October 2026 on the `cyclebeat-it` compose project) | [incident-2026-10-15-postgres-down.md](incident-2026-10-15-postgres-down.md) | [script](evidence/2026-10-15-postgres-down.sh), [raw log](evidence/2026-10-15-postgres-down.log) |

Rule: an incident is reproduced on a disposable compose project, never production; every
statement in a diagnosis cites a line of the committed raw output; the correction is recorded in
`docs/ROADMAP.md`, coded in its own PR.
