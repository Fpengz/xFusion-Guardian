from __future__ import annotations

from xfusion.domain.enums import StepStatus
from xfusion.domain.models.verification import VerificationResult
from xfusion.graph.state import AgentGraphState


def _no_tool_error(output: dict[str, object]) -> bool:
    return "error" not in output


def _has_any(output: dict[str, object], *keys: str) -> bool:
    return any(bool(output.get(key)) for key in keys)


def _verify_state_re_read(output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Tool output contained an error."
    if output:
        return True, "State was re-read and returned structured facts."
    return False, "State re-read returned no structured facts."


def _verify_port_process_recheck(
    step_parameters: dict[str, object],
    step_success_condition: str,
    output: dict[str, object],
) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Port/process re-check returned an error."

    pids = output.get("pids")
    matches = output.get("matches")
    stdout = str(output.get("stdout", ""))
    condition = step_success_condition.lower()
    expect_free = (
        bool(step_parameters.get("expect_free")) or "free" in condition or "no pid" in condition
    )

    if expect_free:
        port_is_free = pids == [] or matches == [] or output.get("ok") is True
        return (
            port_is_free,
            "Port is free after re-check."
            if port_is_free
            else "Port still has matching process activity.",
        )

    has_result = (
        bool(pids) or bool(matches) or bool(stdout) or pids == [] or output.get("ok") is True
    )
    return (
        has_result,
        "Port/process state was re-read."
        if has_result
        else "Port/process state could not be re-read.",
    )


def _verify_filesystem_metadata(output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Filesystem metadata re-check returned an error."
    if (
        _has_any(output, "matches", "items", "previewed_candidates")
        or output.get("exists") is not None
    ):
        return True, "Filesystem metadata was returned in structured output."
    return False, "Filesystem metadata was missing from structured output."


def _verify_existence(step_success_condition: str, output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Existence check returned an error."

    condition = step_success_condition.lower()
    if "absent" in condition or "no longer exists" in condition:
        verified = output.get("absent") is True or output.get("exists") is False
        return (
            verified,
            "Target absence confirmed." if verified else "Target still appears to exist.",
        )

    verified = output.get("exists") is True or output.get("verified") is True
    return (
        verified,
        "Target existence confirmed." if verified else "Target existence was not confirmed.",
    )


def _verify_command_exit_plus_state(output: dict[str, object]) -> tuple[bool, str]:
    if not _no_tool_error(output):
        return False, "Command output contained an error."
    if _has_any(output, "processes", "pid", "stdout") or output.get("ok") is True:
        return True, "Command succeeded and returned structured state evidence."
    return False, "Command did not return structured state evidence."


def _dispatch_verification(
    method: str,
    step_success_condition: str,
    step_parameters: dict[str, object],
    output: dict[str, object],
) -> tuple[bool, str]:
    normalized = method.replace("-", "_")
    if normalized in {"state_read", "state_re_read"}:
        return _verify_state_re_read(output)
    if normalized in {"port_recheck", "port_process_recheck"}:
        return _verify_port_process_recheck(step_parameters, step_success_condition, output)
    if normalized in {"filesystem_metadata_recheck", "filesystem_metadata_re_read"}:
        return _verify_filesystem_metadata(output)
    if normalized in {"existence_check", "existence_nonexistence_check"}:
        return _verify_existence(step_success_condition, output)
    if normalized in {"command_exit_status_plus_state", "tool_success"}:
        return _verify_command_exit_plus_state(output)
    if normalized == "none":
        return True, "No verification required for non-executed/refusal-only step."
    return False, f"Unknown verification method: {method}"


def verify_node(state: AgentGraphState) -> AgentGraphState:
    """Run mandatory post-action verification for the current step."""
    if not state.plan:
        return state

    if not state.current_step_id:
        step = state.plan.next_executable_step()
        if step:
            state.current_step_id = step.step_id

    if not state.current_step_id:
        return state

    step = next(
        (candidate for candidate in state.plan.steps if candidate.step_id == state.current_step_id),
        None,
    )
    if not step or step.status != StepStatus.RUNNING:
        return state

    tool_output = state.step_outputs.get(step.step_id, state.last_tool_output or {})
    success, summary = _dispatch_verification(
        step.verification_method,
        step.success_condition,
        step.parameters,
        tool_output,
    )

    state.verification_result = VerificationResult(
        success=success,
        method=step.verification_method,
        summary=summary,
        outcome="success" if success else "failure",
        details=tool_output,
    )

    if success:
        step.status = StepStatus.SUCCESS
    else:
        step.status = StepStatus.FAILED
        state.response = f"Verification failed: {summary}"

    return state
