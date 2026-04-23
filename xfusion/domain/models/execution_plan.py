from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xfusion.domain.enums import ApprovalMode, InteractionState, RiskLevel, RiskTier, StepStatus


class PlanStep(BaseModel):
    """Represents one planned agent step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(default="", min_length=0)
    id: str | None = Field(default=None, min_length=1)
    intent: str = Field(default="", min_length=0)
    capability: str | None = Field(default=None, min_length=1)
    tool: str = Field(default="", min_length=0)
    args: dict[str, object] = Field(default_factory=dict)
    parameters: dict[str, object] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    expected_outputs: dict[str, object] = Field(default_factory=dict)
    justification: str = ""
    risk_hint: RiskTier | None = None
    approval_required_hint: ApprovalMode | None = None
    preview_summary: str = ""
    on_failure: str = ""
    verification_step_ids: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    confirmation_phrase: str | None = None
    approval_id: str | None = None
    action_fingerprint: str | None = None
    normalized_args: dict[str, object] = Field(default_factory=dict)
    argument_provenance: dict[str, str] = Field(default_factory=dict)
    resolved_references: dict[str, object] = Field(default_factory=dict)
    adapter_id: str | None = None
    policy_rule_id: str | None = None
    approval_mode: ApprovalMode | None = None
    authorized_output_accepted: bool = False
    failure_class: str | None = None
    failure_details: dict[str, object] = Field(default_factory=dict)
    redaction_metadata: dict[str, object] = Field(default_factory=dict)
    started_at: str | None = None
    ended_at: str | None = None
    repair_of_step_id: str | None = None
    repair_proposal_id: str | None = None
    expected_output: str = Field(default="Structured capability output.", min_length=1)
    verification_method: str = Field(min_length=1)
    success_condition: str = Field(min_length=1)
    failure_condition: str = Field(min_length=1)
    fallback_action: str = Field(min_length=1)
    status: StepStatus = StepStatus.PENDING

    @model_validator(mode="before")
    @classmethod
    def normalize_v02_aliases(cls, data: Any) -> Any:
        """Normalize v0.2 fields without allowing conflicting legacy surfaces."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "tool" in normalized and "capability" not in normalized:
            raise ValueError("Legacy tool field without canonical capability is forbidden.")
        if "parameters" in normalized and "args" not in normalized:
            raise ValueError("Legacy parameters field without canonical args is forbidden.")
        if "dependencies" in normalized and "depends_on" not in normalized:
            raise ValueError("Legacy dependencies field without canonical depends_on is forbidden.")
        if (
            normalized.get("capability") is not None
            and normalized.get("tool") is not None
            and normalized["capability"] != normalized["tool"]
        ):
            raise ValueError("Conflicting capability/tool values are not allowed.")
        if (
            "args" in normalized
            and "parameters" in normalized
            and normalized["args"] != normalized["parameters"]
        ):
            raise ValueError("Conflicting args/parameters values are not allowed.")
        if (
            "depends_on" in normalized
            and "dependencies" in normalized
            and normalized["depends_on"] != normalized["dependencies"]
        ):
            raise ValueError("Conflicting depends_on/dependencies values are not allowed.")

        if normalized.get("step_id") is None and normalized.get("id") is not None:
            normalized["step_id"] = normalized["id"]
        if normalized.get("id") is None and normalized.get("step_id") is not None:
            normalized["id"] = normalized["step_id"]

        if normalized.get("tool") is None and normalized.get("capability") is not None:
            normalized["tool"] = normalized["capability"]

        if "parameters" not in normalized and "args" in normalized:
            normalized["parameters"] = normalized["args"]

        if "dependencies" not in normalized and "depends_on" in normalized:
            normalized["dependencies"] = normalized["depends_on"]

        if not normalized.get("intent"):
            normalized["intent"] = (
                normalized.get("justification") or normalized.get("step_id") or "step"
            )

        if "expected_output" not in normalized and "expected_outputs" in normalized:
            normalized["expected_output"] = "Structured capability output."
        if "on_failure" not in normalized and "fallback_action" in normalized:
            normalized["on_failure"] = str(normalized["fallback_action"])

        return normalized

    @model_validator(mode="after")
    def validate_v02_aliases(self) -> PlanStep:
        """Ensure canonical v0.2 and transitional aliases stay identical."""
        if not self.step_id or not self.id:
            raise ValueError("Step requires id/step_id.")
        if not self.tool or not self.capability:
            raise ValueError("Step requires capability/tool.")
        if self.capability != self.tool:
            raise ValueError("Conflicting capability/tool values are not allowed.")
        if self.args != self.parameters:
            raise ValueError("Conflicting args/parameters values are not allowed.")
        if self.depends_on != self.dependencies:
            raise ValueError("Conflicting depends_on/dependencies values are not allowed.")

        self.id = self.step_id
        self.capability = self.tool
        self.args = dict(self.parameters)
        self.depends_on = list(self.dependencies)
        if not self.on_failure:
            self.on_failure = self.fallback_action
        return self


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
            unknown = set(step.dependencies) - step_ids
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
            if all(dep in successful_step_ids for dep in step.dependencies):
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

            for dep in step.dependencies:
                dep_step = next((s for s in self.steps if s.step_id == dep), None)
                if dep_step and dep_step.status in {
                    StepStatus.FAILED,
                    StepStatus.REFUSED,
                    StepStatus.SKIPPED,
                }:
                    return True
        return False
