# XFusion v0.2.3 Execution Risk Gating

> Superseded by [execution-policy-v0.2.4.md](execution-policy-v0.2.4.md) for
> the current release baseline.

This document describes the focused v0.2.3 execution-policy increment.

v0.2.3 keeps the existing deterministic registered-capability execution model,
and adds a stricter risk-aware gating layer before any step can execute.

## Goals

- Keep execution deterministic, fail-closed, and auditable.
- Preserve the registered capability model (`capability + args`).
- Classify step risk before execution and enforce explicit policy outcomes.

## Risk Contract

Each planned step is annotated with a normalized risk contract during policy
processing:

- `risk_level`: `low | medium | high | critical`
- `requires_confirmation`: `bool`
- `deny_reason`: optional denial reason string
- `side_effects`: deterministic side-effect tags
- `reversibility`: `reversible | partially_reversible | destructive`
- `privilege_required`: `bool`

Risk contract source of truth:

- [xfusion/policy/risk.py](../../xfusion/policy/risk.py)

## Deterministic Policy Outcomes

v0.2.3 policy still returns exactly one of:

- `allow`
- `require_confirmation` (step-bound typed confirmation)
- `deny`

The policy decision remains authoritative and is derived from explicit code
rules, not model judgment.

## Rule Table Behavior

The v0.2.3 rule table is intentionally compact and explicit:

- Read-only inspection -> allow
- Bounded cleanup preview (`execute=false`) -> allow
- Unknown risky argument pattern -> deny (fail-closed)
- Broad-impact destructive mutation -> deny
- Network/system-config mutation families (not explicitly enabled) -> deny
- Destructive/process/privileged/filesystem mutation -> require confirmation
- Unclassified mutation -> deny (fail-closed)

## Confirmation Binding

Confirmations remain step-aware and exact:

- Approval record is bound to normalized args, provenance, target context,
  approval mode, risk tier, referenced output fingerprints, and risk contract.
- Material changes invalidate approval before execution.
- Confirmation for one step cannot silently apply to a materially different
  invocation.

## Execution Gate Invariants

Before adapter runtime executes a step:

1. Policy metadata must exist (`policy_rule_id` present).
2. If confirmation is required, a valid approved record must exist.
3. Approval fingerprint must still match current invocation.

If any check fails, execution fails closed and no tool is run.

## Audit Trail Additions

v0.2.3 audit events now include structured decision-trail fields per step:

- original user request
- normalized step (`step_id`, capability, normalized args)
- risk classification
- policy decision
- confirmation required/supplied flags
- execution or non-execution reason

This preserves reviewer legibility and post-incident explainability.
