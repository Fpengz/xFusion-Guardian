from __future__ import annotations

from collections.abc import Iterable

from xfusion.capabilities.schema import validate_schema_contract
from xfusion.domain.enums import ApprovalMode, RiskTier
from xfusion.domain.models.capability import (
    CapabilityDefinition,
    CapabilityPrompt,
    RuntimeConstraints,
)


class CapabilityRegistry:
    """Code-defined registry for v0.2 capabilities."""

    def __init__(self, capabilities: Iterable[CapabilityDefinition]) -> None:
        validated_capabilities: dict[str, CapabilityDefinition] = {}
        errors: list[str] = []
        for capability in capabilities:
            if capability.name in validated_capabilities:
                errors.append(f"{capability.name}: duplicate capability name")
            for schema_name, schema in (
                ("input_schema", capability.input_schema),
                ("output_schema", capability.output_schema),
            ):
                result = validate_schema_contract(schema)
                if not result.valid:
                    for error in result.errors:
                        errors.append(f"{capability.name}.{schema_name}: {error}")
            validated_capabilities[capability.name] = capability
        if errors:
            raise ValueError("Invalid capability schema contract: " + "; ".join(errors))
        self._capabilities = validated_capabilities

    def has(self, name: str) -> bool:
        return name in self._capabilities

    def get(self, name: str) -> CapabilityDefinition | None:
        return self._capabilities.get(name)

    def require(self, name: str) -> CapabilityDefinition:
        capability = self.get(name)
        if capability is None:
            raise KeyError(f"Unknown capability: {name}")
        return capability

    def all(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self._capabilities.values())


def _schema(properties: dict[str, object], required: list[str] | None = None) -> dict[str, object]:
    return {
        "type": "object",
        "required": required or [],
        "properties": properties,
        "additionalProperties": False,
    }


def _string(*, min_length: int = 1, max_length: int = 256) -> dict[str, object]:
    return {"type": "string", "minLength": min_length, "maxLength": max_length}


def _integer(*, minimum: int, maximum: int) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def _number(*, minimum: float = 0.0, maximum: float = 100.0) -> dict[str, object]:
    return {"type": "number", "minimum": minimum, "maximum": maximum}


def _array(*, max_items: int = 100) -> dict[str, object]:
    return {"type": "array", "maxItems": max_items}


def _bool() -> dict[str, object]:
    return {"type": "boolean"}


def _capability(
    *,
    name: str,
    verb: str,
    object_name: str,
    risk_tier: RiskTier,
    approval_mode: ApprovalMode,
    is_read_only: bool,
    input_schema: dict[str, object],
    output_schema: dict[str, object],
    adapter_id: str | None = None,
    verification_recommendation: str = "state_re_read",
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        version=1,
        verb=verb,
        object=object_name,
        risk_tier=risk_tier,
        approval_mode=approval_mode,
        allowed_environments=["dev", "staging", "production"],
        allowed_actor_types=["operator", "assistant"],
        scope_model={},
        input_schema=input_schema,
        output_schema=output_schema,
        runtime_constraints=RuntimeConstraints(
            timeout_sec=30.0,
            max_stdout_bytes=100_000,
            max_stderr_bytes=100_000,
            network_access="denied",
            interactive_tty=False,
            working_directory=".",
        ),
        adapter_id=adapter_id or name,
        is_read_only=is_read_only,
        preview_builder="default",
        verification_recommendation=verification_recommendation,
        redaction_policy="standard",
        prompt=CapabilityPrompt(
            instructions=f"{verb.title()} {object_name} using only validated capability inputs.",
            constraints=[
                "Do not exceed the capability input schema.",
                "Do not infer outputs that are not present in normalized results.",
            ],
        ),
    )


