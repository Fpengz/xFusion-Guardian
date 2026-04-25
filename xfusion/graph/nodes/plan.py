from __future__ import annotations

import uuid

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.capabilities.resolver import resolve_intent_to_capability
from xfusion.domain.enums import InteractionState, ReasoningRole
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState
from xfusion.llm.client import LLMClient
from xfusion.app.settings import Settings


def plan_node(state: AgentGraphState) -> AgentGraphState:
    """Create an ExecutionPlan using LLM-driven capability resolution.
    
    v0.2.4.2: The LLM acts as the router, selecting capabilities from the registry
    based on natural language intent, similar to how agents load tools.
    
    Flow:
    1. Build capability registry with tool schemas
    2. LLM analyzes user input and selects appropriate capability
    3. LLM extracts parameters from user input
    4. System creates execution plan with resolved capability
    5. For complex workflows, add verification steps automatically
    """
    if state.plan:
        return state

    registry = build_default_capability_registry()
    
    # Initialize LLM client for intent resolution
    settings = Settings()
    llm_client = LLMClient(settings) if settings.llm_base_url else None
    
    # Use LLM to resolve intent to capability
    capability_name, extracted_args, clarification = resolve_intent_to_capability(
        user_input=state.user_input,
        registry=registry,
        llm_client=llm_client,
        language=state.language or "en",
    )

    steps = []
    goal = state.user_input

    # Handle clarification requests from LLM
    if clarification:
        state.plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            goal=goal,
            language=state.language,
            interaction_state=InteractionState.AWAITING_DISAMBIGUATION,
            steps=[],
            status="awaiting_disambiguation",
            clarification_question=clarification,
        )
        state.response = clarification
        record_role_proposal(
            state,
            role=ReasoningRole.SUPERVISOR,
            proposal_type="clarification",
            payload={"question": clarification},
            deterministic_layer="plan_node",
            consumes_redacted_inputs_only=True,
        )
        return state

    # Handle no matching capability
    if not capability_name:
        clarification = "I don't have a capability that matches your request. Could you be more specific?"
        state.plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            goal=goal,
            language=state.language,
            interaction_state=InteractionState.AWAITING_DISAMBIGUATION,
            steps=[],
            status="awaiting_disambiguation",
            clarification_question=clarification,
        )
        state.response = clarification
        record_role_proposal(
            state,
            role=ReasoningRole.SUPERVISOR,
            proposal_type="clarification",
            payload={"question": clarification},
            deterministic_layer="plan_node",
            consumes_redacted_inputs_only=True,
        )
        return state

    # Single-step plan from LLM-resolved capability
    step_id = f"execute_{capability_name.replace('.', '_')}"
    steps.append(
        PlanStep(
            step_id=step_id,
            intent=f"Execute {capability_name} with resolved parameters.",
            capability=capability_name,
            args=extracted_args or {},
        )
    )

    # Handle special multi-step workflows that need explicit verification
    # These are cases where we need to add verification steps automatically
    if capability_name == "process.kill":
        # Add verification step for process termination
        port = (extracted_args or {}).get("port")
        if port:
            steps.append(
                PlanStep(
                    step_id="verify_port_free",
                    intent=f"Final verification that port {port} is free.",
                    capability="process.find_by_port",
                    args={"port": port, "expect_free": True},
                    depends_on=[step_id],
                )
            )

    mutating_tools = {
        "process.kill",
        "user.create",
        "user.delete",
        "cleanup.safe_disk_cleanup",
    }
    verification_strategy = (
        "Verify mutating workflow outcomes with planned post-action checks."
        if any(step.capability in mutating_tools for step in steps)
        else None
    )

    state.plan = ExecutionPlan(
        plan_id=str(uuid.uuid4()),
        goal=goal,
        language=state.language,
        interaction_state=InteractionState.EXECUTING,
        steps=steps,
        verification_strategy=verification_strategy,
    )

    read_only_capabilities = {
        "system.current_user",
        "system.detect_os",
        "disk.check_usage",
        "process.find_by_port",
        "file.preview_metadata",
        "file.search",
        "process.list",
    }
    observation_capabilities = [
        step.capability for step in steps if step.capability in read_only_capabilities
    ]
    record_role_proposal(
        state,
        role=ReasoningRole.OBSERVATION,
        proposal_type="tier_0_capability",
        payload={"capabilities": observation_capabilities, "risk_tier": "tier_0"},
        deterministic_layer="plan_node",
        consumes_redacted_inputs_only=True,
    )
    record_role_proposal(
        state,
        role=ReasoningRole.DIAGNOSIS,
        proposal_type="hypothesis",
        payload={"summary": "LLM-driven capability resolver selected capabilities for the request."},
        deterministic_layer="plan_node",
        consumes_redacted_inputs_only=True,
    )
    record_role_proposal(
        state,
        role=ReasoningRole.PLANNING,
        proposal_type="workflow_dag",
        payload={
            "plan_id": state.plan.plan_id,
            "step_ids": [step.step_id for step in state.plan.steps],
            "verification_strategy": state.plan.verification_strategy,
        },
        deterministic_layer="plan_node",
        consumes_redacted_inputs_only=True,
    )
    return state
