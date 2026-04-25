from __future__ import annotations

import re
import uuid

from xfusion.app.settings import Settings
from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.capabilities.resolver import resolve_intent_to_capability
from xfusion.domain.enums import InteractionState, ReasoningRole
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.roles import record_role_proposal
from xfusion.graph.state import AgentGraphState
from xfusion.llm.client import LLMClient


def _looks_like_file_search(user_input: str) -> bool:
    return (
        "find" in user_input
        and "file" in user_input
        and any(token in user_input for token in ("under ", " in ", "named ", "*.", " all "))
    )


def _extract_file_query(raw_input: str) -> str | None:
    quoted = re.search(r'"([^"]+)"', raw_input)
    if quoted:
        return quoted.group(1).strip()

    glob_pattern = re.search(r"(\*\.[A-Za-z0-9]+)", raw_input)
    if glob_pattern:
        return glob_pattern.group(1).strip()

    named = re.search(r"(?:named|called)\s+([A-Za-z0-9._-]+)", raw_input, flags=re.IGNORECASE)
    if named:
        return named.group(1).strip()

    extension = re.search(r"\.([A-Za-z0-9]{1,16})\s+files?", raw_input, flags=re.IGNORECASE)
    if extension:
        return f"*.{extension.group(1).lower()}"

    return None


