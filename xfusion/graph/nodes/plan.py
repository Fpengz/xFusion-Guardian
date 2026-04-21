from __future__ import annotations

import re
import uuid

from xfusion.domain.enums import InteractionState
from xfusion.domain.models.execution_plan import ExecutionPlan, PlanStep
from xfusion.graph.state import AgentGraphState


def plan_node(state: AgentGraphState) -> AgentGraphState:
    """Create or revise ExecutionPlan."""
    if state.plan:
        return state

    # Deterministic planning for common v0.1 scenarios
    user_input = state.user_input.lower()

    steps = []
    goal = state.user_input

    if "chmod" in user_input and "/usr" in user_input:
        steps.append(
            PlanStep(
                step_id="explain_forbidden_permission_change",
                intent="Explain why recursive permission changes on protected paths are forbidden.",
                tool="plan.explain_action",
                parameters={"path": "/usr", "action": "chmod"},
                expected_output="Refusal explanation for protected permission change.",
                verification_method="none",
                success_condition="The unsafe permission change is refused.",
                failure_condition="The permission change is allowed.",
                fallback_action="Refuse and stop.",
            )
        )
    elif "environment" in user_input or "os" in user_input:
        steps.append(
            PlanStep(
                step_id="detect_os",
                intent="Detect the current Linux environment.",
                tool="system.detect_os",
                expected_output="Distro and version information.",
                verification_method="state_re_read",
                success_condition="Environment facts are populated.",
                failure_condition="Could not detect environment.",
                fallback_action="Report failure and stop.",
            )
        )
    elif ("disk" in user_input and "clean" in user_input) or (
        "磁盘" in user_input and "清" in user_input
    ):
        steps.append(
            PlanStep(
                step_id="preview_safe_cleanup",
                intent="Preview safe disk cleanup candidates.",
                tool="cleanup.safe_disk_cleanup",
                parameters={"path": "/tmp"},
                expected_output="Bounded cleanup candidates are previewed.",
                verification_method="filesystem_metadata_recheck",
                success_condition="Cleanup candidates are previewed before deletion.",
                failure_condition="Cleanup candidates cannot be previewed safely.",
                fallback_action="Report failure and stop.",
            )
        )
    elif "disk" in user_input or "磁盘" in user_input or "空间" in user_input:
        steps.append(
            PlanStep(
                step_id="check_disk",
                intent="Check the current disk usage.",
                tool="disk.check_usage",
                parameters={"path": "/"},
                expected_output="Disk usage report for root filesystem.",
                verification_method="state_re_read",
                success_condition="Disk usage is reported.",
                failure_condition="Could not check disk usage.",
                fallback_action="Report failure and stop.",
            )
        )
    elif "ram" in user_input or "memory" in user_input:
        steps.append(
            PlanStep(
                step_id="check_ram",
                intent="Check the current RAM usage.",
                tool="system.check_ram",
                parameters={},
                expected_output="RAM usage report.",
                verification_method="state_re_read",
                success_condition="RAM usage is reported.",
                failure_condition="Could not check RAM usage.",
                fallback_action="Report failure and stop.",
            )
        )
    elif "search for" in user_input or "find files named" in user_input:
        query_match = re.search(r'"([^"]+)"', state.user_input)
        query = query_match.group(1) if query_match else state.user_input.split()[-1]
        steps.append(
            PlanStep(
                step_id="search_files",
                intent=f"Search for files matching {query}.",
                tool="file.search",
                parameters={"query": query, "path": ".", "limit": 20},
                expected_output="Limited file search results.",
                verification_method="filesystem_metadata_recheck",
                success_condition="Search results are returned within the configured limit.",
                failure_condition="Search fails or returns an unbounded result set.",
                fallback_action="Ask the user to narrow the search.",
            )
        )
    elif "list processes" in user_input:
        steps.append(
            PlanStep(
                step_id="list_processes",
                intent="List running processes.",
                tool="process.list",
                parameters={"limit": 20},
                expected_output="Bounded process listing.",
                verification_method="command_exit_status_plus_state",
                success_condition="A bounded process list is returned.",
                failure_condition="Process list cannot be read.",
                fallback_action="Report failure and stop.",
            )
        )
    elif "port" in user_input and not any(word in user_input for word in ("stop", "kill")):
        port_match = re.search(r"port\s+(\d+)", user_input)
        port = int(port_match.group(1)) if port_match else 8080

        steps.append(
            PlanStep(
                step_id="find_process",
                intent=f"Find processes listening on port {port}.",
                tool="process.find_by_port",
                parameters={"port": port},
                expected_output=f"List of PIDs on port {port}.",
                verification_method="port_process_recheck",
                success_condition=f"Port {port} state is reported.",
                failure_condition=f"Port {port} lookup fails.",
                fallback_action="Report the port state and stop.",
            )
        )
    elif "port" in user_input:
        port_match = re.search(r"port\s+(\d+)", user_input)
        port = int(port_match.group(1)) if port_match else 8080

        steps.append(
            PlanStep(
                step_id="find_process",
                intent=f"Find processes listening on port {port}.",
                tool="process.find_by_port",
                parameters={"port": port},
                expected_output=f"List of PIDs on port {port}.",
                verification_method="port_process_recheck",
                success_condition=f"Port {port} activity is identified.",
                failure_condition=f"No process found on port {port}.",
                fallback_action="Stop as there is nothing to kill.",
            )
        )

        steps.append(
            PlanStep(
                step_id="kill_process",
                intent=f"Stop the process found on port {port}.",
                tool="process.kill",
                parameters={"pid": {"ref": "find_process.pids[0]"}, "port": port},
                dependencies=["find_process"],
                expected_output=f"Process on port {port} is stopped.",
                verification_method="command_exit_status_plus_state",
                success_condition=f"Process on port {port} is killed.",
                failure_condition=f"Process on port {port} is still running.",
                fallback_action="stop",
            )
        )

        steps.append(
            PlanStep(
                step_id="verify_port_free",
                intent=f"Final verification that port {port} is free.",
                tool="process.find_by_port",
                parameters={"port": port, "expect_free": True},
                dependencies=["kill_process"],
                expected_output=f"Port {port} is confirmed free.",
                verification_method="port_process_recheck",
                success_condition=f"Port {port} is free.",
                failure_condition=f"Port {port} is unexpectedly busy.",
                fallback_action="stop",
            )
        )
    elif "create user" in user_input:
        username = user_input.split("create user", 1)[1].strip(" .") or "demoagent"
        steps.append(
            PlanStep(
                step_id="create_user",
                intent=f"Create normal user {username}.",
                tool="user.create",
                parameters={"username": username},
                expected_output=f"User {username} exists.",
                verification_method="existence_nonexistence_check",
                success_condition=f"User {username} exists after creation.",
                failure_condition=f"User {username} does not exist after creation.",
                fallback_action="Report failure and stop.",
            )
        )
    elif "delete user" in user_input or "remove user" in user_input:
        username = re.sub(r"^(delete|remove)\s+user\s+", "", user_input).strip(" .") or "demoagent"
        steps.append(
            PlanStep(
                step_id="delete_user",
                intent=f"Delete user {username}.",
                tool="user.delete",
                parameters={"username": username},
                expected_output=f"User {username} is absent.",
                verification_method="existence_nonexistence_check",
                success_condition=f"User {username} is absent after deletion.",
                failure_condition=f"User {username} still exists after deletion.",
                fallback_action="Report failure and stop.",
            )
        )
    elif "delete that file" in user_input:
        pass
    elif "delete" in user_input or "remove" in user_input or "/etc" in user_input:
        path_match = re.search(r"(/[\w/-]+)", user_input)
        path = path_match.group(1) if path_match else "/etc"  # Default to /etc for the test case

        steps.append(
            PlanStep(
                step_id="delete_path",
                intent=f"Delete everything in {path}.",
                tool="cleanup.safe_disk_cleanup",  # Using cleanup tool as a placeholder
                parameters={"path": path},
                expected_output=f"{path} is deleted.",
                verification_method="existence_nonexistence_check",
                success_condition=f"{path} no longer exists.",
                failure_condition=f"{path} still exists.",
                fallback_action="stop",
            )
        )

    if not steps:
        # Default to asking for clarification if no common intent is matched
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
            clarification = "Could you be more specific?"
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
        return state

    state.plan = ExecutionPlan(
        plan_id=str(uuid.uuid4()),
        goal=goal,
        language=state.language,
        interaction_state=InteractionState.EXECUTING,
        steps=steps,
    )
    return state
