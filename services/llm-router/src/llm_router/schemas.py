"""Request/response models of the internal API (prompt 03 §3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_code: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    actor_ref: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
    work_ref: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,15}$")
    role: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    task_class: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    priority: int = Field(ge=0, le=4)
    model: str | None = Field(default=None, max_length=100)
    effort: Effort | None = None
    system: str | None = None
    messages: list[Message] | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, min_length=1)
    json_schema: dict[str, Any] | None = None
    timeout_s: int = Field(default=120, ge=1)
    store_transcript: bool = False

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, v: Any) -> Any:
        if isinstance(v, str) and len(v) == 2 and v[0] in "Pp" and v[1].isdigit():
            return int(v[1])
        return v

    @model_validator(mode="after")
    def _one_input(self) -> RunRequest:
        if (self.messages is None) == (self.prompt is None):
            raise ValueError("send exactly one of `messages` or `prompt`")
        if self.messages is not None and self.messages[-1].role != "user":
            raise ValueError("the last message must come from the user")
        return self

    def as_messages(self) -> list[Message]:
        if self.messages is not None:
            return self.messages
        assert self.prompt is not None
        return [Message(role="user", content=self.prompt)]

    def input_chars(self) -> int:
        return len(self.system or "") + sum(len(m.content) for m in self.as_messages())


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    thinking_tokens: int | None


class RunResponse(BaseModel):
    call_id: str
    status: str
    text: str | None = None
    json_output: Any = Field(default=None, serialization_alias="json")
    usage: UsageOut | None = None
    connection: str
    model: str | None
    effort: str | None
    cost_usd: str | None = None
    equiv_cost_usd: str | None = None
    latency_ms: int | None = None
    error_class: str | None = None
