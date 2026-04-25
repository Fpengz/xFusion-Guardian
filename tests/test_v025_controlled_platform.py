from __future__ import annotations

from pathlib import Path

import pytest

from xfusion.capabilities.catalog import load_v025_catalog, load_vnext_catalog
from xfusion.capabilities.manifest import CapabilityManifestError, load_capability_manifests
from xfusion.capabilities.python_adapters import (
    PythonAdapterRegistry,
    PythonAdapterRegistryError,
)
from xfusion.capabilities.retrieval import (
    CapabilityRetriever,
    RetrievalAvailability,
    RetrievalHistory,
)
from xfusion.domain.enums import ApprovalMode, RiskTier
from xfusion.execution.allowlist import ExecutableRegistry
from xfusion.execution.argv import ArgvExecutionError, build_bound_argv
from xfusion.execution.budget import BudgetExceeded, SessionExecutionBudget
from xfusion.execution.fallback import (
    FallbackExecutionRequest,
    FallbackExecutor,
    SandboxPolicy,
)
from xfusion.execution.normalizers import normalize_output
from xfusion.execution.verification import verify_output


def _write_manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "capability.yaml"
    path.write_text(body, encoding="utf-8")
    return path


VALID_MANIFEST = """
api_version: xfusion.capability/v1
name: system_inspection.check_disk_usage
version: 1
short_description: Inspect filesystem usage for a validated path.
risk_tier: tier_0
approval_mode: auto
is_read_only: true
side_effect_classification: none
input_schema:
  type: object
  required: [path]
  properties:
    path:
      type: string
      minLength: 1
  additionalProperties: false
output_schema:
  type: object
  required: [usage_percent]
  properties:
    usage_percent:
      type: integer
      minimum: 0
      maximum: 100
  additionalProperties: false
target_constraints:
  paths:
    allowed: ["/", "/home", "/var/log"]
    forbidden: ["/etc", "/boot"]
execution:
  type: argv
  executable: coreutils.df
  argv:
    - value: "-P"
    - arg: path
  constraints:
    timeout_ms: 2000
    max_stdout_bytes: 8192
    max_stderr_bytes: 4096
    env_allowlist: []
normalizer:
  type: regex_named_groups
  pattern: '^/dev/disk\\s+\\d+\\s+\\d+\\s+\\d+\\s+(?P<usage_percent>\\d+)%\\s+/$'
  casts:
    usage_percent: integer
verification:
  type: output_check
  field: usage_percent
  operator: between
  min: 0
  max: 100
redaction_policy: standard
prompt:
  instructions: Inspect only the requested path and report structured facts.
  constraints:
    - Do not infer filesystem state that is not present in normalized output.
    - Stay within the validated path scope.
"""


def test_manifest_compiles_to_capability_with_required_v025_metadata(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, VALID_MANIFEST)
    executables = ExecutableRegistry({"coreutils.df": "/bin/df"})

    registry = load_capability_manifests([path], executables=executables)
    capability = registry.require("system_inspection.check_disk_usage")

    assert capability.name == "system_inspection.check_disk_usage"
    assert capability.risk_tier == RiskTier.TIER_0
    assert capability.approval_mode == ApprovalMode.AUTO
    assert capability.side_effect_classification == "none"
    assert capability.execution_binding["type"] == "argv"
    assert capability.verification["type"] == "output_check"


def test_manifest_rejects_unknown_executable_and_partial_arg_interpolation(
    tmp_path: Path,
) -> None:
    unsafe = VALID_MANIFEST.replace("executable: coreutils.df", "executable: unknown.df").replace(
        "- arg: path", '- value: "--path={{ args.path }}"'
    )
    path = _write_manifest(tmp_path, unsafe)

    with pytest.raises(CapabilityManifestError) as exc:
        load_capability_manifests(
            [path],
            executables=ExecutableRegistry({"coreutils.df": "/bin/df"}),
        )

    message = str(exc.value)
    assert "unknown executable id 'unknown.df'" in message
    assert "argv value token contains template syntax" in message


