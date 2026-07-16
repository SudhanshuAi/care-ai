"""Retell Custom Function request/response shapes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RetellCallContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    call_id: str | None = None
    resumed_from_call_id: str | None = None
    agent_id: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    direction: str | None = None
    language: str | None = None
    metadata: dict[str, Any] | None = None


class RetellToolInvocation(BaseModel):
    """Default Retell custom-function body: name + args + call."""

    model_config = ConfigDict(extra="allow")

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    call: RetellCallContext | None = None
