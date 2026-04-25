"""Default command templates for Tier 2 execution."""

from xfusion.capabilities.templates import CommandTemplate, TemplateParameter
from xfusion.policy.categories import PolicyCategory


def build_default_templates() -> list[CommandTemplate]:
    """Build default command templates for common operations."""
    return [
        # File operations
        CommandTemplate(
            name="file.read",
            description="Read contents of a file safely",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=True,
                    description="Path to the file to read",
                ),
                TemplateParameter(
                    name="max_bytes",
                    type="integer",
                    required=False,
                    default=10000,
                    description="Maximum bytes to read",
                ),
            ],
            command="head -c {{max_bytes}} {{path}}",
            timeout=10,
            confirm_required=False,
            file_operations="read",
        ),
        CommandTemplate(
            name="file.list",
            description="List files in a directory",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="directory",
                    required=True,
                    description="Directory path to list",
                ),
                TemplateParameter(
                    name="limit",
                    type="integer",
                    required=False,
                    default=50,
                    description="Maximum number of entries to list",
                ),
            ],
            command="ls -la {{path}}",
            timeout=10,
            confirm_required=False,
            file_operations="read",
        ),
        CommandTemplate(
            name="file.create",
            description="Create a new file with content",
            category=PolicyCategory.WRITE_SAFE,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=True,
                    description="Path where to create the file",
                ),
                TemplateParameter(
                    name="content",
                    type="string",
                    required=True,
                    description="Content to write to the file",
                ),
            ],
            command="echo {{content}} > {{path}}",
            timeout=10,
            confirm_required=True,
            file_operations="write",
            enabled=False,
        ),
        CommandTemplate(
            name="file.delete",
            description="Delete a file (requires confirmation)",
            category=PolicyCategory.DESTRUCTIVE,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=True,
                    description="Path to the file to delete",
                ),
            ],
            command="rm {{path}}",
            timeout=10,
            confirm_required=True,
            file_operations="write",
        ),
        CommandTemplate(
            name="directory.create",
            description="Create a new directory",
            category=PolicyCategory.WRITE_SAFE,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=True,
                    description="Path where to create the directory",
                ),
            ],
            command="mkdir -p {{path}}",
            timeout=10,
            confirm_required=True,
            file_operations="write",
        ),
        # Process operations
        CommandTemplate(
            name="process.list_all",
            description="List all running processes",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="limit",
                    type="integer",
                    required=False,
                    default=100,
                    description="Maximum number of processes to list",
                ),
            ],
            command="ps aux",
            timeout=10,
            confirm_required=False,
        ),
        CommandTemplate(
            name="process.find_by_name",
            description="Find processes by name pattern",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="pattern",
                    type="string",
                    required=True,
                    description="Pattern to search for in process names",
                ),
            ],
            command="pgrep -a {{pattern}}",
            timeout=10,
            confirm_required=False,
        ),
        CommandTemplate(
            name="process.terminate",
            description="Terminate a process by PID",
            category=PolicyCategory.DESTRUCTIVE,
            parameters=[
                TemplateParameter(
                    name="pid",
                    type="integer",
                    required=True,
                    description="Process ID to terminate",
                ),
                TemplateParameter(
                    name="signal",
                    type="string",
                    required=False,
                    default="TERM",
                    validation="^(TERM|KILL|INT|HUP)$",
                    description="Signal to send (TERM, KILL, INT, HUP)",
                ),
            ],
            command="kill -{{signal}} {{pid}}",
            timeout=10,
            confirm_required=True,
        ),
        # System information
        CommandTemplate(
            name="system.disk_usage",
            description="Check disk usage",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=False,
                    default="/",
                    description="Path to check disk usage for",
                ),
            ],
            command="df -h {{path}}",
            timeout=10,
            confirm_required=False,
        ),
        CommandTemplate(
            name="system.memory_usage",
            description="Check memory usage",
            category=PolicyCategory.READ_ONLY,
            parameters=[],
            command="free -h",
            timeout=10,
            confirm_required=False,
        ),
        CommandTemplate(
            name="system.uptime",
            description="Check system uptime",
            category=PolicyCategory.READ_ONLY,
            parameters=[],
            command="uptime",
            timeout=10,
            confirm_required=False,
        ),
        # Network (read-only)
        CommandTemplate(
            name="network.connections",
            description="List network connections",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="port",
                    type="integer",
                    required=False,
                    description="Filter by port number",
                ),
            ],
            command="ss -tlnp",
            timeout=10,
            confirm_required=False,
            network_restricted=True,
        ),
        CommandTemplate(
            name="network.interfaces",
            description="List network interfaces",
            category=PolicyCategory.READ_ONLY,
            parameters=[],
            command="ip addr show",
            timeout=10,
            confirm_required=False,
            network_restricted=True,
        ),
        # Cleanup operations
        CommandTemplate(
            name="cleanup.temp_files",
            description="List temporary files older than N days",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="directory",
                    required=True,
                    description="Directory to search in",
                ),
                TemplateParameter(
                    name="days",
                    type="integer",
                    required=False,
                    default=7,
                    description="Files older than this many days",
                ),
            ],
            command="find {{path}} -type f -mtime +{{days}} -ls",
            timeout=30,
            confirm_required=False,
            file_operations="read",
        ),
        CommandTemplate(
            name="cleanup.delete_temp_files",
            description="Delete temporary files older than N days",
            category=PolicyCategory.DESTRUCTIVE,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="directory",
                    required=True,
                    description="Directory to clean",
                ),
                TemplateParameter(
                    name="days",
                    type="integer",
                    required=False,
                    default=7,
                    description="Files older than this many days",
                ),
            ],
            command="find {{path}} -type f -mtime +{{days}} -delete",
            timeout=30,
            confirm_required=True,
            file_operations="write",
        ),
        # Log operations
        CommandTemplate(
            name="logs.tail",
            description="View last lines of a log file",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=True,
                    description="Path to the log file",
                ),
                TemplateParameter(
                    name="lines",
                    type="integer",
                    required=False,
                    default=50,
                    description="Number of lines to show",
                ),
            ],
            command="tail -n {{lines}} {{path}}",
            timeout=10,
            confirm_required=False,
            file_operations="read",
        ),
        CommandTemplate(
            name="logs.search",
            description="Search for pattern in log file",
            category=PolicyCategory.READ_ONLY,
            parameters=[
                TemplateParameter(
                    name="path",
                    type="string",
                    required=True,
                    description="Path to the log file",
                ),
                TemplateParameter(
                    name="pattern",
                    type="string",
                    required=True,
                    description="Pattern to search for",
                ),
            ],
            command="grep {{pattern}} {{path}}",
            timeout=30,
            confirm_required=False,
            file_operations="read",
        ),
    ]
