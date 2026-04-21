from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolInput(BaseModel):
    """Base class for typed tool inputs."""

    model_config = ConfigDict(extra="forbid")


class ToolOutput(BaseModel):
    """Base class for typed tool outputs."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    data: dict[str, object] = Field(default_factory=dict)
