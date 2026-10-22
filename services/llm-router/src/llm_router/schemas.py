"""Request/response models of the internal API (prompt 03 §3)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from hq_common import vision
from llm_router.backends.base import ImagePart, Part

Effort = Literal["low", "medium", "high", "xhigh", "max"]
# Ledger metadata an agent call may carry (never content).
META_KEYS = frozenset(
    {
        "charter",
        "run_id",
        "step",
        "trigger",
        "purpose",
        # prompt 08 §6-§7: the sealed skill versions and teachings in the
        # system prompt (lists), and an academy eval's run, suite and case
        "skills",
        "addenda",
        "eval_run",
        "suite",
        "case",
        # prompt 08 §2.3: an oversight run's protocol and severity (a
        # `critical` one still runs once the oversight share is spent)
        "protocol",
        "severity",
    }
)
# Keys whose value is a list of short refs ("SK-001@3", "TE-0001").
META_LISTS = frozenset({"skills", "addenda"})
META_LIST_MAX = 30


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text"]
    text: str = Field(min_length=1)


class ImageBlock(BaseModel):
    """An image a model may see (prompt 06 §2): bytes only, never a URL."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["image"]
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    data: str = Field(min_length=1, repr=False)  # base64
    _size: int = PrivateAttr(default=0)

    @model_validator(mode="after")
    def _bytes(self) -> ImageBlock:
        self._size = len(vision.decode(self.media_type, self.data))
        return self

    @property
    def size(self) -> int:
        return self._size


Block = Annotated[TextBlock | ImageBlock, Field(discriminator="type")]


class Message(BaseModel):
    """A turn: a text, or (user turns only) text and image blocks in order."""

    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str | list[Block]

    @field_validator("content")
    @classmethod
    def _not_empty(cls, v: str | list[Any]) -> str | list[Any]:
        if not v:
            raise ValueError("content must not be empty")
        return v

    @model_validator(mode="after")
    def _images_from_the_user(self) -> Message:
        if self.role != "user" and self.images():
            raise ValueError("only a user turn may carry images")
        return self

    def text(self) -> str:
        """The message's text (all text blocks, in order)."""
        if isinstance(self.content, str):
            return self.content
        return "\n\n".join(b.text for b in self.content if isinstance(b, TextBlock))

    def images(self) -> list[ImageBlock]:
        if isinstance(self.content, str):
            return []
        return [b for b in self.content if isinstance(b, ImageBlock)]

    def parts(self) -> tuple[Part, ...]:
        """The ordered parts for a backend when the turn has images, else ()."""
        if not self.images():
            return ()
        assert not isinstance(self.content, str)
        return tuple(
            b.text if isinstance(b, TextBlock) else ImagePart(b.media_type, b.data)
            for b in self.content
        )

    def without_bytes(self) -> dict[str, Any]:
        """For a stored transcript: an image is kept as its type and size only."""
        if isinstance(self.content, str):
            return {"role": self.role, "content": self.content}
        return {
            "role": self.role,
            "content": [
                {"type": "text", "text": b.text}
                if isinstance(b, TextBlock)
                else {"type": "image", "media_type": b.media_type, "bytes": b.size}
                for b in self.content
            ],
        }


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
    # The most output tokens this call may produce (prompt 5.1 §2.6: an agent
    # step's hard cap); the router clamps it to LLM_MAX_OUTPUT_TOKENS.
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    store_transcript: bool = False
    # The employee behind an agent call (its code): assignments by employee
    # (`<CO>:<code>`, written by a hire) apply after the role's (prompt 05 §2).
    employee: str | None = Field(
        default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}-[A-Z0-9]+(-[A-Z0-9]+)?$"
    )
    # Ledger metadata of an agent call (allow-listed keys, short values).
    meta: dict[str, str | int | list[str]] | None = None

    @field_validator("meta")
    @classmethod
    def _meta(
        cls, v: dict[str, str | int | list[str]] | None
    ) -> dict[str, str | int | list[str]] | None:
        if v is None:
            return v
        unknown = set(v) - META_KEYS
        if unknown:
            raise ValueError(f"unknown meta keys: {sorted(unknown)}")
        for key, value in v.items():
            if isinstance(value, list):
                if key not in META_LISTS or len(value) > META_LIST_MAX:
                    raise ValueError(f"meta {key}: a list only for {sorted(META_LISTS)}")
                if any(len(item) > 32 for item in value):
                    raise ValueError("meta list items are at most 32 characters")
            elif isinstance(value, str) and len(value) > 64:
                raise ValueError("meta values are at most 64 characters")
        return v

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
        images = self.images()
        if len(images) > vision.MAX_IMAGES:
            raise ValueError(f"at most {vision.MAX_IMAGES} images per request")
        if sum(i.size for i in images) > vision.MAX_TOTAL_BYTES:
            raise ValueError("images are larger than 20 MiB together")
        return self

    def images(self) -> list[ImageBlock]:
        return [i for m in self.messages or [] for i in m.images()]

    def as_messages(self) -> list[Message]:
        if self.messages is not None:
            return self.messages
        assert self.prompt is not None
        return [Message(role="user", content=self.prompt)]

    def input_chars(self) -> int:
        """Text only: images have their own limits (hq_common.vision)."""
        return len(self.system or "") + sum(len(m.text()) for m in self.as_messages())


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    thinking_tokens: int | None
    cache_write_1h_tokens: int | None = None  # part of cache_write_tokens, when reported


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
