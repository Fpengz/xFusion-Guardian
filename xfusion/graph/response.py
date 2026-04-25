from __future__ import annotations

import json
from typing import Any, cast

from xfusion.capabilities.registry import build_default_capability_registry
from xfusion.domain.enums import InteractionState
from xfusion.graph.state import AgentGraphState


def format_agent_response(state: AgentGraphState) -> str:
    """Build user-facing or debug response from authoritative audited state."""
    if not state.plan:
        return state.response

    plan = state.plan
    source_record = _latest_authoritative_record(state)
    audit_status = source_record["status"] if source_record else "not_recorded"
    response = (
        _format_debug_response(state, source_record=source_record, audit_status=str(audit_status))
        if state.response_mode == "debug"
        else _format_normal_response(state, source_record=source_record)
    )
    state.audit_records.append(
        {
            "timestamp": "final",
            "plan_id": plan.plan_id,
            "event": "final_explanation_snapshot",
            "response": response,
            "source_audit_status": audit_status,
            "source_audit_record": source_record,
            "response_mode": state.response_mode,
        }
    )
    return response


def _format_normal_response(
    state: AgentGraphState,
    *,
    source_record: dict[str, object] | None,
) -> str:
    result = _result_summary(state, source_record)
    about_to_run = _about_to_run_summary(state, source_record)
    ran = _ran_summary(state, source_record)
    output = _output_summary(state, source_record)
    meaning = _meaning_summary(state, source_record, fallback=result)
    verification = _verification_summary(state, source_record)
    lines = [
        f"Result: {result}",
        f"About to run: {about_to_run}",
        f"Ran: {ran}",
        f"Output: {output}",
        f"What this means: {meaning}",
        f"Verification: {verification}",
    ]
    next_actions = _next_actions(state)
    if next_actions:
        lines.append("Next actions:")
        lines.extend(f"{i}. {action}" for i, action in enumerate(next_actions, start=1))
    return "\n".join(lines)


def _format_debug_response(
    state: AgentGraphState,
    *,
    source_record: dict[str, object] | None,
    audit_status: str,
) -> str:
    plan = state.plan
    if not plan:
        return state.response
    env = state.environment
    source_plan = source_record.get("plan_draft") if source_record else None
    source_plan_dict = cast(dict[str, Any], source_plan) if isinstance(source_plan, dict) else {}
    source_steps = source_plan_dict.get("steps", [])
    plan_tools = _plan_tools_from_audit(source_steps) or (
        ", ".join(str(step.capability) for step in plan.steps) if plan.steps else "none"
    )
    policy_record = _policy_record_from_audit(source_record)
    risk = policy_record.get("risk_tier", "none")
    risk_reason = policy_record.get("reason", "No policy action needed.")
    verification_record = cast(
        dict[str, Any], source_record.get("verification_result", {}) if source_record else {}
    )
    verification = (
        verification_record.get("summary")
        if isinstance(verification_record, dict) and verification_record.get("summary")
        else "Not executed for this state."
    )
    action = (
        str(source_record.get("summary"))
        if source_record and source_record.get("summary")
        else state.response or "No action executed."
    )
    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        action = f"Confirmation required: type '{state.pending_confirmation_phrase}'."
    elif plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        action = plan.clarification_question or state.response
    next_step = _next_recommendation(state)
    intent = (
        str(source_record.get("interpreted_intent"))
        if source_record and source_record.get("interpreted_intent")
        else plan.goal
    )
    return "\n".join(
        [
            f"Intent: {intent}",
            (
                "Environment: "
                f"{env.distro_family} {env.distro_version}; "
                f"user={env.current_user}; sudo={env.sudo_available}; "
                f"systemd={env.systemd_available}; package={env.package_manager}; "
                f"disk_pressure={env.disk_pressure}"
            ),
            f"Plan: {len(plan.steps)} step(s): {plan_tools}",
            f"Risk: {risk} - {risk_reason}",
            f"Action: {action}",
            f"Command Trace: {_format_trace_for_debug(source_record)}",
            f"Verification: {verification}",
            f"Audit: explanation derived from authoritative audit status={audit_status}",
            f"State: {plan.interaction_state}; status={plan.status}",
            f"Next: {next_step}",
        ]
    )


def _result_summary(state: AgentGraphState, source_record: dict[str, object] | None) -> str:
    plan = state.plan
    if not plan:
        return state.response or "No action executed."

    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        phrase = state.pending_confirmation_phrase
        if phrase:
            return f"Ready to proceed. Waiting for your typed confirmation: '{phrase}'."
        return "Ready to proceed. Waiting for your confirmation."
    if plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        return plan.clarification_question or "I need one missing target or scope detail."
    if plan.interaction_state == InteractionState.REFUSED:
        reason = _policy_reason(source_record)
        return f"I couldn't run this request because {reason}"
    if plan.interaction_state == InteractionState.FAILED:
        detail = _first_nonempty_line(_action_summary(source_record, fallback=state.response))
        if detail:
            return f"I couldn't complete this safely. {detail}"
        return "I couldn't complete this safely."

    action = _action_summary(source_record, fallback=state.response)
    if action:
        first_line = _first_nonempty_line(action)
        if first_line:
            return f"Done. {first_line}"
    return "Done."


