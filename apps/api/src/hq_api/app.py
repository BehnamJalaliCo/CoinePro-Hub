"""FastAPI application: /api/v1 (owner), /internal/v1 (agents, services).

OpenAPI 3.1 comes from this app and is committed to openapi/hq-api.v1.json
(CI fails when it drifts). operationId = the handler's name (stable).
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

from hq_api import __version__, errors, media
from hq_api.errors import ApiError, problem_response
from hq_api.hub import Hub
from hq_api.openapi_examples import add_examples
from hq_api.routes import (
    academy,
    agent_tools,
    audit_control,
    auth,
    backups,
    brands,
    charter,
    decisions,
    deliverables,
    egress,
    errands,
    feedback,
    files,
    founding,
    governance,
    growth,
    growth_funnel,
    inbox,
    inquiries,
    intake,
    internal,
    knowledge,
    lifecycle,
    meetings,
    messages,
    meta,
    mgmt,
    notifications,
    orders,
    org,
    oversight,
    owner,
    people,
    revenue,
    runs,
    skills,
    stream,
    support,
    tools,
    treasury,
    work,
    workshop,
)
from hq_api.routes import ads as ads_routes  # prompt 22 part 3: §31.6
from hq_api.routes import advisor as advisor_routes  # prompt 12 part A
from hq_api.routes import archive as archive_routes  # prompt 14: the archive
from hq_api.routes import archive_agents as archive_agent_routes  # prompt 14: its agent tools
from hq_api.routes import ask as ask_routes  # prompt 12 §2, §3, §13 (on prompt 11)
from hq_api.routes import automations as automation_routes  # prompt 22 part 3: §31.7
from hq_api.routes import campaigns as campaign_routes  # prompt 22 part 3: §31.5
from hq_api.routes import connections as connection_routes  # prompt 21 part 3: §29.12
from hq_api.routes import council as council_routes  # prompt 21: the council v2
from hq_api.routes import dceo as dceo_routes
from hq_api.routes import erase as erase_routes  # prompt 26: §37.2-§37.3 erasing for good
from hq_api.routes import flow_auto as flow_auto_routes  # ⟨1.37⟩ §59.7 flows, board, today
from hq_api.routes import flows as flow_routes  # ⟨2026-11-13⟩ n8n's daily runs
from hq_api.routes import grok as grok_routes  # prompt 24: §33.7, §33.10
from hq_api.routes import groups as group_routes  # prompt 21 part 3: §29.9, §29.11
from hq_api.routes import home as home_routes  # prompt 21 part 3: §29.13
from hq_api.routes import hubops as hubops_routes  # ⟨1.20⟩ §38 the hub run from the app
from hq_api.routes import journey as journey_routes  # prompt 24: §33.8-§33.9
from hq_api.routes import kits as kit_routes  # prompt 22: §31.2 company kits
from hq_api.routes import legal as legal_routes  # prompt 13: the legal counsel
from hq_api.routes import lines as line_routes  # prompt 22: production lines (§30, §31.1)
from hq_api.routes import linked as linked_routes  # ⟨2026-11-06⟩ linked.read along a link
from hq_api.routes import links as link_routes  # prompt 25: §35.6 company links, the canvas
from hq_api.routes import live as live_routes  # ⟨1.24⟩ §42.3 the live views' seed
from hq_api.routes import look as look_routes  # ⟨1.33⟩ §55 what the 1.0.1 look reads
from hq_api.routes import media as media_routes  # prompt 13, the media half
from hq_api.routes import money as money_routes  # prompt 24: §33.2-§33.3 payments, the board
from hq_api.routes import narrators as narrator_routes  # ⟨1.31⟩ §48 a company's narrator
from hq_api.routes import newsletter as newsletter_routes  # prompt 22 part 3: §31.3
from hq_api.routes import office as office_routes  # prompt 25: §35.5 the owner's office
from hq_api.routes import order_report as order_report_routes  # prompt 21: §29.1-§29.2, §29.6
from hq_api.routes import playbooks as playbook_routes  # ⟨1.22⟩ §40 a session's playbook
from hq_api.routes import site_links as site_link_routes  # ⟨1.37⟩ §59.5-§59.6 links, replies
from hq_api.routes import reviews as review_routes
from hq_api.routes import role_drafts as role_draft_routes  # prompt 13 §1.1
from hq_api.routes import routines as routine_routes  # ⟨1.31⟩ §50 a routine from one sentence
from hq_api.routes import rules as rule_routes  # prompt 21: the owner's rules
from hq_api.routes import sales as sales_routes  # prompt 24: §33.1, §33.4-§33.5
from hq_api.routes import seo as seo_routes  # prompt 22 part 3: §31.4
from hq_api.routes import servers as server_routes  # prompt 17: company server runners
from hq_api.routes import session_team as session_team_routes  # ⟨1.35⟩ §57 the session's team
from hq_api.routes import sessions as session_routes  # prompt 25: §35.1-§35.3 every order a session
from hq_api.routes import speech as speech_routes  # ⟨2026-11-06⟩ speech.make: AI Studio's voices
from hq_api.routes import substitutes as substitute_routes  # prompt 12 part A
from hq_api.routes import talk as talk_routes  # prompt 23: §32 the owner's talk
from hq_api.routes import voice as voice_session_routes  # prompt 21: long voice
from hq_api.routes import voice_engines as voice_engine_routes  # prompt 23: §32.5-§32.6
from hq_api.routes import voices as voice_routes  # prompt 13: the voice registry
from hq_api.routes import watch as watch_routes  # prompt 19: catalogue, client errors

log = logging.getLogger("hq_api.access")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# Raw-body uploads and their own size caps (checked again while streaming).
UPLOAD_PATHS = ("/internal/v1/files", "/api/v1/files", "/api/v1/transcribe")
RUNNER_RESULT_BYTES = 32 * 1024 * 1024  # 20 MB as base64 and its JSON
RUNNER_EVENTS_BYTES = 8 * 1024 * 1024
SUBSTITUTE_DONE_BYTES = 48 * 1024 * 1024


def upload_limit(path: str, max_file: int, max_body: int) -> int:
    if path.startswith("/internal/v1/tts/") and path.endswith("/done"):
        return mgmt.MAX_AUDIO  # ⟨1.5⟩ a briefing's Ogg from the TTS one-shot
    if path.startswith("/internal/v1/media/render/") and path.endswith("/output"):
        return media_routes.MAX_OUTPUT  # ⟨1.6⟩ a render's file from the render one-shot
    if path.startswith("/internal/v1/substitutes/jobs/") and path.endswith("/done"):
        return SUBSTITUTE_DONE_BYTES  # ⟨1.10.1⟩ a CLI's whole answer (≤ 20 MB) and its JSON
    if path == "/api/v1/files":
        return media.VIDEO.max_bytes  # the largest kind; each kind is held to its own
    if path == "/api/v1/transcribe" or (
        path.startswith("/api/v1/transcribe/sessions/") and "/chunks/" in path
    ):
        return media.AUDIO.max_bytes  # ⟨1.11⟩ §29.5 a long voice's chunk too
    if path.startswith("/api/v1/runners/jobs/") and path.endswith("/files"):
        return media.VIDEO.max_bytes  # §43 a workspace turn's `out/` file, as an owner upload
    if path.startswith("/api/v1/runners/jobs/"):
        # ⟨1.8⟩ a runner's output batch, or a read's ≤ 20 MB file in its result
        return RUNNER_RESULT_BYTES if path.endswith("/result") else RUNNER_EVENTS_BYTES
    return max_file if path in UPLOAD_PATHS else max_body


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(
    hub: Hub | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
    *,
    openapi_url: str | None = "/api/v1/openapi.json",
) -> FastAPI:
    app = FastAPI(
        title="CoinePro HQ Core API",
        version="1.0.0",
        summary="Holding core: identity, organisation, work, inboxes, notifications, audit.",
        description=(
            "Contract: contracts/HQ_CORE_API_v1.md. Public endpoints live under /api/v1 "
            "(owner only, passkey sessions); /internal/v1 is for agents and services and is "
            "never routed by the public edge. Errors are application/problem+json with a "
            "stable `code` and a Persian `message_fa`."
        ),
        generate_unique_id_function=_operation_id,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=openapi_url,
        servers=[{"url": "/"}],
    )
    if hub is not None:
        app.state.hub = hub
    errors.install(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id", "")
        request.state.request_id = rid if _REQUEST_ID.match(rid) else str(uuid.uuid4())
        settings = request.app.state.hub.settings
        limit = upload_limit(request.url.path, settings.max_file_bytes, settings.max_body_bytes)
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return problem_response(
                request, ApiError(413, "validation_failed", "request body too large")
            )
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        route = request.scope.get("route")
        log.info(
            "request",
            extra={
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": request.state.request_id,
            },
        )
        return response

    # ⟨1.5⟩ prompt 12 part B: first, so /runs/health is not read as /runs/{id}
    app.include_router(mgmt.first_router, prefix="/api/v1")
    for module in (
        meta,
        auth,
        org,
        work,
        governance,  # prompt 11 §4-§10; before decisions: /decisions/batchable is no ref
        decisions,
        deliverables,
        files,
        messages,
        inbox,
        notifications,
        owner,
        audit_control,
        treasury,
        stream,
        runs,
        workshop,
        orders,
        oversight,
        backups,
        tools,
        egress,
        inquiries,
        errands,
        people,
        skills,
        academy,
        founding,
        brands,
        # prompt 10 (contract §19): revenue, support, growth, feedback, intake
        revenue,
        support,
        growth,
        growth_funnel,
        feedback,
        intake,
        lifecycle,  # /growth/templates, /growth/rules, /growth/nps (prompt 10 §7)
        # prompt 11 §1-§3 (contract §20.1-§20.3): meetings, the charter, knowledge
        meetings,
        charter,
        knowledge,
        mgmt,  # prompt 12 part B (contract §21.4-§21.9)
    ):
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(internal.router, prefix="/internal/v1")
    app.include_router(agent_tools.router, prefix="/internal/v1")
    app.include_router(workshop.internal_router, prefix="/internal/v1")
    app.include_router(oversight.internal_router, prefix="/internal/v1")
    app.include_router(tools.internal_router, prefix="/internal/v1")
    app.include_router(egress.internal_router, prefix="/internal/v1")
    app.include_router(inquiries.internal_router, prefix="/internal/v1")
    app.include_router(errands.internal_router, prefix="/internal/v1")
    app.include_router(people.internal_router, prefix="/internal/v1")
    app.include_router(skills.internal_router, prefix="/internal/v1")
    app.include_router(academy.internal_router, prefix="/internal/v1")
    app.include_router(founding.internal_router, prefix="/internal/v1")
    app.include_router(mgmt.internal_router, prefix="/internal/v1")
    for p10 in (revenue, support, growth, growth_funnel, feedback):
        app.include_router(p10.internal_router, prefix="/internal/v1")
    for p11 in (meetings, charter, knowledge):  # prompt 11 §1-§3
        app.include_router(p11.internal_router, prefix="/internal/v1")
    app.include_router(governance.internal_router, prefix="/internal/v1")  # prompt 11 §4-§10
    # Prompt 12 part A (contract §21.1, §21.13): the advisor's memos and the
    # substitute players.
    for p12a in (advisor_routes, substitute_routes):
        app.include_router(p12a.router, prefix="/api/v1")
        app.include_router(p12a.internal_router, prefix="/internal/v1")
    # Prompt 12 §2, §3, §13 (contract §21.2, §21.3, §21.10): ask the hub, the
    # weekly review, the digital CEO's predictions.
    for p12f in (ask_routes, review_routes, dceo_routes):
        app.include_router(p12f.router, prefix="/api/v1")
    app.include_router(ask_routes.internal_router, prefix="/internal/v1")
    # Prompt 13 §1.1 (contract §22.5): roles written on demand.
    app.include_router(role_draft_routes.router, prefix="/api/v1")
    app.include_router(role_draft_routes.internal_router, prefix="/internal/v1")
    # Prompt 13, the legal and voice half (contract §22.3, §22.4).
    for p13b in (legal_routes, voice_routes):
        app.include_router(p13b.router, prefix="/api/v1")
        app.include_router(p13b.internal_router, prefix="/internal/v1")
    # The only public routes prompt 10 adds (webhooks; never /internal).
    app.include_router(intake.webhook_router, prefix="/intake/v1")
    # ⟨1.6⟩ prompt 13, the media half (contract §22.2): the media studio, and the
    # one public route it adds (a signed 15-minute file URL Instagram fetches).
    app.include_router(media_routes.router, prefix="/api/v1")
    app.include_router(media_routes.internal_router, prefix="/internal/v1")
    app.include_router(media_routes.public_router, prefix="/public/v1")
    # ⟨1.8⟩ prompt 17 (contract §26): company server runners; their agent tools.
    app.include_router(server_routes.router, prefix="/api/v1")
    app.include_router(server_routes.internal_router, prefix="/internal/v1")
    app.include_router(watch_routes.router, prefix="/api/v1")
    app.include_router(watch_routes.internal_router, prefix="/internal/v1")
    # ⟨1.11⟩ prompt 21 part 3 (contract §29.9, §29.11-§29.13): working groups,
    # readiness, connections, the owner's home; their agent tools.
    for p21c in (group_routes, connection_routes):
        app.include_router(p21c.router, prefix="/api/v1")
        app.include_router(p21c.internal_router, prefix="/internal/v1")
    app.include_router(home_routes.router, prefix="/api/v1")
    # ⟨1.13⟩ prompt 22 part 3 (contract §31.3-§31.5): newsletter, SEO rank and competitors,
    # the campaign calendar (all owner only).
    for p22g in (newsletter_routes, seo_routes, campaign_routes):
        app.include_router(p22g.router, prefix="/api/v1")
    # ⟨1.7⟩ prompt 14 (contract §23): the archive of record and its agent tools.
    app.include_router(archive_routes.router, prefix="/api/v1")
    app.include_router(archive_agent_routes.internal_router, prefix="/internal/v1")
    # ⟨1.11⟩ prompt 21 (contract §29.3, §29.5, §29.8): the owner's rules, long
    # voice, the council v2's «اجرا کن» and fact packs
    for p21b in (rule_routes, voice_session_routes, council_routes):
        app.include_router(p21b.router, prefix="/api/v1")
    # ⟨1.11⟩ prompt 21 part 1 (contract §29.1, §29.2, §29.6): the order report and
    # its fixes; order.ack, order.progress, work.budget, card.decide.
    app.include_router(order_report_routes.router, prefix="/api/v1")
    app.include_router(order_report_routes.internal_router, prefix="/internal/v1")
    # ⟨1.17⟩ prompt 25 (contract §35.1-§35.3): every order a session: the list, participants,
    # the plan, close / reopen / hide
    app.include_router(session_routes.router, prefix="/api/v1")
    # ⟨1.35⟩ §57: the session's team, one person at a time (side talks, an empty seat's hire)
    app.include_router(session_team_routes.router, prefix="/api/v1")
    # ⟨1.22⟩ §40: a session's playbook (drafted, sealed, given to another company)
    app.include_router(playbook_routes.router, prefix="/api/v1")
    # ⟨1.19⟩ prompt 26 (contract §37.2-§37.3): an archive record or an output erased for good, an
    # agent's proposed erase (the session's own erase is in session_routes)
    app.include_router(erase_routes.router, prefix="/api/v1")
    app.include_router(erase_routes.internal_router, prefix="/internal/v1")
    # ⟨1.13⟩ prompt 22 part 3 (contract §31.6, §31.7): ad budgets, automations from a sentence.
    # ⟨1.37⟩ §59 the flow automations, the board and the owner's day (before /automations/{ref}),
    # a company's links and a flow's replies; n8n's tick and summary
    app.include_router(flow_auto_routes.router, prefix="/api/v1")
    app.include_router(flow_auto_routes.internal_router, prefix="/internal/v1")
    app.include_router(site_link_routes.router, prefix="/api/v1")
    for p22c in (ads_routes, automation_routes):
        app.include_router(p22c.router, prefix="/api/v1")
    # ⟨2026-11-06⟩ a CEO's or manager's proposed automation (the owner seals it)
    app.include_router(automation_routes.internal_router, prefix="/internal/v1")
    # ⟨1.12⟩ prompt 22 (contract §30.5, §31.1): production lines; n8n's signed callback
    app.include_router(line_routes.router, prefix="/api/v1")
    app.include_router(line_routes.internal_router, prefix="/internal/v1")
    # ⟨2026-11-13⟩ a working group's daily run, started by n8n (domain/flows.py)
    app.include_router(flow_routes.router, prefix="/api/v1")
    app.include_router(flow_routes.internal_router, prefix="/internal/v1")
    # prompt 22 (contract §31.2): a ready company from one order
    app.include_router(kit_routes.router, prefix="/api/v1")
    # ⟨1.14⟩ prompt 23 (contract §32): the owner's talk (owner only)
    app.include_router(talk_routes.router, prefix="/api/v1")
    # ⟨1.15⟩ prompt 24 (contract §33.8-§33.9): the company journey, personas and the message test
    app.include_router(journey_routes.router, prefix="/api/v1")
    # ⟨1.17⟩ (contract §35.6): the links between companies and the owner's canvas (owner only)
    app.include_router(link_routes.router, prefix="/api/v1")
    # ⟨2026-11-06⟩ a company's data along an `on` link (linked.read, A0): «عین رگ انسان»
    app.include_router(linked_routes.internal_router, prefix="/internal/v1")
    # ⟨2026-11-06⟩ a voice from Google AI Studio for the media roles (speech.make, A1)
    app.include_router(speech_routes.internal_router, prefix="/internal/v1")
    # ⟨1.31⟩ §48 a company's narrator (the owner's setting; narrator.set in his session), and
    # §50 a standing routine from one sentence
    app.include_router(narrator_routes.router, prefix="/api/v1")
    app.include_router(narrator_routes.internal_router, prefix="/internal/v1")
    app.include_router(routine_routes.router, prefix="/api/v1")
    app.include_router(look_routes.router, prefix="/api/v1")
    # ⟨1.20⟩ §38: hub operations (hub.ops, its dispatcher) and the owner's services page
    app.include_router(hubops_routes.router, prefix="/api/v1")
    app.include_router(hubops_routes.internal_router, prefix="/internal/v1")
    # ⟨1.17⟩ (contract §35.5): the owner's office (owner only)
    app.include_router(office_routes.router, prefix="/api/v1")
    # ⟨1.24⟩ (contract §42.3): the holding live, seeded (owner only)
    app.include_router(live_routes.router, prefix="/api/v1")
    # ⟨1.15⟩ prompt 24 (contract §33.1-§33.6): payments and the revenue board; usage reports, the
    # CRM and affiliate follow-up (OPA hq.money); the agents' read of them
    app.include_router(money_routes.router, prefix="/api/v1")
    app.include_router(sales_routes.router, prefix="/api/v1")
    app.include_router(money_routes.internal_router, prefix="/internal/v1")
    # ⟨1.15⟩ prompt 24 (contract §33.7, §33.10): parallel parts, the workspace's stop
    app.include_router(grok_routes.router, prefix="/api/v1")
    app.include_router(grok_routes.internal_router, prefix="/internal/v1")
    # prompt 23 (contract §32.5-§32.6): the voice engines, the key and its light, the meter and the
    # cap; Piper's queue for the TTS one-shot
    app.include_router(voice_engine_routes.router, prefix="/api/v1")
    app.include_router(voice_engine_routes.internal_router, prefix="/internal/v1")
    app.state.version = __version__

    plain_openapi = app.openapi

    def openapi_with_examples() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = add_examples(plain_openapi())
        return app.openapi_schema

    app.openapi = openapi_with_examples  # type: ignore[method-assign]
    return app


async def _noop(_: FastAPI) -> AsyncIterator[None]:
    yield


def openapi_document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()
