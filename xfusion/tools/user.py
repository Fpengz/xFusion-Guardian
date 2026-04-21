from __future__ import annotations

from xfusion.execution.command_runner import CommandRunner
from xfusion.tools.base import ToolOutput


class UserTools:
    """Scoped user-management tools."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def create(self, username: str) -> ToolOutput:
        """Create a normal local user with a home directory."""
        res = self.runner.run(["sudo", "useradd", "-m", username])
        if res.exit_code != 0:
            return ToolOutput(
                summary=f"Failed to create user {username}: {res.stderr}",
                data={"error": res.stderr},
            )
        check = self.runner.run(["id", username])
        return ToolOutput(
            summary=f"Created user {username}.",
            data={"username": username, "exists": check.exit_code == 0, "stdout": check.stdout},
        )

    def delete(self, username: str) -> ToolOutput:
        """Delete a local user and home directory."""
        res = self.runner.run(["sudo", "userdel", "-r", username])
        if res.exit_code != 0:
            return ToolOutput(
                summary=f"Failed to delete user {username}: {res.stderr}",
                data={"error": res.stderr},
            )
        check = self.runner.run(["id", username])
        return ToolOutput(
            summary=f"Deleted user {username}.",
            data={"username": username, "absent": check.exit_code != 0},
        )
