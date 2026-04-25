> [!IMPORTANT]
> Historical, non-normative v0.2 material. This document is archived for
> historical reference only. For all current behavior, use the normative
> [docs/specs/xfusion-v0.2.md](../../specs/xfusion-v0.2.md).

# XFusion v0.2.1 Review And Merge Readiness

This note packages reviewer-facing artifacts for the current patch-level
hardening pass. Normative behavior remains
[docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md).

## PR Summary

- Strengthens verification/repair semantics with explicit typed artifacts and
  auditable repair lineage.
- Ensures materially changed repairs re-enter deterministic validation, policy,
  and approval paths through normal graph flow.
- Adds runtime-attributed role-boundary enforcement records with deterministic
  accepted/rejected/downgraded disposition.
- Expands verification-dataset integration with focused high-value cases for
  repair and role-boundary invariants.
- Preserves fail-closed posture and does not reintroduce legacy authority
  surfaces.

## Release Notes (v0.2.1)

- Added typed verification and repair models, including trigger/equivalence/
  approval requirement linkage.
- Added runtime role proposal enforcement records and audit visibility for role
  provenance.
- Added targeted verification dataset scenarios and tests for:
  failed verification repair proposals, repair re-entry and reapproval, TERM to
  KILL escalation, target-change approval invalidation, inconclusive
  verification handling, and role proposal rejection.
- Improved reviewer documentation and cross-links for merge readiness.

## How To Review Safely

Review in this order to minimize ambiguity:

1. [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md)
2. [docs/architecture/capability-schema.md](architecture/capability-schema.md)
3. [xfusion/domain/models/verification.py](../xfusion/domain/models/verification.py)
4. [xfusion/graph/nodes/verify.py](../xfusion/graph/nodes/verify.py)
5. [xfusion/roles/contracts.py](../xfusion/roles/contracts.py)
6. [xfusion/graph/auditing.py](../xfusion/graph/auditing.py)
7. [tests/test_verification_repair_roles.py](../tests/test_verification_repair_roles.py)
8. [docs/release-readiness-v0.2.md](release-readiness-v0.2.md)

Review checks to prioritize:

- No role proposal directly authorizes execution.
- No repair bypasses validation/policy/approval.
- Inconclusive verification is not treated as success.
- Approval reuse requires deterministic equivalence and explicit policy allow.
- Final explanation remains derived from authoritative audit state.

## Known Limitations (Current, Explicit)

- Repair generation is narrow and deterministic, not broad semantic planning.
- Equivalent-repair approval reuse uses a simple explicit policy gate and is not
  yet backed by richer policy-table declarations.
- Role boundaries are runtime-enforced and auditable but not physically isolated
  runtimes/processes.
- Runtime network/containment controls are deterministic/declarative but not
  full OS-level sandbox isolation.
- Verification dataset coverage is strong in repair/role areas but still
  expandable across broader adversarial/fault classes.

## Follow-On Hardening Track

1. Expand deterministic repair proposal library and semantic repair templates.
2. Move equivalent-repair reuse decisions to richer policy-table-driven rules.
3. Introduce physical/runtime isolation per reasoning role.
4. Add stronger OS-level containment/network sandbox controls.
5. Expand verification dataset breadth and CI coverage reporting.
