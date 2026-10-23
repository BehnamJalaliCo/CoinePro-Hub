"""The owner zone's token share (prompt 12 §15, contract §21.0).

The *automatic* runs of the owner's zone (the advisor's automatic memos,
proactive notes and weekly review brief, the librarian, the digital CEO's
model predictions and principles) together use at most
OWNER_ZONE_DAILY_SHARE (default 0.25, pending the owner's decision) of the
agents' daily token cap (AGENT_DAILY_TOKEN_CAP, per UTC day). llm-router
enforces it on every automatic call of these task classes, like the
oversight share; the api defers what no longer fits (automatic memos and
proactive notes wait for the next day, predictions fall back to the
baseline). What the owner asks for directly (an ask, a memo on request, a
message) always runs, inside the overall cap, and counts in the zone too.

A call says which it is in its meta: `owner_zone: "auto"` or `"direct"`.
Substitute players' calls never count here (contract §21.13).
"""

from __future__ import annotations

import math

TASK_CLASSES = (
    "advisor_memo",
    "advisor_proactive",
    "advisor_review",
    "ask_hub",
    "dceo_predict",
    "dceo_principles",
)
DEFAULT_SHARE = 0.25
AUTO = "auto"
DIRECT = "direct"


def parse_share(value: str | None) -> float:
    """OWNER_ZONE_DAILY_SHARE from the environment: empty = the default; a
    fraction between 0 and 1 (0 = no automatic run of the zone at all)."""
    if value is None or not value.strip():
        return DEFAULT_SHARE
    share = float(value)
    if not math.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("OWNER_ZONE_DAILY_SHARE must be a fraction between 0 and 1")
    return share


def limit(daily_cap: int, share: float) -> int:
    """Tokens the zone's automatic runs may use per UTC day; a cap of 0 means
    nothing at all, so the share is 0 too."""
    if daily_cap <= 0:
        return 0
    return int(daily_cap * min(max(share, 0.0), 1.0))


def spent(used: int, daily_cap: int, share: float) -> bool:
    """True once the zone's tokens of the day reach its share."""
    return used >= limit(daily_cap, share)


def applies(task_class: str | None, zone: str | None) -> bool:
    """Whether a call is an automatic run of the zone (the share stops it)."""
    return task_class in TASK_CLASSES and zone != DIRECT
