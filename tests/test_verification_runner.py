from __future__ import annotations

from pathlib import Path

from xfusion.execution.command_runner import CommandRunner
from xfusion.tools.disk import DiskTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.registry import ToolRegistry
from xfusion.tools.system import SystemTools
from xfusion.verification.loader import load_scenarios
from xfusion.verification.runner import run_fake_tool_scenario, run_static_scenario


def test_verification_runner_all_scenarios():
    scenarios_dir = Path("verification/scenarios/")
    total = 0
    for scenarios_path in scenarios_dir.glob("*.yaml"):
        scenarios = load_scenarios(scenarios_path)
        assert len(scenarios) > 0
        total += len(scenarios)

        runner = CommandRunner()
        system_tools = SystemTools(runner)
        disk_tools = DiskTools(runner)
        process_tools = ProcessTools(runner)
        registry = ToolRegistry(system_tools, disk_tools, process_tools)

        for scenario in scenarios:
            if scenario.mode == "static":
                result = run_static_scenario(scenario, registry)
                assert result["success"], (
                    f"Scenario {scenario.id} in {scenarios_path} failed: {result['errors']}"
                )
            elif scenario.mode == "fake_tool":
                result = run_fake_tool_scenario(scenario)
                assert result["success"], (
                    f"Scenario {scenario.id} in {scenarios_path} failed: {result['errors']}"
                )
            else:
                assert scenario.mode == "live_vm"

    assert total >= 20
