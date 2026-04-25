from __future__ import annotations

from pathlib import Path

from xfusion.capabilities.manifest import load_capability_manifests
from xfusion.capabilities.registry import CapabilityRegistry
from xfusion.execution.allowlist import ExecutableRegistry


def default_executable_registry() -> ExecutableRegistry:
    """Reviewed executable IDs available to argv-backed manifests."""

    return ExecutableRegistry(
        {
            "coreutils.df": "/bin/df",
            "coreutils.ps": "/bin/ps",
            "systemd.systemctl": "/bin/systemctl",
            "systemd.journalctl": "/bin/journalctl",
            "iproute.ss": "/usr/bin/ss",
            "iproute.ip": "/sbin/ip",
            "dns.getent": "/usr/bin/getent",
            "network.ping": "/bin/ping",
            "network.traceroute": "/usr/bin/traceroute",
            "docker.docker": "/usr/bin/docker",
        }
    )


def load_v025_catalog(catalog_root: Path | None = None) -> CapabilityRegistry:
    """Load the reviewed v0.2.5 capability catalog manifests."""

    root = catalog_root or Path(__file__).resolve().parents[3] / "capabilities" / "v0.2.5"
    paths = sorted(root.glob("*/*.yaml"))
    return load_capability_manifests(paths, executables=default_executable_registry())


load_vnext_catalog = load_v025_catalog
