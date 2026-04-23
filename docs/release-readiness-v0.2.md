# XFusion v0.2 Reviewer Notes

This note summarizes the merge/release posture for the v0.2 implementation. The
normative behavior remains [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md).

## What Changed

- v0.2.4 keeps deterministic per-step risk classification and adds normalized
  machine-readable policy outputs (`decision`, `confirmation_type`,
  `deny_code`) with separate human-readable reasoning text.
- v0.2.4 makes `high` risk explicit and enforced through admin confirmation
  semantics, while preserving fail-closed deny behavior for `critical`.
- v0.2.4 adds execute-time policy integrity snapshots and stronger approval
  binding against step/order/dependency/state drift.
- v0.2.4 audit records now include normalized policy/non-execution code fields
  in addition to human-readable summaries.
- Execution is capability governed: plans invoke registered `capability + args`
  contracts instead of the legacy `tool + parameters` surface.
- Static validation rejects unknown capabilities, conflicting legacy fields,
  invalid dependencies, fabricated references, unknown args, and schema
  mismatches before policy or execution.
- Legacy-only invocation fields are fail-closed: `tool`, `parameters`, and
  `dependencies` cannot be used without canonical `capability`, `args`, and
  `depends_on`.
- Policy, approval, runtime constraints, output normalization, redaction,
  verification, and audit records form the deterministic authority path.
- Adapter outputs are centrally schema-validated before they can be audited as
  successful outcomes, referenced by downstream steps, or used in final
  explanations.
- Final responses are derived from authoritative audit state, including the
  final explanation snapshot.
- Verification outcomes and repairs are now typed and auditable, including
  verification-to-repair transition linkage and deterministic repair re-entry.
- Runtime role-boundary enforcement now records attributable accepted/rejected/
  downgraded role proposals in audit-visible state.

## Reviewer Path

For the main execution path, read these files in order:

1. [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md)
2. [xfusion/domain/models/execution_plan.py](../xfusion/domain/models/execution_plan.py)
3. [xfusion/capabilities/registry.py](../xfusion/capabilities/registry.py)
4. [xfusion/planning/validator.py](../xfusion/planning/validator.py)
5. [xfusion/planning/reference_resolver.py](../xfusion/planning/reference_resolver.py)
6. [xfusion/policy/rules.py](../xfusion/policy/rules.py)
7. [xfusion/execution/runtime.py](../xfusion/execution/runtime.py)
8. [xfusion/graph/auditing.py](../xfusion/graph/auditing.py)
9. [xfusion/graph/response.py](../xfusion/graph/response.py)
10. [tests/test_v02_contracts.py](../tests/test_v02_contracts.py) and
    [tests/test_v02_hardening.py](../tests/test_v02_hardening.py)
11. [xfusion/graph/nodes/verify.py](../xfusion/graph/nodes/verify.py)
12. [xfusion/roles/contracts.py](../xfusion/roles/contracts.py)
13. [xfusion/domain/models/verification.py](../xfusion/domain/models/verification.py)
14. [tests/test_verification_repair_roles.py](../tests/test_verification_repair_roles.py)

## Intentional Boundaries

- XFusion uses the explicit XFusion Capability Schema contract documented in
  [docs/architecture/capability-schema.md](architecture/capability-schema.md), not a
  general JSON Schema compatibility promise.
- Unsupported schema keywords fail validation by design at capability
  registration/startup and at runtime rather than being ignored.
- Legacy materials are archived under [docs/archive/v0.1](archive/v0.1) with
  non-normative banners. The v0.2 spec is the current source of truth.
- SSH, web UI, voice, persistent memory, unrestricted shell execution, and
  multi-agent orchestration remain non-goals for this release.

## Current Residual Risks

These are known follow-on hardening areas, not hidden debt:

- Repair generation is intentionally narrow and deterministic; it is not yet a
  broad semantic repair planner.
- Equivalent-repair approval reuse is fail-closed but currently controlled by
  simple policy logic (`approval_summary` gate) rather than richer policy-table
  declarations.
- Role boundaries are runtime-enforced and auditable but not physically isolated
  into separate runtimes/processes.
- Runtime network denial and containment remain declarative guardrails, not full
  OS-level sandbox isolation.
- Verification dataset integration is focused on high-value repair/role
  invariants; broader corpus expansion remains a follow-on track.

## Deferred Modules (Post-v0.2.4)

These follow-ons are explicitly deferred beyond v0.2.4 and are tracked in the
v0.2.4 release notes:
[docs/release-plan-v0.2.4.md](release-plan-v0.2.4.md).

- Broader command-family policy coverage beyond current registered capabilities.
- More configurable policy tables and environment profile overrides.
- Physical runtime isolation/sandboxing (outside the v0.2.4 deterministic scope).
- Additional adversarial verification corpus expansion for policy permutations.

Status: **Post-v0.2.4 Deferred**.

See [docs/release-plan-v0.2.4.md](release-plan-v0.2.4.md) for reviewer-facing
release packaging and follow-on backlog.

## Verification Gate

Before merge/release, run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```
