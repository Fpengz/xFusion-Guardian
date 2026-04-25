"""Structured command templates for Tier 2 execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xfusion.policy.categories import PolicyCategory


class TemplateParameter(BaseModel):
    """Parameter definition for a command template."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str  # string, integer, boolean, file, directory
    required: bool = False
    validation: str | None = None  # regex pattern
    default: Any = None
    description: str = ""


class CommandTemplate(BaseModel):
    """Structured command template for Tier 2 execution."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    category: PolicyCategory
    parameters: list[TemplateParameter] = Field(default_factory=list)
    command: str  # Template with {{param}} placeholders
    timeout: int = 30  # Seconds
    confirm_required: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)  # Empty allows all
    network_restricted: bool = False
    file_operations: str = "none"  # none, read, write, all
    version: int = 1
    enabled: bool = True


@dataclass(frozen=True)
class TemplateValidationResult:
    """Result of template parameter validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    resolved_command: str | None = None


class TemplateEngine:
    """Engine for validating and rendering command templates."""

    def __init__(self, templates: list[CommandTemplate]) -> None:
        self.templates: dict[str, CommandTemplate] = {t.name: t for t in templates if t.enabled}

    def get_template(self, name: str) -> CommandTemplate | None:
        """Get a template by name."""
        return self.templates.get(name)

    def validate_parameters(
        self, template_name: str, params: dict[str, Any]
    ) -> TemplateValidationResult:
        """Validate parameters against a template and render the command."""
        template = self.get_template(template_name)
        if not template:
            return TemplateValidationResult(
                valid=False, errors=[f"Template '{template_name}' not found"]
            )

        errors: list[str] = []

        # Check required parameters
        for param in template.parameters:
            if param.required and param.name not in params:
                errors.append(f"Missing required parameter: {param.name}")

        # Validate provided parameters
        for param_name, value in params.items():
            param_def = next((p for p in template.parameters if p.name == param_name), None)
            if not param_def:
                errors.append(f"Unknown parameter: {param_name}")
                continue

            # Type validation
            if not self._validate_type(value, param_def.type):
                err_msg = (
                    f"Parameter '{param_name}' expected type {param_def.type}, "
                    f"got {type(value).__name__}"
                )
                errors.append(err_msg)
                continue

            # Regex validation
            if (
                param_def.validation
                and isinstance(value, str)
                and not re.match(param_def.validation, value)
            ):
                errors.append(
                    f"Parameter '{param_name}' value '{value}' does not match "
                    f"pattern {param_def.validation}"
                )

        if errors:
            return TemplateValidationResult(valid=False, errors=errors)

        # Render command
        try:
            rendered = self._render_command(template, params)
            return TemplateValidationResult(valid=True, errors=[], resolved_command=rendered)
        except Exception as e:
            return TemplateValidationResult(valid=False, errors=[f"Failed to render command: {e}"])

    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Validate value against expected type."""
        if expected_type == "string":
            return isinstance(value, str)
        elif expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        elif expected_type == "boolean":
            return isinstance(value, bool)
        elif expected_type in ("file", "directory"):
            return isinstance(value, str)
        return True

    def _render_command(self, template: CommandTemplate, params: dict[str, Any]) -> str:
        """Render command template with parameters."""
        command = template.command

        # Apply defaults for missing optional parameters
        for param in template.parameters:
            if param.name not in params and param.default is not None:
                params[param.name] = param.default

        # Replace {{param}} placeholders
        for param_name, value in params.items():
            placeholder = "{{" + param_name + "}}"
            if isinstance(value, str):
                # Simple shell escaping for strings
                value = value.replace("'", "'\\''")
                value = f"'{value}'"
            else:
                value = str(value)
            command = command.replace(placeholder, value)

        return command

    def list_templates(self) -> list[CommandTemplate]:
        """List all available templates."""
        return list(self.templates.values())

    def search_templates(self, query: str) -> list[CommandTemplate]:
        """Search templates by name or description."""
        query_lower = query.lower()
        return [
            t
            for t in self.templates.values()
            if query_lower in t.name.lower() or query_lower in t.description.lower()
        ]
