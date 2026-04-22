# Pydantic v2 + LangGraph Architecture Blueprint

This document defines the current and target architecture for XFusion's **Pydantic v2 + LangGraph-first architecture**, with LangChain used only as optional integration glue.

The v0.1 implementation now uses this stack. Some sections below remain blueprint-level guidance for future refinements, but the package layout, core contracts, and graph loop are the current baseline.

## References

- LangGraph overview: <https://docs.langchain.com/oss/python/langgraph>
- LangGraph persistence and human-in-the-loop: <https://docs.langchain.com/oss/python/langgraph/persistence>
- Pydantic configuration docs: <https://pydantic.dev/docs/validation/latest/api/pydantic/config/>
- Pydantic migration/config guidance: <https://docs.pydantic.dev/2.12/migration/>

## Architectural Stance

The target stack is:

```text
Pydantic v2 = contract truth
LangGraph = orchestration and state transitions
LangChain = optional model/tool/provider glue
Plain Python = deterministic trust boundaries
```

Pydantic owns all internal contracts: execution plans, steps, environment state, policy decisions, verification results, audit records, graph state, and verification scenarios. Models should use Pydantic v2 patterns: `BaseModel`, `ConfigDict(extra="forbid")`, `Field`, modern type hints, and `Annotated` when validation metadata belongs with the type.

LangGraph owns orchestration: shared state, node sequencing, branch logic, clarification/confirmation pauses, and future checkpointing. The target graph maps directly to the existing XFusion loop:

```text
parse -> disambiguate -> plan -> policy -> confirm -> execute -> verify -> update -> respond
```

LangChain is optional. Use it only where it genuinely reduces boilerplate: provider adapters, prompt helpers, structured model integrations, or tool wrappers. Do not use a prebuilt LangChain agent as XFusion's main control loop.

The deterministic trust boundary must remain plain Python. Policy classification, protected-path checks, dependency enforcement, confirmation rules, execution permission, and final tool authorization must not be delegated to an LLM or framework agent.

## Target Repo Layout

```text
xfusion/
  app/
    cli.py
    settings.py

  domain/
    enums.py
    models/
      execution_plan.py
      environment.py
      policy.py
      verification.py
      audit.py
      scenarios.py

  graph/
    state.py
    nodes/
      parse.py
      disambiguate.py
      plan.py
      policy.py
      confirm.py
      execute.py
      verify.py
      update.py
      respond.py
    wiring.py

  llm/
    client.py
    prompts.py
    parsers.py

  policy/
    rules.py
    protected_paths.py
    confirmations.py

  tools/
    base.py
    registry.py
    system.py
    disk.py
    file.py
    process.py
    user.py
    cleanup.py

  execution/
    command_runner.py
    executor.py

  audit/
    logger.py
    jsonl_sink.py

  verification/
    loader.py
    runner.py
    scenarios/
      gold_demo.yaml
      regression.yaml
      edge_probes.yaml

  tests/
    unit/
    integration/
    verification/
```

## Layer Ownership

### `app`

Owns user entrypoints and runtime settings. It should not implement policy, tool execution, or graph routing.

### `domain`

Owns Pydantic models and enums. It should contain validation and serialization contracts, not orchestration.

### `graph`

Owns LangGraph state, nodes, transitions, interrupts, and response routing. It calls domain services but does not decide safety by itself.

### `llm`

Owns model clients, prompts, and structured parsing helpers. It may draft parsed intents or plans, but deterministic validation must happen after model output.

### `policy`

Owns protected paths, risk rules, confirmation phrases, and deterministic authorization. This is a trust boundary.

### `tools`

Owns typed tool definitions and registry. Tools accept Pydantic inputs and return Pydantic outputs. They do not expose arbitrary shell passthrough.

### `execution`

Owns command execution, timeout handling, subprocess results, and low-level OS interaction.

### `audit`

Owns audit records and JSONL persistence.

### `verification`

Owns scenario schema, YAML loading, static checks, fake-tool checks, and future live VM rehearsal hooks.

## Contract Model Blueprint

