# XFusion v0.2.2 Review And Merge Readiness

This note packages reviewer-facing artifacts for the v0.2.2 production-depth
hardening pass. Normative behavior remains
[docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md).

## PR Summary

- Strengthens deterministic repair/equivalence handling without opening a new
  policy or execution architecture track.
- Keeps repair lineage and re-entry semantics explicit and auditable.
- Clarifies practical containment boundaries in runtime-facing paths and
  hardens verification guardrails where feasible in the current repo model.
- Expands high-value regression and hardening tests while keeping fail-closed
  behavior explicit.
- Cleans reviewer-facing hygiene and historical references so current authority
  boundaries are easier to audit.

## Release Notes (v0.2.2)

- Removed compatibility-era `PlanStep` alias normalization (`id`, `tool`,
  `parameters`, `dependencies`) from authoritative model parsing.
- Standardized tests and fixtures around canonical `step_id` and `args` usage.
- Hardened verification method mapping for bounded filesystem-style capabilities
  and aligned runner expectations.
- Updated CLI and documentation wording to reflect v0.2.2 hardening baseline.
- Fixed broken historical archive links and retained historical materials under
  explicit non-normative markings.

## How To Review Safely

Review in this order:

1. [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md)
2. [docs/release-readiness-v0.2.md](release-readiness-v0.2.md)
3. [xfusion/domain/models/execution_plan.py](../xfusion/domain/models/execution_plan.py)
4. [xfusion/graph/nodes/verify.py](../xfusion/graph/nodes/verify.py)
5. [xfusion/verification/runner.py](../xfusion/verification/runner.py)
6. [tests/test_v02_contracts.py](../tests/test_v02_contracts.py)
7. [tests/test_v02_hardening.py](../tests/test_v02_hardening.py)
8. [tests/test_verification_repair_roles.py](../tests/test_verification_repair_roles.py)

Review checks to prioritize:

- No compatibility aliases are silently accepted in authoritative parsing.
- Unknown/unsupported forms still fail closed before execution.
- Repair/equivalence does not bypass validation, policy, or approval.
- Inconclusive verification is not promoted to success.
- User-visible responses remain derived from authoritative audit state.

## Required Verification Gate

Before merge/release:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## Residual Risks (Post-v0.2.2, Explicit)

- Repair generation remains deterministic and intentionally bounded, not a broad
  semantic planner.
- Equivalent-repair approval reuse remains fail-closed and policy-gated; richer
  policy-table expressiveness can still expand.
- Role boundary and containment controls remain runtime/declarative guardrails,
  not full OS-level sandbox isolation.
- Verification corpus breadth improved but can still grow across additional
  adversarial and fault-injection classes.
