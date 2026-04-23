from __future__ import annotations

from pathlib import Path

from xfusion.domain.models.scenarios import ExpectedScenario, VerificationScenario
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


def _static_scenario(
    *,
    expected_risk_level: str,
    expected_requires_confirmation: bool,
) -> VerificationScenario:
    return VerificationScenario(
        id="runner-risk-check",
        category="regression",
        mode="static",
        language="en",
        input="check disk usage",
        preconditions={"distro": "ubuntu", "sudo": True, "disk_pressure": "normal"},
        safe_for_live_execution=False,
        expected=ExpectedScenario(
            plan_length=1,
            plan_tools=["disk.check_usage"],
            executed_tools=[],
            risk_level=expected_risk_level,
            interaction_state="executing",
            requires_confirmation=expected_requires_confirmation,
            verification_method="state_re_read",
            verification_outcome="n/a",
            final_status="planned",
            outcome_contains=["planned"],
            refusal_or_fallback="",
        ),
    )


def test_run_static_scenario_reports_risk_level_mismatch() -> None:
    scenario = _static_scenario(
        expected_risk_level="forbidden",
        expected_requires_confirmation=False,
    )

    result = run_static_scenario(scenario)
    errors = result["errors"]
    assert isinstance(errors, list)
    error_messages = [str(error) for error in errors]

    assert result["success"] is False
    assert any("Expected risk forbidden, got low" in error for error in error_messages)


def test_run_static_scenario_reports_confirmation_mismatch() -> None:
    scenario = _static_scenario(
        expected_risk_level="low",
        expected_requires_confirmation=True,
    )

    result = run_static_scenario(scenario)
    errors = result["errors"]
    assert isinstance(errors, list)
    error_messages = [str(error) for error in errors]

    assert result["success"] is False
    assert any(
        "Expected requires_confirmation True, got False" in error for error in error_messages
    )