def _verification_summary(state: AgentGraphState, source_record: dict[str, object] | None) -> str:
    plan = state.plan
    if not plan:
        return "No verification data."
    if plan.interaction_state in {
        InteractionState.AWAITING_CONFIRMATION,
        InteractionState.AWAITING_DISAMBIGUATION,
        InteractionState.REFUSED,
    }:
        return "No changes were made."

    verification_record = cast(
        dict[str, Any], source_record.get("verification_result", {}) if source_record else {}
    )
    if isinstance(verification_record, dict):
        summary = verification_record.get("summary")
        if summary:
            return str(summary)
    if plan.interaction_state == InteractionState.COMPLETED:
        return "Completed and verified."
    return "Verification did not pass."


def _next_actions(state: AgentGraphState) -> list[str]:
    plan = state.plan
    if not plan:
        return ["Ask for a Linux administration task."]
    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        typed = state.pending_confirmation_phrase
        typed_action = (
            f"Type exactly '{typed}' to proceed." if typed else "Provide the required confirmation."
        )
        return [typed_action, "Reply with anything else to abort this action."]
    if plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        question = plan.clarification_question or "Specify the missing target or scope."
        return [question]
    if plan.interaction_state == InteractionState.REFUSED:
        return [
            "Use a narrower safe target and retry.",
            "If helpful, ask for a read-only inspection first.",
        ]
    if plan.interaction_state == InteractionState.FAILED:
        return [
            "Review the failure detail above and retry with a clearer or narrower target.",
            "Run a read-only check first to gather current state before retrying.",
        ]
    if plan.interaction_state == InteractionState.COMPLETED:
        return []
    return ["Continue with the next safe planned step."]


def _policy_reason(source_record: dict[str, object] | None) -> str:
    policy_record = _policy_record_from_audit(source_record)
    reason = policy_record.get("reason_text") or policy_record.get("reason")
    if reason:
        return str(reason).rstrip(".") + "."
    summary = _action_summary(source_record, fallback="")
    if summary:
        return _first_nonempty_line(summary).rstrip(".") + "."
    return "it violates policy constraints."


def _action_summary(source_record: dict[str, object] | None, *, fallback: str) -> str:
    if source_record and source_record.get("summary"):
        return str(source_record.get("summary"))
    return fallback


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _should_render_command_transcript(
    state: AgentGraphState,
    source_record: dict[str, object] | None,
) -> bool:
    plan = state.plan
    if not plan or plan.interaction_state != InteractionState.COMPLETED:
        return False
    capability = _capability_from_source_record(source_record)
    if not capability:
        return False
    try:
        definition = build_default_capability_registry().require(capability)
    except KeyError:
        return False
    return bool(definition.is_read_only and _extract_command_trace(source_record))


def _about_to_run_summary(state: AgentGraphState, source_record: dict[str, object] | None) -> str:
    traced = _format_trace_commands(source_record, key="planned_argv")
    if traced != "No command trace recorded.":
        return traced
    if not state.plan:
        return "No command planned."
    if not state.plan.steps:
        return "No command planned."
    capabilities = ", ".join(str(step.capability) for step in state.plan.steps)
    if state.plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        return (
            "No command planned yet; awaiting clarification. "
            f"Draft capability scope: {capabilities}."
        )
    return f"No shell command trace recorded. Planned capability path: {capabilities}."


def _ran_summary(state: AgentGraphState, source_record: dict[str, object] | None) -> str:
    traced = _format_trace_commands(source_record, key="ran_argv")
    if traced != "No command trace recorded.":
        return traced
    if not state.plan:
        return "No command ran."
    if state.plan.interaction_state in {
        InteractionState.AWAITING_CONFIRMATION,
        InteractionState.AWAITING_DISAMBIGUATION,
        InteractionState.REFUSED,
    }:
        return "No command ran."
    return "No command trace recorded by adapter runtime."


def _output_summary(state: AgentGraphState, source_record: dict[str, object] | None) -> str:
    trace_output = _format_trace_output_snippet(source_record)
    if trace_output != "No output snippet recorded.":
        return trace_output
    if source_record and source_record.get("normalized_output"):
        return _clip_text(str(source_record.get("normalized_output")), limit=240)
    action = _action_summary(source_record, fallback=state.response)
    first = _first_nonempty_line(action)
    if first:
        return first
    return "No command output recorded."


