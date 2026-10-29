"""The substitute players (prompt 12 §9.1, contract §21.13): ChatGPT and
Gemini on the owner's subscriptions, and DeepSeek's free chat, called onto
the pitch for one bounded task at a time. Claude holds the project.

The bench's rules, in code:
  - A substitute answers one bounded question (a seat call): no thread, no
    memory, no write path; its output is labelled `source` and is never
    evidence (nothing here raises, closes or disputes a finding, or confirms
    or refutes a claim).
  - Its input is masked (§16.6) and passes the data guard: personal data or a
    secret -> `policy_denied`; for `quick_search` (a public web search) the
    whole egress guard of web.search (no internal name, ref or code).
  - Nothing falls back silently: a player that is off, signed out, expired,
    `limited`, or over its seat's daily cap makes the call `skipped` (counted
    in `month.skipped`); the caller carries on with its own model. A Claude
    run never goes to a substitute and a seat never goes to Claude.
  - Substitute calls count against no daily cap or share; the ledger records
    them (llm.calls, caller 'substitutes') at their equivalent cost.
The runs:
  - CLI seats (`via: "cli"`): the host dispatcher claims queued calls one at a
    time for both players (POST /internal/v1/substitutes/jobs/claim), runs the
    official CLI one-shot in the runner and posts the result (.../done).
  - Web seats (`via: "web"`, every `creative`, every DeepSeek seat): the
    worker runs them through egress's signed-in browser profiles, one job per
    player at a time and at least 60 s apart.
The launch gate: while the holding's kill switch is engaged a seat call is
`skipped` (holding_locked), the claim answers no job and the worker runs no
web job: no model and no outside service is reached.
Every sign-in is the owner's (the app's headless sign-in or the terminal);
nothing here signs in by itself, and no credential ever passes through it
(only the owner's one-time pasted code, handed to the runner once).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import gate, notify
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Model
from hq_api.worker.jalali import to_jalali
from hq_common.redact import scrub

log = logging.getLogger("hq_api.domain.substitutes")

Player = Literal["gpt", "gemini", "deepseek"]
PLAYERS: tuple[str, ...] = ("gpt", "gemini", "deepseek")
SEATS = (
    "advisor_second_opinion",
    "code_review",
    "overseer_cross_check",
    "assistant_errand",
    "content_draft",
    "long_read",
    "quick_search",
    "third_opinion",
    "creative",
)
Seat = Literal[
    "advisor_second_opinion",
    "code_review",
    "overseer_cross_check",
    "assistant_errand",
    "content_draft",
    "long_read",
    "quick_search",
    "third_opinion",
    "creative",
]
# The ledger's task class of each seat (contract §21.13). DeepSeek's two
# seats (added 2026-10-22) have none of their own: the nearest ones.
TASK_CLASS = {
    "advisor_second_opinion": "sub_second_opinion",
    "third_opinion": "sub_second_opinion",
    "code_review": "sub_code_review",
    "overseer_cross_check": "sub_cross_check",
    "assistant_errand": "sub_errand",
    "quick_search": "sub_errand",
    "content_draft": "sub_draft",
    "long_read": "sub_long_read",
    "creative": "sub_creative",
}
# Players, as seeded (contract §21.13; the owner's choices). Model ids are
# data: checked against what each CLI offers under the subscription.
DEFAULT_PLAYERS: dict[str, dict[str, Any]] = {
    "gpt": {
        "connection": "chatgpt-plus",
        "runner": "codex_cli",
        "web": "chatgpt-web",
        "plan_fa": "ChatGPT Plus (اشتراک مالک)",
        "price_usd": Decimal("20"),
        "models": [
            {"id": "gpt-5.5", "label": "GPT 5.5", "tier": "strong", "available": True},
            {"id": "gpt-5.3", "label": "GPT 5.3", "tier": "light", "available": True},
        ],
        "capabilities": {"text": "cli", "image": "web", "video": "off"},
    },
    "gemini": {
        "connection": "gemini-pro",
        "runner": "gemini_cli",
        "web": "gemini-web",
        "plan_fa": "Google AI Pro (اشتراک مالک)",
        "price_usd": Decimal("20"),
        "models": [
            {"id": "gemini-3.8", "label": "Gemini 3.8", "tier": "strong", "available": True}
        ],
        # ⟨1.7.2⟩: Google ended the Gemini CLI for individuals; text runs on the web.
        "capabilities": {"text": "web", "image": "web", "video": "web"},
    },
    "deepseek": {
        "connection": "deepseek-free",
        "runner": None,
        "web": "deepseek-web",
        "plan_fa": "DeepSeek (رایگان)",
        "price_usd": Decimal("0"),
        "models": [
            {"id": "deepseek-chat", "label": "DeepSeek (وب)", "tier": "strong", "available": True}
        ],
        "capabilities": {"text": "web", "image": "off", "video": "off"},
    },
}
# Seats (contract §21.13 table; owner decision §0.8 #10: all on).
DEFAULT_SEATS: dict[str, list[dict[str, Any]]] = {
    "gpt": [
        {"seat": "advisor_second_opinion", "via": "cli", "model": "gpt-5.5", "enabled": True, "per_day": 3},
        {"seat": "code_review", "via": "cli", "model": "gpt-5.5", "enabled": True, "per_day": 10},
        {"seat": "overseer_cross_check", "via": "cli", "model": "gpt-5.5", "enabled": True, "per_day": 20},
        {"seat": "assistant_errand", "via": "cli", "model": "gpt-5.3", "enabled": True, "per_day": 30},
        {"seat": "creative", "via": "web", "model": "gpt-5.5", "enabled": True, "per_day": 20,
         "per_day_video": 0},
    ],
    "gemini": [
        # ⟨1.7.2⟩: every Gemini seat runs via the signed-in web profile.
        {"seat": "code_review", "via": "web", "model": "gemini-3.8", "enabled": False, "per_day": 10},
        {"seat": "content_draft", "via": "web", "model": "gemini-3.8", "enabled": True, "per_day": 30},
        {"seat": "long_read", "via": "web", "model": "gemini-3.8", "enabled": True, "per_day": 10},
        {"seat": "creative", "via": "web", "model": "gemini-3.8", "enabled": True, "per_day": 20,
         "per_day_video": 3},
    ],
    "deepseek": [
        {"seat": "quick_search", "via": "web", "model": "deepseek-chat", "enabled": True, "per_day": 60},
        {"seat": "third_opinion", "via": "web", "model": "deepseek-chat", "enabled": True, "per_day": 5},
    ],
}  # fmt: skip
SEAT_ORDER = {s: i for i, s in enumerate(SEATS)}
WEB_PACE = timedelta(seconds=60)
LOGIN_MINUTES = 10
CALL_TIMEOUT_S = {"code_review": 900, "creative": 900, "long_read": 600}
TEXT_LIMIT = 200_000
SERVICE = Principal(kind="service", code="substitutes", role="service")
OWNER_TZ = "Asia/Tehran"


# ------------------------------------------------------------------ shapes --
class ModelRow(BaseModel):
    id: str
    label: str
    tier: Literal["strong", "light"]
    available: bool


class Login(BaseModel):
    state: Literal["signed_out", "signing_in", "signed_in", "expired"]
    plan_fa: str
    since: datetime | None
    last_ok_at: datetime | None


class Web(BaseModel):
    account: str
    state: Literal["signed_in", "expired", "signed_out"]
    last_ok_at: datetime | None
    recipe_version: str
    last_failure: str | None


class SeatOut(BaseModel):
    seat: str
    via: Literal["cli", "web"]
    model: str
    enabled: bool
    per_day: int
    used_today: int
    per_day_video: int | None = None
    used_today_video: int | None = None


class Month(BaseModel):
    key: str
    calls: int
    skipped: int
    input_tokens: int
    output_tokens: int
    estimated: bool
    equiv_usd: str
    price_usd: str
    value_ratio: float | None


class Substitute(BaseModel):
    player: Player
    connection: str
    connection_id: UUID | None
    runner: Literal["codex_cli", "gemini_cli"] | None
    login: Login
    status: Literal["ready", "limited", "off", "error"]
    limited_until: datetime | None
    status_reason: str | None
    models: list[ModelRow]
    capabilities: dict[str, str]
    web: Web
    seats: list[SeatOut]
    month: Month
    version: int


class SeatIn(Model):
    seat: Seat
    via: Literal["cli", "web"]
    model: str = Field(min_length=1, max_length=80)
    enabled: bool
    per_day: int = Field(ge=0, le=1000)
    per_day_video: int | None = Field(default=None, ge=0, le=100)


class Overlay(Model):
    title_fa: str = Field(min_length=1, max_length=80)
    body_fa: str | None = Field(default=None, max_length=200)
    cta_fa: str | None = Field(default=None, max_length=60)
    mark: bool = True


Placement = Literal[
    "telegram_post", "telegram_story", "instagram_post", "instagram_story", "banner", "other"
]
ASPECT = {
    "telegram_post": "16:9",
    "telegram_story": "9:16",
    "instagram_post": "4:5",
    "instagram_story": "9:16",
    "banner": "16:9",
    "other": "1:1",
}


class CallIn(Model):
    """substitute.call (agents/tools.md, contract §21.13)."""

    seat: Seat
    player: Player | None = None
    input_md: str = Field(min_length=1, max_length=TEXT_LIMIT)
    file_ids: list[UUID] = Field(default_factory=list, max_length=10)
    repo: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    head_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    kind: Literal["text", "image", "video"] = "text"
    placement: Placement | None = None
    overlay: Overlay | None = None
    duration_s: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def _shape(self) -> CallIn:
        if self.seat == "code_review" and not (self.repo and self.head_sha):
            raise ValueError("code_review needs repo and head_sha")
        if self.seat != "code_review" and (self.repo or self.head_sha):
            raise ValueError("repository code goes to code_review only")
        if self.seat == "creative":
            if self.kind == "text":
                raise ValueError("creative is kind image or video")
            if self.placement is None:
                raise ValueError("creative needs its placement")
        elif self.kind != "text":
            raise ValueError("image and video only in the creative seat")
        if self.duration_s is not None and self.kind != "video":
            raise ValueError("duration_s is for a video")
        return self


class CreativeIn(Model):
    company: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    kind: Literal["image", "video"]
    brief_md: str = Field(min_length=1, max_length=4000)
    placement: Placement
    overlay: Overlay | None = None
    duration_s: int | None = Field(default=None, ge=1, le=10)
    player: Literal["gpt", "gemini"] | None = None

    @field_validator("duration_s")
    @classmethod
    def _video(cls, v: int | None) -> int | None:
        return v


class NoteIn(Model):
    note: str | None = Field(default=None, max_length=2000)


class DoneIn(Model):
    """The dispatcher's result of one CLI job (the interface file)."""

    ok: bool
    text_md: str | None = Field(default=None, max_length=TEXT_LIMIT)
    findings: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    usage: dict[str, Any] | None = None
    error: (
        Literal[
            "limited", "signed_out", "timeout", "failed", "no_access", "not_ready", "unavailable"
        ]
        | None
    ) = None
    limited_until: datetime | None = None
    status_reason: str | None = Field(default=None, max_length=300)
    models: list[str] | None = Field(default=None, max_length=50)


