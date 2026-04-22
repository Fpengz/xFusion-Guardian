from __future__ import annotations

import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("XFUSION_RUN_LIVE_VM") != "1",
    reason="Live Lima VM rehearsal is opt-in; set XFUSION_RUN_LIVE_VM=1.",
)


def test_live_vm_rehearsal_command_smoke() -> None:
    """Run a minimal CLI smoke check in an explicitly opted-in VM/session."""
    result = subprocess.run(
        ["uv", "run", "xfusion"],
        input="check disk usage\nexit\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    assert "Intent:" in result.stdout
    assert "Verification:" in result.stdout
    assert "Disk usage" in result.stdout
