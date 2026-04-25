from __future__ import annotations

from xfusion.domain.enums import ReasoningRole
from xfusion.graph.state import AgentGraphState
from xfusion.roles.contracts import RoleProposal, enforce_role_proposal


def record_role_proposal(
    state: AgentGraphState,
    *,
    role: ReasoningRole,
    proposal_type: str,
    payload: dict[str, object],
    deterministic_layer: str,
    attributable_step_id: str | None = None,
    consumes_redacted_inputs_only: bool = True,
    requested_authority: list[str] | None = None,
) -> None:
    """Validate and record one non-authoritative role proposal at runtime."""
    proposal = RoleProposal(
        role=role,
        proposal_type=proposal_type,
        payload=payload,
        consumes_redacted_inputs_only=consumes_redacted_inputs_only,
        requested_authority=requested_authority or [],
    )
    contracts = {
        ReasoningRole(role_name): contract for role_name, contract in state.role_contracts.items()
    }
    record = enforce_role_proposal(
        proposal,
        contracts=contracts,
        deterministic_layer=deterministic_layer,
        attributable_step_id=attributable_step_id,
    )
    state.role_runtime_records.append(record)
