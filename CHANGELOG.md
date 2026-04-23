# Changelog

## v0.2.2 - 2026-04-23

- Expanded deterministic verification-repair hardening with explicit
  equivalence/reapproval behavior and stricter fail-closed tests for escalation,
  non-equivalence, and inconclusive outcomes.
- Clarified runtime containment boundary expectations (deterministic guardrails,
  not OS sandboxing) and hardened verification dispatch mappings used for
  bounded filesystem-style operations.
- Expanded verification and regression coverage across repair, role-boundary,
  and workflow invariants with canonical `step_id`/`args` contracts.
- Completed hygiene sweep for reviewer clarity: fixed archive broken links,
  removed stale compatibility normalization codepaths, updated CLI/reviewer
  wording, and preserved historical materials with explicit archive marking.
- Preserved v0.2 architecture authority and fail-closed posture; no new
  execution surface or policy model was introduced.

## v0.2.1 - 2026-04-23

- Hardened verification and repair lifecycle with explicit typed artifacts,
  verification-to-repair lineage, and deterministic re-entry behavior.
- Added runtime-attributed role-boundary enforcement records and audit
  provenance visibility for accepted/rejected/downgraded role proposals.
- Added focused verification-dataset scenarios and tests for repair and role
  boundary invariants.
- Performed architecture hygiene sweep: removed legacy v0.1 compatibility
  aliases (`tool`, `parameters`, `id`, `dependencies`) from authoritative models
  and transitioned execution runtime to canonical `args` and `step_id`.
- Improved reviewer/merge readiness documentation and start-here pointers.

## v0.2.0

- Introduced capability-governed deterministic pipeline aligned to
  [docs/specs/xfusion-v0.2.md](docs/specs/xfusion-v0.2.md).