def test_manifest_requires_verification_and_side_effect_classification(tmp_path: Path) -> None:
    unsafe = VALID_MANIFEST.replace("side_effect_classification: none\n", "").replace(
        "verification:\n  type: output_check\n  field: usage_percent\n  operator: between\n"
        "  min: 0\n  max: 100\n",
        "",
    )
    path = _write_manifest(tmp_path, unsafe)

    with pytest.raises(CapabilityManifestError) as exc:
        load_capability_manifests(
            [path],
            executables=ExecutableRegistry({"coreutils.df": "/bin/df"}),
        )

    assert "side_effect_classification" in str(exc.value)
    assert "verification" in str(exc.value)


def test_manifest_requires_prompt_metadata_block(tmp_path: Path) -> None:
    unsafe = VALID_MANIFEST.replace(
        "prompt:\n"
        "  instructions: Inspect only the requested path and report structured facts.\n"
        "  constraints:\n"
        "    - Do not infer filesystem state that is not present in normalized output.\n"
        "    - Stay within the validated path scope.\n",
        "",
    )
    path = _write_manifest(tmp_path, unsafe)

    with pytest.raises(CapabilityManifestError) as exc:
        load_capability_manifests(
            [path],
            executables=ExecutableRegistry({"coreutils.df": "/bin/df"}),
        )

    assert "prompt" in str(exc.value)


def test_bound_argv_uses_absolute_executable_and_rejects_missing_args() -> None:
    binding = {
        "type": "argv",
        "executable": "coreutils.df",
        "argv": [{"value": "-P"}, {"arg": "path"}],
    }
    executables = ExecutableRegistry({"coreutils.df": "/bin/df"})

    assert build_bound_argv(binding, {"path": "/home"}, executables) == ["/bin/df", "-P", "/home"]

    with pytest.raises(ArgvExecutionError, match="missing argv arg binding 'path'"):
        build_bound_argv(binding, {}, executables)


def test_budget_exhaustion_stops_execution_with_structured_reason() -> None:
    budget = SessionExecutionBudget(max_steps=1, max_commands=1, max_mutations=0)
    budget.reserve_step(command_count=1, mutation_count=0, exposed_bytes=10, risk_cost=1)

    with pytest.raises(BudgetExceeded) as exc:
        budget.reserve_step(command_count=1, mutation_count=0, exposed_bytes=10, risk_cost=1)

    assert exc.value.reason == "max_steps_exceeded"
    assert exc.value.audit_record()["status"] == "budget_exceeded"


def test_retriever_returns_confidence_ranking_and_explainability(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, VALID_MANIFEST)
    registry = load_capability_manifests(
        [path],
        executables=ExecutableRegistry({"coreutils.df": "/bin/df"}),
    )
    history = RetrievalHistory(successes={"system_inspection.check_disk_usage": 3})

    result = CapabilityRetriever(registry, history=history).retrieve(
        "check disk usage for /home", top_k=1
    )

    assert result.candidates[0].name == "system_inspection.check_disk_usage"
    assert result.candidates[0].capability_confidence > 0.5
    assert "semantic_similarity" in result.candidates[0].ranking_signals
    assert result.candidates[0].why_selected.startswith("Selected because")


def test_normalization_and_verification_fail_closed_on_mismatch() -> None:
    normalized = normalize_output(
        stdout="not a df line",
        stderr="",
        exit_code=0,
        normalizer={
            "type": "regex_named_groups",
            "pattern": r"(?P<usage_percent>\d+)%",
            "casts": {"usage_percent": "integer"},
        },
    )

    assert not normalized.valid
    verification = verify_output(
        output={},
        exit_code=0,
        verification={
            "type": "output_check",
            "field": "usage_percent",
            "operator": "between",
            "min": 0,
            "max": 100,
        },
    )
    assert not verification.verified


def test_fallback_requires_policy_approval_and_sandbox_for_generated_python() -> None:
    executor = FallbackExecutor(allow_agent_generated_python=False)
    request = FallbackExecutionRequest(
        fallback_type="agent_generated_python",
        justification="Need a custom parser.",
        code="open('/etc/passwd').read()",
        policy_approved=True,
        sandbox={"allow_files": [], "allow_network": False, "allow_subprocess": False},
        budget_reserved=True,
        verification={"type": "exit_status", "expected": 0},
    )

    result = executor.execute(request)

    assert result.status == "denied"
    assert result.reason == "agent_generated_python_disabled"


