"""Cost from our own price table (llm.connections.pricing, USD per 1M tokens).

This is the only source of `cost_usd` (API) and `equiv_cost_usd`
(subscription); the SDK's own estimate is kept in the ledger meta for
comparison only (owner decision, prompt 04 §9).

One entry per model id:
    input, output, cache_read, cache_write   cache_write = 5-minute writes
    cache_write_1h                           optional: 1-hour writes
    long_prompt                              optional tier: {above_prompt_tokens,
                                             and the same rate keys}
    source_url, as_of                        where the numbers come from

A request whose prompt (input + cache read + cache write tokens) is above
`above_prompt_tokens` pays every rate of the long_prompt tier (Anthropic's
rule for Claude Haiku 5.5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

MILLION = Decimal(1_000_000)
QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int | None = None  # None: not reported separately (inside output)
    # The part of cache_write_tokens written with the 1-hour TTL, when reported.
    cache_write_1h_tokens: int | None = None

    @property
    def total(self) -> int:
        """Tokens counted against budgets: every token the call moved."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    @property
    def prompt_tokens(self) -> int:
        """Prompt length as Anthropic counts it for long-prompt pricing."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


def _rates(price: Mapping[str, Any], usage: Usage) -> Mapping[str, Any]:
    tier = price.get("long_prompt")
    if isinstance(tier, Mapping) and usage.prompt_tokens > int(tier.get("above_prompt_tokens", 0)):
        return tier
    return price


def cost_usd(pricing: Mapping[str, Any], model: str, usage: Usage) -> Decimal | None:
    """None when the table has no price for the model."""
    p = pricing.get(model)
    if not isinstance(p, Mapping) or p.get("input") is None or p.get("output") is None:
        return None
    r = _rates(p, usage)

    def rate(key: str, default: Any = 0) -> Decimal:
        value = r.get(key)
        return Decimal(str(default if value is None else value))

    written_1h = min(usage.cache_write_1h_tokens or 0, usage.cache_write_tokens)
    written_5m = usage.cache_write_tokens - written_1h
    # Without a 1-hour price, 1-hour writes are priced as 5-minute writes.
    rate_1h = rate("cache_write_1h", r.get("cache_write", 0))
    total = (
        usage.input_tokens * rate("input")
        + usage.output_tokens * rate("output")
        + usage.cache_read_tokens * rate("cache_read")
        + written_5m * rate("cache_write")
        + written_1h * rate_1h
    ) / MILLION
    return total.quantize(QUANT)
