# AGENTS.md — CycleBeat (Codex / other agents)

The reference is **`CLAUDE.md`** at the root — read it in full and apply it.
This file is only a pointer (Codex reads AGENTS.md): never fork the rules.

Non-negotiable reminders if CLAUDE.md is unreachable:
1. Truth sources: repo code > Appendix E of the V3 plan > V3 plan > V2 plan §6-9.
2. Nothing invented: ambiguity → question or 2 quantified options.
3. One phase = one branch + one PR; DoD = `make lint && make test-unit && make dbt` green.
4. Prohibitions: secrets/.env; openapi.yaml modified without backend+front in the same PR;
   SQL outside repositories/ and dbt/; unjustified dependency; paid brick (zero cost).
5. E.2 formulas (confidence, BPM normalization, zones): normative, no variant.
6. Every session ends with an entry in docs/ai-workflow.md.