All models should use:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base pattern for XFusion Pydantic contracts."""

    model_config = ConfigDict(extra="forbid")
```

Use `TypedDict` only for loose external payloads, such as raw provider responses, where validating into Pydantic immediately is not practical.

### `domain/enums.py`

```python
from __future__ import annotations

from enum import StrEnum


class InteractionState(StrEnum):
    AWAITING_DISAMBIGUATION = "awaiting_disambiguation"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REFUSED = "refused"
    ABORTED = "aborted"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REFUSED = "refused"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FORBIDDEN = "forbidden"
```

### `domain/models/execution_plan.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xfusion.domain.enums import InteractionState, RiskLevel, StepStatus


class PlanStep(BaseModel):
    """Represents one planned agent step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    confirmation_phrase: str | None = None
    expected_output: str = Field(min_length=1)
    verification_method: str = Field(min_length=1)
    success_condition: str = Field(min_length=1)
    failure_condition: str = Field(min_length=1)
    fallback_action: str = Field(min_length=1)
    status: StepStatus = StepStatus.PENDING


class ExecutionPlan(BaseModel):
    """Represents the complete plan for a user request."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    language: str = Field(min_length=1)
    interaction_state: InteractionState = InteractionState.EXECUTING
    steps: list[PlanStep]
    max_steps: int = Field(default=8, ge=1, le=20)
    current_step: str | None = None
    status: str = "executing"
    clarification_question: str | None = None

    @model_validator(mode="after")
    def validate_dependencies(self) -> ExecutionPlan:
        """Reject dependencies that reference unknown steps."""
        step_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            unknown = set(step.dependencies) - step_ids
            if unknown:
                raise ValueError(f"Unknown step dependencies: {sorted(unknown)}")
        return self

    def next_executable_step(self) -> PlanStep | None:
        """Return the next pending step whose dependencies succeeded."""
        ...
```

### `domain/models/environment.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentState(BaseModel):
    """Current OS and runtime facts used for planning and policy."""

    model_config = ConfigDict(extra="forbid")

    distro_family: str = "unknown"
    distro_version: str = "unknown"
    current_user: str = "unknown"
    sudo_available: bool = False
    systemd_available: bool = False
    package_manager: str = "unknown"
    disk_pressure: str = "unknown"
    session_locality: str = "local"
    protected_paths: tuple[str, ...] = ("/", "/etc", "/boot", "/usr", "/var/lib")
    active_facts: dict[str, object] = Field(default_factory=dict)
```

### `domain/models/policy.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.enums import RiskLevel


class PolicyDecision(BaseModel):
    """Deterministic authorization result for a planned step."""

    model_config = ConfigDict(extra="forbid")

    risk_level: RiskLevel
    allowed: bool
    requires_confirmation: bool
    reason: str = Field(min_length=1)
```

### `domain/models/verification.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VerificationResult(BaseModel):
    """Result of post-execution verification."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    method: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    outcome: str = Field(default="unknown")
    details: dict[str, object] = Field(default_factory=dict)
```

### `domain/models/audit.py`

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditRecord(BaseModel):
    """Append-only audit record for one plan step."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    plan_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    interaction_state: str = Field(min_length=1)
    before_state: dict[str, object]
    action_taken: dict[str, object]
    after_state: dict[str, object]
    verification_result: dict[str, object]
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
```

### `domain/models/scenarios.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExpectedScenario(BaseModel):
    """Expected behavior for one verification scenario."""

    model_config = ConfigDict(extra="forbid")

    plan_length: int = Field(ge=0)
    plan_tools: list[str]
    executed_tools: list[str]
    risk_level: str
    interaction_state: str
    requires_confirmation: bool
    verification_method: str
    verification_outcome: str
    final_status: str
    outcome_contains: list[str]
    refusal_or_fallback: str


