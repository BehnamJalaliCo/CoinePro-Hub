"""Intake from outside (prompt 10 §9, contract §19.8). Empty until §9 lands.

Owner (/api/v1, router):     GET /intake/sources, POST /intake/sources 🔏 intake.source
Public (/intake/v1, webhook_router; the only public routes prompt 10 adds,
served by Caddy, never /internal):
                             POST /telegram/{company}/{channel}, /chatwoot/{company},
                             /product/{company}; 401 unauthenticated on a bad
                             signature with no detail
Tables: intake.sources, nonces, events, rejections (migration 0025).
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["intake"])
webhook_router = APIRouter(tags=["intake"])
