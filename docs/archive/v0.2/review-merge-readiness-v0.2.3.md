> [!IMPORTANT]
> Historical, non-normative v0.2 material. This document is archived for
> historical reference only. For all current behavior, use the normative
> [docs/specs/xfusion-v0.2.md](../../specs/xfusion-v0.2.md).

# XFusion v0.2.3 Review And Merge Readiness

This note packages reviewer-facing artifacts for the v0.2.3 focused execution
policy increment. Normative behavior remains
[docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md).

## PR Summary

- Adds deterministic per-step risk classification on top of the existing
  registered capability execution model.
- Enforces explicit allow / require_confirmation / deny policy outcomes through
  a compact code-defined policy table.
- Keeps approval step-bound and tightens fingerprint binding to include risk
  contract metadata.
- Hardens execution so steps cannot run without policy metadata and approved
  confirmation where required.
- Extends audit records with a structured decision trail for policy and
  confirmation outcomes.

## Release Notes (v0.2.3)

- Introduced normalized risk contract fields per step: risk level,
  confirmation requirement, deny reason, side effects, reversibility, and
  privilege requirement.
- Added deterministic risk traits + policy rule table in
  `xfusion/policy/risk.py` and integrated it into `evaluate_policy`.
- Added fail-closed handling for unknown risky argument patterns and
  unclassified mutation paths.
- Added execution preflight guardrails for missing policy metadata and missing
  approval state when confirmation is required.
- Extended audit payloads to include normalized step, risk classification,
  policy decision snapshot, confirmation state, and non-execution reason.

## How To Review Safely

Review in this order:

1. [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md)
2. [docs/architecture/execution-policy-v0.2.3.md](architecture/execution-policy-v0.2.3.md)
3. [xfusion/policy/risk.py](../xfusion/policy/risk.py)
4. [xfusion/policy/rules.py](../xfusion/policy/rules.py)
5. [xfusion/graph/nodes/policy.py](../xfusion/graph/nodes/policy.py)
6. [xfusion/graph/nodes/execute.py](../xfusion/graph/nodes/execute.py)
7. [xfusion/graph/auditing.py](../xfusion/graph/auditing.py)
8. [tests/test_v023_risk_gating.py](../tests/test_v023_risk_gating.py)

Review checks to prioritize:

- Risky steps cannot bypass policy evaluation.
- Confirmation-gated steps do not execute without exact approved binding.
- Denied actions fail closed and do not run adapters.
- Unknown risky patterns are denied by default.
- Audit trail contains policy + confirmation decision artifacts for each step.

## Required Verification Gate

Before merge/release:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## Residual Risks (Post-v0.2.3, Explicit)

- Risk policy remains intentionally compact and capability-family based; it is
  not a broad semantic command analyzer.
- Capability set is still intentionally limited; network/firewall/package
  mutation families remain denied unless explicitly introduced later.
- Runtime containment remains deterministic guardrails, not full OS sandboxing.