def _extract_search_path(raw_input: str) -> str | None:
    path_match = re.search(
        r"(?:under|in)\s+([~/A-Za-z0-9._/\-]+)",
        raw_input,
        flags=re.IGNORECASE,
    )
    if not path_match:
        return None
    return path_match.group(1).rstrip(".,;:)")


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
    user_input = state.user_input.lower()

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

    # Fallback to keyword-based multi-step planning if LLM failed or for complex legacy patterns
    if not capability_name:
        if "chmod" in user_input and "/usr" in user_input:
            steps.append(
                PlanStep(
                    step_id="explain_forbidden_permission_change",
                    intent=(
                        "Explain why recursive permission changes on protected paths are forbidden."
                    ),
                    capability="plan.explain_action",
                    args={"path": "/usr", "action": "chmod"},
                )
            )
        elif "environment" in user_input or "os" in user_input:
            steps.append(
                PlanStep(
                    step_id="detect_os",
                    intent="Detect the current Linux environment.",
                    capability="system.detect_os",
                )
            )
        elif ("disk" in user_input and ("clean" in user_input or "full" in user_input)) or (
            "磁盘" in user_input and "清" in user_input
        ):
            cleanup_paths = ["/tmp", "/var/tmp"]
            steps.extend(
                [
                    PlanStep(
                        step_id="check_disk_pressure",
                        intent="Check disk pressure before cleanup.",
                        capability="disk.check_usage",
                        args={"path": "/"},
                    ),
                    PlanStep(
                        step_id="find_large_candidates",
                        intent="Identify bounded cleanup contributors.",
                        capability="disk.find_large_directories",
                        args={"path": "/tmp", "limit": 10},
                        depends_on=["check_disk_pressure"],
                    ),
                    PlanStep(
                        step_id="preview_safe_cleanup",
                        intent="Preview safe cleanup candidates.",
                        capability="cleanup.safe_disk_cleanup",
                        args={
                            "approved_paths": cleanup_paths,
                            "candidate_class": "demo_cache",
                            "older_than_days": 0,
                            "max_files": 20,
                            "max_bytes": 50_000_000,
                            "execute": False,
                        },
                        depends_on=["find_large_candidates"],
                    ),
                    PlanStep(
                        step_id="execute_safe_cleanup",
                        intent="Delete only approved previewed cleanup candidates.",
                        capability="cleanup.safe_disk_cleanup",
                        args={
                            "approved_paths": cleanup_paths,
                            "candidate_class": "demo_cache",
                            "older_than_days": 0,
                            "max_files": 20,
                            "max_bytes": 50_000_000,
                            "execute": True,
                        },
                        depends_on=["preview_safe_cleanup"],
                        verification_step_ids=["verify_disk_after_cleanup"],
                    ),
                    PlanStep(
                        step_id="verify_disk_after_cleanup",
                        intent="Verify disk state after cleanup.",
                        capability="disk.check_usage",
                        args={"path": "/"},
                        depends_on=["execute_safe_cleanup"],
                    ),
                ]
            )
        elif "disk" in user_input or "磁盘" in user_input or "空间" in user_input:
            steps.append(
                PlanStep(
                    step_id="check_disk",
                    intent="Check the current disk usage.",
                    capability="disk.check_usage",
                    args={"path": "/"},
                )
            )
        elif "ram" in user_input or "memory" in user_input:
            steps.append(
                PlanStep(
                    step_id="check_ram",
                    intent="Check the current RAM usage.",
                    capability="system.check_ram",
                    args={},
                )
            )
        elif "preview metadata for" in user_input:
            path = state.user_input.split("for", 1)[1].strip(" .") or "."
            steps.append(
                PlanStep(
                    step_id="preview_metadata",
                    intent=f"Preview metadata for {path}.",
                    capability="file.preview_metadata",
                    args={"path": path},
                )
            )
        elif (
            "search for" in user_input
            or "find files named" in user_input
            or _looks_like_file_search(user_input)
        ):
            query = _extract_file_query(state.user_input)
            path = _extract_search_path(state.user_input) or "."
            if not query:
                query_match = re.search(r'"([^"]+)"', state.user_input)
                query = query_match.group(1) if query_match else state.user_input.split()[-1]
            steps.append(
                PlanStep(
                    step_id="search_files",
                    intent=f"Search for files matching {query}.",
                    capability="file.search",
                    args={"query": query, "path": path, "limit": 50},
                )
            )
        elif "list processes" in user_input:
            steps.append(
                PlanStep(
                    step_id="list_processes",
                    intent="List running processes.",
                    capability="process.list",
                    args={"limit": 20},
                )
            )
        elif "port" in user_input:
            port_match = re.search(r"port\s+(\d+)", user_input)
            port = int(port_match.group(1)) if port_match else 8080

            steps.append(
                PlanStep(
                    step_id="find_process",
                    intent=f"Find processes listening on port {port}.",
                    capability="process.find_by_port",
                    args={"port": port},
                )
            )

            if any(word in user_input for word in ("stop", "kill")):
                steps.append(
                    PlanStep(
                        step_id="kill_process",
                        intent=f"Stop the process found on port {port}.",
                        capability="process.kill",
                        args={"pid": "$steps.find_process.outputs.pids[0]", "port": port},
                        depends_on=["find_process"],
                        verification_step_ids=["verify_port_free"],
                    )
                )

                steps.append(
                    PlanStep(
                        step_id="verify_port_free",
                        intent=f"Final verification that port {port} is free.",
                        capability="process.find_by_port",
                        args={"port": port, "expect_free": True},
                        depends_on=["kill_process"],
                    )
                )
        elif "create user" in user_input:
            username = user_input.split("create user", 1)[1].strip(" .") or "demoagent"
            steps.append(
                PlanStep(
                    step_id="create_user",
                    intent=f"Create normal user {username}.",
                    capability="user.create",
                    args={"username": username},
                )
            )
        elif "delete user" in user_input or "remove user" in user_input:
            username = (
                re.sub(r"^(delete|remove)\s+user\s+", "", user_input).strip(" .") or "demoagent"
            )
            steps.append(
                PlanStep(
                    step_id="delete_user",
                    intent=f"Delete user {username}.",
                    capability="user.delete",
                    args={"username": username},
                )
            )
        elif (
            "delete" in user_input or "remove" in user_input or "/etc" in user_input
        ) and "delete that file" not in user_input:
            path_match = re.search(r"(/[\w/-]+)", user_input)
            path = path_match.group(1) if path_match else "/etc"

            steps.append(
                PlanStep(
                    step_id="delete_path",
                    intent=f"Delete everything in {path}.",
                    capability="cleanup.safe_disk_cleanup",
                    args={"path": path},
                )
            )

    # If still no steps, ask for clarification
    if not capability_name and not steps:
        if "clean logs" in user_input:
            clarification = "Which log path, age, and size scope should I use?"
        elif "stop it" in user_input:
            clarification = "Which process or port should I stop?"
        elif "find files" in user_input:
            clarification = "What file name or pattern should I search for?"
        elif "clean everything" in user_input:
            clarification = "What bounded cleanup scope should I use?"
        elif "delete that file" in user_input:
            clarification = "Which file should I delete? Please provide the exact path."
        else:
            clarification = (
                "I don't have a capability that matches your request. Could you be more specific?"
            )

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

    # If LLM resolved a single capability and we don't have keyword steps yet
    if capability_name and not steps:
        # Standardize step IDs for common capabilities to maintain test compatibility
        standard_ids = {
            "disk.check_usage": "check_disk",
            "system.detect_os": "detect_os",
            "process.list": "list_processes",
            "system.check_ram": "check_ram",
            "file.preview_metadata": "preview_metadata",
            "file.search": "search_files",
            "user.create": "create_user",
            "user.delete": "delete_user",
        }
        standard_intents = {
            "system.detect_os": "Detect the current Linux environment.",
        }
        step_id = standard_ids.get(capability_name, f"execute_{capability_name.replace('.', '_')}")

        steps.append(
            PlanStep(
                step_id=step_id,
                intent=standard_intents.get(
                    capability_name,
                    f"Execute {capability_name} with resolved parameters.",
                ),
                capability=capability_name,
                args=extracted_args or {},
            )
        )

        # Add verification for specific mutating tools if resolved via LLM
        if capability_name == "process.kill":
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
        payload={
            "summary": "LLM-driven capability resolver selected capabilities for the request."
        },
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
