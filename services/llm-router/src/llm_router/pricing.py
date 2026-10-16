"""Cost from our own price table (llm.connections.pricing, USD per 1M tokens)."""

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

    @property
    def total(self) -> int:
        """Tokens counted against budgets: every token the call moved."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


def cost_usd(pricing: Mapping[str, Any], model: str, usage: Usage) -> Decimal | None:
    """None when the table has no price for the model."""
    p = pricing.get(model)
    if not p:
        return None

    def rate(key: str) -> Decimal:
        return Decimal(str(p.get(key, 0)))

    total = (
        usage.input_tokens * rate("input")
        + usage.output_tokens * rate("output")
        + usage.cache_read_tokens * rate("cache_read")
        + usage.cache_write_tokens * rate("cache_write")
    ) / MILLION
    return total.quantize(QUANT)