class LoginStarted(Model):
    method: Literal["device_code", "auth_code"]
    verification_url: str = Field(pattern=r"^https://", max_length=2000)
    user_code: str | None = Field(default=None, max_length=64)


class LoginCode(Model):
    code: str = Field(min_length=1, max_length=512, repr=False)


class SubstituteLogin(BaseModel):
    id: UUID
    connection: str
    method: Literal["device_code", "auth_code"] | None
    verification_url: str | None
    user_code: str | None
    expires_at: datetime
    state: Literal["waiting", "done", "expired", "failed"]
    status_reason: str | None


class Creative(BaseModel):
    id: UUID
    ref: str
    company: str
    kind: Literal["image", "video"]
    brief_md: str
    prompt_md: str
    placement: str
    aspect: str
    duration_s: int | None
    overlay: dict[str, Any] | None
    composed: Any | None
    player: Literal["gpt", "gemini"]
    model: str
    path: Literal["web", "cli", "api"]
    state: Literal["queued", "generating", "review", "accepted", "rejected", "failed"]
    requested_by: Any
    work_ref: str | None
    errand_ref: str | None
    files: list[Any]
    review_md: str | None
    source: dict[str, Any] | None
    ai_generated: bool
    created_at: datetime
    updated_at: datetime
    version: int


# ------------------------------------------------------------------- dates --
def owner_day(now: datetime | None = None, tz: str = OWNER_TZ) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()


def month_key(day: date) -> str:
    y, m, _ = to_jalali(day)
    return f"{y:04d}-{m:02d}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# -------------------------------------------------------------------- seed --
async def seed(tx: Tx, holding_id: UUID) -> int:
    """The three players and their default seats, once (never overwritten)."""
    added = 0
    for player, p in DEFAULT_PLAYERS.items():
        row = await tx.first(
            """INSERT INTO substitutes.players (company_id, player, connection_key, runner, web_account,
                   plan_fa, models, capabilities, price_usd)
               VALUES (:co, :p, :conn, :runner, :web, :plan, CAST(:models AS jsonb),
                       CAST(:caps AS jsonb), :price)
               ON CONFLICT (player) DO NOTHING RETURNING id""",
            co=holding_id,
            p=player,
            conn=p["connection"],
            runner=p["runner"],
            web=p["web"],
            plan=p["plan_fa"],
            models=json.dumps(p["models"]),
            caps=json.dumps(p["capabilities"]),
            price=p["price_usd"],
        )
        if row is None:
            continue
        added += 1
        for i, s in enumerate(DEFAULT_SEATS[player]):
            await tx.exec(
                """INSERT INTO substitutes.seats (company_id, player, seat, via, model, enabled, per_day,
                       per_day_video, position)
                   VALUES (:co, :p, :seat, :via, :model, :en, :pd, :pdv, :pos)
                   ON CONFLICT (player, seat) DO NOTHING""",
                co=holding_id,
                p=player,
                seat=s["seat"],
                via=s["via"],
                model=s["model"],
                en=s["enabled"],
                pd=s["per_day"],
                pdv=s.get("per_day_video"),
                pos=i,
            )
    return added


# ------------------------------------------------------------------ render --
async def _settings(tx: Tx) -> dict[str, Any]:
    raw = await tx.scalar("SELECT substitutes FROM owner.settings WHERE id = 1")
    return {"behind_ratio": 0.4, "creative_default_image": "gpt", **(raw or {})}


async def render_all(tx: Tx, only: str | None = None) -> list[Substitute]:
    today = owner_day()
    mkey = month_key(today)
    players = await tx.all(
        """SELECT p.*, c.id AS connection_id, c.pricing FROM substitutes.players p
           LEFT JOIN llm.connections c ON c.key = p.connection_key
           WHERE CAST(:only AS text) IS NULL OR p.player = :only
           ORDER BY array_position(ARRAY['gpt', 'gemini', 'deepseek'], p.player)""",
        only=only,
    )
    seats = await tx.all("SELECT * FROM substitutes.seats ORDER BY position, seat")
    used = await tx.all(
        """SELECT player, seat, task, count(*) AS n FROM substitutes.calls
           WHERE day = :d AND kind = 'call' AND state IN ('queued', 'running', 'done')
           GROUP BY player, seat, task""",
        d=today,
    )
    used_map = {(u["player"], u["seat"], u["task"]): int(u["n"]) for u in used}
    month = await tx.all(
        """SELECT player, count(*) FILTER (WHERE state <> 'skipped') AS calls,
                  count(*) FILTER (WHERE state = 'skipped') AS skipped,
                  COALESCE(sum(input_tokens), 0) AS inp, COALESCE(sum(output_tokens), 0) AS outp,
                  bool_or(estimated) AS est, COALESCE(sum(equiv_usd), 0) AS usd
           FROM substitutes.calls WHERE month_key = :m AND kind = 'call' GROUP BY player""",
        m=mkey,
    )
    month_map = {m["player"]: m for m in month}
    out: list[Substitute] = []
    for p in players:
        m = month_map.get(p["player"])
        price = Decimal(p["price_usd"])
        equiv = Decimal(m["usd"]) if m else Decimal(0)
        ratio = float(equiv / price) if price > 0 else None
        out.append(
            Substitute(
                player=p["player"],
                connection=p["connection_key"],
                connection_id=p["connection_id"],
                runner=p["runner"],
                login=Login(
                    state=p["login_state"],
                    plan_fa=p["plan_fa"],
                    since=p["login_since"],
                    last_ok_at=p["login_last_ok_at"],
                ),
                status=p["status"],
                limited_until=p["limited_until"],
                status_reason=p["status_reason"],
                models=[ModelRow.model_validate(x) for x in p["models"] or []],
                capabilities=dict(p["capabilities"] or {}),
                web=Web(
                    account=p["web_account"],
                    state=p["web_state"],
                    last_ok_at=p["web_last_ok_at"],
                    recipe_version=p["recipe_version"],
                    last_failure=p["web_last_failure"],
                ),
                seats=[
                    SeatOut(
                        seat=s["seat"],
                        via=s["via"],
                        model=s["model"],
                        enabled=s["enabled"],
                        per_day=s["per_day"],
                        used_today=used_map.get((p["player"], s["seat"], "image"), 0)
                        + used_map.get((p["player"], s["seat"], "text"), 0),
                        per_day_video=s["per_day_video"] if s["seat"] == "creative" else None,
                        used_today_video=used_map.get((p["player"], s["seat"], "video"), 0)
                        if s["seat"] == "creative"
                        else None,
                    )
                    for s in seats
                    if s["player"] == p["player"]
                ],
                month=Month(
                    key=mkey,
                    calls=int(m["calls"]) if m else 0,
                    skipped=int(m["skipped"]) if m else 0,
                    input_tokens=int(m["inp"]) if m else 0,
                    output_tokens=int(m["outp"]) if m else 0,
                    estimated=bool(m["est"]) if m else False,
                    equiv_usd=str(equiv.quantize(Decimal("0.01"))),
                    price_usd=str(price.quantize(Decimal("0.01"))),
                    value_ratio=round(ratio, 3) if ratio is not None else None,
                ),
                version=p["version"],
            )
        )
    return out


# ----------------------------------------------------------------- the guard --
async def guard(tx: Tx, hub: Any, seat: str, text: str) -> str | None:
    """Why this input may not reach a substitute, or None (contract §21.13:
    masked, through the data guard; a public search: nothing internal)."""
    from hq_api.domain import egress as G

    if seat == "quick_search":
        codes = {c.code for c in await hub.companies.all()}
        employees = frozenset(r["code"] for r in await tx.all("SELECT code FROM core.employees"))
        return G.internal_data([text], codes, employees)
    if scrub(text) != text:
        return "personal_or_secret_data"
    for hidden in G._hidden(G.decoded(text)):
        if scrub(hidden) != hidden:
            return "personal_or_secret_data"
    return None


