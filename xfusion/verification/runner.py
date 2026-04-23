from __future__ import annotations

from typing import Any

from xfusion.domain.enums import InteractionState
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.scenarios import VerificationScenario
from xfusion.graph.nodes.parse import parse_node
from xfusion.graph.nodes.plan import plan_node
from xfusion.graph.state import AgentGraphState
from xfusion.graph.wiring import build_agent_graph
from xfusion.policy.rules import evaluate_policy
from xfusion.tools.base import ToolOutput


def _environment_from_preconditions(preconditions: dict[str, object]) -> EnvironmentState:
    """Map scenario preconditions onto the deterministic environment model."""
    return EnvironmentState(
        distro_family=str(preconditions.get("distro", "unknown")),
        sudo_available=bool(preconditions.get("sudo", False)),
        disk_pressure=str(preconditions.get("disk_pressure", "unknown")),
    )


def _initial_state(scenario: VerificationScenario) -> AgentGraphState:
    return AgentGraphState(
        user_input=scenario.input,
        environment=_environment_from_preconditions(scenario.preconditions),
        language=scenario.language,
    )


def _compare_common_expectations(
    scenario: VerificationScenario,
    state: AgentGraphState,
    executed_tools: list[str],
) -> list[str]:
    errors: list[str] = []
    plan = state.plan
    expected = scenario.expected

    if not plan:
        errors.append("Expected a plan but graph state has no plan.")
        return errors

    if len(plan.steps) != expected.plan_length:
        errors.append(f"Expected plan length {expected.plan_length}, got {len(plan.steps)}")

    plan_tools = [step.capability for step in plan.steps]
    if plan_tools != expected.plan_tools:
        errors.append(f"Expected plan tools {expected.plan_tools}, got {plan_tools}")

    if executed_tools != expected.executed_tools:
        errors.append(f"Expected executed tools {expected.executed_tools}, got {executed_tools}")

    if plan.interaction_state != expected.interaction_state:
        errors.append(
            f"Expected interaction state {expected.interaction_state}, got {plan.interaction_state}"
        )

    if plan.status != expected.final_status and not (
        expected.final_status == "planned" and plan.status == "executing"
    ):
        errors.append(f"Expected final status {expected.final_status}, got {plan.status}")

    if expected.outcome_contains:
        response = state.response.lower()
        missing = [text for text in expected.outcome_contains if text.lower() not in response]
        if missing:
            errors.append(f"Expected response to contain {missing}, got {state.response!r}")

    return errors


def run_static_scenario(
    scenario: VerificationScenario, registry: object | None = None
) -> dict[str, object]:
    """Run parse/plan/policy checks without tool execution."""
    del registry

    state = plan_node(parse_node(_initial_state(scenario)))
    errors: list[str] = []
    expected = scenario.expected

    if not state.plan:
        errors.append("Planning produced no ExecutionPlan.")
    elif state.plan.steps:
        decisions = [
            evaluate_policy(
                capability_name=step.capability,
                resolved_args=step.args,
                argument_provenance={key: "literal_or_validated_user_input" for key in step.args},
                environment=state.environment,
            )
            for step in state.plan.steps
        ]
        decisive = next((decision for decision in decisions if decision.is_denied), None)
        decisive = decisive or next(
            (decision for decision in decisions if decision.requires_approval), None
        )
        decisive = decisive or decisions[0]

        if decisive.is_denied:
            state.plan.interaction_state = InteractionState.REFUSED
            state.plan.status = "refused"
            state.response = decisive.reason
        elif decisive.requires_approval:
            state.plan.interaction_state = InteractionState.AWAITING_CONFIRMATION
            state.plan.status = "awaiting_confirmation"
            state.response = "This action requires confirmation: " + ", ".join(
                step.intent for step in state.plan.steps
            )
        else:
            state.plan.interaction_state = InteractionState.EXECUTING
            state.plan.status = "executing"
            state.response = "Planned: " + ", ".join(step.intent for step in state.plan.steps)
    elif expected.risk_level != "none":
        errors.append(f"Expected risk {expected.risk_level}, got none")

    if expected.verification_method != "none" and state.plan and state.plan.steps:
        step = state.plan.steps[-1]
        actual_method = step.verification_method
        if actual_method == "none":
            if "expect_free" in step.args or step.capability in {
                "process.kill",
                "process.find_by_port",
            }:
                actual_method = "port_process_recheck"
            elif step.capability in {"user.create", "user.delete"}:
                actual_method = "existence_nonexistence_check"
            elif step.capability in {
                "disk.check_usage",
                "system.detect_environment",
                "system.detect_os",
            }:
                actual_method = "state_re_read"
            elif step.capability in {"system.current_user", "process.list"}:
                actual_method = "command_exit_status_plus_state"
            elif step.capability in {
                "disk.find_large_directories",
                "cleanup.safe_disk_cleanup",
            } or ("approved_paths" in step.args):
                actual_method = "filesystem_metadata_recheck"
            elif "path" in step.args:
                if step.capability == "file.search":
                    actual_method = "filesystem_metadata_recheck"
                else:
                    actual_method = "existence_check"

        if actual_method != expected.verification_method:
            errors.append(
                f"Expected verification method {expected.verification_method}, got {actual_method}"
            )

    if expected.interaction_state == "awaiting_disambiguation" and expected.executed_tools:
        errors.append("Disambiguation scenarios must not execute tools.")

    errors.extend(_compare_common_expectations(scenario, state, executed_tools=[]))
    return {"scenario_id": scenario.id, "success": not errors, "errors": errors}


class FakeWorkflowRegistry:
    """Deterministic fake tools for workflow scenario rehearsal."""

    def __init__(self) -> None:
        self.executed_tools: list[str] = []
        self.port_occupied = True

    def execute(self, name: str, args: dict[str, Any]) -> ToolOutput:
        self.executed_tools.append(name)
        if name == "process.find_by_port":
            pids: list[str] = ["4242"] if self.port_occupied else []
            summary = "Found process on port." if pids else "Port is free."
            return ToolOutput(summary=summary, data={"pids": pids})
        if name == "process.kill":
            self.port_occupied = False
            return ToolOutput(
                summary="Sent TERM to PID 4242.",
                data={"ok": True, "pid": 4242, "signal": "TERM"},
            )
        return ToolOutput(
            summary=f"Unsupported fake tool {name}.", data={"error": "unsupported_fake_tool"}
        )


def run_fake_tool_scenario(scenario: VerificationScenario) -> dict[str, object]:
    """Run a fake-tool workflow without live VM side effects."""
    registry = FakeWorkflowRegistry()
    graph = build_agent_graph(registry).compile()
    result = AgentGraphState.model_validate(graph.invoke(_initial_state(scenario).model_dump()))

    if result.plan and result.plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        phrase = result.pending_confirmation_phrase or ""
        result.user_input = phrase
        result = AgentGraphState.model_validate(graph.invoke(result.model_dump()))

    errors = _compare_common_expectations(scenario, result, executed_tools=registry.executed_tools)

    if scenario.expected.verification_method != "none":
        actual_method = result.verification_result.method if result.verification_result else "none"
        if actual_method != scenario.expected.verification_method:
            errors.append(
                "Expected verification method "
                f"{scenario.expected.verification_method}, got {actual_method}"
            )

    if scenario.expected.verification_outcome == "port_free":
        port_free = registry.port_occupied is False
        if not port_free:
            errors.append("Expected fake port to be free after workflow.")

    return {"scenario_id": scenario.id, "success": not errors, "errors": errors}
