"""Specialist agents for XFusion v0.2.4.3.

This module transforms reasoning roles into specialist agents with domain-specific expertise.
Each agent encapsulates knowledge, decision logic, and proposal generation for its specialty.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.capabilities.resolver import resolve_intent_to_capability
from xfusion.domain.enums import ReasoningRole

if TYPE_CHECKING:
    from xfusion.graph.state import AgentGraphState


class SpecialistAgent(ABC):
    """Base class for specialist agents in the XFusion system.

    Each specialist agent:
    - Has a specific domain of expertise (corresponds to a ReasoningRole)
    - Can analyze state and generate proposals within its domain
    - Cannot execute actions directly (non-authoritative)
    - Records all proposals for audit trail
    """

    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry

    @property
    @abstractmethod
    def role(self) -> ReasoningRole:
        """Return the reasoning role this agent specializes in."""
        pass

    @property
    @abstractmethod
    def expertise_description(self) -> str:
        """Describe this agent's area of expertise."""
        pass

    @abstractmethod
    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze the current state and return findings within this agent's domain."""
        pass

    @abstractmethod
    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate a proposal based on analysis. Must be non-authoritative."""
        pass


class SupervisorAgent(SpecialistAgent):
    """Supervisor specialist agent for intent interpretation and coordination.

    Responsibilities:
    - Interpret user intent from natural language
    - Coordinate outputs from other specialist agents
    - Request clarification when needed
    - Make high-level workflow decisions
    """

    @property
    def role(self) -> ReasoningRole:
        return ReasoningRole.SUPERVISOR

    @property
    def expertise_description(self) -> str:
        return "Interpret user intent, coordinate specialist outputs, and request clarification."

    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze user input to determine intent and language."""
        # Detect language
        language = "zh" if any("一" <= c <= "鿿" for c in state.user_input) else "en"

        return {
            "user_input": state.user_input,
            "language": language,
            "has_plan": state.plan is not None,
            "interaction_state": state.plan.interaction_state if state.plan else None,
        }

    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Propose intent classification or coordination action."""
        if analysis["has_plan"]:
            # Coordination mode: decide next steps based on plan state
            recommendation = (
                "continue_execution"
                if analysis["interaction_state"] == "executing"
                else "await_input"
            )
            return {
                "proposal_type": "coordination",
                "current_state": analysis["interaction_state"],
                "recommendation": recommendation,
            }
        else:
            # Intent classification mode
            return {
                "proposal_type": "intent",
                "goal": state.user_input,
                "language": analysis["language"],
            }


class ObservationAgent(SpecialistAgent):
    """Observation specialist agent for evidence gathering.

    Responsibilities:
    - Propose bounded read-only Tier 0 capabilities
    - Gather system state information
    - Identify what evidence is available
    """

    @property
    def role(self) -> ReasoningRole:
        return ReasoningRole.OBSERVATION

    @property
    def expertise_description(self) -> str:
        return "Propose bounded read-only Tier 0 evidence-gathering capabilities."

    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze what observations are needed or available."""
        read_only_capabilities = {
            "system.current_user",
            "system.detect_os",
            "disk.check_usage",
            "process.find_by_port",
            "file.preview_metadata",
            "file.search",
            "process.list",
            "system.check_ram",
        }

        # Find capabilities relevant to current context
        available_observation_caps = []
        if self.registry:
            for cap_name in read_only_capabilities:
                if self.registry.has(cap_name):
                    available_observation_caps.append(cap_name)

        return {
            "available_observation_capabilities": available_observation_caps,
            "current_step": state.current_step_id,
            "environment": state.environment.model_dump() if state.environment else {},
        }

    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Propose observation capabilities for evidence gathering."""
        # If we have a plan with steps, identify which ones are observations
        if state.plan:
            observation_capabilities = [
                step.capability
                for step in state.plan.steps
                if step.capability in analysis["available_observation_capabilities"]
            ]

            return {
                "proposal_type": "tier_0_capability",
                "capabilities": observation_capabilities,
                "risk_tier": "tier_0",
            }

        return {
            "proposal_type": "missing_evidence",
            "needed_observations": analysis["available_observation_capabilities"][:3],
        }


class DiagnosisAgent(SpecialistAgent):
    """Diagnosis specialist agent for hypothesis generation.

    Responsibilities:
    - Produce advisory hypotheses from typed observations
    - Assess confidence levels
    - Identify missing evidence
    - Never change authority or make policy decisions
    """

    @property
    def role(self) -> ReasoningRole:
        return ReasoningRole.DIAGNOSIS

    @property
    def expertise_description(self) -> str:
        return "Produce advisory hypotheses from typed observations without changing authority."

    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze observations to form diagnostic hypotheses."""
        # Gather available evidence
        evidence = []
        if state.step_outputs:
            for step_id, output in state.step_outputs.items():
                evidence.append(
                    {
                        "step_id": step_id,
                        "output_summary": str(output)[:200],  # Truncate for analysis
                    }
                )

        # Check for errors or failures
        has_errors = False
        if state.plan:
            for step in state.plan.steps:
                if step.failure_class or step.status == "failed":
                    has_errors = True
                    evidence.append(
                        {
                            "step_id": step.step_id,
                            "failure": step.failure_class,
                            "details": step.failure_details,
                        }
                    )

        return {
            "evidence": evidence,
            "has_errors": has_errors,
            "verification_result": state.verification_result,
        }

    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate diagnostic hypotheses based on evidence."""
        if analysis["has_errors"]:
            # Form hypothesis about failure cause
            return {
                "proposal_type": "hypothesis",
                "summary": "Execution encountered errors requiring diagnosis.",
                "confidence": 0.7,
                "missing_evidence": ["root_cause_analysis"],
            }
        else:
            # Normal operational hypothesis
            return {
                "proposal_type": "hypothesis",
                "summary": "LLM-driven capability resolver selected capabilities for the request.",
                "confidence": 0.9,
            }


class PlanningAgent(SpecialistAgent):
    """Planning specialist agent for workflow orchestration.

    Responsibilities:
    - Draft typed workflow DAGs with explicit dependencies
    - Define verification strategies
    - Reference resolution planning
    - Cannot authorize or override policy/risk
    """

    @property
    def role(self) -> ReasoningRole:
        return ReasoningRole.PLANNING

    @property
    def expertise_description(self) -> str:
        return "Draft typed workflow DAGs with explicit dependencies, references, and verification."

    def __init__(self, registry: CapabilityRegistry | None = None):
        super().__init__(registry)
        self.llm_client = None  # Will be initialized when needed

    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze requirements for workflow planning."""
        # Use LLM-driven capability resolution
        if not self.registry:
            return {
                "error": "No capability registry available for planning",
                "resolved_capability": None,
            }

        # Initialize LLM client if settings available
        try:
            from xfusion.app.settings import Settings
            from xfusion.llm.client import LLMClient

            settings = Settings()
            if settings.llm_base_url:
                self.llm_client = LLMClient(settings)
        except Exception:
            pass  # Will use fallback

        # Resolve intent to capability
        capability_name, extracted_args, clarification = resolve_intent_to_capability(
            user_input=state.user_input,
            registry=self.registry,
            llm_client=self.llm_client,
            language=state.language or "en",
        )

        return {
            "resolved_capability": capability_name,
            "extracted_args": extracted_args,
            "clarification_needed": clarification,
            "user_input": state.user_input,
        }

    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Propose workflow plan based on resolved capability."""
        if analysis.get("clarification_needed"):
            return {
                "proposal_type": "clarification",
                "question": analysis["clarification_needed"],
            }

        if not analysis.get("resolved_capability"):
            return {
                "proposal_type": "workflow_dag",
                "status": "no_capability_matched",
                "recommendation": "Request more specific input",
            }

        # Build workflow proposal
        mutating_tools = {
            "process.kill",
            "user.create",
            "user.delete",
            "cleanup.safe_disk_cleanup",
        }

        verification_strategy = (
            "Verify mutating workflow outcomes with planned post-action checks."
            if analysis["resolved_capability"] in mutating_tools
            else None
        )

        return {
            "proposal_type": "workflow_dag",
            "primary_capability": analysis["resolved_capability"],
            "args": analysis["extracted_args"],
            "verification_strategy": verification_strategy,
            "is_mutating": analysis["resolved_capability"] in mutating_tools,
        }


class VerificationAgent(SpecialistAgent):
    """Verification specialist agent for outcome validation.

    Responsibilities:
    - Evaluate redacted execution evidence
    - Propose non-authoritative repair ideas
    - Cannot auto-execute mutation repairs
    - Consumes only redacted inputs
    """

    @property
    def role(self) -> ReasoningRole:
        return ReasoningRole.VERIFICATION

    @property
    def expertise_description(self) -> str:
        return "Evaluate redacted execution evidence and propose non-authoritative repair ideas."

    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze execution outcomes for verification."""
        if not state.current_step_id:
            return {
                "status": "no_active_step",
                "can_verify": False,
            }

        # Get tool output for current step
        tool_output = state.step_outputs.get(state.current_step_id, state.last_tool_output or {})

        # Check if verification already performed
        existing_verification = state.verification_result

        return {
            "current_step_id": state.current_step_id,
            "tool_output": tool_output,
            "existing_verification": (
                existing_verification.model_dump() if existing_verification else None
            ),
            "repair_proposals_count": len(state.repair_proposals),
        }

    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Propose verification outcome or repair if needed."""
        if not analysis["can_verify"]:
            return {
                "proposal_type": "verification_outcome",
                "status": "skipped",
                "reason": "No active step to verify",
            }

        if analysis["existing_verification"]:
            # Already verified, report outcome
            return {
                "proposal_type": "verification_outcome",
                "verification_id": analysis["existing_verification"].get("verification_id"),
                "outcome": analysis["existing_verification"].get("outcome"),
                "summary": analysis["existing_verification"].get("summary"),
            }

        # Initial verification pending
        return {
            "proposal_type": "verification_outcome",
            "status": "pending",
            "ready_for_verification": True,
        }


class ExplanationAgent(SpecialistAgent):
    """Explanation specialist agent for audit summarization.

    Responsibilities:
    - Summarize authoritative audited state
    - Provide safe next step recommendations
    - Cannot mutate authoritative records
    - Consumes only audited redacted inputs
    """

    @property
    def role(self) -> ReasoningRole:
        return ReasoningRole.EXPLANATION

    @property
    def expertise_description(self) -> str:
        return "Summarize authoritative audited state and safe next steps."

    def analyze(self, state: AgentGraphState) -> dict[str, Any]:
        """Analyze audit trail and current state for explanation."""
        audit_summary = []
        if state.audit_records:
            for record in state.audit_records[-5:]:  # Last 5 records
                # Ensure record is treated as dict for type safety
                if isinstance(record, dict):
                    audit_summary.append(
                        {
                            "status": record.get("status"),
                            "summary": str(record.get("summary", ""))[:100],
                        }
                    )

        return {
            "plan_id": state.plan.plan_id if state.plan else None,
            "plan_status": state.plan.status if state.plan else None,
            "interaction_state": state.plan.interaction_state if state.plan else None,
            "audit_records_count": len(state.audit_records),
            "recent_audit_summary": audit_summary,
            "response": state.response,
            "repair_proposals_count": len(state.repair_proposals),
        }

    def propose(self, state: AgentGraphState, analysis: dict[str, Any]) -> dict[str, Any]:
        """Propose audit summary and safe next steps."""
        safe_next_steps = []

        if analysis["interaction_state"] == "completed":
            safe_next_steps.append("Task completed successfully")
        elif analysis["interaction_state"] == "failed":
            safe_next_steps.append("Review failure details and consider retry")
        elif analysis["interaction_state"] == "awaiting_confirmation":
            safe_next_steps.append("Awaiting user confirmation to proceed")
        elif analysis["interaction_state"] == "refused":
            safe_next_steps.append("Action refused by policy; consider alternative approach")

        latest_status = (
            analysis["recent_audit_summary"][-1]["status"]
            if analysis["recent_audit_summary"]
            else None
        )
        return {
            "proposal_type": "audit_summary",
            "plan_id": analysis["plan_id"],
            "latest_status": latest_status,
            "repair_count": analysis["repair_proposals_count"],
            "safe_next_steps": safe_next_steps,
        }


def build_specialist_agents(
    registry: CapabilityRegistry | None = None,
) -> dict[ReasoningRole, SpecialistAgent]:
    """Build all specialist agents for the XFusion system."""
    return {
        ReasoningRole.SUPERVISOR: SupervisorAgent(registry),
        ReasoningRole.OBSERVATION: ObservationAgent(registry),
        ReasoningRole.DIAGNOSIS: DiagnosisAgent(registry),
        ReasoningRole.PLANNING: PlanningAgent(registry),
        ReasoningRole.VERIFICATION: VerificationAgent(registry),
        ReasoningRole.EXPLANATION: ExplanationAgent(registry),
    }
