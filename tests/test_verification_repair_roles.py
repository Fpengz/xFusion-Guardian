from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from xfusion.domain.enums import InteractionState, ReasoningRole, StepStatus, VerificationStatus
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState
from xfusion.graph.wiring import build_agent_graph
from xfusion.roles.contracts import RoleProposal
from xfusion.tools.base import ToolOutput


class OutputRegistry:
    def __init__(self, outputs: dict[str, dict[str, object]]) -> None:
        self.outputs = outputs
        self.executed_tools: list[str] = []

    def execute(self, name: str, parameters: dict[str, object]) -> ToolOutput:
        del parameters
        self.executed_tools.append(name)
        return ToolOutput(summary="adapter returned test output", data=self.outputs[name])


def _state(plan: ExecutionPlan, *, user_input: str = "test") -> dict[str, Any]:
    return {
        "user_input": user_input,
        "environment": EnvironmentState(),
        "language": "en",
        "plan": plan,
        "current_step_id": None,
        "policy_decision": None,
        "verification_result": None,
        "last_tool_output": None,
        "step_outputs": {},
        "authorized_step_outputs": {},
        "repair_proposals": [],
        "active_repair_step_ids": [],
        "pending_confirmation_phrase": None,
        "pending_approval_id": None,
        "response": "",
        "audit_records": [],
        "role_runtime_records": [],
    }


def _load_dataset_cases() -> list[dict[str, Any]]:
    path = Path("tests/verification_dataset/scenarios/repair_role_hardening.yaml")
    with path.open("r", encoding="utf-8") as handle:
        return list(yaml.safe_load(handle))


def test_dataset_has_high_value_subset_for_repair_and_roles() -> None:
    cases = _load_dataset_cases()
    ids = {case["case_id"] for case in cases}

    assert {
        "failed_verification_typed_repair_001",
        "repair_revalidation_reapproval_001",
        "term_kill_escalation_001",
        "target_change_invalidates_approval_001",
        "inconclusive_not_success_001",
        "role_boundary_mutation_rejection_001",
    }.issubset(ids)


def test_failed_verification_produces_typed_repair_with_audit_lineage() -> None:
    plan = ExecutionPlan(
        plan_id="repair-typed-lineage",
        goal="verify free port",
        language="en",
        steps=[
            PlanStep(
                id="verify_port",
                capability="process.find_by_port",
                args={"port": 8080, "expect_free": True},
                expected_outputs={"pids": "array"},
                justification="Verify the port is free.",
                verification_method="port_process_recheck",
                success_condition="Port is free.",
                failure_condition="Port remains occupied.",
                fallback_action="stop",
            )
        ],
    )
    graph = build_agent_graph(OutputRegistry({"process.find_by_port": {"pids": [1234]}})).compile()

    state = graph.invoke(_state(plan, user_input="verify port"))

    assert state["repair_proposals"]
    proposal = state["repair_proposals"][0]
    assert proposal.trigger.failed_step_id == "verify_port"
    assert proposal.trigger.verification_id == proposal.audit_link.split(":")[0]
    assert proposal.state == "accepted_for_reentry"
    assert any(step.repair_proposal_id == proposal.proposal_id for step in state["plan"].steps)

    verification_records = [
        record
        for record in state["audit_records"]
        if isinstance(record, dict) and record.get("status") == "verification_failure"
    ]
    assert verification_records
    assert verification_records[-1]["repair_proposals"]


def test_term_to_kill_escalation_requires_new_reapproval_and_reentry() -> None:
    plan = ExecutionPlan(
        plan_id="term-kill-reentry",
        goal="stop process",
        language="en",
        steps=[
            PlanStep(
                id="kill",
                capability="process.kill",
                args={"pid": 1234, "signal": "TERM"},
                expected_outputs={"ok": "boolean"},
                justification="Stop bounded process.",
                verification_method="existence_nonexistence_check",
                success_condition="Target absence confirmed.",
                failure_condition="Target still appears to exist.",
                fallback_action="stop",
            )
        ],
        verification_strategy="verify kill result",
    )
    registry = OutputRegistry({"process.kill": {"ok": True, "pid": 1234, "signal": "TERM"}})
    graph = build_agent_graph(registry).compile()

    state = graph.invoke(_state(plan, user_input="stop pid 1234"))
    first_approval_id = state["pending_approval_id"]
    assert first_approval_id

    state["user_input"] = state["pending_confirmation_phrase"]
    state = graph.invoke(state)

    proposal = state["repair_proposals"][0]
    assert proposal.draft.escalation is True
    assert proposal.draft.args["signal"] == "KILL"
    assert proposal.equivalence.equivalent is False
    assert proposal.approval_requirement.requires_reapproval is True

    assert state["plan"].interaction_state == InteractionState.AWAITING_CONFIRMATION
    assert state["pending_approval_id"]
    assert state["pending_approval_id"] != first_approval_id


