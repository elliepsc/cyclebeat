# ADR-B6 — Kubernetes outside the core track (only if DevOps target)

- **Status**: Proposed · **Gated**
- **Module**: B6 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

The core deployment is Render + docker-compose (sufficient for the grid). B6 would deploy the stack on a local
**kind** cluster + **K8sGPT** for operational diagnosis (improves the crit. 13 "operational diagnosis" artifact).
V3.1 already classified it as "optional if time permits".

## Decision drivers

- Ellie's goal is "**a little** DataOps", not deep DevOps/infra.
- Zero cost (local kind, OSS K8sGPT).
- **Low** career ROI for a DE/AE target; **real** only for a DevOps-adjacent target.

## Options

- **A — Don't do B6** unless there's an explicit reorientation toward a DevOps role. **Recommended by default.**
- B — Do B6: manifests/Helm on kind + K8sGPT on an injected failure. Take only if the job target changes.

## Decision (proposed)

**Option A** by default: B6 stays `Gated` and **non-priority**. Move to B (implementation) only if Ellie
explicitly targets DevOps/platform roles. The other bonuses (B1–B5) take precedence without exception.

## Consequences

- No work as long as the target remains DE/AE + LLM/agentic.
- If activated: kind cluster, manifests/Helm, documented K8sGPT diagnosis, ADR moved to `Accepted`.

## Gate opening condition

Core V3.1 deployed **and** assumed reorientation toward DevOps. Otherwise, stay `Gated` indefinitely.
