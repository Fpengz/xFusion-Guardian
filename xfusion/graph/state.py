from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from xfusion.domain.models.approval import ApprovalRecord
from xfusion.domain.models.environment import EnvironmentState
from xfusion.domain.models.execution_plan import ExecutionPlan
from xfusion.domain.models.policy import PolicyDecision
from xfusion.domain.models.verification import VerificationResult
from xfusion.planning.validator import PlanValidationResult
from xfusion.roles.contracts import RoleContract, build_default_role_contracts


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
    response: str = ""
    audit_records: list[dict[str, object]] = Field(default_factory=list)
    audit_log_path: str | None = None
