# XFusion v0.2.4 Execution Policy Integrity

This document describes the focused v0.2.4 hardening increment on top of v0.2.3.

v0.2.4 keeps the same deterministic, registered-capability execution model and
adds stronger machine-readable policy normalization plus execute-time integrity
binding.

## Normalized Policy Fields

Policy and risk metadata now separate machine codes from human text:

- `decision`: `allow | require_confirmation | deny`
- `confirmation_type`: `none | user | admin`
- `deny_code`: stable machine-readable denial code
- `reason_text`: human-readable explanation
- `non_execution.code`: stable machine-readable non-execution reason
- `non_execution.reason_text`: human-readable non-execution explanation

The step risk contract also carries normalized fields:

- `risk_level`: `low | medium | high | critical`
- `requires_confirmation`: `bool`
- `confirmation_type`: `none | user | admin`
- `deny_code`: stable code when denied
- `deny_reason_text`: human-readable deny reason

## Risk Semantics

v0.2.4 enforces deterministic risk semantics:

- `low` -> `allow`
- `medium` -> `require_confirmation` with `confirmation_type=user`
- `high` -> `require_confirmation` with `confirmation_type=admin`
- `critical` -> `deny` (fail-closed default)

`high` is now explicitly enforced (for example destructive/process-control
mutations), and no longer collapses into `medium` behavior.

## Execute-Time Integrity Layer

Every step now has a deterministic policy snapshot hash bound to:

- capability name
- normalized args
- argument provenance
- policy decision metadata
- risk contract
- environment state
- step binding (`plan_id`, `step_id`, step index, dependencies, repair lineage)

Before execution, policy is always re-evaluated and a new snapshot hash is
computed. If stored and live hashes differ, execution fails closed with
`policy_integrity_mismatch` and no tool call is made.

## Approval Binding Hardening

Approval action fingerprints now additionally bind:

- `policy_snapshot_hash`
- deterministic `step_binding` (including step index and dependencies)

This prevents replay or reuse when plan structure, step identity/order,
dependencies, policy state, or normalized invocation materially change.

`high` risk approvals use `ADMIN_APPROVE ...` typed confirmation phrases.
`medium` risk approvals continue to use `APPROVE ...`.

## Multi-Step / Cross-Turn Guarantees

v0.2.4 enforces the following invariants:

1. Policy is rechecked at execute time for every step.
2. A step approved under one snapshot cannot execute under a changed snapshot.
3. Step reorder/mutation invalidates previously issued approvals.
4. Argument/provenance/reference drift invalidates previously issued approvals.
5. If integrity cannot be proven, execution fails closed.

## Audit Trail Updates

Audit records now include normalized policy and non-execution fields:

- `policy_decision_code`
- `confirmation_type`
- `deny_code`
- `non_execution` object with `code` and `reason_text`

Legacy `non_execution_reason` string remains for compatibility.

## Out of Scope (Unchanged)

- No arbitrary shell passthrough.
- No broad semantic planner.
- No capability surface expansion beyond registered tools.
- No OS/container runtime isolation redesign.