def test_python_adapter_registry_fails_closed_unless_unavailable_mode_enabled() -> None:
    with pytest.raises(PythonAdapterRegistryError, match="unbound python adapter"):
        PythonAdapterRegistry({}, allow_unavailable_adapters=False).require(
            "catalog.system_inspection.check_disk_usage"
        )

    output = PythonAdapterRegistry({}, allow_unavailable_adapters=True).execute(
        "catalog.system_inspection.check_disk_usage", {}
    )

    assert output.data == {
        "status": "unavailable",
        "summary": "Python adapter is not implemented.",
        "unavailable_reason": "unbound_adapter",
    }


def test_sandbox_policy_denies_file_network_subprocess_and_import_escapes() -> None:
    policy = SandboxPolicy(
        allowed_files=["/tmp/xfusion-safe.txt"],
        allow_network=False,
        allow_subprocess=False,
        allowed_imports=["json"],
    )

    assert policy.validate_code("import json\nprint('ok')") is None
    assert policy.validate_code("open('/etc/passwd').read()") == "sandbox_file_scope_violation"
    assert policy.validate_code("import socket") == "sandbox_import_forbidden:socket"
    assert policy.validate_code("import subprocess") == "sandbox_import_forbidden:subprocess"
    assert (
        policy.validate_code("__import__('os').system('id')") == "sandbox_dynamic_import_forbidden"
    )


def test_restricted_fallback_requires_budget_and_verification_metadata() -> None:
    request = FallbackExecutionRequest(
        fallback_type="restricted_command_execution",
        justification="No reviewed capability covers this diagnostic.",
        policy_approved=True,
        argv=["/bin/uname", "-r"],
        budget_reserved=False,
        verification={"type": "exit_status", "expected": 0},
    )

    result = FallbackExecutor().execute(request)

    assert result.status == "denied"
    assert result.reason == "budget_reservation_required"


def test_restricted_fallback_requires_allowlisted_executable() -> None:
    request = FallbackExecutionRequest(
        fallback_type="restricted_command_execution",
        justification="No reviewed capability covers this diagnostic.",
        policy_approved=True,
        argv=["/bin/uname", "-r"],
        budget_reserved=True,
        verification={"type": "exit_status", "expected": 0},
    )

    result = FallbackExecutor(executables=ExecutableRegistry({"coreutils.df": "/bin/df"})).execute(
        request
    )

    assert result.status == "denied"
    assert result.reason == "fallback_executable_not_allowlisted"


def test_retriever_penalizes_unavailable_high_risk_side_effect_capabilities(
    tmp_path: Path,
) -> None:
    safe_path = _write_manifest(tmp_path, VALID_MANIFEST)
    risky_path = tmp_path / "risky.yaml"
    risky_path.write_text(
        VALID_MANIFEST.replace(
            "name: system_inspection.check_disk_usage",
            "name: storage_management.mount_volume",
        )
        .replace("risk_tier: tier_0", "risk_tier: tier_2")
        .replace("approval_mode: auto", "approval_mode: admin")
        .replace("is_read_only: true", "is_read_only: false")
        .replace(
            "side_effect_classification: none", "side_effect_classification: privileged_system"
        ),
        encoding="utf-8",
    )
    registry = load_capability_manifests(
        [safe_path, risky_path],
        executables=ExecutableRegistry({"coreutils.df": "/bin/df"}),
    )
    availability = RetrievalAvailability(
        unavailable={"storage_management.mount_volume": "unbound_adapter"}
    )

    result = CapabilityRetriever(registry, availability=availability).retrieve(
        "check disk usage or mount volume", top_k=2
    )

    assert result.candidates[0].name == "system_inspection.check_disk_usage"
    assert result.candidates[1].ranking_signals["availability_penalty"] == 1.0
    assert (
        result.candidates[0].rejected_alternatives[0]["name"] == "storage_management.mount_volume"
    )


def test_v025_catalog_contains_supplied_capability_surface() -> None:
    registry = load_v025_catalog()
    capability_names = {capability.name for capability in registry.all()}

    assert len(capability_names) >= 180
    assert "system_inspection.check_disk_usage" in capability_names
    assert "service_management.restart_service" in capability_names
    assert "network_diagnostics.check_dns_resolution" in capability_names
    assert "storage_management.mount_volume" in capability_names
    assert "runtime_debugging.capture_core_dump" in capability_names


def test_legacy_vnext_catalog_loader_alias_points_to_v025_catalog() -> None:
    assert load_vnext_catalog is load_v025_catalog