def test_target_change_after_failed_verification_invalidates_reused_approval() -> None:
    plan = ExecutionPlan(
        plan_id="target-change-invalidates-reuse",
        goal="retry same kill target",
        language="en",
        steps=[
            PlanStep(
                id="kill",
                capability="process.kill",
                args={"pid": 1234, "signal": "KILL"},
                expected_outputs={"ok": "boolean"},
                justification="Stop bounded process.",
                verification_method="existence_nonexistence_check",
                success_condition="Target absence confirmed.",
                failure_condition="Target still appears to exist.",
                fallback_action="stop",
            )
        ],
        verification_strategy="verify kill result",
        approval_summary={"allow_equivalent_repair_approval_reuse": True},
    )
    registry = OutputRegistry({"process.kill": {"ok": True, "pid": 1234, "signal": "KILL"}})
    graph = build_agent_graph(registry).compile()

    state = graph.invoke(_state(plan, user_input="force stop"))
    state["user_input"] = state["pending_confirmation_phrase"]
    state = graph.invoke(state)

    repair_step = next(step for step in state["plan"].steps if step.repair_of_step_id == "kill")
    assert repair_step.approval_id

    repair_step.status = StepStatus.PENDING
    repair_step.args = {"pid": 9999, "signal": "KILL"}
    repair_step.parameters = {"pid": 9999, "signal": "KILL"}
    state["plan"].interaction_state = InteractionState.EXECUTING
    state["plan"].status = "executing"

    state = graph.invoke(state)

    assert any(record.get("status") == "approval_invalidated" for record in state["audit_records"])


def test_inconclusive_verification_is_never_promoted_to_success() -> None:
    plan = ExecutionPlan(
        plan_id="inconclusive-not-success",
        goal="read current user",
        language="en",
        steps=[
            PlanStep(
                id="whoami",
                capability="system.current_user",
                args={},
                expected_outputs={"username": "string"},
                justification="Read current user.",
                verification_method="unknown_method",
                success_condition="User was returned.",
                failure_condition="User unavailable.",
                fallback_action="stop",
            )
        ],
    )
    graph = build_agent_graph(
        OutputRegistry({"system.current_user": {"username": "operator"}})
    ).compile()

    state = graph.invoke(_state(plan, user_input="whoami"))

    assert state["verification_result"].success is False
    assert state["verification_result"].outcome == VerificationStatus.INCONCLUSIVE
    assert state["plan"].interaction_state == InteractionState.FAILED


def test_role_boundary_runtime_record_rejects_observation_mutation_and_is_auditable() -> None:
    state = AgentGraphState(user_input="role boundary", environment=EnvironmentState())

    record_role_proposal(
        state,
        role=ReasoningRole.OBSERVATION,
        proposal_type="tier_0_capability",
        payload={"capability": "process.kill", "risk_tier": "tier_1"},
        deterministic_layer="test",
        consumes_redacted_inputs_only=True,
    )

    runtime_record = state.role_runtime_records[-1]
    assert runtime_record.proposal.role == ReasoningRole.OBSERVATION
    assert runtime_record.disposition in {"rejected", "downgraded"}
    assert runtime_record.accepted is False
    assert runtime_record.effective_payload == {}

    role_proposal = RoleProposal(
        role=ReasoningRole.VERIFICATION,
        proposal_type="repair_proposal",
        payload={"auto_execute_repair": True},
    )
    state.role_runtime_records.clear()
    record_role_proposal(
        state,
        role=role_proposal.role,
        proposal_type=role_proposal.proposal_type,
        payload=role_proposal.payload,
        deterministic_layer="test",
        consumes_redacted_inputs_only=True,
    )
    assert state.role_runtime_records[-1].accepted is False
