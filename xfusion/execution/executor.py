from __future__ import annotations

from xfusion.domain.models.execution_plan import PlanStep
from xfusion.tools.base import ToolOutput
from xfusion.tools.registry import ToolRegistry


def execute_step(step: PlanStep, registry: ToolRegistry) -> ToolOutput:
    """Execute exactly one planned step using the tool registry."""
    return registry.execute(str(step.capability), step.args)
