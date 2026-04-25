from __future__ import annotations

from pathlib import Path

import yaml

from xfusion.domain.models.scenarios import VerificationScenario


def load_scenarios(path: Path) -> list[VerificationScenario]:
    """Load and validate YAML verification scenarios."""
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        return []

    return [VerificationScenario(**item) for item in data]
