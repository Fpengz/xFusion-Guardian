# XFusion Guardian

XFusion Guardian is a v0.2 capability-governed Linux administration agent for the AI
Hackathon 2026 preliminary problem: an operating-system intelligent agent that
can manage a real Linux server through natural language.

The project is demo-first and safety-first. It uses typed capability proposals,
explicit execution plans, deterministic policy checks, approval gates,
controlled adapters, mandatory verification, short-lived memory, redaction, and
JSONL audit records so Linux admin workflows are explainable, bounded, and
testable.

## Reviewer Start Here

If you are reviewing safety, authority boundaries, or merge readiness, start in
this order:

1. [docs/specs/xfusion-v0.2.md](docs/specs/xfusion-v0.2.md) (normative source of truth)
2. [docs/architecture/capability-schema.md](docs/architecture/capability-schema.md) (schema contract)
3. [docs/architecture/execution-policy-v0.2.5.md](docs/architecture/execution-policy-v0.2.5.md) (policy integrity and normalized decision chain)
4. [docs/release-readiness-v0.2.md](docs/release-readiness-v0.2.md) (current reviewer posture)
5. [docs/release-plan-v0.2.5.md](docs/release-plan-v0.2.5.md) (v0.2.5 release notes and follow-ons)

## What It Does

- Understands English and Chinese Linux admin requests.
- Builds an `ExecutionPlan` for every request, including dependencies and
  verification contracts.
- Senses environment facts such as distro, current user, sudo availability,
  systemd availability, package manager, disk pressure, and protected paths.
- Routes through reviewed execution surfaces in order: registered capability,
  structured argv-safe template, then restricted shell fallback with a structured
  fallback reason.
- Classifies each planned step into deterministic allow/confirm/deny policy outcomes.
- Requires approval-bound exact typed confirmation for mutation capabilities.
- Refuses forbidden operations on protected paths such as `/`, `/etc`, `/usr`,
  `/boot`, and `/var/lib`.
- Verifies postconditions after execution instead of trusting tool success.
- Ships with a YAML verification suite for demo rehearsal and regression tests.

## Current v0.2 Scope

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

The implemented v0.2 follows a LangGraph-orchestrated control loop with
Pydantic contracts. A Conversation Gateway sits before orchestration so only
explicit operational intent can reach the execution graph:

```text
user input
  -> conversation gateway
  -> existing graph only when requires_execution=true
  -> agent proposal
  -> plan schema validation
  -> dependency/DAG validation
  -> reference validation/resolution
  -> capability/template resolution
  -> capability schema or template parameter validation
  -> policy decision
  -> approval gate
  -> controlled adapter execution
  -> output normalization
  -> redaction
  -> verification
  -> explanation
```

Important trust boundary:

- LLMs may support language understanding, ambiguity detection, plan drafting,
  and response wording.
- The Conversation Gateway uses LLM-assisted classification, but routing is
  enforced by deterministic contracts. Conversational and clarification turns do
  not mutate agent state, write execution audit records, or trigger capability,
  template, or shell execution surfaces.
- Deterministic Python code owns policy classification, dependency enforcement,
  reference resolution, capability/template validation, approval validation,
  execution authorization, output redaction, audit state, and verification.

## Repository Map

