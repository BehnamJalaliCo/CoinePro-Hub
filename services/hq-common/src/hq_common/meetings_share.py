"""The meetings' daily token share (prompt 11 §1.2, contract §20.1 ⟨1.5⟩).

All the meetings of one UTC day together use at most MEETINGS_DAILY_SHARE
(default 0.15, the owner's to change) of the agents' daily token cap
(AGENT_DAILY_TOKEN_CAP: input + output + cache tokens). The api reserves each
meeting's budget from what is left at its start (a meeting that does not fit
runs `written`); llm-router enforces the share on every model call of a
meeting turn (`meta.meeting`), like the oversight share of §18.1. A war room
is outside the share: it has no meeting cap and stays inside the daily cap
and the holding's kill switch only. Each meeting's own cap is the router's
scope `meeting:<ref>` (`meta.meeting_cap`).
"""

from __future__ import annotations

import math

DEFAULT_SHARE = 0.15
WAR_ROOM = "war_room"  # the meeting kind outside the share (and without a meeting cap)


def parse_share(value: str | None) -> float:
    """MEETINGS_DAILY_SHARE from the environment: empty = the default; a
    fraction between 0 and 1 (0 = no meeting turns but the war room's)."""
    if value is None or not value.strip():
        return DEFAULT_SHARE
    share = float(value)
    if not math.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("MEETINGS_DAILY_SHARE must be a fraction between 0 and 1")
    return share


def limit(daily_cap: int, share: float) -> int:
    """Tokens the meetings may use per UTC day. AGENT_DAILY_TOKEN_CAP=0 means
    nothing at all (never "no cap"), so its share is 0 too."""
    if daily_cap <= 0:
        return 0
    return int(daily_cap * min(max(share, 0.0), 1.0))


def spent(used: int, daily_cap: int, share: float) -> bool:
    """True once the meetings' tokens of the day reach their share."""
    return used >= limit(daily_cap, share)
