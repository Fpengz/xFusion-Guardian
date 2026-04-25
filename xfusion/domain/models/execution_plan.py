from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xfusion.domain.enums import (
    ApprovalMode,
    ExecutionSurface,
    InteractionState,
    PolicyCategory,
    RiskLevel,
    RiskTier,
    StepStatus,
)


class PlanStep(BaseModel):
    """Represents one planned agent step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    intent: str = Field(default="", min_length=0)
    capability: str = Field(min_length=1)
    args: dict[str, object] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    expected_outputs: dict[str, object] = Field(default_factory=dict)
    justification: str = ""
    risk_hint: RiskTier | None = None
    approval_required_hint: ApprovalMode | None = None
    execution_surface: ExecutionSurface = ExecutionSurface.CAPABILITY
    policy_category: PolicyCategory | None = None
    impact_scope: dict[str, object] = Field(default_factory=dict)
    agent_risk_assessment: dict[str, object] = Field(default_factory=dict)
    system_risk_envelope: dict[str, object] = Field(default_factory=dict)
    final_risk_category: PolicyCategory | None = None
    resolution_record: dict[str, object] = Field(default_factory=dict)
    fallback_reason: str | None = None
    preview_summary: str = ""
    on_failure: str = ""
    verification_step_ids: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    approval_id: str | None = None
    action_fingerprint: str | None = None
    intent_hash: str | None = None
    planned_action_hash: str | None = None
    approved_action_hash: str | None = None
    executed_action_hash: str | None = None
    normalized_args: dict[str, object] = Field(default_factory=dict)
    argument_provenance: dict[str, str] = Field(default_factory=dict)
    resolved_references: dict[str, object] = Field(default_factory=dict)
    adapter_id: str | None = None
    policy_rule_id: str | None = None
    policy_snapshot_hash: str | None = None
    policy_snapshot: dict[str, object] = Field(default_factory=dict)
    approval_mode: ApprovalMode | None = None
    risk_contract: dict[str, object] = Field(default_factory=dict)
    confirmation_supplied: bool | None = None
    authorized_output_accepted: bool = False
    failure_class: str | None = None
    non_execution_code: str | None = None
    non_execution_reason_text: str | None = None
    failure_details: dict[str, object] = Field(default_factory=dict)
    redaction_metadata: dict[str, object] = Field(default_factory=dict)
    command_trace: list[dict[str, object]] = Field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None
    repair_of_step_id: str | None = None
    repair_proposal_id: str | None = None
    status: StepStatus = StepStatus.PENDING

    # Runtime verification/confirmation fields consumed by deterministic graph nodes.
    verification_method: str = "none"
    success_condition: str = "none"
    failure_condition: str = "none"
    fallback_action: str = "stop"
    expected_output: str = "Structured capability output."
    requires_confirmation: bool = False
    confirmation_phrase: str | None = None


class ExecutionPlan(BaseModel):
    """Represents the complete plan for a user request."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    language: str = Field(min_length=1)
    interaction_state: InteractionState = InteractionState.EXECUTING
    steps: list[PlanStep]
    max_steps: int = Field(default=8, ge=1, le=20)
    current_step: str | None = None
    status: str = "executing"
    clarification_question: str | None = None
    intent_class: str = "operation"
    target_context: dict[str, object] = Field(default_factory=dict)
    created_by: str = "xfusion"
    created_at: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    approval_summary: dict[str, object] = Field(default_factory=dict)
    verification_strategy: str | None = None
    verification_no_meaningful_verifier: bool = False

    @model_validator(mode="after")
    def validate_dependencies(self) -> ExecutionPlan:
        """Reject dependencies that reference unknown steps."""
        step_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            unknown = set(step.depends_on) - step_ids
            if unknown:
                raise ValueError(f"Unknown step dependencies: {sorted(unknown)}")
        return self

    def next_executable_step(self) -> PlanStep | None:
        """Return the next pending or running step whose dependencies succeeded."""
        # Step ids that are successful
        successful_step_ids = {s.step_id for s in self.steps if s.status == StepStatus.SUCCESS}

        for step in self.steps:
            if step.status not in {StepStatus.PENDING, StepStatus.RUNNING}:
                continue

            # All dependencies must be successful
            if all(dep in successful_step_ids for dep in step.depends_on):
                return step
        return None

    def has_unexecutable_pending_steps(self) -> bool:
        """Return True if there are pending steps that cannot execute due to failed dependencies."""
        pending_step_ids = {s.step_id for s in self.steps if s.status == StepStatus.PENDING}

        if not pending_step_ids:
            return False

        # Check if any pending step has at least one dependency that failed or will never succeed
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue

            for dep in step.depends_on:
                dep_step = next((s for s in self.steps if s.step_id == dep), None)
                if dep_step and dep_step.status in {
                    StepStatus.FAILED,
                    StepStatus.REFUSED,
                    StepStatus.SKIPPED,
                }:
                    return True
        return False
