from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.models.approval import ApprovalRecord
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan
from xfusion.domain.models.policy import PolicyDecision
from xfusion.domain.models.verification import RepairProposal, VerificationResult
from xfusion.planning.validator import PlanValidationResult
from xfusion.roles.contracts import (
    RoleContract,
    RoleProposalRuntimeRecord,
    build_default_role_contracts,
)


class AgentGraphState(BaseModel):
    """Shared LangGraph state for one user request/session turn."""

    model_config = ConfigDict(extra="forbid")

    user_input: str
    language: str = "en"
    environment: EnvironmentState
    plan: ExecutionPlan | None = None
    current_step_id: str | None = None
    validation_result: PlanValidationResult | None = None
    policy_decision: PolicyDecision | None = None
    verification_result: VerificationResult | None = None
    repair_proposals: list[RepairProposal] = Field(default_factory=list)
    active_repair_step_ids: list[str] = Field(default_factory=list)
    last_tool_output: dict[str, object] | None = None
    step_outputs: dict[str, dict[str, object]] = Field(default_factory=dict)
    authorized_step_outputs: dict[str, dict[str, object]] = Field(default_factory=dict)
    approval_records: dict[str, ApprovalRecord] = Field(default_factory=dict)
    pending_approval_id: str | None = None
    pending_confirmation_phrase: str | None = None
    role_contracts: dict[str, RoleContract] = Field(
        default_factory=lambda: {
            role.value: contract for role, contract in build_default_role_contracts().items()
        }
    )
    role_runtime_records: list[RoleProposalRuntimeRecord] = Field(default_factory=list)
    response_mode: Literal["normal", "debug"] = "normal"
    response: str = ""
    prompt_records: list[dict[str, object]] = Field(default_factory=list)
    audit_records: list[dict[str, object]] = Field(default_factory=list)
    audit_log_path: str | None = None
