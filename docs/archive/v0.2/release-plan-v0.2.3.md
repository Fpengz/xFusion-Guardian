> [!IMPORTANT]
> Historical, non-normative v0.2 material. This document is archived for
> historical reference only. For all current behavior, use the normative
> [docs/specs/xfusion-v0.2.md](../../specs/xfusion-v0.2.md).

# XFusion v0.2.3 Release Plan

## Release Framing

v0.2.3 is a focused, shippable execution-policy increment for the existing v0.2
architecture.

Normative source remains:

- [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md)

Primary objective: add deterministic risk-aware execution gating on top of the
registered capability model without opening a v0.3 redesign track.

## Implemented Scope

### V023-WS1: Deterministic Risk Classification Contract

- Added deterministic per-step risk classification before execution.
- Added normalized risk contract fields:
  - `risk_level` (`low|medium|high|critical`)
  - `requires_confirmation`
  - `deny_reason`
  - `side_effects`
  - `reversibility`
  - `privilege_required`
- Integrated risk metadata into `PolicyDecision` and `PlanStep` audit-visible
  state.

### V023-WS2: Policy Table For Allow / Confirm / Deny

- Added explicit deterministic policy rule table in
  [xfusion/policy/risk.py](../xfusion/policy/risk.py).
- Kept fail-closed defaults for risky unknown patterns and unclassified
  mutation paths.
- Preserved protected-path and scope-denial guardrails.

### V023-WS3: Confirmation Gating And Approval Binding Hardening

- Confirmation-gated steps now pause until exact typed confirmation.
- Approval action fingerprint now includes risk-contract metadata, tightening
  step-bound approval reuse guarantees.
- Materially different args/risk profile invalidate approval before execution.

### V023-WS4: Executor Non-Bypass Guardrails

- Execution now refuses steps that bypass policy metadata.
- If execution is called directly (test/runtime edge), policy is re-evaluated
  deterministically and fail-closed behavior is enforced.
- Confirmation-required steps fail closed when approval state is missing or
  invalid.

### V023-WS5: Structured Audit Decision Trail

- Extended per-step audit records with:
  - normalized step payload
  - risk classification
  - policy decision snapshot
  - confirmation required/supplied flags
  - non-execution reason

## Test Coverage Added

- Read-only commands execute without confirmation.
- Mutations require confirmation with step-bound approval.
- Unknown risky patterns are denied fail-closed.
- Confirmation cannot be reused across materially changed commands.
- Dependency workflows still gate mutation steps safely.
- Audit output includes policy/risk/confirmation decision trail.

Primary test artifact:

- [tests/test_v023_risk_gating.py](../tests/test_v023_risk_gating.py)

## Deferred To v0.3

- Broader command-family coverage beyond the current registered capability set.
- Richer policy-table configurability and environment profile overrides.
- Stronger physical runtime isolation/sandboxing (outside v0.2.3 scope).
- Expanded verification corpus for additional adversarial policy permutations.
