"""The one interface between the line engine and its step adapters (contract §30.2).

The engine (lines/engine.py) owns runs, gates, caps, versions and the ledger; an adapter only does
its step: it gets a StepContext and returns a StepOutput, or raises StepFailed with a plain Persian
reason. Adapters never write a run's rows, never publish outside `publish`/`deliver`, and never fall
back to another model silently. The registry maps a step kind to its adapter; tests swap in fakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

KINDS = (
    "gpt_text", "dedupe", "tts", "pattern_search", "council_pick", "opus_build", "render",
    "cover", "quality", "publish", "deliver", "n8n", "seal",
)  # fmt: skip


@dataclass(frozen=True)
class StepOutput:
    text: str | None = None
    file_id: str | None = None
    files: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    via: str = ""  # the tool or player that answered ("chatgpt-web", "aistudio-web", "router:opus", "ig-hub", ...)
    tokens: int = 0
    usd_equiv: Decimal = Decimal(0)


@dataclass(frozen=True)
class StepContext:
    run_ref: str
    line_ref: str
    company: str  # company code
    platform: str
    channel: dict[str, Any]
    step: dict[
        str, Any
    ]  # the StepDef as the line overrides it (key, kind, prompt_fa, settings, ...)
    prompt: str | None  # prompt_fa with {{vars}} filled from the inputs and the line
    inputs: dict[str, StepOutput]  # the outputs of the steps named in `inputs`, by step key
    library: tuple[
        dict[str, Any], ...
    ]  # the line's assets (cover folders, voices, prompts, patterns)
    dry: bool  # a dry run: publish and deliver answer without leaving
    hub: Any  # the Hub (settings, db, temporal, egress client); adapters use what they need


class StepFailed(Exception):
    """A step that cannot finish; `reason_fa` is shown to the owner as it is."""

    def __init__(self, reason_fa: str, *, code: str = "step_failed", retry: bool = False) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa
        self.code = code
        self.retry = retry


class StepAdapter(Protocol):
    kind: str

    async def run(self, ctx: StepContext) -> StepOutput: ...


REGISTRY: dict[str, StepAdapter] = {}


def register(adapter: StepAdapter) -> StepAdapter:
    if adapter.kind not in KINDS:
        raise ValueError(f"unknown step kind {adapter.kind}")
    REGISTRY[adapter.kind] = adapter
    return adapter