class VerificationScenario(BaseModel):
    """YAML-backed verification scenario."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    mode: str = Field(pattern="^(static|fake_tool|live_vm)$")
    language: str = Field(min_length=1)
    input: str = Field(min_length=1)
    preconditions: dict[str, object]
    safe_for_live_execution: bool
    notes: str = ""
    expected: ExpectedScenario
```

## Graph Blueprint

### `graph/state.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan
from xfusion.domain.models.policy import PolicyDecision
from xfusion.domain.models.verification import VerificationResult


class AgentGraphState(BaseModel):
    """Shared LangGraph state for one user request/session turn."""

    model_config = ConfigDict(extra="forbid")

    user_input: str
    language: str = "en"
    environment: EnvironmentState
    plan: ExecutionPlan | None = None
    current_step_id: str | None = None
    policy_decision: PolicyDecision | None = None
    verification_result: VerificationResult | None = None
    pending_confirmation_phrase: str | None = None
    response: str = ""
    audit_records: list[dict[str, object]] = Field(default_factory=list)
```

### Nodes

Each node should be a small function that accepts and returns `AgentGraphState` or a partial state update compatible with LangGraph.

```python
def parse_node(state: AgentGraphState) -> AgentGraphState: ...
def disambiguate_node(state: AgentGraphState) -> AgentGraphState: ...
def plan_node(state: AgentGraphState) -> AgentGraphState: ...
def policy_node(state: AgentGraphState) -> AgentGraphState: ...
def confirm_node(state: AgentGraphState) -> AgentGraphState: ...
def execute_node(state: AgentGraphState) -> AgentGraphState: ...
def verify_node(state: AgentGraphState) -> AgentGraphState: ...
def update_node(state: AgentGraphState) -> AgentGraphState: ...
def respond_node(state: AgentGraphState) -> AgentGraphState: ...
```

Node ownership:

- `parse`: normalize language input and produce a parsed intent candidate.
- `disambiguate`: set `awaiting_disambiguation` when target/scope/risk boundary is unclear.
- `plan`: create or revise `ExecutionPlan`.
- `policy`: call deterministic policy rules for the next executable step.
- `confirm`: pause for exact typed confirmation when required.
- `execute`: call only registered typed tools.
- `verify`: run mandatory post-action verification.
- `update`: refresh environment/memory/audit state.
- `respond`: format final or intermediate response.

### Routing Rules

```python
def route_after_parse(state: AgentGraphState) -> str:
    if state.plan and state.plan.interaction_state == "awaiting_disambiguation":
        return "respond"
    return "plan"


def route_after_policy(state: AgentGraphState) -> str:
    decision = state.policy_decision
    if decision is None:
        return "respond"
    if not decision.allowed or decision.risk_level == "forbidden":
        return "respond"
    if decision.requires_confirmation:
        return "confirm"
    return "execute"


def route_after_update(state: AgentGraphState) -> str:
    plan = state.plan
    if plan is None:
        return "respond"
    if plan.status in {"completed", "failed", "aborted", "refused"}:
        return "respond"
    return "policy"
```

### `graph/wiring.py`

```python
from __future__ import annotations

from langgraph.graph import END, StateGraph

from xfusion.graph.state import AgentGraphState


def build_agent_graph() -> StateGraph:
    """Build the XFusion LangGraph workflow."""
    graph = StateGraph(AgentGraphState)
    graph.add_node("parse", parse_node)
    graph.add_node("disambiguate", disambiguate_node)
    graph.add_node("plan", plan_node)
    graph.add_node("policy", policy_node)
    graph.add_node("confirm", confirm_node)
    graph.add_node("execute", execute_node)
    graph.add_node("verify", verify_node)
    graph.add_node("update", update_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "disambiguate")
    graph.add_conditional_edges("disambiguate", route_after_disambiguate)
    graph.add_edge("plan", "policy")
    graph.add_conditional_edges("policy", route_after_policy)
    graph.add_edge("confirm", "respond")
    graph.add_edge("execute", "verify")
    graph.add_edge("verify", "update")
    graph.add_conditional_edges("update", route_after_update)
    graph.add_edge("respond", END)
    return graph
```

Checkpointing can be added later through LangGraph checkpointers. v0.1 should start with in-memory graph execution so the migration does not mix orchestration refactor with persistence design.

## File-by-File Blueprint

### `app/settings.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid")

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    audit_log_path: str = "audit.jsonl"


def load_settings() -> Settings:
    """Load settings from process environment."""
    ...
```

### `policy/rules.py`

```python
def evaluate_policy(
    *,
    tool: str,
    parameters: dict[str, object],
    environment: EnvironmentState,
) -> PolicyDecision:
    """Return deterministic policy decision for one planned tool call."""
    ...
```

### `tools/base.py`

```python
class ToolInput(BaseModel):
    """Base class for typed tool inputs."""

    model_config = ConfigDict(extra="forbid")


class ToolOutput(BaseModel):
    """Base class for typed tool outputs."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    data: dict[str, object] = Field(default_factory=dict)
