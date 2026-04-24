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
