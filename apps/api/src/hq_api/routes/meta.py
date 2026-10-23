"""Health and meta (contract §11)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hq_api import __version__
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import briefings, org
from hq_api.errors import responses
from hq_api.hub import Hub, get_hub
from hq_api.workshop import service as workshop

router = APIRouter(tags=["meta"])


class Health(BaseModel):
    status: str


class Channels(BaseModel):
    in_app: bool
    web_push: bool
    fcm: bool
    telegram: bool


class WorkshopMeta(BaseModel):
    runtime: Literal["managed", "self_hosted"] | None


class Precedence(BaseModel):
    rank: int
    kinds: list[str]
    note_fa: str


class TtsMeta(BaseModel):
    enabled: bool
    engine: str
    version: str
    voice: str
    license: str


class Meta(BaseModel):
    api_version: str
    service_version: str
    login_configured: bool
    public_origin: str | None
    channels: Channels
    stream_retention_days: int
    # ⟨1.3⟩ null until the owner chooses (then POST /workshop/sessions works)
    workshop: WorkshopMeta
    # ⟨1.4⟩ who outranks whom (§18.0); Employee.rank follows it
    precedence: list[Precedence]
    # ⟨1.5⟩ the hub's Persian voice (§21.4): engine, voice, its licence; `enabled`
    # is the opt-in TTS profile (off: briefings are text, audio_state "off")
    tts: TtsMeta | None = None


@router.get("/health", response_model=Health)
async def get_health(hub: Hub = Depends(get_hub)) -> Health:
    """Liveness without authentication: `{status}` only, nothing else."""
    return Health(status="ok")


@router.get("/meta", response_model=Meta, responses=responses(401))
async def get_meta(ctx: Ctx = Depends(owner_ctx)) -> Meta:
    """Versions, enabled channels and whether passkey login is configured."""
    s = ctx.hub.settings
    sec = ctx.hub.secrets
    return Meta(
        api_version="v1",
        service_version=__version__,
        login_configured=s.login_configured,
        public_origin=s.public_origin or None,
        channels=Channels(
            in_app=True,
            web_push=sec.web_push_ready and s.login_configured,
            fcm=sec.fcm_ready,
            telegram=sec.telegram_ready,
        ),
        stream_retention_days=30,
        workshop=WorkshopMeta.model_validate({"runtime": workshop.meta_runtime(ctx.hub)}),
        precedence=[
            Precedence(rank=r, kinds=list(kinds), note_fa=note) for r, kinds, note in org.PRECEDENCE
        ],
        tts=TtsMeta(enabled=s.tts, **briefings.voice(s)),
    )