def _meaning_summary(
    state: AgentGraphState,
    source_record: dict[str, object] | None,
    *,
    fallback: str,
) -> str:
    meaning = _first_nonempty_line(_action_summary(source_record, fallback=state.response))
    if meaning:
        return meaning
    first = _first_nonempty_line(fallback)
    return first or "Execution completed."


def _capability_from_source_record(source_record: dict[str, object] | None) -> str:
    if not source_record:
        return ""
    action = source_record.get("action_taken")
    if not isinstance(action, dict):
        return ""
    action_dict = cast(dict[str, Any], action)
    capability = action_dict.get("capability")
    return str(capability) if capability else ""


def _extract_command_trace(source_record: dict[str, object] | None) -> list[dict[str, object]]:
    if not source_record:
        return []
    action = source_record.get("action_taken")
    if not isinstance(action, dict):
        return []
    action_dict = cast(dict[str, Any], action)
    trace = action_dict.get("command_trace")
    if not isinstance(trace, list):
        return []
    normalized: list[dict[str, object]] = []
    for entry in trace:
        if isinstance(entry, dict):
            normalized.append({str(k): v for k, v in entry.items()})
    return normalized


def _format_trace_commands(source_record: dict[str, object] | None, *, key: str) -> str:
    trace = _extract_command_trace(source_record)
    if not trace:
        return "No command trace recorded."
    commands: list[str] = []
    for entry in trace:
        argv = entry.get(key)
        if isinstance(argv, list) and all(isinstance(part, str) for part in argv):
            commands.append(json.dumps(argv))
    if not commands:
        return "No command trace recorded."
    return "; ".join(commands)


def _format_trace_output_snippet(source_record: dict[str, object] | None) -> str:
    trace = _extract_command_trace(source_record)
    if not trace:
        return "No output snippet recorded."
    snippets: list[str] = []
    for entry in trace:
        stdout = str(entry.get("stdout_excerpt", "")).strip()
        stderr = str(entry.get("stderr_excerpt", "")).strip()
        exit_code = entry.get("exit_code")
        if stdout:
            snippets.append(f"exit={exit_code} stdout={_clip_text(stdout)}")
        elif stderr:
            snippets.append(f"exit={exit_code} stderr={_clip_text(stderr)}")
        else:
            snippets.append(f"exit={exit_code} (no output)")
    return " | ".join(snippets[:2])


def _clip_text(text: str, *, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _format_trace_for_debug(source_record: dict[str, object] | None) -> str:
    trace = _extract_command_trace(source_record)
    if not trace:
        return "none"
    return json.dumps(trace)


def _latest_authoritative_record(state: AgentGraphState) -> dict[str, object] | None:
    for record in reversed(state.audit_records):
        if not isinstance(record, dict):
            continue
        if record.get("event") == "final_explanation_snapshot":
            continue
        if record.get("status"):
            return record
    return None


def _plan_tools_from_audit(source_steps: object) -> str:
    if not isinstance(source_steps, list):
        return ""
    capabilities = [
        str(cast(dict[str, Any], step).get("capability"))
        for step in source_steps
        if isinstance(step, dict) and cast(dict[str, Any], step).get("capability")
    ]
    return ", ".join(capabilities)


def _policy_record_from_audit(source_record: dict[str, object] | None) -> dict[str, object]:
    if not source_record:
        return {}
    action = source_record.get("action_taken")
    if not isinstance(action, dict):
        return {}
    action_dict = cast(dict[str, Any], action)
    policy_decision = action_dict.get("policy_decision")
    if isinstance(policy_decision, dict):
        return policy_decision
    return {}


def _next_recommendation(state: AgentGraphState) -> str:
    plan = state.plan
    if not plan:
        return "Ask for a Linux administration task."
    if plan.interaction_state == InteractionState.AWAITING_CONFIRMATION:
        return "Type the exact confirmation phrase to proceed, or anything else to abort."
    if plan.interaction_state == InteractionState.AWAITING_DISAMBIGUATION:
        return "Provide the missing target, scope, or risk boundary."
    if plan.interaction_state == InteractionState.REFUSED:
        return "Choose a narrower safe target or request a read-only inspection."
    if plan.interaction_state == InteractionState.FAILED:
        return "Review the verification failure before retrying."
    if plan.interaction_state == InteractionState.COMPLETED:
        if "disk" in plan.goal.lower() and (
            "clean" in plan.goal.lower() or "full" in plan.goal.lower()
        ):
            return "Consider preventive monitoring for disk pressure and cleanup candidate growth."
        return "Review the verification result and audit log before taking follow-up action."
    return "Continue with the next safe planned step."
