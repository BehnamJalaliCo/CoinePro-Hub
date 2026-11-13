"""⟨1.37⟩ Contract §59.4, §59.7-§59.10 (prompt 38): the flow automations, the use form, the board,
the owner's day, and n8n's clock (`/internal/v1/flows/tick`, `/internal/v1/flows/summary`).

Included before `routes/automations.py`, so `/automations/board`, `/automations/today` and
`/automations/calendar` are matched before `/automations/{ref}`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["automations"])
internal_router = APIRouter(tags=["flows"])
