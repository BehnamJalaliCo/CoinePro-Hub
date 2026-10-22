"""The feedback inbox (prompt 10 §8, contract §19.7). Empty until §8 lands.

Owner (/api/v1):  GET /feedback, PATCH /feedback/{ref} (If-Match)
Agents (/internal/v1, internal_router): feedback.tag
Tables: feedback.items, signals, keywords (migration 0025). Quotes are
hq_common.customer_mask.quote(): no handle, no UID.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["feedback"])
internal_router = APIRouter(tags=["internal"])