- [xfusion/](xfusion/) - Python package and agent implementation
- [docs/specs/xfusion-v0.2.md](docs/specs/xfusion-v0.2.md) - normative v0.2 spec
- [docs/architecture/capability-schema.md](docs/architecture/capability-schema.md) - XFusion Capability Schema contract
- [docs/architecture/execution-policy-v0.2.5.md](docs/architecture/execution-policy-v0.2.5.md) - v0.2.5 policy integrity and machine-readable decision-chain contract
- [docs/architecture/v0.2.5-controlled-execution-platform.md](docs/architecture/v0.2.5-controlled-execution-platform.md) - v0.2.5 hybrid manifest capability engine
- [docs/architecture/schema-subset.md](docs/architecture/schema-subset.md) - quick pointer to the schema subset contract
- [docs/release-readiness-v0.2.md](docs/release-readiness-v0.2.md) - reviewer notes
- [docs/release-plan-v0.2.5.md](docs/release-plan-v0.2.5.md) - v0.2.5 release notes and deferred backlog
- [docs/verification/verification-suite.md](docs/verification/verification-suite.md) - verification suite design
- [docs/archive/v0.1/](docs/archive/v0.1/) - historical, non-normative legacy materials
- [CHANGELOG.md](CHANGELOG.md) - release notes
- [verification/scenarios/](verification/scenarios/) - YAML scenario suite
- [tests/](tests/) - smoke, safety, workflow, and verification runner tests
- [AGENTS.md](AGENTS.md) - context guide for future agents and engineers

## Quick Start

Install dependencies with `uv`:

```bash
uv sync --dev
```

Run the CLI (launches the Interactive TUI):

```bash
uv run xfusion
```

### Interactive TUI & Slash Commands

The interactive TUI provides a compact, theme-aware "Guardian" cockpit with first-class slash commands and a searchable command palette. It keeps audit/debug detail tucked away until requested while preserving the policy-governed execution flow.

- **Trigger Palette**: Type `/` to open the searchable command palette.
- **Navigation**: Use `Up`/`Down` arrows to navigate commands and `Tab` to autocomplete.
- **Cancel/Close**: Use `Esc` to close the palette or `Ctrl+C` to cancel current input.

#### Core Commands
- `/help`: Show all available commands and descriptions.
- `/new`: Start a fresh conversation session.
- `/clear`: Visually clear the terminal timeline (shortcut: `Ctrl+L`).
- `/debug`: Toggle verbose execution mode (shows internal traces and policy details).
- `/exit`: Gracefully exit the application.

#### Session & Info Commands
- `/sessions`: List saved conversation sessions.
- `/resume <id>`: Resume a previous session by its ID.
- `/capabilities`: List reviewed registered capabilities.
- `/templates`: List reviewed structured command templates.
- `/audit`: Show recent audit trace records for the current session.
- `/status`: Show current environment and session metadata.
- `/policy`: Display active execution policy and risk thresholds.
- `/model`: View current LLM provider and model configuration.
- `/config`: Show effective application settings.

Direct `!` shell execution is intentionally unavailable in the TUI. Describe the
operation in natural language so XFusion can choose capability, template, or
restricted shell under policy and approval enforcement.

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
capability can run, the agent performs:

1. ambiguity detection
2. execution plan construction
3. dependency and reference validation
4. capability schema validation
5. environment-aware deterministic policy evaluation
6. approval validation when required
7. controlled adapter execution
8. output normalization and redaction
9. mandatory verification
10. state update and audit-derived response generation

This keeps the demo agent agentic enough for multi-step workflows while keeping
the dangerous decisions inspectable and controllable.

## Status

v0.2 capability-governed execution is implemented and tested. The current
shipping increment is `v0.2.5`, which keeps the v0.2 architecture authoritative
while adding the agent-led hybrid execution contracts: capability before
template before restricted shell, `SystemRiskEnvelope`, policy categories,
structured fallback reasons, and integrity/audit fields for all execution
surfaces. The v0.2 spec remains the baseline source of truth; the v0.2.5 spec
documents the hybrid execution increment.
Legacy materials live only in the historical archive and are explicitly
non-normative.

| Area | Status |
| --- | --- |
| Explicit plan-executing graph | implemented |
| Deterministic policy and approval records | implemented |
| Persistent JSONL audit logs | implemented |
| Seven acceptance demo scenarios | implemented |
| Safe cleanup | implemented with limitations: approved demo/temp candidates only |
| Live VM rehearsal | implemented with limitations: opt-in, skipped by default |
| SSH, web UI, voice, persistent memory, multi-agent orchestration | future |
