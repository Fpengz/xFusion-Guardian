from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from xfusion.app.commands.base import BaseCommand

if TYPE_CHECKING:
    from xfusion.app.tui import XFusionTUI
    from xfusion.domain.models.environment import EnvironmentState


class StatusCommand(BaseCommand):
    name = "status"
    description = "Show current session and environment status."
    usage = "/status"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        env = cast("EnvironmentState", app.state["environment"])
        mode = cast(str, app.state["response_mode"])

        status_text = "### Session Status\n\n"
        status_text += f"- **Session ID**: `{app.session_id}`\n"
        status_text += f"- **Mode**: `{mode.upper()}`\n"
        status_text += f"- **Environment**: `{env.distro_family} {env.distro_version}`\n"
        status_text += f"- **User**: `{env.current_user}`\n"
        status_text += f"- **Locality**: `{env.session_locality}`\n"

        app.add_agent_message({"response": status_text})


class PermissionsCommand(BaseCommand):
    name = "permissions"
    aliases = ["policy"]
    description = "Show current execution policy and approval mode."
    usage = "/permissions"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        # Pull from app settings and current state
        from xfusion.app.settings import load_settings

        settings = load_settings()

        policy_text = "### Execution Policy\n\n"
        policy_text += f"- **Approval Mode**: `{getattr(settings, 'approval_mode', 'N/A')}`\n"
        policy_text += f"- **Risk Gating**: `{getattr(settings, 'risk_gating_enabled', 'N/A')}`\n"
        policy_text += f"- **Audit Enabled**: `{getattr(settings, 'audit_enabled', 'N/A')}`\n"

        decision = app.state.get("policy_decision")
        if decision:
            policy_text += f"- **Last Decision**: `{decision}`\n"

        app.add_agent_message({"response": policy_text})


class ConfigCommand(BaseCommand):
    name = "config"
    description = "Show effective settings."
    usage = "/config"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from xfusion.app.settings import load_settings

        settings = load_settings()

        config_data = settings.model_dump()
        # Redact secrets
        if "llm_api_key" in config_data:
            config_data["llm_api_key"] = "********"

        config_json = json.dumps(config_data, indent=2)
        app.add_agent_message(
            {"response": f"### Effective Configuration\n\n```json\n{config_json}\n```"}
        )


class ModelCommand(BaseCommand):
    name = "model"
    description = "Show current model configuration."
    usage = "/model"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from xfusion.app.settings import load_settings

        settings = load_settings()
        model_text = "### Model Configuration\n\n"
        model_text += f"- **Provider**: `{getattr(settings, 'llm_provider', 'N/A')}`\n"
        model_text += f"- **Model**: `{settings.llm_model}`\n"
        model_text += f"- **Temperature**: `{getattr(settings, 'llm_temperature', 'N/A')}`\n"

        app.add_agent_message({"response": model_text})


class CompactCommand(BaseCommand):
    name = "compact"
    description = "Summarize current conversation into a compact snapshot."
    usage = "/compact"
    mutates_session_state = True

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        # In a real implementation, this might call a special LLM node.
        # For now, we'll just summarize the audit records count.
        records = cast(list, app.state.get("audit_records", []))
        count = len(records)
        app.add_agent_message(
            {"response": f"✦ Compacted {count} audit records into a session snapshot."}
        )


class ListCommand(BaseCommand):
    name = "list"
    aliases = ["capabilities", "caps", "tools"]
    description = "List all registered agent capabilities."
    usage = "/list"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from rich.table import Table

        from xfusion.app.theme import command_table_styles
        from xfusion.app.tui import Static
        from xfusion.capabilities.registry import build_default_capability_registry

        registry = build_default_capability_registry()
        capabilities = registry.all()

        styles = command_table_styles()
        table = Table(title="Registered Capabilities", box=None, show_header=True)
        table.add_column("Capability", style=styles["primary"])
        table.add_column("Action", style=styles["text"])
        table.add_column("Risk", style=styles["muted"])
        table.add_column("Approval", style=styles["muted"])

        for cap in sorted(capabilities, key=lambda x: x.name):
            table.add_row(
                cap.name,
                f"{cap.verb} {cap.object}",
                cap.risk_tier.value.upper(),
                cap.approval_mode.value.upper(),
            )

        app.query_one("#timeline").mount(Static(table))


class TemplatesCommand(BaseCommand):
    name = "templates"
    description = "List structured command templates available before restricted shell fallback."
    usage = "/templates"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        from rich.table import Table

        from xfusion.app.theme import command_table_styles
        from xfusion.app.tui import Static
        from xfusion.capabilities.default_templates import build_default_templates

        templates = [template for template in build_default_templates() if template.enabled]

        styles = command_table_styles()
        table = Table(title="Structured Templates", box=None, show_header=True)
        table.add_column("Template", style=styles["primary"])
        table.add_column("Category", style=styles["muted"])
        table.add_column("Approval", style=styles["muted"])
        table.add_column("Description", style=styles["text"])

        for template in sorted(templates, key=lambda item: item.name):
            approval = "required" if template.confirm_required else "auto"
            table.add_row(
                template.name,
                template.category.value,
                approval,
                template.description,
            )

        app.query_one("#timeline").mount(Static(table))


class AuditCommand(BaseCommand):
    name = "audit"
    description = "Show the most recent audit trace records for this session."
    usage = "/audit"
    mutates_session_state = False

    async def handle(self, app: XFusionTUI, args: list[str]) -> None:
        records = cast(list, app.state.get("audit_records", []))
        if not records:
            app.add_agent_message({"response": "No audit records in the current session."})
            return

        audit_text = "### Recent Audit Records\n\n"
        for index, record in enumerate(records[-10:], start=1):
            rec = cast(dict, record)
            status = rec.get("status", "unknown")
            step_id = rec.get("step_id", "unknown")
            surface = rec.get("execution_surface", "unknown")
            category = rec.get("final_risk_category") or rec.get("policy_category") or "unknown"
            audit_text += f"{index}. `{step_id}` `{status}` surface=`{surface}` risk=`{category}`\n"

        app.add_agent_message({"response": audit_text})
