# XFusion Agent/Engineer Guide

This repo contains **XFusion v0.2**, a capability-governed Linux operations
agent for the AI Hackathon 2026 preliminary problem. The goal is not to build a
generic shell wrapper. The goal is a deterministic, policy-governed,
plan-executing system agent that can manage a real Linux server through natural
language while remaining auditable and controllable.

## Current Status

v0.2 is a Python CLI-first implementation. The only normative product and
technical spec is:

- [docs/specs/xfusion-v0.2.md](docs/specs/xfusion-v0.2.md)

Historical legacy materials live under [docs/archive/v0.1](docs/archive/v0.1)
and are explicitly non-normative.

The current implementation includes:

- capability-governed `ExecutionPlan` and step contracts
- dependency and reference enforcement
- deterministic policy engine
- approval records bound to typed confirmations and action fingerprints
- controlled adapter runtime
- XFusion Capability Schema validation for capability input/output contracts
- output normalization and redaction before general-purpose exposure
- verification flow
- final responses derived from authoritative audit state
- append-only JSONL audit traces via `XFUSION_AUDIT_LOG_PATH`
- CLI entrypoint
- OpenAI-compatible LLM client scaffold

The LLM boundary is intentionally narrow. The model may help with request
understanding, ambiguity support, plan drafting, diagnosis suggestions,
verification suggestions, and response wording. Policy classification,
dependency enforcement, reference resolution, approval rules, schema validation,
execution permission, redaction, audit state, and final capability
authorization remain deterministic.

## Project Commands