# ------------------------------------------------------------- seat calls --
class SignedInIn(Model):
    """The owner finished a sign-in in their own terminal (prompt 14.1): the
    browser profile (`make <x>-web-login`) or the CLI (`make chatgpt-login`).
    Optimistic: the first job that meets a login page marks it `expired`."""

    player: Player
    via: Literal["cli", "web"]


async def signed_in(tx: Tx, body: SignedInIn) -> dict[str, Any]:
    p = await _player(tx, body.player, lock=True)
    if body.via == "web":
        if p["web_account"] is None:
            raise ApiError(
                422, "validation_failed", fields={"via": "this player has no web profile"}
            )
        # A player that works only on the web (DeepSeek; Gemini since ⟨1.7.2⟩) is
        # ready once its profile is signed in; GPT's state stays its CLI's.
        web_only = p["runner"] != "codex_cli"
        await tx.exec(
            """UPDATE substitutes.players SET web_state = 'signed_in', web_last_ok_at = now(),
                   web_last_failure = NULL,
                   status = CASE WHEN :w AND status = 'off' THEN 'ready' ELSE status END,
                   status_reason = CASE WHEN :w AND status = 'off' THEN NULL ELSE status_reason END,
                   updated_at = now()
               WHERE player = :p""",
            p=body.player,
            w=web_only,
        )
    else:
        if p["runner"] != "codex_cli":  # ⟨1.7.2⟩ the Gemini CLI is gone; DeepSeek has none
            raise ApiError(409, "not_ready", "no CLI sign-in for this player")
        await tx.exec(
            """UPDATE substitutes.players SET login_state = 'signed_in', login_since = now(),
                   login_last_ok_at = now(), status = 'ready', status_reason = NULL, updated_at = now()
               WHERE player = :p""",
            p=body.player,
        )
    row = await _player(tx, body.player)
    return {"player": row["player"], "login": row["login_state"], "web": row["web_state"]}