def build_default_capability_registry() -> CapabilityRegistry:
    """Build the code-defined capability registry for the current local adapters."""
    capabilities = [
        _capability(
            name="system.detect_os",
            verb="read",
            object_name="environment",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({}),
            output_schema=_schema(
                {
                    "distro_family": _string(),
                    "distro_version": _string(),
                    "current_user": _string(),
                    "sudo_available": _bool(),
                    "systemd_available": _bool(),
                    "package_manager": _string(),
                    "disk_pressure": _string(),
                    "session_locality": _string(),
                    "protected_paths": _array(max_items=32),
                    "active_facts": {"type": "object"},
                }
            ),
        ),
        _capability(
            name="system.check_ram",
            verb="read",
            object_name="memory",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({}),
            output_schema=_schema(
                {
                    "stdout": _string(min_length=0, max_length=100_000),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
        ),
        _capability(
            name="system.current_user",
            verb="read",
            object_name="user",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({}),
            output_schema=_schema({"username": _string()}, ["username"]),
        ),
        _capability(
            name="system.check_sudo",
            verb="read",
            object_name="privilege",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({}),
            output_schema=_schema({"sudo_available": _bool()}),
        ),
        _capability(
            name="system.service_status",
            verb="read",
            object_name="service",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({"service": _string(max_length=128)}, ["service"]),
            output_schema=_schema(
                {"service": _string(max_length=128), "status": _string(max_length=64)}
            ),
        ),
        _capability(
            name="system.service_start",
            verb="start",
            object_name="service",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({"service": _string(max_length=128)}, ["service"]),
            output_schema=_schema(
                {"service": _string(max_length=128), "status": _string(max_length=64)}
            ),
            verification_recommendation="state_re_read",
        ),
        _capability(
            name="system.service_stop",
            verb="stop",
            object_name="service",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({"service": _string(max_length=128)}, ["service"]),
            output_schema=_schema(
                {"service": _string(max_length=128), "status": _string(max_length=64)}
            ),
            verification_recommendation="state_re_read",
        ),
        _capability(
            name="system.service_restart",
            verb="restart",
            object_name="service",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({"service": _string(max_length=128)}, ["service"]),
            output_schema=_schema(
                {"service": _string(max_length=128), "status": _string(max_length=64)}
            ),
            verification_recommendation="state_re_read",
        ),
        _capability(
            name="system.service_reload",
            verb="reload",
            object_name="service",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({"service": _string(max_length=128)}, ["service"]),
            output_schema=_schema(
                {"service": _string(max_length=128), "status": _string(max_length=64)}
            ),
            verification_recommendation="state_re_read",
        ),
        _capability(
            name="system.list_services",
            verb="read",
            object_name="service",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({}),
            output_schema=_schema({"stdout": _string(min_length=0, max_length=100_000)}),
        ),
        _capability(
            name="system.restart_failed_services",
            verb="restart",
            object_name="service",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({}),
            output_schema=_schema(
                {"restarted": _array(max_items=128), "errors": _array(max_items=128)}
            ),
            verification_recommendation="command_exit_status_plus_state",
        ),
        _capability(
            name="disk.check_usage",
            verb="read",
            object_name="disk",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({"path": _string(max_length=4096)}, ["path"]),
            output_schema=_schema(
                {
                    "usage_percent": _integer(minimum=0, maximum=100),
                    "stdout": _string(min_length=0, max_length=100_000),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
        ),
        _capability(
            name="disk.find_large_directories",
            verb="read",
            object_name="directory",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema(
                {"path": _string(max_length=4096), "limit": _integer(minimum=1, maximum=100)},
                ["path"],
            ),
            output_schema=_schema(
                {"items": _array(max_items=100), "error": _string(min_length=0, max_length=100_000)}
            ),
        ),
        _capability(
            name="file.search",
            verb="read",
            object_name="file",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema(
                {
                    "query": _string(max_length=256),
                    "path": _string(max_length=4096),
                    "limit": _integer(minimum=1, maximum=100),
                },
                ["query", "path"],
            ),
            output_schema=_schema(
                {
                    "matches": _array(max_items=100),
                    "limit": _integer(minimum=1, maximum=100),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
        ),
        _capability(
            name="file.preview_metadata",
            verb="read",
            object_name="file_metadata",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({"path": _string(max_length=4096)}, ["path"]),
            output_schema=_schema(
                {
                    "exists": _bool(),
                    "path": _string(max_length=4096),
                    "is_dir": _bool(),
                    "size_bytes": _integer(minimum=0, maximum=10_000_000_000_000),
                    "mtime": _number(minimum=0, maximum=10_000_000_000),
                }
            ),
        ),
        _capability(
            name="file.read_file",
            verb="read",
            object_name="file",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema(
                {
                    "path": _string(max_length=4096),
                    "max_bytes": _integer(minimum=1, maximum=1_000_000),
                },
                ["path"],
            ),
            output_schema=_schema(
                {
                    "content": _string(min_length=0, max_length=1_000_000),
                    "path": _string(max_length=4096),
                    "truncated": _bool(),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
        ),
        _capability(
            name="file.append_file",
            verb="write",
            object_name="file",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {"path": _string(max_length=4096), "content": _string(max_length=1_000_000)},
                ["path", "content"],
            ),
            output_schema=_schema(
                {
                    "path": _string(max_length=4096),
                    "bytes_written": _integer(minimum=0, maximum=1_000_000),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
            verification_recommendation="state_re_read",
        ),
        _capability(
            name="file.write_file",
            verb="write",
            object_name="file",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {"path": _string(max_length=4096), "content": _string(max_length=1_000_000)},
                ["path", "content"],
            ),
            output_schema=_schema(
                {
                    "path": _string(max_length=4096),
                    "bytes_written": _integer(minimum=0, maximum=1_000_000),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
            verification_recommendation="state_re_read",
        ),
        _capability(
            name="file.delete",
            verb="delete",
            object_name="file",
            risk_tier=RiskTier.TIER_2,
            approval_mode=ApprovalMode.ADMIN,
            is_read_only=False,
            input_schema=_schema({"path": _string(max_length=4096)}, ["path"]),
            output_schema=_schema(
                {"path": _string(max_length=4096), "deleted": _bool(), "error": _string()}
            ),
            verification_recommendation="existence_nonexistence_check",
        ),
        _capability(
            name="file.move",
            verb="move",
            object_name="file",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {"source": _string(max_length=4096), "destination": _string(max_length=4096)},
                ["source", "destination"],
            ),
            output_schema=_schema(
                {
                    "source": _string(max_length=4096),
                    "destination": _string(max_length=4096),
                    "error": _string(),
                }
            ),
            verification_recommendation="filesystem_metadata_recheck",
        ),
        _capability(
            name="file.copy",
            verb="copy",
            object_name="file",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {"source": _string(max_length=4096), "destination": _string(max_length=4096)},
                ["source", "destination"],
            ),
            output_schema=_schema(
                {
                    "source": _string(max_length=4096),
                    "destination": _string(max_length=4096),
                    "error": _string(),
                }
            ),
            verification_recommendation="filesystem_metadata_recheck",
        ),
        _capability(
            name="file.chmod",
            verb="write",
            object_name="file",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {"path": _string(max_length=4096), "mode": _string(max_length=32)},
                ["path", "mode"],
            ),
            output_schema=_schema(
                {"path": _string(max_length=4096), "mode": _string(max_length=32)}
            ),
            verification_recommendation="filesystem_metadata_recheck",
        ),
        _capability(
            name="file.chown",
            verb="write",
            object_name="file",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {"path": _string(max_length=4096), "owner": _string(max_length=128)},
                ["path", "owner"],
            ),
            output_schema=_schema(
                {"path": _string(max_length=4096), "owner": _string(max_length=128)}
            ),
            verification_recommendation="filesystem_metadata_recheck",
        ),
        _capability(
            name="process.list",
            verb="read",
            object_name="process",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({"limit": _integer(minimum=1, maximum=500)}),
            output_schema=_schema(
                {
                    "processes": _array(max_items=500),
                    "limit": _integer(minimum=1, maximum=500),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
        ),
        _capability(
            name="process.find_by_port",
            verb="read",
            object_name="port",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema(
                {"port": _integer(minimum=1, maximum=65535), "expect_free": {"type": "boolean"}},
                ["port"],
            ),
            output_schema=_schema(
                {
                    "pids": _array(max_items=128),
                    "stdout": _string(min_length=0, max_length=100_000),
                }
            ),
            verification_recommendation="port_process_recheck",
        ),
        _capability(
            name="process.kill",
            verb="terminate",
            object_name="process",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {
                    "pid": _integer(minimum=1, maximum=4_194_304),
                    "signal": {"type": "string", "enum": ["TERM", "KILL"]},
                    "port": _integer(minimum=1, maximum=65535),
                },
                ["pid"],
            ),
            output_schema=_schema(
                {
                    "ok": _bool(),
                    "pid": _integer(minimum=1, maximum=4_194_304),
                    "signal": {"type": "string", "enum": ["TERM", "KILL"]},
                    "port": _integer(minimum=1, maximum=65535),
                    "error": _string(min_length=0, max_length=100_000),
                },
                ["ok"],
            ),
            verification_recommendation="command_exit_status_plus_state",
        ),
        _capability(
            name="process.inspect",
            verb="read",
            object_name="process",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({"pid": _integer(minimum=1, maximum=4_194_304)}, ["pid"]),
            output_schema=_schema(
                {
                    "pid": _integer(minimum=1, maximum=4_194_304),
                    "stdout": _string(min_length=0, max_length=100_000),
                }
            ),
        ),
        _capability(
            name="process.zombie_procs",
            verb="read",
            object_name="zombie",
            risk_tier=RiskTier.TIER_0,
            approval_mode=ApprovalMode.AUTO,
            is_read_only=True,
            input_schema=_schema({}),
            output_schema=_schema({"zombies": _array(max_items=1024)}),
        ),
        _capability(
            name="process.terminate_by_name",
            verb="terminate",
            object_name="process",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {
                    "name": _string(max_length=256),
                    "signal": {"type": "string", "enum": ["TERM", "KILL"]},
                },
                ["name"],
            ),
            output_schema=_schema(
                {
                    "name": _string(max_length=256),
                    "signal": {"type": "string", "enum": ["TERM", "KILL"]},
                }
            ),
            verification_recommendation="command_exit_status_plus_state",
        ),
        _capability(
            name="user.create",
            verb="create",
            object_name="user",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({"username": _string(max_length=64)}, ["username"]),
            output_schema=_schema(
                {
                    "username": _string(max_length=64),
                    "exists": _bool(),
                    "stdout": _string(min_length=0, max_length=100_000),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
            verification_recommendation="existence_nonexistence_check",
        ),
        _capability(
            name="user.delete",
            verb="delete",
            object_name="user",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema({"username": _string(max_length=64)}, ["username"]),
            output_schema=_schema(
                {
                    "username": _string(max_length=64),
                    "absent": _bool(),
                    "error": _string(min_length=0, max_length=100_000),
                }
            ),
            verification_recommendation="existence_nonexistence_check",
        ),
        _capability(
            name="cleanup.safe_disk_cleanup",
            verb="delete",
            object_name="cleanup_candidate",
            risk_tier=RiskTier.TIER_1,
            approval_mode=ApprovalMode.HUMAN,
            is_read_only=False,
            input_schema=_schema(
                {
                    "approved_paths": _array(max_items=20),
                    "candidate_class": _string(max_length=64),
                    "older_than_days": _integer(minimum=0, maximum=3650),
                    "max_files": _integer(minimum=1, maximum=10_000),
                    "max_bytes": _integer(minimum=1, maximum=10_000_000_000),
                    "execute": {"type": "boolean"},
                    "path": _string(max_length=4096),
                }
            ),
            output_schema=_schema(
                {
                    "previewed_candidates": _array(max_items=10_000),
                    "deleted": _array(max_items=10_000),
                    "reclaimed_bytes": _integer(minimum=0, maximum=10_000_000_000),
                    "ok": _bool(),
                    "error": _string(min_length=0, max_length=100_000),
                    "path": _string(max_length=4096),
                }
            ),
            verification_recommendation="filesystem_metadata_recheck",
        ),
        _capability(
            name="plan.explain_action",
            verb="explain",
            object_name="policy_refusal",
            risk_tier=RiskTier.TIER_3,
            approval_mode=ApprovalMode.DENY,
            is_read_only=True,
            input_schema=_schema(
                {"path": _string(max_length=4096), "action": _string(max_length=64)}
            ),
            output_schema=_schema({"reason": _string(max_length=4096)}),
            verification_recommendation="none",
        ),
    ]
    return CapabilityRegistry(capabilities)
