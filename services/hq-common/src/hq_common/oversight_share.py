"""The oversight token share (prompt 08 §2.3, contract §18.1 v1.4.4).

The Chief Overseer and QC (the inspector) together use at most
OVERSIGHT_DAILY_SHARE (default 0.2) of the agents' daily token cap
(AGENT_DAILY_TOKEN_CAP, per UTC day: input + output + cache tokens).
llm-router enforces it on every call of those two roles, like a budget at
100%; the api's protocol runs record `deferred` for what no longer fits.
Only a `critical` protocol's run goes on once the share is spent.
"""

from __future__ import annotations

import math

ROLES = ("overseer", "inspector")  # the Chief Overseer and QC (agents/roles)
DEFAULT_SHARE = 0.2
CRITICAL = "critical"


def parse_share(value: str | None) -> float:
    """OVERSIGHT_DAILY_SHARE from the environment: empty = the default; a
    fraction between 0 and 1 (0 = oversight runs only critical protocols)."""
    if value is None or not value.strip():
        return DEFAULT_SHARE
    share = float(value)
    if not math.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("OVERSIGHT_DAILY_SHARE must be a fraction between 0 and 1")
    return share


def limit(daily_cap: int, share: float) -> int:
    """Tokens oversight may use per UTC day. AGENT_DAILY_TOKEN_CAP=0 means
    nothing at all (prompt 08.1: never "no cap"), so its share is 0 too."""
    if daily_cap <= 0:
        return 0
    return int(daily_cap * min(max(share, 0.0), 1.0))


def spent(used: int, daily_cap: int, share: float) -> bool:
    """True once oversight's tokens of the day reach its share."""
    return used >= limit(daily_cap, share)
