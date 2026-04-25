from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    """Raised when a session, plan, or step would exceed its execution budget."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def audit_record(self) -> dict[str, str]:
        return {"status": "budget_exceeded", "reason": self.reason}


@dataclass
class SessionExecutionBudget:
    """Session-level execution budget with per-step reservations."""

    max_steps: int = 20
    max_wall_time_ms: int = 300_000
    max_commands: int = 50
    max_mutations: int = 5
    max_fallback_attempts: int = 2
    max_bytes_exposed: int = 1_000_000
    max_cumulative_risk: int = 20
    started_at_monotonic: float = field(default_factory=time.monotonic)
    steps_used: int = 0
    commands_used: int = 0
    mutations_used: int = 0
    fallback_attempts_used: int = 0
    bytes_exposed: int = 0
    cumulative_risk: int = 0

    def reserve_step(
        self,
        *,
        command_count: int,
        mutation_count: int,
        exposed_bytes: int,
        risk_cost: int,
        fallback_attempts: int = 0,
    ) -> None:
        self._check_wall_time()
        candidates = {
            "max_steps_exceeded": self.steps_used + 1 > self.max_steps,
            "max_commands_exceeded": self.commands_used + command_count > self.max_commands,
            "max_mutations_exceeded": self.mutations_used + mutation_count > self.max_mutations,
            "max_fallback_attempts_exceeded": (
                self.fallback_attempts_used + fallback_attempts > self.max_fallback_attempts
            ),
            "max_bytes_exposed_exceeded": (
                self.bytes_exposed + exposed_bytes > self.max_bytes_exposed
            ),
            "max_cumulative_risk_exceeded": (
                self.cumulative_risk + risk_cost > self.max_cumulative_risk
            ),
        }
        for reason, exceeded in candidates.items():
            if exceeded:
                raise BudgetExceeded(reason)
        self.steps_used += 1
        self.commands_used += command_count
        self.mutations_used += mutation_count
        self.fallback_attempts_used += fallback_attempts
        self.bytes_exposed += exposed_bytes
        self.cumulative_risk += risk_cost

    def _check_wall_time(self) -> None:
        elapsed_ms = int((time.monotonic() - self.started_at_monotonic) * 1000)
        if elapsed_ms > self.max_wall_time_ms:
            raise BudgetExceeded("max_wall_time_exceeded")
