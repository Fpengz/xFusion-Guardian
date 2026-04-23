# XFusion v0.2 Reviewer Notes

This note summarizes the merge/release posture for the v0.2 implementation. The
normative behavior remains [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md).

## What Changed

- Execution is capability governed: plans invoke registered `capability + args`
  contracts instead of the legacy `tool + parameters` surface.
- Static validation rejects unknown capabilities, conflicting legacy fields,
  invalid dependencies, fabricated references, unknown args, and schema
  mismatches before policy or execution.
- Policy, approval, runtime constraints, output normalization, redaction,
  verification, and audit records form the deterministic authority path.
- Adapter outputs are centrally schema-validated before they can be audited as
  successful outcomes, referenced by downstream steps, or used in final
  explanations.
- Final responses are derived from authoritative audit state, including the
  final explanation snapshot.

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

## Verification Gate

Before merge/release, run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```