```

### `tools/registry.py`

```python
class ToolRegistry:
    """Registry for safe, typed XFusion tools."""

    def register(self, tool: ToolDefinition) -> None: ...
    def get(self, name: str) -> ToolDefinition: ...
    def execute(self, name: str, payload: dict[str, object]) -> ToolOutput: ...
```

### `execution/command_runner.py`

```python
class CommandRunner:
    """Runs bounded local commands with timeout and captured output."""

    def run(self, command: list[str], *, timeout: float) -> CommandResult:
        """Run one non-interactive command."""
        ...
```

### `audit/jsonl_sink.py`

```python
class JsonlAuditSink:
    """Append-only JSONL sink for validated audit records."""

    def write(self, record: AuditRecord) -> None:
        """Append one audit record."""
        ...
```

### `verification/loader.py`

```python
def load_scenarios(path: Path) -> list[VerificationScenario]:
    """Load and validate YAML verification scenarios."""
    ...
```

### `verification/runner.py`

```python
def run_static_scenario(scenario: VerificationScenario) -> ScenarioResult:
    """Run parse/plan/policy checks without tool execution."""
    ...


def run_fake_tool_scenario(scenario: VerificationScenario) -> ScenarioResult:
    """Run a scenario through deterministic fake tools."""
    ...
```

## Historical Migration Mapping

| Current file | Target location |
| --- | --- |
| `xfusion/models.py` | `xfusion/domain/enums.py`, `xfusion/domain/models/*` |
| `xfusion/agent.py` | `xfusion/graph/state.py`, `xfusion/graph/nodes/*`, `xfusion/graph/wiring.py` |
| `xfusion/environment.py` | `xfusion/domain/models/environment.py`, `xfusion/tools/system.py` |
| `xfusion/parser.py` | `xfusion/llm/parsers.py`, `xfusion/graph/nodes/parse.py` |
| `xfusion/planner.py` | `xfusion/graph/nodes/plan.py`, `xfusion/domain/models/execution_plan.py` |
| `xfusion/policy.py` | `xfusion/policy/rules.py`, `xfusion/policy/protected_paths.py` |
| `xfusion/tools.py` | `xfusion/tools/base.py`, `xfusion/tools/registry.py`, domain-specific tool modules |
| `xfusion/audit.py` | `xfusion/audit/logger.py`, `xfusion/audit/jsonl_sink.py` |
| `xfusion/verification.py` | `xfusion/verification/loader.py`, `xfusion/verification/runner.py` |
| `xfusion/cli.py` | `xfusion/app/cli.py` |
| `xfusion/llm.py` | `xfusion/llm/client.py` |

## Dependency Stance

Add these when the refactor begins:

```toml
dependencies = [
  "pydantic>=2.12,<3",
  "langgraph>=1,<2",
  "pyyaml>=6.0.2",
]
```

Add selectively only if a concrete integration needs them:

```toml
"langchain-core>=1,<2"
"langchain-openai>=1,<2"
```

Keep:

- `uv` for environment and dependency management.
- `pytest` for tests.
- `ruff` for lint/format.
- `ty` for type checking.

## Migration Order

1. Add Pydantic domain models beside current dataclasses.
2. Convert verification scenario schemas to Pydantic first.
3. Convert execution plan, policy, verification, and audit models.
4. Split tool modules behind the existing `ToolRouter` interface.
5. Introduce LangGraph state and nodes around the existing services.
6. Switch CLI from custom `Agent` loop to compiled graph invocation.
7. Add checkpointing only after the in-memory graph preserves all current tests.

Each step must preserve:

- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run ty check`

## Non-Goals

- Do not replace deterministic policy with LLM judgment.
- Do not introduce a LangChain prebuilt agent loop.
- Do not add graph persistence during the first orchestration refactor.
- Do not broaden shell execution beyond registered typed tools.
- Do not move to a web UI as part of this architecture migration.
