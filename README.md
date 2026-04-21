# XFusion Guardian

XFusion Guardian is a v0.1 safety-aware Linux administration agent for the AI
Hackathon 2026 preliminary problem: an operating-system intelligent agent that
can manage a real Linux server through natural language.

The project is demo-first and safety-first. It uses an explicit execution plan,
deterministic policy checks, typed confirmation gates, mandatory verification,
short-lived memory, and JSONL audit records so Linux admin workflows are
explainable, bounded, and testable.

## What It Does

- Understands English and Chinese Linux admin requests.
- Builds an `ExecutionPlan` for every request, including dependencies and
  verification contracts.
- Senses environment facts such as distro, current user, sudo availability,
  systemd availability, package manager, disk pressure, and protected paths.
- Routes only through scoped typed tools, never arbitrary shell passthrough.
- Requires exact typed confirmation for medium/high-risk actions.
- Refuses forbidden operations on protected paths such as `/`, `/etc`, `/usr`,
  `/boot`, and `/var/lib`.
- Verifies postconditions after execution instead of trusting tool success.
- Ships with a YAML verification suite for demo rehearsal and regression tests.

## Current v0.1 Scope

Supported workflow areas:

- Linux environment detection
- Disk usage checks and safe cleanup previews
- File search and metadata preview
- Process listing and port lookup
- Confirmation-gated process stop by port
- Confirmation-gated user create/delete
- Dangerous or ambiguous request refusal

Official demo sandbox:

- Lima Ubuntu 24.04 VM on Apple Silicon macOS
- Multipass as fallback
- Docker for development only, not official demo execution

## Architecture

The implemented v0.1 follows a LangGraph-orchestrated control loop with
Pydantic contracts:

```text
Parse
  -> Disambiguate
  -> Plan
  -> Policy
  -> Confirm
  -> Execute
  -> Verify
  -> Update
  -> Respond
```

Important trust boundary:

- LLMs may support language understanding, ambiguity detection, plan drafting,
  and response wording.
- Deterministic Python code owns policy classification, dependency enforcement,
  confirmation validation, execution authorization, and verification.

## Repository Map

- [xfusion/](xfusion/) - Python package and agent implementation
- [docs/specs/xfusion-v0.1.md](docs/specs/xfusion-v0.1.md) - frozen v0.1 spec
- [docs/architecture/pydantic-langgraph-blueprint.md](docs/architecture/pydantic-langgraph-blueprint.md) - target architecture blueprint
- [docs/demo-script.md](docs/demo-script.md) - seven-scenario acceptance demo
- [docs/sandbox-lima.md](docs/sandbox-lima.md) - Lima sandbox setup
- [docs/tools.md](docs/tools.md) - tool surface and guarantees
- [docs/verification-suite.md](docs/verification-suite.md) - verification suite design
- [verification/scenarios/](verification/scenarios/) - YAML scenario suite
- [tests/](tests/) - smoke, safety, workflow, and verification runner tests
- [AGENTS.md](AGENTS.md) - context guide for future agents and engineers

## Quick Start

Install dependencies with `uv`:

```bash
uv sync --dev
```

Run the CLI:

```bash
uv run xfusion
```

Run the verification gates:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## Configuration

Copy `.env.example` and fill in OpenAI-compatible LLM settings if needed:

```bash
cp .env.example .env
```

Environment variables:

- `XFUSION_LLM_BASE_URL`
- `XFUSION_LLM_API_KEY`
- `XFUSION_LLM_MODEL`
- `XFUSION_AUDIT_LOG_PATH`

The current safety-critical path remains deterministic even when LLM settings
are unavailable.

## Verification Suite

The verification suite is scenario-based rather than a large NL-to-label
dataset. Each case defines:

- user input and language
- environment preconditions
- expected plan shape
- expected risk and interaction state
- planned tools versus executed tools
- verification method and outcome
- expected final status or refusal/fallback

Scenario layers:

- gold demo scenarios
- regression scenarios
- deterministic safety edge probes

Default tests load the root [verification/scenarios](verification/scenarios)
suite. `live_vm` scenarios are documented for Lima rehearsal but are not run by
default.

## Safety Posture

XFusion Guardian is intentionally not a command passthrough proxy. Before any
tool can run, the agent performs:

1. ambiguity detection
2. execution plan construction
3. dependency enforcement
4. environment-aware deterministic policy evaluation
5. exact typed confirmation when required
6. bounded tool execution
7. mandatory verification
8. state update and audit summarization

This keeps the demo agent agentic enough for multi-step workflows while keeping
the dangerous decisions inspectable and controllable.

## Status

v0.1 baseline is implemented and tested. The post-v0.1 direction is documented
in the Pydantic + LangGraph architecture blueprint; future work should migrate
incrementally while preserving the verification suite and safety invariants.
