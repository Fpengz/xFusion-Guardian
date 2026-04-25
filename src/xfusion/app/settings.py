from __future__ import annotations

import os
from typing import Literal, cast

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    """Runtime settings loaded from environment variables."""

    model_config = ConfigDict(extra="forbid")

    llm_base_url: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None)
    llm_model: str | None = Field(default=None)
    audit_log_path: str = "audit.jsonl"
    response_mode: Literal["normal", "debug"] = "normal"


def _response_mode_from_env(raw: str | None) -> Literal["normal", "debug"]:
    if raw == "debug":
        return "debug"
    return cast(Literal["normal", "debug"], "normal")


def load_settings() -> Settings:
    """Load settings from process environment."""
    load_dotenv()
    return Settings(
        llm_base_url=os.environ.get("XFUSION_LLM_BASE_URL"),
        llm_api_key=os.environ.get("XFUSION_LLM_API_KEY"),
        llm_model=os.environ.get("XFUSION_LLM_MODEL"),
        audit_log_path=os.environ.get("XFUSION_AUDIT_LOG_PATH", "audit.jsonl"),
        response_mode=_response_mode_from_env(os.environ.get("XFUSION_RESPONSE_MODE")),
    )