async def _player(tx: Tx, player: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(
        "SELECT * FROM substitutes.players WHERE player = :p"  # noqa: S608 - constant
        + (" FOR UPDATE" if lock else ""),
        p=player,
    )
    if row is None:
        raise ApiError(409, "not_ready", "the substitute players are not seeded")
    return row


async def holder(
    tx: Tx, seat: str, player: str | None, kind: str = "text"
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(player row, seat row) that takes the call: the named player if it
    holds the seat, else the default holder (an enabled seat first; for an
    image, owner_settings.substitutes.creative_default_image)."""
    rows = await tx.all(
        """SELECT s.*, p.player AS p FROM substitutes.seats s JOIN substitutes.players p ON p.player = s.player
           WHERE s.seat = :seat ORDER BY s.enabled DESC,
                 array_position(ARRAY['gpt', 'gemini', 'deepseek'], s.player)""",
        seat=seat,
    )
    if player is not None:
        rows = [r for r in rows if r["player"] == player]
    elif seat == "creative":
        if kind == "video":
            rows = sorted(rows, key=lambda r: r["player"] != "gemini")
        else:
            default = (await _settings(tx)).get("creative_default_image", "gpt")
            rows = sorted(rows, key=lambda r: (not r["enabled"], r["player"] != default))
    if not rows:
        return None
    s = rows[0]
    return await _player(tx, s["player"]), s


def _skip_reason(p: dict[str, Any], s: dict[str, Any], now: datetime) -> str | None:
    if not s["enabled"]:
        return "off"
    if p["status"] == "limited" and (p["limited_until"] is None or p["limited_until"] > now):
        return "limited"
    if s["via"] == "web":
        if p["web_state"] != "signed_in":
            return "expired" if p["web_state"] == "expired" else "signed_out"
        return None
    if p["login_state"] != "signed_in":
        return "expired" if p["login_state"] == "expired" else "signed_out"
    if p["status"] in ("off", "error"):
        return "off"
    return None


async def seat_call(
    tx: Tx,
    hub: Any,
    who: Principal,
    *,
    seat: str,
    input_md: str,
    company_id: UUID,
    purpose: tuple[str, str] | None = None,
    player: str | None = None,
    task: str = "text",
    checkout: dict[str, Any] | None = None,
    file_ids: list[UUID] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One seat call: `queued` for its runner, or `skipped` with its reason
    (holding_locked, off, signed_out, expired, limited, per_day). The input
    is checked by `guard` first (the caller decides what a refusal means)."""
    now = now or datetime.now(UTC)
    day = owner_day(now)
    found = await holder(tx, seat, player, task)
    lock = await gate.automation_lock(tx)
    reason: str | None
    s_row: dict[str, Any] | None
    if found is None:
        p_name, s_row, reason = player or "gpt", None, "off"
    else:
        p, s_row = found
        p_name = p["player"]
        reason = _skip_reason(p, s_row, now)
    if lock is not None:  # the launch gate first: nothing is called while locked
        reason = gate.REASONS.get(lock, lock)
    if reason is None and s_row is not None:
        cap = s_row["per_day_video"] if task == "video" else s_row["per_day"]
        n = int(
            await tx.scalar(
                """SELECT count(*) FROM substitutes.calls
                   WHERE player = :p AND seat = :s AND day = :d AND kind = 'call' AND task = :t
                     AND state IN ('queued', 'running', 'done')""",
                p=p_name,
                s=seat,
                d=day,
                t=task if task == "video" else ("image" if task == "image" else "text"),
            )
            or 0
        )
        if cap is None or n >= int(cap):
            reason = "per_day"
    via = s_row["via"] if s_row is not None else "cli"
    model = s_row["model"] if s_row is not None else None
    masked = scrub(input_md)
    row = await tx.one(
        """INSERT INTO substitutes.calls (company_id, player, seat, via, task, model, state, state_reason,
               caller_kind, caller_code, purpose_kind, purpose_ref, input_md, input_sha256, checkout,
               file_ids, timeout_s, day, month_key, finished_at)
           VALUES (:co, :p, :seat, :via, :task, :model, :st, :reason, :ck, :cc, :pk, :pr, :inp, :sha,
                   CAST(:checkout AS jsonb), CAST(:files AS uuid[]), :timeout, :day, :mkey,
                   CASE WHEN :st = 'skipped' THEN now() END)
           RETURNING *""",
        co=company_id,
        p=p_name,
        seat=seat,
        via=via,
        task=task,
        model=model,
        st="skipped" if reason else "queued",
        reason=reason,
        ck=who.kind,
        cc=who.code,
        pk=purpose[0] if purpose else None,
        pr=purpose[1] if purpose else None,
        inp=None if reason else masked,
        sha=_sha(masked),
        checkout=json.dumps(checkout) if checkout else None,
        files=[str(f) for f in file_ids or []],
        timeout=CALL_TIMEOUT_S.get(seat, 300),
        day=day,
        mkey=month_key(day),
    )
    holding = await hub.companies.holding()
    await events.emit(
        tx,
        holding.code,
        "substitute.updated",
        p_name,
        {"seat": seat, "call": str(row["id"]), "state": row["state"], "reason": reason},
    )
    return row


def refusal(reason: str) -> ApiError:
    """A skipped call as the tool's refusal (contract §21.13)."""
    if reason in ("limited", "per_day"):
        return ApiError(429, "rate_limited", f"the substitute seat is {reason}")
    if reason in ("holding_locked", "company_locked", "deploy_freeze"):
        return ApiError(423, "company_locked", f"locked: {reason}")
    return ApiError(503, "channel_not_configured", f"the substitute player is {reason}")


def source(call: dict[str, Any]) -> dict[str, Any]:
    at = call["finished_at"] or call["created_at"]
    return {
        "player": call["player"],
        "model": call["model"],
        "connection": DEFAULT_PLAYERS[call["player"]]["connection"],
        "at": at.isoformat(),
    }


# ---------------------------------------------------------- the CLI queue --
async def claim(tx: Tx) -> dict[str, Any]:
    """The dispatcher's next CLI job (one at a time for both players), or none
    (always none while the holding's kill switch is engaged)."""
    lock = await gate.holding_lock(tx)
    if lock is not None:
        return {"job": None, "skipped": gate.REASONS.get(lock, lock)}
    # A job the dispatcher lost (claimed, never answered) ends as failed.
    await tx.exec(
        """UPDATE substitutes.calls SET state = 'failed', state_reason = 'timeout', finished_at = now(),
               input_md = NULL
           WHERE via = 'cli' AND state = 'running'
             AND claimed_at < now() - make_interval(secs => timeout_s + 120)"""
    )
    if await tx.scalar(
        "SELECT 1 FROM substitutes.calls WHERE via = 'cli' AND state = 'running' LIMIT 1"
    ):
        return {"job": None}
    c = await tx.first(
        """SELECT c.*, p.runner FROM substitutes.calls c JOIN substitutes.players p ON p.player = c.player
           WHERE c.via = 'cli' AND c.state = 'queued' AND p.runner IS NOT NULL
           ORDER BY c.created_at LIMIT 1 FOR UPDATE OF c SKIP LOCKED"""
    )
    if c is None:
        return {"job": None}
    await tx.exec(
        "UPDATE substitutes.calls SET state = 'running', claimed_at = now() WHERE id = :id",
        id=c["id"],
    )
    login = None
    if c["kind"] == "login" and c["login_id"] is not None:
        method = await tx.scalar(
            "SELECT method FROM substitutes.logins WHERE id = :id", id=c["login_id"]
        )
        login = {"id": str(c["login_id"]), "method": method or "device_code"}
    return {
        "job": {
            "id": str(c["id"]),
            "kind": c["kind"],
            "player": c["player"],
            "runner": c["runner"],
            "seat": c["seat"],
            "model": c["model"],
            "input_md": c["input_md"],
            "checkout": c["checkout"],
            "login": login,
            "timeout_s": c["timeout_s"],
        }
    }


def equiv_usd(pricing: dict[str, Any] | None, model: str | None, inp: int, out: int) -> Decimal:
    """The API-price equivalent (contract §10 price table); 0 when the
    connection's pricing has no row for the model (the owner fills it)."""
    row = (pricing or {}).get(model or "")
    if not isinstance(row, dict):
        return Decimal(0)
    try:
        i = Decimal(str(row.get("input_per_mtok", row.get("input", 0))))
        o = Decimal(str(row.get("output_per_mtok", row.get("output", 0))))
    except (ArithmeticError, ValueError):
        return Decimal(0)
    return (i * inp + o * out) / Decimal(1_000_000)


async def _ledger(
    tx: Tx, call: dict[str, Any], inp: int, out: int, usd: Decimal, est: bool
) -> None:
    """The ledger row of a finished call (caller 'substitutes'): equivalent
    cost only; it counts against no daily cap or share."""
    conn = await tx.first(
        "SELECT id, provider FROM llm.connections WHERE key = :k",
        k=DEFAULT_PLAYERS[call["player"]]["connection"],
    )
    await tx.exec(
        """INSERT INTO llm.calls (id, started_at, finished_at, company_id, actor_ref, task_class, priority,
               caller, connection_id, provider, model, input_tokens, output_tokens, cost_usd,
               equiv_cost_usd, status, meta)
           VALUES (gen_random_uuid(), COALESCE(:start, now()), now(), :co, :actor, :tc, 3, 'substitutes',
                   :conn, :prov, :model, :inp, :out, 0, :usd, 'ok', CAST(:meta AS jsonb))""",
        start=call["claimed_at"],
        co=call["company_id"],
        actor=call["caller_code"],
        tc=TASK_CLASS.get(call["seat"] or "", "sub_errand"),
        conn=conn["id"] if conn else None,
        prov=conn["provider"] if conn else None,
        model=call["model"],
        inp=inp,
        out=out,
        usd=usd,
        meta=json.dumps(
            {"seat": call["seat"], "substitute_call": str(call["id"]), "estimated": est}
        ),
    )


async def finish(
    tx: Tx, hub: Any, call_id: UUID, body: DoneIn, *, via: str = "cli"
) -> dict[str, Any]:
    """A job's result (idempotent): the call, the player's state, the ledger
    and whatever waits on it (a memo's opinion, a creative)."""
    c = await tx.first(
        "SELECT * FROM substitutes.calls WHERE id = :id AND via = :via FOR UPDATE",
        id=call_id,
        via=via,
    )
    if c is None:
        raise ApiError(404, "not_found")
    if c["state"] in ("done", "failed", "skipped"):
        return c
    p = await _player(tx, c["player"], lock=True)
    reason = (body.status_reason or body.error or "")[:300] or None
    usage = body.usage or {}
    inp = max(int(usage.get("input_tokens") or 0), 0)
    out = max(int(usage.get("output_tokens") or 0), 0)
    est = bool(usage.get("estimated", not usage))
    state = "done" if body.ok else "failed"
    result: dict[str, Any] | None = None
    if body.ok and c["kind"] == "call":
        result = {}
        if body.text_md is not None:
            result["text_md"] = scrub(body.text_md)
        if body.findings is not None:
            result["findings"] = [_finding(f) for f in body.findings[:200]]
        result["source"] = {**source({**c, "finished_at": datetime.now(UTC)})}
    if not body.ok and body.error == "limited":
        state = "skipped"  # the seat is skipped, never moved to Claude
        await tx.exec(
            """UPDATE substitutes.players SET status = 'limited', limited_until = :u,
                   status_reason = 'the subscription quota is used up', updated_at = now()
               WHERE player = :p""",
            u=body.limited_until or datetime.now(UTC) + timedelta(hours=5),
            p=c["player"],
        )
    elif not body.ok and body.error == "unavailable":  # ⟨1.7.2⟩ the Gemini CLI player
        state = "skipped"
        await tx.exec(
            """UPDATE substitutes.players SET status = 'off', status_reason = :r, updated_at = now()
               WHERE player = :p""",
            r=reason,
            p=c["player"],
        )
    elif not body.ok and body.error == "signed_out":
        state = "skipped"
        await tx.exec(
            """UPDATE substitutes.players SET login_state = 'expired', status = 'off',
                   status_reason = 'signed out: the owner signs in again', updated_at = now()
               WHERE player = :p""",
            p=c["player"],
        )
    equiv = equiv_usd(
        await tx.scalar(
            "SELECT pricing FROM llm.connections WHERE key = :k", k=p["connection_key"]
        ),
        c["model"],
        inp,
        out,
    )
    row = await tx.one(
        """UPDATE substitutes.calls SET state = :st, state_reason = :r, result = CAST(:res AS jsonb),
               input_tokens = :inp, output_tokens = :out, estimated = :est, equiv_usd = :usd,
               finished_at = now(), input_md = NULL
           WHERE id = :id RETURNING *""",
        st=state,
        r=reason if state != "done" else None,
        res=json.dumps(result, ensure_ascii=False) if result is not None else None,
        inp=inp,
        out=out,
        est=est,
        usd=equiv,
        id=c["id"],
    )
    if c["kind"] == "call" and state == "done":
        await tx.exec(
            """UPDATE substitutes.players SET login_last_ok_at = now(),
                   status = CASE WHEN status = 'limited' THEN 'ready' ELSE status END,
                   limited_until = NULL, updated_at = now()
               WHERE player = :p""",
            p=c["player"],
        )
        await _ledger(tx, row, inp, out, equiv, est)
    elif c["kind"] == "login":
        await _login_done(tx, c, body)
    elif c["kind"] == "logout" and body.ok:
        await tx.exec(
            """UPDATE substitutes.players SET login_state = 'signed_out', status = 'off', updated_at = now()
               WHERE player = :p""",
            p=c["player"],
        )
    elif c["kind"] == "models" and body.ok and body.models is not None:
        await apply_models(tx, c["player"], body.models, c["model"])
    await _applied(tx, hub, row)
    holding = await hub.companies.holding()
    await events.emit(
        tx,
        holding.code,
        "substitute.updated",
        c["player"],
        {"call": str(c["id"]), "state": state, "reason": reason if state != "done" else None},
    )
    return row


def _finding(f: dict[str, Any]) -> dict[str, Any]:
    sev = str(f.get("severity") or "low")
    return {
        "path": str(f.get("path") or "")[:500],
        "line": int(f["line"]) if str(f.get("line") or "").isdigit() else None,
        "severity": sev if sev in ("low", "medium", "high", "critical") else "low",
        "title_fa": scrub(str(f.get("title_fa") or ""))[:300],
        "detail_md": scrub(str(f.get("detail_md") or ""))[:4000],
        # Verified by the CTO or QC before it reaches a card's risk note.
        "verified": None,
    }


async def _applied(tx: Tx, hub: Any, call: dict[str, Any]) -> None:
    """What waits on a finished call."""
    if call["purpose_kind"] == "memo" and call["seat"] in (
        "advisor_second_opinion",
        "third_opinion",
    ):
        from hq_api.domain import advisor

        await advisor.apply_opinion(tx, str(call["purpose_ref"]), str(call["seat"]), call)
    elif call["purpose_kind"] == "claim" and call["seat"] == "overseer_cross_check":
        await apply_cross_check(tx, hub, call)
    elif call["caller_kind"] == "agent" and call["purpose_kind"] is None and call["kind"] == "call":
        await deliver_to_agent(tx, hub, call)


REPLY_TOKENS = 20_000


async def deliver_to_agent(tx: Tx, hub: Any, call: dict[str, Any]) -> None:
    """An agent's call that answered after substitute.call said `queued`: the
    labelled answer (or why it was skipped) goes back to the caller as a work
    item (work is a record; the caller sleeps until it arrives)."""
    from hq_api.domain import work as W

    if call["delivered_at"] is not None:
        return
    emp = await tx.first(
        """SELECT e.code, e.company_id, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE e.code = :c AND e.status = 'active'""",
        c=call["caller_code"],
    )
    if emp is None:
        return
    res = call["result"] or {}
    if call["state"] == "done":
        answer = res.get("text_md") or json.dumps(res.get("findings") or [], ensure_ascii=False)
        body = (
            f"The substitute player's answer to your substitute.call ({call['seat']}, call "
            f"{call['id']}). Source: {json.dumps(source(call))}. It is never evidence: check it, "
            "use it or drop it; you answer for the result.\n\n" + str(answer)[:6000]
        )
    else:
        body = (
            f"Your substitute.call ({call['seat']}, call {call['id']}) was {call['state']}: "
            f"{call['state_reason'] or 'no answer'}. Carry on with your own model."
        )
    w = await W.create(
        tx,
        SERVICE,
        company_id=emp["company_id"],
        company_code=emp["company"],
        title=f"پاسخ بازیکن ذخیره ({call['seat']})"[:300],
        brief=body,
        kind="one_off",
        priority="P3",
        assignee_code=emp["code"],
        budget=W.BudgetIn(tokens=REPLY_TOKENS),
    )
    await tx.exec(
        "UPDATE substitutes.calls SET delivered_at = now(), reply_work_id = :w WHERE id = :id",
        w=w["id"],
        id=call["id"],
    )


async def ask_models(tx: Tx, hub: Any) -> int:
    """Once a day: one `models` job per signed-in CLI player (what its CLI
    offers under the subscription), unless one waits already."""
    holding = await hub.companies.holding()
    day = owner_day()
    n = 0
    for p in await tx.all(
        """SELECT player, runner, models FROM substitutes.players
           WHERE runner IS NOT NULL AND login_state = 'signed_in'"""
    ):
        if await tx.scalar(
            """SELECT 1 FROM substitutes.calls WHERE player = :p AND kind = 'models'
               AND state IN ('queued', 'running')""",
            p=p["player"],
        ):
            continue
        # Codex lists what the account offers; Gemini CLI has no listing, so
        # each of its models is probed by a job of its own (`model` named).
        probes: list[str | None] = (
            [str(m["id"]) for m in p["models"] or []] if p["runner"] == "gemini_cli" else [None]
        )
        for model in probes:
            await tx.exec(
                """INSERT INTO substitutes.calls (company_id, player, kind, via, state, caller_kind,
                       caller_code, model, timeout_s, day, month_key)
                   VALUES (:co, :p, 'models', 'cli', 'queued', 'service', 'substitutes', :m, 120, :day,
                           :mkey)""",
                co=holding.id,
                p=p["player"],
                m=model,
                day=day,
                mkey=month_key(day),
            )
            n += 1
    return n


async def apply_models(tx: Tx, player: str, offered: list[str], probed: str | None = None) -> None:
    """What the CLI offers under the subscription: a model it does not offer
    is `available: false`, and a seat on it moves to the nearest available
    model of the same tier (the morning report says so). A probe of one
    model (`probed`, Gemini CLI) decides that model only."""
    p = await _player(tx, player, lock=True)
    models = [
        dict(m, available=m["id"] in offered) if probed is None or m["id"] == probed else dict(m)
        for m in p["models"] or []
    ]
    await tx.exec(
        """UPDATE substitutes.players SET models = CAST(:m AS jsonb), models_checked_at = now(),
               updated_at = now() WHERE player = :p""",
        m=json.dumps(models),
        p=player,
    )
    by_id = {m["id"]: m for m in models}
    for s in await tx.all("SELECT * FROM substitutes.seats WHERE player = :p", p=player):
        cur = by_id.get(s["model"])
        if cur is None or cur["available"]:
            continue
        alt = next(
            (m["id"] for m in models if m["available"] and m["tier"] == cur["tier"]),
            None,
        )
        if alt is not None:
            await tx.exec(
                "UPDATE substitutes.seats SET model = :m, updated_at = now() WHERE id = :id",
                m=alt,
                id=s["id"],
            )


# --------------------------------------------------------------- sign-ins --
async def start_login(
    tx: Tx, hub: Any, who: Principal, connection: dict[str, Any]
) -> dict[str, Any]:
    """A CLI's own headless sign-in, started from the app (after its seal)."""
    p = await tx.first(
        "SELECT * FROM substitutes.players WHERE connection_key = :k FOR UPDATE",
        k=connection["key"],
    )
    if p is None or p["runner"] is None:
        raise ApiError(409, "not_ready", "this connection has no CLI to sign in (web only)")
    if not hub.settings.substitutes_runner:
        raise ApiError(
            409,
            "not_ready",
            f"the substitutes runner is off: sign in from the terminal (make {_make(p['player'])})",
        )
    lock = await gate.holding_lock(tx)
    if lock is not None:
        raise ApiError(423, "company_locked", "the holding's kill switch is engaged")
    holding = await hub.companies.holding()
    login = await tx.one(
        """INSERT INTO substitutes.logins (company_id, player, connection_key, expires_at)
           VALUES (:co, :p, :k, now() + make_interval(mins => :m)) RETURNING *""",
        co=holding.id,
        p=p["player"],
        k=connection["key"],
        m=LOGIN_MINUTES,
    )
    day = owner_day()
    call = await tx.one(
        """INSERT INTO substitutes.calls (company_id, player, kind, via, state, caller_kind, caller_code,
               login_id, timeout_s, day, month_key)
           VALUES (:co, :p, 'login', 'cli', 'queued', :ck, :cc, :login, :t, :day, :mkey) RETURNING *""",
        co=holding.id,
        p=p["player"],
        ck=who.kind,
        cc=who.code,
        login=login["id"],
        t=LOGIN_MINUTES * 60,
        day=day,
        mkey=month_key(day),
    )
    login = await tx.one(
        "UPDATE substitutes.logins SET call_id = :c WHERE id = :id RETURNING *",
        c=call["id"],
        id=login["id"],
    )
    await tx.exec(
        "UPDATE substitutes.players SET login_state = 'signing_in', updated_at = now() WHERE id = :id",
        id=p["id"],
    )
    return login


def _make(player: str) -> str:
    return {"gpt": "chatgpt-login", "gemini": "gemini-web-login"}.get(player, "deepseek-web-login")


def render_login(r: dict[str, Any]) -> SubstituteLogin:
    state = r["state"]
    if state == "waiting" and r["expires_at"] <= datetime.now(UTC):
        state = "expired"
    return SubstituteLogin(
        id=r["id"],
        connection=r["connection_key"],
        method=r["method"],
        verification_url=r["verification_url"],
        user_code=r["user_code"],
        expires_at=r["expires_at"],
        state=state,
        status_reason=r["status_reason"],
    )


async def login_started(tx: Tx, login_id: UUID, body: LoginStarted) -> dict[str, Any]:
    row = await tx.first(
        """UPDATE substitutes.logins SET method = :m, verification_url = :u, user_code = :c, updated_at = now()
           WHERE id = :id AND state = 'waiting' RETURNING *""",
        m=body.method,
        u=body.verification_url,
        c=body.user_code,
        id=login_id,
    )
    if row is None:
        raise ApiError(409, "not_ready", "the sign-in is not waiting")
    return row


async def give_code(tx: Tx, login: dict[str, Any], code: str) -> dict[str, Any]:
    """The owner's pasted code (write-only), auth_code sign-ins only, while
    waiting and inside its 10 minutes."""
    if login["method"] != "auth_code":
        raise ApiError(409, "not_ready", "this sign-in takes no code")
    if login["state"] != "waiting" or login["expires_at"] <= datetime.now(UTC):
        raise ApiError(409, "not_ready", "the sign-in is over (at most 10 minutes)")
    row: dict[str, Any] = await tx.one(
        """UPDATE substitutes.logins SET code = :c, code_given_at = now(), updated_at = now()
           WHERE id = :id RETURNING *""",
        c=code,
        id=login["id"],
    )
    return row


async def take_code(tx: Tx, login_id: UUID) -> dict[str, Any]:
    """The runner's one read of the owner's code; it is gone afterwards."""
    row = await tx.first("SELECT * FROM substitutes.logins WHERE id = :id FOR UPDATE", id=login_id)
    if row is None:
        raise ApiError(404, "not_found")
    if row["state"] != "waiting" or row["expires_at"] <= datetime.now(UTC):
        return {"code": None, "state": "expired" if row["state"] == "waiting" else row["state"]}
    code = row["code"]
    if code is not None:
        await tx.exec(
            "UPDATE substitutes.logins SET code = NULL, updated_at = now() WHERE id = :id",
            id=login_id,
        )
    return {"code": code, "state": "waiting"}


async def _login_done(tx: Tx, call: dict[str, Any], body: DoneIn) -> None:
    ok = body.ok
    await tx.exec(
        """UPDATE substitutes.logins SET state = :st, status_reason = :r, code = NULL, updated_at = now()
           WHERE id = :id""",
        st="done" if ok else "failed",
        r=None if ok else (body.status_reason or body.error or "failed")[:300],
        id=call["login_id"],
    )
    if ok:
        await tx.exec(
            """UPDATE substitutes.players SET login_state = 'signed_in', login_since = now(),
                   login_last_ok_at = now(), status = 'ready', status_reason = NULL, updated_at = now()
               WHERE player = :p""",
            p=call["player"],
        )
    else:
        await tx.exec(
            """UPDATE substitutes.players SET login_state = 'signed_out', status = 'off',
                   status_reason = :r, updated_at = now() WHERE player = :p""",
            r=(body.status_reason or "the sign-in did not finish")[:300],
            p=call["player"],
        )


async def logout(tx: Tx, hub: Any, who: Principal, connection: dict[str, Any]) -> dict[str, Any]:
    p = await tx.first(
        "SELECT * FROM substitutes.players WHERE connection_key = :k FOR UPDATE",
        k=connection["key"],
    )
    if p is None or p["runner"] is None:
        raise ApiError(409, "not_ready", "this connection has no CLI sign-in")
    day = owner_day()
    holding = await hub.companies.holding()
    # The runner removes the stored sign-in on its next pass (nothing else
    # ever reads it); the player is signed out at once.
    await tx.exec(
        """INSERT INTO substitutes.calls (company_id, player, kind, via, state, caller_kind, caller_code,
               timeout_s, day, month_key)
           VALUES (:co, :p, 'logout', 'cli', 'queued', :ck, :cc, 120, :day, :mkey)""",
        co=holding.id,
        p=p["player"],
        ck=who.kind,
        cc=who.code,
        day=day,
        mkey=month_key(day),
    )
    row: dict[str, Any] = await tx.one(
        """UPDATE substitutes.players SET login_state = 'signed_out', status = 'off',
               status_reason = 'signed out by the owner', updated_at = now()
           WHERE id = :id RETURNING *""",
        id=p["id"],
    )
    return row


async def web_logout(tx: Tx, player: str) -> dict[str, Any]:
    """The signed-in browser profile is wiped (by egress, on the worker's next
    pass); the player's web seats are skipped from now on."""
    row: dict[str, Any] = await tx.one(
        """UPDATE substitutes.players SET web_state = 'signed_out', web_last_failure = 'wipe requested',
               updated_at = now() WHERE player = :p RETURNING *""",
        p=player,
    )
    return row


# -------------------------------------------------------------------- seats --
async def put_seats(tx: Tx, player: str, seats: list[SeatIn], version: int) -> None:
    p = await _player(tx, player, lock=True)
    if p["version"] != version:
        raise ApiError(409, "version_conflict")
    names = [s.seat for s in seats]
    if len(set(names)) != len(names):
        raise ApiError(422, "validation_failed", fields={"seats": "each seat once"})
    models = {m["id"] for m in p["models"] or []}
    for s in seats:
        if s.model not in models:
            raise ApiError(
                422, "validation_failed", fields={s.seat: f"{s.model} is not one of its models"}
            )
        if (s.seat == "creative" or player == "deepseek") and s.via != "web":
            raise ApiError(422, "validation_failed", fields={s.seat: "this seat runs via web"})
        if s.via == "cli" and p["runner"] is None:
            raise ApiError(422, "validation_failed", fields={s.seat: "this player has no CLI"})
    holding_id = p["company_id"]
    for i, s in enumerate(seats):
        await tx.exec(
            """INSERT INTO substitutes.seats (company_id, player, seat, via, model, enabled, per_day,
                   per_day_video, position)
               VALUES (:co, :p, :seat, :via, :model, :en, :pd, :pdv, :pos)
               ON CONFLICT (player, seat) DO UPDATE SET via = EXCLUDED.via, model = EXCLUDED.model,
                   enabled = EXCLUDED.enabled, per_day = EXCLUDED.per_day,
                   per_day_video = EXCLUDED.per_day_video, position = EXCLUDED.position, updated_at = now()""",
            co=holding_id,
            p=player,
            seat=s.seat,
            via=s.via,
            model=s.model,
            en=s.enabled,
            pd=s.per_day,
            pdv=s.per_day_video if s.seat == "creative" else None,
            pos=i,
        )
    # A seat left out of the list is switched off (rows are never deleted).
    await tx.exec(
        """UPDATE substitutes.seats SET enabled = false, updated_at = now()
           WHERE player = :p AND NOT (seat = ANY(:names))""",
        p=player,
        names=names,
    )
    await tx.exec("UPDATE substitutes.players SET updated_at = now() WHERE id = :id", id=p["id"])


# ---------------------------------------------------------------- creatives --
CREATIVE_SQL = """
    SELECT r.*, c.code AS company, w.ref AS work_ref FROM substitutes.creatives r
    JOIN core.companies c ON c.id = r.company_id
    LEFT JOIN work.work w ON w.id = r.work_id
"""
NO_TEXT = (
    "Do not put any text, letters, numbers, logos or watermarks in the image; leave clean space "
    "for text the hub adds later."
)


def template_prompt(brief: str, placement: str, kind: str, duration: int | None) -> str:
    """The owner's own creative: the hub's prompt from the brief (rules
    first); an agent's creative carries the prompt its Claude agent wrote."""
    aspect = ASPECT[placement]
    what = f"A short video of at most {duration or 10} seconds" if kind == "video" else "An image"
    return f"{what} for an ad ({placement}, aspect {aspect}): {scrub(brief)[:3000]}\n{NO_TEXT}"


async def create_creative(
    tx: Tx,
    hub: Any,
    who: Principal,
    *,
    company_id: UUID,
    kind: str,
    brief_md: str,
    prompt_md: str,
    placement: str,
    overlay: Overlay | None,
    duration_s: int | None,
    player: str | None,
    work_id: UUID | None = None,
) -> dict[str, Any]:
    if kind == "video" and player == "gpt":
        raise ApiError(422, "validation_failed", fields={"player": "videos are Gemini's"})
    prompt = prompt_md if NO_TEXT in prompt_md else f"{prompt_md.rstrip()}\n{NO_TEXT}"
    found = await holder(tx, "creative", player, kind)
    p_name = found[0]["player"] if found else (player or "gpt")
    model = found[1]["model"] if found else DEFAULT_PLAYERS[p_name]["models"][0]["id"]
    row = await tx.one(
        """INSERT INTO substitutes.creatives (company_id, kind, brief_md, prompt_md, placement, aspect,
               duration_s, overlay, player, model, path, requested_by_kind, requested_by_code, work_id)
           VALUES (:co, :kind, :brief, :prompt, :pl, :asp, :dur, CAST(:ov AS jsonb), :p, :m, 'web',
                   :rk, :rc, :w)
           RETURNING *""",
        co=company_id,
        kind=kind,
        brief=scrub(brief_md),
        prompt=scrub(prompt)[:8000],
        pl=placement,
        asp=ASPECT[placement],
        dur=duration_s if kind == "video" else None,
        ov=overlay.model_dump_json() if overlay else None,
        p=p_name,
        m=model,
        rk=who.kind,
        rc=who.code,
        w=work_id,
    )
    holding = await hub.companies.holding()
    call = await seat_call(
        tx,
        hub,
        who,
        seat="creative",
        input_md=prompt,
        company_id=company_id,
        purpose=("creative", row["ref"]),
        player=p_name,
        task=kind,
    )
    state = "queued" if call["state"] == "queued" else "failed"
    row = await tx.one(
        """UPDATE substitutes.creatives SET call_id = :c, state = :st,
               review_md = CASE WHEN :st = 'failed' THEN :why ELSE review_md END, updated_at = now()
           WHERE id = :id RETURNING *""",
        c=call["id"],
        st=state,
        why=f"not made: the player is {call['state_reason']}",
        id=row["id"],
    )
    await events.emit(
        tx,
        holding.code,
        "creative.updated",
        row["ref"],
        {"state": row["state"], "company": await hub.companies.code_of(company_id)},
    )
    return row


async def decide_creative(
    tx: Tx, hub: Any, who: Principal, ref: str, accept: bool, note: str | None
) -> dict[str, Any]:
    r = await tx.first(CREATIVE_SQL + " WHERE r.ref = :ref FOR UPDATE OF r", ref=ref)
    if r is None:
        raise ApiError(404, "not_found")
    if r["state"] != "review":
        raise ApiError(409, "version_conflict", f"{ref} is {r['state']}")
    row: dict[str, Any] = await tx.one(
        """UPDATE substitutes.creatives SET state = :st, owner_note = :n, updated_at = now()
           WHERE id = :id RETURNING *""",
        st="accepted" if accept else "rejected",
        n=note,
        id=r["id"],
    )
    # Accepting is not publishing: a post or a story anywhere is an external
    # act and needs its own decision card (A3), as always.
    await audit.record(
        tx,
        who,
        company_id=r["company_id"],
        action="creative.accept" if accept else "creative.reject",
        action_class="A1",
        target_kind="creative",
        target_ref=ref,
        summary=(note or "")[:200],
    )
    holding = await hub.companies.holding()
    await events.emit(
        tx, holding.code, "creative.updated", ref, {"state": row["state"], "company": r["company"]}
    )
    return row


# ---------------------------------------------------------- morning report --
async def report_lines(tx: Tx) -> list[str]:
    """One line per player for the morning report («ChatGPT: معادل $X از $20
    این ماه»), and a seat that moved to another model."""
    names = {"gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}
    lines = []
    for s in await render_all(tx):
        if s.player == "deepseek":
            lines.append(f"{names[s.player]}: {s.month.calls} فراخوانی این ماه (رایگان)")
        else:
            lines.append(
                f"{names[s.player]}: معادل ${s.month.equiv_usd} از ${s.month.price_usd} این ماه"
            )
        gone = [m.label for m in s.models if not m.available]
        if gone:
            lines.append(f"{names[s.player]}: مدل‌های در دسترس نیست: {'، '.join(gone)}")
    return lines


async def behind_check(tx: Tx, hub: Any, now: datetime | None = None) -> int:
    """On the 15th of the Jalali month, a signed-in paid player under
    owner_settings.substitutes.behind_ratio gets one `report` notification
    suggesting seats to widen; nothing widens by itself."""
    day = owner_day(now)
    if to_jalali(day)[2] != 15:
        return 0
    ratio = float((await _settings(tx)).get("behind_ratio", 0.4))
    holding = await hub.companies.holding()
    sent = 0
    for s in await render_all(tx):
        if (
            s.login.state != "signed_in"
            or s.month.value_ratio is None
            or Decimal(s.month.price_usd) <= 0
        ):
            continue
        # Without the price table (§10) the equivalent is unknown, not zero.
        if not await tx.scalar(
            "SELECT pricing <> '{}'::jsonb FROM llm.connections WHERE key = :k", k=s.connection
        ):
            continue
        if s.month.value_ratio >= ratio:
            continue
        key = f"substitute-behind:{s.player}:{s.month.key}"
        if await tx.scalar(
            "SELECT 1 FROM notify.notifications WHERE link_kind = 'substitute' AND link_ref = :k",
            k=key,
        ):
            continue
        closed = [x.seat for x in s.seats if not x.enabled]
        await notify.raise_notification(
            tx,
            company_id=holding.id,
            company_code=holding.code,
            level="report",
            title_fa=f"بازیکن ذخیره {s.player}: مصرف این ماه عقب است",
            body_fa=(
                f"معادل ${s.month.equiv_usd} از ${s.month.price_usd} (نسبت {s.month.value_ratio}). "
                + (f"جایگاه‌هایی که میشود باز کرد: {', '.join(closed)}" if closed else "")
            )[:500],
            link_kind="substitute",
            link_ref=key,
        )
        sent += 1
    return sent


# -------------------------------------------------------------- the web path --
async def web_jobs(hub: Any, egress: Any, now: datetime | None = None) -> dict[str, Any]:
    """The worker's pass over queued web calls (one per player at a time, at
    least 60 s apart). Nothing while the holding's kill switch is engaged."""
    now = now or datetime.now(UTC)
    # The owner's sealed web sign-out: egress wipes the profile (local, no
    # outside call, so it runs while the holding is locked too).
    async with hub.db.tx(await hub.companies.ids()) as tx:
        wipes = await tx.all(
            """SELECT player, web_account FROM substitutes.players
               WHERE web_state = 'signed_out' AND web_last_failure = 'wipe requested'"""
        )
    wiped = 0
    for w in wipes:
        answer = await egress.web_logout(account=w["web_account"])
        if answer.get("ok"):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await tx.exec(
                    """UPDATE substitutes.players SET web_last_failure = NULL, updated_at = now()
                       WHERE player = :p AND web_last_failure = 'wipe requested'""",
                    p=w["player"],
                )
            wiped += 1
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lock = await gate.holding_lock(tx)
        if lock is not None:
            return gate.skipped(lock, ran=0, wiped=wiped)
        picked = []
        for player in PLAYERS:
            p = await tx.first(
                "SELECT * FROM substitutes.players WHERE player = :p FOR UPDATE SKIP LOCKED",
                p=player,
            )
            if p is None or (p["web_last_job_at"] and now - p["web_last_job_at"] < WEB_PACE):
                continue
            if await tx.scalar(
                "SELECT 1 FROM substitutes.calls WHERE player = :p AND via = 'web' AND state = 'running'",
                p=player,
            ):
                continue
            c = await tx.first(
                """SELECT * FROM substitutes.calls WHERE player = :p AND via = 'web' AND state = 'queued'
                   ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED""",
                p=player,
            )
            if c is None:
                continue
            if p["web_state"] != "signed_in":
                await _skip_web(
                    tx, hub, c, "expired" if p["web_state"] == "expired" else "signed_out"
                )
                continue
            await tx.exec(
                "UPDATE substitutes.calls SET state = 'running', claimed_at = now() WHERE id = :id",
                id=c["id"],
            )
            await tx.exec(
                "UPDATE substitutes.players SET web_last_job_at = :t WHERE id = :id",
                t=now,
                id=p["id"],
            )
            picked.append((dict(c), p["web_account"]))
    ran = 0
    for c, account in picked:
        answer = await egress.web(
            account=account, task=c["task"], prompt=c["input_md"] or "", timeout_s=c["timeout_s"]
        )
        await apply_web(hub, c, account, answer)
        ran += 1
    return {"ran": ran, "wiped": wiped}


async def _skip_web(tx: Tx, hub: Any, c: dict[str, Any], reason: str) -> None:
    await tx.exec(
        """UPDATE substitutes.calls SET state = 'skipped', state_reason = :r, finished_at = now(), input_md = NULL
           WHERE id = :id""",
        r=reason,
        id=c["id"],
    )
    if c["purpose_kind"] == "creative":
        await tx.exec(
            """UPDATE substitutes.creatives SET state = 'failed', review_md = :why, updated_at = now()
               WHERE ref = :ref""",
            why=f"not made: the browser profile is {reason}",
            ref=c["purpose_ref"],
        )


async def apply_web(hub: Any, c: dict[str, Any], account: str, answer: dict[str, Any]) -> None:
    """One web job's answer from egress (the interface file)."""
    from hq_api.domain import creative_overlay

    ok = bool(answer.get("ok"))
    error = str(answer.get("error") or "")
    file_bytes: bytes | None = None
    stored: tuple[UUID, UUID | None] | None = None
    if ok and isinstance(answer.get("file"), dict):
        import base64

        try:
            file_bytes = base64.b64decode(str(answer["file"].get("b64") or ""), validate=True)
        except ValueError:
            ok, error = False, "recipe_failed"
    creative = None
    if ok and file_bytes is not None and c["purpose_kind"] == "creative":
        async with hub.db.tx(await hub.companies.ids()) as tx:
            creative = await tx.first(CREATIVE_SQL + " WHERE r.ref = :ref", ref=c["purpose_ref"])
        if creative is not None:
            try:
                stored = await creative_overlay.store_result(
                    hub, creative, file_bytes, str(answer["file"].get("name") or "result")
                )
            except creative_overlay.Refused as exc:
                ok, error = False, f"refused: {exc}"[:120]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        p = await _player(tx, c["player"], lock=True)
        if ok:
            await tx.exec(
                """UPDATE substitutes.players SET web_last_ok_at = now(), web_last_failure = NULL,
                       recipe_version = COALESCE(:v, recipe_version), updated_at = now() WHERE id = :id""",
                v=str(answer.get("recipe_version") or "")[:40] or None,
                id=p["id"],
            )
            body = DoneIn(
                ok=True,
                text_md=answer.get("text_md"),
                usage={
                    "input_tokens": len(c["input_md"] or "") // 4,
                    "output_tokens": len(str(answer.get("text_md") or "")) // 4,
                    "estimated": True,
                },
            )
            await finish(tx, hub, c["id"], body, via="web")
            if stored is not None and creative is not None:
                original, composed = stored
                await tx.exec(
                    """UPDATE substitutes.creatives SET state = 'review', file_ids = ARRAY[CAST(:o AS uuid)],
                           composed_file_id = :c, source = CAST(:s AS jsonb), updated_at = now()
                       WHERE id = :id""",
                    o=str(original),
                    c=composed,
                    s=json.dumps(source({**c, "finished_at": datetime.now(UTC)})),
                    id=creative["id"],
                )
                holding = await hub.companies.holding()
                await events.emit(
                    tx, holding.code, "creative.updated", creative["ref"], {"state": "review"}
                )
            return
        await tx.exec(
            "UPDATE substitutes.players SET web_last_failure = :f, updated_at = now() WHERE id = :id",
            f=(f"{error}: {answer.get('step') or ''}".strip(": "))[:300],
            id=p["id"],
        )
        if error == "expired":
            await web_expired(tx, hub, p)
            await _skip_web(tx, hub, c, "expired")
            # Its other waiting web calls are skipped too (never sent elsewhere).
            for other in await tx.all(
                """SELECT * FROM substitutes.calls WHERE player = :p AND via = 'web'
                   AND state = 'queued' FOR UPDATE SKIP LOCKED""",
                p=c["player"],
            ):
                await _skip_web(tx, hub, other, "expired")
            return
        if error == "off":
            await _skip_web(tx, hub, c, "off")
            return
        await tx.exec(
            """UPDATE substitutes.calls SET state = 'failed', state_reason = :r, finished_at = now(),
                   input_md = NULL WHERE id = :id""",
            r=error[:300] or "failed",
            id=c["id"],
        )
        if c["purpose_kind"] == "creative":
            await tx.exec(
                """UPDATE substitutes.creatives SET state = 'failed', review_md = :why, updated_at = now()
                   WHERE ref = :ref""",
                why=f"not made: {error or 'failed'}",
                ref=c["purpose_ref"],
            )
        if error == "recipe_failed":
            await recipe_fallback(tx, hub, c, account, answer)


async def web_expired(tx: Tx, hub: Any, p: dict[str, Any]) -> None:
    """A signed-out or expired profile: its seats are skipped from now on and
    the owner gets ONE `report` notification to sign in again (never an
    automatic sign-in)."""
    if p["web_state"] == "expired":
        return
    await tx.exec(
        "UPDATE substitutes.players SET web_state = 'expired', updated_at = now() WHERE id = :id",
        id=p["id"],
    )
    holding = await hub.companies.holding()
    await notify.raise_notification(
        tx,
        company_id=holding.id,
        company_code=holding.code,
        level="report",
        title_fa=f"ورود مرورگر {p['web_account']} منقضی شده",
        body_fa=f"جایگاه‌های وب این بازیکن رد میشوند تا مالک دوباره وارد شود: make {p['web_account']}-login",
        link_kind="substitute",
        link_ref=p["player"],
    )


async def recipe_fallback(
    tx: Tx, hub: Any, c: dict[str, Any], account: str, answer: dict[str, Any]
) -> dict[str, Any] | None:
    """A recipe broken by a site change: ONE Claude run finishes the same job
    with web.browse on that account (screenshots; never a secret) and writes
    the recipe fix as a reviewed change. It goes to the hub's platform SRE;
    with nobody in that seat there is no fallback (the call stays failed)."""
    from hq_api.domain import work as W

    sre = await tx.first(
        """SELECT e.code, e.company_id FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE c.kind = 'holding' AND e.role = 'hub_platform_sre' AND e.status = 'active' LIMIT 1"""
    )
    if sre is None:
        return None
    holding = await hub.companies.holding()
    return await W.create(
        tx,
        SERVICE,
        company_id=holding.id,
        company_code=holding.code,
        title=f"دستور مرورگر {account} شکست: کار را تمام کن و اصلاح را پیشنهاد بده"[:300],
        brief=(
            f"The reviewed recipe infra/egress/recipes/{account}.yaml failed at step "
            f"{str(answer.get('step') or '?')[:80]} (the site changed). Finish the same job with "
            f"web.browse on the service account {account} (screenshots only; never read or copy a "
            "cookie or a secret), then propose the recipe fix as a reviewed change (a work note with "
            "the new steps). The job (masked prompt):\n" + (c["input_md"] or "")[:4000]
        ),
        kind="one_off",
        priority="P3",
        assignee_code=sre["code"],
    )


# ------------------------------------------------------------- code review --
async def queue_code_review(
    tx: Tx,
    hub: Any,
    who: Principal,
    *,
    company_id: UUID,
    repo: str,
    head_sha: str,
    diff_md: str,
    purpose: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """A second review of a change (a deploy card's PR, a founding's audit, a
    workshop diff): never approves or blocks; its findings wait for the CTO's
    or QC's check before any of them reaches a card's risk note."""
    prompt = (
        "Review this change as a second reviewer. The repository is your read-only working "
        "directory at the commit under review. Answer with ONE JSON object: "
        '{"findings": [{"path", "line", "severity": "low|medium|high|critical", "title_fa", '
        '"detail_md"}]}.\n\n' + diff_md[:150_000]
    )
    return await seat_call(
        tx,
        hub,
        who,
        seat="code_review",
        input_md=prompt,
        company_id=company_id,
        purpose=purpose,
        checkout={"repo": repo, "head_sha": head_sha},
    )


def parse_findings(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return []
    rows = raw.get("findings") if isinstance(raw, dict) else None
    return (
        [_finding(f) for f in rows[:200] if isinstance(f, dict)] if isinstance(rows, list) else []
    )


def second_review_of(c: dict[str, Any] | None) -> dict[str, Any] | None:
    """`deploy.second_review` of a card's latest code_review call (pure; the
    card's payload never changes, so the card reads it from the call)."""
    if c is None or c.get("state") != "done":
        return None
    res = c.get("result") or {}
    if isinstance(res, str):
        res = json.loads(res)
    findings = res.get("findings") or parse_findings(str(res.get("text_md") or ""))
    verified = sum(1 for f in findings if f.get("verified") is True)
    return {"player": c["player"], "model": c["model"], "findings": findings, "verified": verified}


async def second_review(tx: Tx, decision_ref: str) -> dict[str, Any] | None:
    """`deploy.second_review` as the card shows it (contract §21.13)."""
    c = await tx.first(
        """SELECT * FROM substitutes.calls WHERE purpose_kind = 'decision' AND purpose_ref = :r
             AND seat = 'code_review' ORDER BY created_at DESC LIMIT 1""",
        r=decision_ref,
    )
    return second_review_of(c)


def deploy_diff_md(diff: dict[str, Any]) -> str:
    """A deploy card's diff (prompt 12 §7, already masked) as the review's text."""
    out = [
        f"base {diff.get('base_sha')} -> head {diff.get('head_sha')}: {diff.get('total_files')} files, "
        f"+{diff.get('total_additions')} -{diff.get('total_deletions')}"
        + (" (truncated)" if diff.get("truncated") else "")
    ]
    for f in diff.get("files") or []:
        out.append(f"diff --git a/{f.get('path')} b/{f.get('path')} ({f.get('status')})")
        if f.get("binary"):
            out.append("(binary file, no patch)")
        elif f.get("patch") is None:
            out.append("(patch left out: the card's size bound)")
        else:
            out.append(str(f["patch"]))
    return "\n".join(out)


async def review_deploy(tx: Tx, hub: Any, d: dict[str, Any]) -> dict[str, Any] | None:
    """Prompt 12 §7 x §9.1: a new deploy card with the real diff gets its
    second code review (seat code_review), by code. It never approves or
    blocks; nothing reaches the card's risk note unverified. None when the
    card has no diff (no_access, too large): there is nothing to review."""
    payload = d.get("payload") or {}
    diff = payload.get("diff")
    if d.get("kind") != "deploy" or not isinstance(diff, dict) or not diff.get("files"):
        return None
    return await queue_code_review(
        tx,
        hub,
        DEPLOY_REVIEW,
        company_id=d["company_id"],
        repo=str(payload["repo"]),
        head_sha=str(payload["head_sha"]),
        diff_md=deploy_diff_md(diff),
        purpose=("decision", str(d["ref"])),
    )


# ------------------------------------------------------------ cross-check --
CROSS_CHECK = Principal(kind="service", code="claims-rules", role="service")
DEPLOY_REVIEW = Principal(kind="service", code="deploy-review", role="service")
CROSS_VERDICTS = ("confirmed", "refuted", "unverifiable")
CROSS_PROMPT = (
    "Check this one claim as a second, independent checker. Decide only from what is given here "
    "and what you know for sure; say unverifiable otherwise. Answer with ONE JSON object: "
    '{{"verdict": "confirmed|refuted|unverifiable", "reason_md": "<= 600 characters"}}.\n\n'
    "Claim: {claim}\nIn the deliverable: {title}\nIts summary: {summary}"
)
RETURN_TOKENS = 40_000


async def queue_cross_check(tx: Tx, hub: Any, claim: dict[str, Any]) -> dict[str, Any] | None:
    """A sampled claim's second check (seat overseer_cross_check, contract
    §21.13), queued by code when the claim is recorded in a sample protocol
    (`protocol` set): the masked claim and its deliverable's title and summary,
    never the checker's verdict or notes. Once per deliverable and claim text,
    so a claim the overseer decides again is not checked again. None when the
    input may not reach a substitute (personal data, a secret)."""
    dl = await tx.first(
        "SELECT title, summary FROM cartable.deliverables WHERE id = :id",
        id=claim["deliverable_id"],
    )
    title = str((dl or {}).get("title") or "")
    summary = str((dl or {}).get("summary") or "")[:4000]
    if summary and await guard(tx, hub, "overseer_cross_check", summary) is not None:
        summary = ""  # the claim alone rather than a deliverable's personal data
    text = CROSS_PROMPT.format(claim=claim["claim_md"], title=title, summary=summary or "-")
    if await guard(tx, hub, "overseer_cross_check", text) is not None:
        return None
    if await tx.scalar(
        """SELECT 1 FROM substitutes.calls s JOIN quality.claims q ON q.ref = s.purpose_ref
           WHERE s.seat = 'overseer_cross_check' AND s.purpose_kind = 'claim'
             AND q.deliverable_id = :dl AND q.claim_md = :claim AND q.id <> :id LIMIT 1""",
        dl=claim["deliverable_id"],
        claim=claim["claim_md"],
        id=claim["id"],
    ):
        return None
    return await seat_call(
        tx,
        hub,
        CROSS_CHECK,
        seat="overseer_cross_check",
        input_md=text,
        company_id=claim["company_id"],
        purpose=("claim", str(claim["ref"])),
    )


def cross_verdict(text: str) -> tuple[str | None, str]:
    """(verdict, reason) of a cross-check's answer; (None, "") when it gave none."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None, ""
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return None, ""
    if not isinstance(raw, dict) or raw.get("verdict") not in CROSS_VERDICTS:
        return None, ""
    return str(raw["verdict"]), scrub(str(raw.get("reason_md") or ""))[:600]


async def apply_cross_check(tx: Tx, hub: Any, call: dict[str, Any]) -> None:
    """A finished cross-check. When its verdict differs from the recorded one,
    the claim goes back to the overseer as a work item (look again, decide on
    evidence you can cite). It never decides the claim: no quality.claims row
    and no claim.verdict come from it; an agreeing or empty answer only stays
    on the call."""
    from hq_api.domain import work as W

    if call["state"] != "done" or call["delivered_at"] is not None:
        return
    claim = await tx.first(
        """SELECT q.*, c.code AS company FROM quality.claims q JOIN core.companies c ON c.id = q.company_id
           WHERE q.ref = :r""",
        r=call["purpose_ref"],
    )
    verdict, reason = cross_verdict(str((call["result"] or {}).get("text_md") or ""))
    if claim is None or verdict is None or verdict == claim["verdict"]:
        return
    overseer = await tx.first(
        """SELECT e.code, e.company_id, c.code AS company FROM core.employees e
           JOIN core.companies c ON c.id = e.company_id
           WHERE e.kind = 'overseer' AND e.status = 'active' AND c.kind = 'holding'
           ORDER BY e.created_at LIMIT 1"""
    )
    if overseer is None:
        log.info("cross-check disagrees but no overseer is seated", extra={"claim": claim["ref"]})
        return
    brief = (
        f"A cross-check disagrees with claim {claim['ref']} of deliverable {claim['deliverable_ref']} "
        f"({claim['company']}, by {claim['employee_code'] or '-'}): recorded {claim['verdict']} by "
        f"{claim['checked_by_code']}, the cross-check says {verdict}. Source: {json.dumps(source(call))}. "
        "It is a second pair of eyes, never evidence and never a verdict: look again and decide on "
        "evidence you can cite; record claim.verdict only from your own check.\n\n"
        f"Claim: {claim['claim_md']}\nThe cross-check's reason: {reason or '-'}"
    )
    w = await W.create(
        tx,
        SERVICE,
        company_id=overseer["company_id"],
        company_code=overseer["company"],
        title=f"بازبینی دوباره‌ی ادعای {claim['ref']}"[:300],
        brief=brief,
        kind="one_off",
        priority="P2",
        assignee_code=overseer["code"],
        budget=W.BudgetIn(tokens=RETURN_TOKENS),
    )
    await tx.exec(
        "UPDATE substitutes.calls SET delivered_at = now(), reply_work_id = :w WHERE id = :id",
        w=w["id"],
        id=call["id"],
    )
    await audit.record(
        tx,
        audit.SYSTEM,
        company_id=claim["company_id"],
        action="claim.returned",
        action_class="A1",
        target_kind="claim",
        target_ref=claim["ref"],
        summary=f"cross-check {verdict} vs {claim['verdict']}: back to {overseer['code']}",
    )
