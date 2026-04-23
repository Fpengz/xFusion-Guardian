# XFusion v0.2.4 Release Notes

## Summary

v0.2.4 is a focused hardening increment that keeps the v0.2 architecture and
registered-capability model intact while improving policy integrity and audit
machine-readability.

## Implemented

- Normalized machine-readable policy outputs (`decision`, `confirmation_type`,
  `deny_code`) with separate human-readable `reason_text`.
- Normalized machine-readable non-execution reason codes with human-readable
  text, propagated into step state and audit records.
- Explicit `high` risk semantics with admin confirmation path (`ADMIN_APPROVE`
  typed confirmation phrase).
- Deterministic execute-time policy integrity checks using per-step policy
  snapshot hashes.
- Approval fingerprint hardening with policy snapshot and step-binding data,
  preventing replay across step/order/dependency/state drift.
- Adversarial tests for stale snapshots, risk drift, argument mutation,
  reordered plan tampering, and normalized audit-code output.

## Not Changed (Intentional)

- No arbitrary shell execution.
- No broad semantic planner.
- No expansion beyond registered typed capabilities.
- No physical sandbox/isolation redesign.

## Residual Limitations

- Policy coverage remains compact and capability-family based.
- Admin confirmation remains typed-confirmation semantics, not identity-backed
  external auth.
- Runtime isolation remains declarative and policy-guarded, not OS-level
  sandboxing.

## Suggested Follow-ons (Post-v0.2.4)

1. Add identity-bound admin confirmation (for example external principal
   attestation) while preserving deterministic approval fingerprints.
2. Expand policy-table coverage for more capability families and environment
   profiles.
3. Extend adversarial verification scenarios for broader cross-turn/session
   replay simulations.
4. Add optional signed audit snapshots for stronger offline tamper evidence.
