"""⟨2026-11-13⟩ A working group's daily run (domain/flows.py): started by n8n's signed call, or by
the owner (to run a day now, e.g. a test).

    POST /internal/v1/flows/{key}/run   n8n, HMAC-signed (X-HQ-Signature over `<t>.<raw body>`)
    POST /api/v1/flows/{key}/run        the owner
Body `{day?: YYYY-MM-DD}` (the day the post goes out; left out: tomorrow, Tehran). Both need an
`Idempotency-Key` (n8n sends `flow:<key>:<day>`): one order per flow and day."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import flows as FL
from hq_api.errors import ApiError, responses
from hq_api.hub import Hub, get_hub
from hq_api.lines import signing
from hq_api.principal import Principal
from hq_api.routes.lines import n8n_secret
from hq_api.schemas import Model

router = APIRouter(tags=["flows"])
internal_router = APIRouter(tags=["flows"])
E = responses(401, 404, 409, 422)
OWNER = Principal(kind="owner", code="owner", role="owner")


class FlowRunIn(Model):
    day: date | None = None


class FlowRunOut(BaseModel):
    order: str
    work: str | None
    publish_at: str
    why_fa: str


@router.post("/flows/{key}/run", response_model=FlowRunOut, status_code=201, responses=E)
async def run_flow(
    key: str, body: FlowRunIn, request: Request, background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:  # fmt: skip
    """The owner runs a flow's day now (a test, or a day n8n missed)."""
    return FlowRunOut(**await FL.start(ctx, request, background, key, body.day))


@internal_router.post("/flows/{key}/run", response_model=FlowRunOut, status_code=201, responses=E)
async def run_flow_n8n(
    key: str, request: Request, background: BackgroundTasks, hub: Hub = Depends(get_hub)
) -> Any:
    """n8n's daily call, signed like a line's callback; the order is the owner's standing order
    (2026-11-13), carried out at his pace «خودکار»."""
    raw = await request.body()
    if not signing.verify(await n8n_secret(hub), raw, request.headers.get(signing.HEADER)):
        raise ApiError(401, "unauthenticated", "bad signature")
    try:
        body = FlowRunIn.model_validate_json(raw or b"{}")
    except ValueError as exc:
        raise ApiError(422, "validation_failed", "not a flow body") from exc
    ctx = Ctx(hub=hub, who=OWNER, request=request)
    return FlowRunOut(**await FL.start(ctx, request, background, key, body.day))
