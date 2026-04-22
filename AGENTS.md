# XFusion Agent/Engineer Guide

This repo contains **XFusion v0.1**, a safety-aware Linux administration agent for the AI Hackathon 2026 preliminary problem. The goal is not to build a generic shell wrapper. The goal is a deterministic, policy-governed, plan-executing system agent that can manage a real Linux server through natural language while remaining auditable and controllable.

## Current Status

v0.1 is a Python CLI-first implementation. The frozen product/technical spec is the source of truth:

- [docs/specs/xfusion-v0.1.md](docs/specs/xfusion-v0.1.md)

The current implementation includes:

- explicit `ExecutionPlan` and step model
- dependency enforcement
- interaction states
- deterministic policy engine
- context-aware risk classification
- short-lived graph state for active plans
- typed confirmation boundaries
- scoped tool router
- verification flow
- append-only JSONL audit traces via `XFUSION_AUDIT_LOG_PATH`
- CLI entrypoint
- OpenAI-compatible LLM client scaffold

The LLM boundary is intentionally narrow. The LLM may help with language understanding, ambiguity support, plan drafting, and response wording. Policy classification, dependency enforcement, confirmation rules, execution permission, and final tool authorization remain deterministic.

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
- [docs/specs/xfusion-v0.1.md](docs/specs/xfusion-v0.1.md): frozen v0.1 spec and acceptance criteria.
- [problem_statement.pdf](problem_statement.pdf): original contest problem statement.

Submission and demo docs:

- [docs/demo-script.md](docs/demo-script.md): seven-scenario acceptance demo.
- [docs/sandbox-lima.md](docs/sandbox-lima.md): official Lima Ubuntu VM demo sandbox notes.
- [docs/self-test.md](docs/self-test.md): local and VM self-test checklist.
- [docs/verification-suite.md](docs/verification-suite.md): standardized YAML scenario suite.
- [verification/README.md](verification/README.md): verification suite editing guide.

Agent architecture docs:

- [docs/architecture/pydantic-langgraph-blueprint.md](docs/architecture/pydantic-langgraph-blueprint.md): current Pydantic v2 + LangGraph architecture and next-step blueprint.
- [docs/tools.md](docs/tools.md): v0.1 tool surface and guarantees.
- [docs/prompts/core-agent-prompt.md](docs/prompts/core-agent-prompt.md): documented LLM boundary and core agent prompt.

Core code:

- [xfusion/domain/models](xfusion/domain/models): Pydantic contracts for plans, environment, policy, verification, audit, and scenarios.
- [xfusion/graph](xfusion/graph): LangGraph state, nodes, wiring, response formatting, and audit event helpers.
- [xfusion/policy](xfusion/policy): deterministic policy, protected path checks, and confirmation helpers.
- [xfusion/tools](xfusion/tools): scoped typed tools for system, disk, file, process, user, and cleanup operations.
- [xfusion/audit](xfusion/audit): JSONL audit trace writer.
- [xfusion/app/cli.py](xfusion/app/cli.py): CLI entrypoint.
- [xfusion/llm/client.py](xfusion/llm/client.py): OpenAI-compatible client scaffold.

Tests:

- [tests/test_smoke.py](tests/test_smoke.py): CLI and graph smoke tests.
- [tests/test_plan_correctness.py](tests/test_plan_correctness.py): plan shape, dependency, refusal, and abort behavior.
- [tests/test_data_flow.py](tests/test_data_flow.py): step-output data flow across workflows.
- [tests/test_safety_invariants.py](tests/test_safety_invariants.py): confirmation and verification invariants.
- [tests/test_response_and_audit_contract.py](tests/test_response_and_audit_contract.py): judge response contract and JSONL audit persistence.
- [tests/test_workflow_completion.py](tests/test_workflow_completion.py): demo workflow completion tests.
- [tests/test_verification_runner.py](tests/test_verification_runner.py): YAML scenario static/fake-tool checks.
- [tests/test_live_vm_rehearsal.py](tests/test_live_vm_rehearsal.py): opt-in Lima/live-session rehearsal smoke.

## Architecture Invariants

Preserve these unless the frozen spec is intentionally revised:

- No arbitrary shell passthrough.
- Every request becomes an `ExecutionPlan`, even one-step requests.
- A step cannot execute unless all dependencies succeeded.
- Medium/high-risk actions require exact typed confirmation.
- Confirmations never persist across plans.
- Memory is short-lived and scoped to the active session/plan.
- Tools accept structured input and return structured output.
- Mutating tools require policy approval before execution.
- Verification is mandatory after execution.
- Audit traces must map intent to plan, step, action, state changes, verification, and outcome.
- The agent must ask clarification instead of guessing when target, scope, or risk boundary is unclear.

## Safety Model

Risk levels:

- `low`: read-only inspection, usually executes directly.
- `medium`: bounded state-changing actions, requires typed confirmation.
- `high`: suspicious or broad actions, requires stricter handling or refusal.
- `forbidden`: protected paths, unsafe privilege changes, or unsupported tools; always refused.

Protected targets include:

- `/`
- `/etc`
- `/boot`
- `/usr`
- `/var/lib`
- sudoers/SSH security configuration
- broad recursive permission changes
- unclear destructive operations

Context matters. For example, bounded log cleanup can be more reasonable under high disk pressure than when disk pressure is normal. Keep risk reasoning grounded in `EnvironmentModel`.

## Implementation Notes

- Python target: 3.11+.
- Package/dependency management: `uv`.
- Lint/format: `ruff`.
- Type checking: `ty`.
- Tests: `pytest`.
- Official demo sandbox: Lima Ubuntu 24.04 VM on Apple Silicon macOS.
- Docker is acceptable for development smoke tests only, not for the official demo.

The current parser is deterministic for v0.1 stability. If wiring in LLM-based parsing, keep the deterministic policy and tool authorization boundary intact.

## Roadmap Status

| Area | Status |
| --- | --- |
| Pydantic + LangGraph control loop | implemented |
| Exact typed confirmation | implemented |
| Mandatory verification | implemented |
| Persistent JSONL audit logs | implemented |
| Seven-scenario demo spine | implemented |
| Safe cleanup | implemented with limitations: approved demo/temp candidates only |
| Live VM rehearsal | implemented with limitations: opt-in smoke test, not default |
| SSH/web/voice/persistent memory/multi-agent orchestration | future |

## Development Workflow

When changing behavior:

1. Update or add tests first.
2. Implement the smallest change that satisfies the contract.
3. Run `uv run pytest -q`.
4. Run `uv run ruff check .`.
5. Run `uv run ruff format --check .`.
6. Run `uv run ty check`.
7. Update docs if the user-facing behavior, tool surface, safety model, or demo flow changed.

Avoid unrelated refactors. This project is intentionally small and audit-friendly.

## Demo Mindset

The judge-facing story is:

```text
Natural language request
→ explicit execution plan
→ environment-aware policy decision
→ typed confirmation when needed
→ bounded tool execution
→ verification
→ state update
→ audit trace
→ clear natural-language response
```

The strongest v0.1 demo is the disk-pressure workflow: detect disk pressure, propose safe cleanup, explain why the candidates are safe in this environment, request confirmation, execute bounded cleanup, verify the result, and suggest preventive monitoring.
