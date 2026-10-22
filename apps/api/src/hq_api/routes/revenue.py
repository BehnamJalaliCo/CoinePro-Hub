"""The revenue radar (prompt 10 §2, contract §19.1). Empty until §2 lands.

Owner (/api/v1):  GET /revenue/summary, GET /revenue/days, GET|POST /revenue/accounts
                  (POST 🔏 revenue.account, body hash), POST /revenue/accounts/{id}/pull
                  (Idempotency-Key required, at most REVENUE_PULL_MAX_DAYS)
Agents (/internal/v1, internal_router): revenue.read (OPA op "revenue.read", A0)
Tables: revenue.accounts, days, invitees, pulls, alerts (migration 0025).
Every pull the worker starts asks hq_api.domain.gate first and skips while locked.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["revenue"])
internal_router = APIRouter(tags=["internal"])