Use `uv` for all project commands.

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format .
uv run ruff format --check .
uv run ty check
uv run xfusion
```

Before claiming work is complete, run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## Docs Index

Start here:

- [README.md](README.md): short project overview and development commands.
- [docs/specs/xfusion-v0.2.md](docs/specs/xfusion-v0.2.md): normative v0.2 spec.
- [docs/architecture/capability-schema.md](docs/architecture/capability-schema.md): XFusion Capability Schema contract.
- [docs/architecture/execution-policy-v0.2.5.md](docs/architecture/execution-policy-v0.2.5.md): current policy integrity and confirmation semantics.
- [docs/release-readiness-v0.2.md](docs/release-readiness-v0.2.md): reviewer notes.
- [docs/release-plan-v0.2.5.md](docs/release-plan-v0.2.5.md): v0.2.5 release notes and deferred follow-ons.
- [problem_statement.pdf](problem_statement.pdf): original contest problem statement.

Supporting docs:

- [docs/verification/verification-suite.md](docs/verification/verification-suite.md): standardized YAML scenario suite.
- [verification/README.md](verification/README.md): verification suite editing guide.
- [docs/archive/v0.1](docs/archive/v0.1): historical, non-normative legacy materials.

Core code:

- [xfusion/domain/models](xfusion/domain/models): Pydantic contracts for plans, environment, policy, verification, audit, capabilities, and scenarios.
- [xfusion/capabilities](xfusion/capabilities): capability registry and schema contract validation.
- [xfusion/planning](xfusion/planning): static plan validation and reference resolution.
- [xfusion/execution](xfusion/execution): controlled runtime and command runner.
- [xfusion/graph](xfusion/graph): LangGraph state, nodes, wiring, response formatting, and audit helpers.
- [xfusion/policy](xfusion/policy): deterministic policy, approval, protected path checks, and confirmation helpers.
- [xfusion/tools](xfusion/tools): scoped typed adapters for system, disk, file, process, user, and cleanup operations.
- [xfusion/audit](xfusion/audit): JSONL audit trace writer.
- [xfusion/app/cli.py](xfusion/app/cli.py): CLI entrypoint.
- [xfusion/llm/client.py](xfusion/llm/client.py): OpenAI-compatible client scaffold.

Tests:

- [tests/test_v02_contracts.py](tests/test_v02_contracts.py): v0.2 plan, approval, role, and runtime contracts.
- [tests/test_v02_hardening.py](tests/test_v02_hardening.py): safety hardening, schema contract, redaction, audit, and documentation invariants.
- [tests/test_smoke.py](tests/test_smoke.py): CLI and graph smoke tests.
- [tests/test_plan_correctness.py](tests/test_plan_correctness.py): plan shape, dependency, refusal, and abort behavior.
- [tests/test_data_flow.py](tests/test_data_flow.py): step-output data flow across workflows.
- [tests/test_safety_invariants.py](tests/test_safety_invariants.py): confirmation and verification invariants.
- [tests/test_response_and_audit_contract.py](tests/test_response_and_audit_contract.py): judge response contract and JSONL audit persistence.
- [tests/test_workflow_completion.py](tests/test_workflow_completion.py): demo workflow completion tests.
- [tests/test_verification_runner.py](tests/test_verification_runner.py): YAML scenario static/fake-tool checks.
- [tests/test_live_vm_rehearsal.py](tests/test_live_vm_rehearsal.py): opt-in Lima/live-session rehearsal smoke.

## Architecture Invariants

Preserve these unless the v0.2 spec is intentionally revised:

- No arbitrary shell passthrough.
- Every request becomes an `ExecutionPlan`, even one-step requests.
- Each step invokes exactly one registered capability.
- A step cannot execute unless all dependencies succeeded.
- References must use `$steps.<step_id>.outputs.<field>` and resolve only from authorized upstream outputs.
- Capability input/output schemas are authoritative and fail closed when unsupported or malformed.
- Mutating actions require policy approval before execution.
- Approval is invalidated on material change.
- Memory is short-lived and scoped to the active session/plan.
- Tools/adapters accept structured input and return structured output.
- Output is normalized and redacted before model-visible, user-visible, or general-purpose audit/log exposure.
- Verification is mandatory after execution.
- Final responses derive from authoritative audit state.
- The agent must ask clarification instead of guessing when target, scope, or risk boundary is unclear.

## Safety Model

Risk tiers:

- `tier_0`: read-only inspection within validated scope.
- `tier_1`: bounded reversible mutation, requires human approval.
- `tier_2`: high-risk mutation, requires admin approval or denial.
- `tier_3`: prohibited or broad-impact operation, denied.

Protected targets include:

- `/`
- `/etc`
- `/boot`
- `/usr`
- `/var/lib`
- sudoers/SSH security configuration
- broad recursive permission changes
- unclear destructive operations

Context matters. For example, bounded log cleanup can be more reasonable under
high disk pressure than when disk pressure is normal. Keep risk reasoning
grounded in `EnvironmentModel`.

## Implementation Notes

- Python target: 3.11+.
- Package/dependency management: `uv`.
- Lint/format: `ruff`.
- Type checking: `ty`.
- Tests: `pytest`.
- Official demo sandbox: Lima Ubuntu 24.04 VM on Apple Silicon macOS.
- Docker is acceptable for development smoke tests only, not for the official demo.

The parser is deterministic for stability. If wiring in LLM-based parsing, keep
the deterministic policy, schema, approval, redaction, and tool authorization
boundaries intact.

## Development Workflow

When changing behavior:

1. Update or add tests first.
2. Implement the smallest change that satisfies the contract.
3. Run `uv run pytest -q`.
4. Run `uv run ruff check .`.
5. Run `uv run ruff format --check .`.
6. Run `uv run ty check`.
7. Update docs if the user-facing behavior, capability surface, safety model, schema contract, or demo flow changed.

Avoid unrelated refactors. This project is intentionally small and audit-friendly.

## Demo Mindset

The judge-facing story is:

```text
Natural language request
-> explicit execution plan
-> reference and schema validation
-> environment-aware policy decision
-> approval-bound typed confirmation when needed
-> controlled adapter execution
-> output normalization and redaction
-> verification
-> authoritative audit trace
-> clear audit-derived response
```
