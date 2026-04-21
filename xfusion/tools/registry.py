from __future__ import annotations

from collections.abc import Callable
from typing import Any

from xfusion.tools.base import ToolOutput
from xfusion.tools.cleanup import CleanupTools
from xfusion.tools.disk import DiskTools
from xfusion.tools.file import FileTools
from xfusion.tools.process import ProcessTools
from xfusion.tools.system import SystemTools
from xfusion.tools.user import UserTools


class ToolRegistry:
    """Registry for safe, typed XFusion tools."""

    def __init__(
        self,
        system_tools: SystemTools,
        disk_tools: DiskTools,
        process_tools: ProcessTools,
        file_tools: FileTools | None = None,
        user_tools: UserTools | None = None,
        cleanup_tools: CleanupTools | None = None,
    ) -> None:
        runner = system_tools.runner
        file_tools = file_tools or FileTools(runner)
        user_tools = user_tools or UserTools(runner)
        cleanup_tools = cleanup_tools or CleanupTools(runner)

        self.tools: dict[str, Callable[..., ToolOutput]] = {
            "system.detect_os": system_tools.detect_os,
            "system.check_ram": system_tools.check_ram,
            "system.current_user": system_tools.current_user,
            "system.check_sudo": system_tools.check_sudo,
            "system.service_status": system_tools.service_status,
            "disk.check_usage": disk_tools.check_usage,
            "disk.find_large_directories": disk_tools.find_large_directories,
            "file.search": file_tools.search,
            "file.preview_metadata": file_tools.preview_metadata,
            "process.list": process_tools.list,
            "process.find_by_port": process_tools.find_by_port,
            "process.kill": process_tools.kill,
            "user.create": user_tools.create,
            "user.delete": user_tools.delete,
            "cleanup.safe_disk_cleanup": cleanup_tools.safe_disk_cleanup,
        }

    def execute(self, name: str, parameters: dict[str, Any]) -> ToolOutput:
        """Execute a tool by name with parameters."""
        if name not in self.tools:
            return ToolOutput(summary=f"Tool '{name}' not found.", data={"error": "not_found"})

        try:
            return self.tools[name](**parameters)
        except Exception as e:
            return ToolOutput(summary=f"Error executing tool '{name}': {e}", data={"error": str(e)})
