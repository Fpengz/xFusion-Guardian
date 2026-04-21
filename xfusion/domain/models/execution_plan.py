from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xfusion.domain.enums import InteractionState, RiskLevel, StepStatus


class PlanStep(BaseModel):
    """Represents one planned agent step."""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    confirmation_phrase: str | None = None
    expected_output: str = Field(min_length=1)
    verification_method: str = Field(min_length=1)
    success_condition: str = Field(min_length=1)
    failure_condition: str = Field(min_length=1)
    fallback_action: str = Field(min_length=1)
    status: StepStatus = StepStatus.PENDING


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
