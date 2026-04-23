from __future__ import annotations

from xfusion.domain.enums import InteractionState, StepStatus
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.nodes.confirm import confirm_node
from xfusion.graph.nodes.execute import execute_node
from xfusion.graph.nodes.verify import verify_node
from xfusion.graph.state import AgentGraphState
from xfusion.tools.base import ToolOutput


class StubRegistry:
    def __init__(self, output: ToolOutput) -> None:
        self.output = output
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, name: str, parameters: dict[str, object]) -> ToolOutput:
        self.calls.append((name, parameters))
        return self.output


def make_state(step: PlanStep, user_input: str = "") -> AgentGraphState:
    return AgentGraphState(
        user_input=user_input,
        environment=EnvironmentState(),
        plan=ExecutionPlan(
            plan_id="plan-1",
            goal="test",
            language="en",
            interaction_state=InteractionState.EXECUTING,
            steps=[step],
        ),
    )


def test_tool_success_can_still_fail_verification() -> None:
    step = PlanStep(
        step_id="verify_port",
        intent="Verify port is free",
        tool="process.find_by_port",
        parameters={"port": 8080},
        expected_output="Port is free.",
        verification_method="port_recheck",
        success_condition="No PIDs are listening.",
        failure_condition="A PID is still listening.",
        fallback_action="abort",
    )
    state = make_state(step)

    state = execute_node(
        state, registry=StubRegistry(ToolOutput(summary="ok", data={"pids": ["1234"]}))
    )
    assert state.plan is not None
    plan = state.plan
    assert plan.steps[0].status == StepStatus.RUNNING

    state = verify_node(state)

    assert state.plan is not None
    plan = state.plan
    assert plan.steps[0].status == StepStatus.FAILED
    assert state.verification_result is not None
    assert state.verification_result.success is False


def test_yes_is_rejected_for_risky_confirmation() -> None:
    step = PlanStep(
        step_id="kill_process",
        intent="Kill process",
        tool="process.kill",
        parameters={"pid": 1234},
        expected_output="Killed",
        verification_method="tool_success",
        success_condition="Signal sent.",
        failure_condition="Signal failed.",
        fallback_action="abort",
        requires_confirmation=True,
        confirmation_phrase="I understand the risks of Kill process",
    )
    state = make_state(step, user_input="yes")
    assert state.plan is not None
    state.plan.interaction_state = InteractionState.AWAITING_CONFIRMATION
    state.pending_confirmation_phrase = step.confirmation_phrase

    state = confirm_node(state)

    assert state.plan is not None
    assert state.plan.interaction_state == InteractionState.ABORTED
    assert state.pending_confirmation_phrase is None


def test_exact_confirmation_phrase_succeeds_and_clears_once() -> None:
    phrase = "I understand the risks of Kill process"
    step = PlanStep(
        step_id="kill_process",
        intent="Kill process",
        tool="process.kill",
        parameters={"pid": 1234},
        expected_output="Killed",
        verification_method="tool_success",
        success_condition="Signal sent.",
        failure_condition="Signal failed.",
        fallback_action="abort",
        requires_confirmation=True,
        confirmation_phrase=phrase,
    )
    state = make_state(step, user_input=phrase)
    assert state.plan is not None
    state.plan.interaction_state = InteractionState.AWAITING_CONFIRMATION
    state.pending_confirmation_phrase = phrase

    state = confirm_node(state)

    assert state.plan is not None
    assert state.plan.interaction_state == InteractionState.ABORTED
    assert state.pending_confirmation_phrase is None
    assert state.plan.steps[0].confirmation_phrase is None


def test_confirmation_does_not_persist_across_plans() -> None:
    phrase = "I understand the risks of Kill process"
    first_step = PlanStep(
        step_id="kill_process",
        intent="Kill process",
        tool="process.kill",
        parameters={"pid": 1234},
        expected_output="Killed",
        verification_method="tool_success",
        success_condition="Signal sent.",
        failure_condition="Signal failed.",
        fallback_action="abort",
        requires_confirmation=True,
        confirmation_phrase=phrase,
    )
    state = make_state(first_step, user_input=phrase)
    assert state.plan is not None
    state.plan.interaction_state = InteractionState.AWAITING_CONFIRMATION
    state.pending_confirmation_phrase = phrase
    state = confirm_node(state)

    second_step = PlanStep(
        step_id="kill_again",
        intent="Kill another process",
        tool="process.kill",
        parameters={"pid": 5678},
        expected_output="Killed",
        verification_method="tool_success",
        success_condition="Signal sent.",
        failure_condition="Signal failed.",
        fallback_action="abort",
        requires_confirmation=True,
    )
    state.user_input = phrase
    state.plan = ExecutionPlan(
        plan_id="plan-2",
        goal="second",
        language="en",
        interaction_state=InteractionState.AWAITING_CONFIRMATION,
        steps=[second_step],
    )

    state = confirm_node(state)

    assert state.plan is not None
    assert state.plan.interaction_state == InteractionState.ABORTED
