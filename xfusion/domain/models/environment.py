from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EnvironmentState(BaseModel):
    """Current OS and runtime facts used for planning and policy."""

    model_config = ConfigDict(extra="forbid")

    distro_family: str = "unknown"
    distro_version: str = "unknown"
    current_user: str = "unknown"
    sudo_available: bool = False
    systemd_available: bool = False
    package_manager: str = "unknown"
    disk_pressure: str = "unknown"
    session_locality: str = "local"
    protected_paths: tuple[str, ...] = ("/", "/etc", "/boot", "/usr", "/var/lib")
    active_facts: dict[str, object] = Field(default_factory=dict)
