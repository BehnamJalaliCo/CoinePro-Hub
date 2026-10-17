"""Cost from our own price table (llm.connections.pricing, USD per 1M tokens).

Mirror of services/llm-router/src/llm_router/pricing.py (the only cost source,
owner decision prompt 04 §9), used for the Token Treasury's "what if this had
run on model X" (design list #22). tests/test_treasury.py pins the parity.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

MILLION = Decimal(1_000_000)
QUANT = Decimal("0.000001")


def cost_usd(
    pricing: Mapping[str, Any],
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_write_1h_tokens: int = 0,
) -> Decimal | None:
    p = pricing.get(model)
    if not isinstance(p, Mapping) or p.get("input") is None or p.get("output") is None:
        return None
    rates: Mapping[str, Any] = p
    tier = p.get("long_prompt")
    prompt = input_tokens + cache_read_tokens + cache_write_tokens
    if isinstance(tier, Mapping) and prompt > int(tier.get("above_prompt_tokens", 0)):
        rates = tier

    def rate(key: str, default: Any = 0) -> Decimal:
        value = rates.get(key)
        return Decimal(str(default if value is None else value))

    written_1h = min(cache_write_1h_tokens, cache_write_tokens)
    total = (
        input_tokens * rate("input")
        + output_tokens * rate("output")
        + cache_read_tokens * rate("cache_read")
        + (cache_write_tokens - written_1h) * rate("cache_write")
        + written_1h * rate("cache_write_1h", rates.get("cache_write", 0))
    ) / MILLION
    return total.quantize(QUANT)
