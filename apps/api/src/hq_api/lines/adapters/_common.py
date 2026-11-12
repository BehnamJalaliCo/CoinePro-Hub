"""What the step adapters share (contract §30.2): the substitutes' seat call with a wait, the
profile-browser jobs through egress, OpenBao secrets, the company's files, plain Persian reasons.

Every outside call leaves through egress (`/v1/substitutes/web`, `/v1/http`, `/v1/media/publish`),
every model call through the LLM router or a substitute seat (ledgered there). Nothing here opens a
socket of its own except to those services. No secret is ever logged or returned.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from hq_api.domain import files as F
from hq_api.domain import gate, players
from hq_api.domain import substitutes as S
from hq_api.lines.base import StepContext, StepFailed
from hq_api.principal import Principal

log = logging.getLogger("hq_api.lines.adapters")

SERVICE = Principal(kind="service", code="lines", role="service")
POLL_S = 5.0  # how often a waiting step looks at its substitute call
BUSY_TRIES = 8  # a profile browser busy with someone else's job: tried again this often
BUSY_WAIT_S = 20.0

# Tests put fakes here; production leaves them None.
WEB_OVERRIDE: Any = None  # the egress profile-browser client
ROUTER_OVERRIDE: Any = None  # the LLM router client
sleep = asyncio.sleep  # tests make it instant

ACCOUNT_FA = {
    "chatgpt-web": "ChatGPT",
    "aistudio-web": "گوگل ای‌آی استودیو",
    "pinterest-web": "پینترست",
}
SKIP_FA = {
    "off": "این جایگاه خاموش است.",
    "signed_out": "حساب وارد نشده است؛ مالک باید وارد شود.",
    "expired": "ورود حساب منقضی شده؛ مالک باید دوباره وارد شود.",
    "limited": "سقف مصرف حساب پر شده؛ بعداً دوباره امتحان می‌شود.",
    "per_day": "سقف روزانه‌ی این جایگاه پر شده است.",
    "error": "حساب در همین ساعت‌ها خطا داده و کنار گذاشته شده است.",
    "holding_locked": "هلدینگ قفل است؛ هیچ کاری اجرا نمی‌شود.",
    "company_locked": "این شرکت قفل است.",
    "deploy_freeze": "هاب در توقف استقرار است.",
    # ⟨2026-11-11⟩ the ends a call gets from the hub itself
    "too_long": "متن برای این جایگاه بلندتر از حد است.",
    "not_claimed": "نوبت این کار به موقع نرسید.",
    "timeout": "جواب به موقع نرسید.",
    "browser_unavailable": "مرورگر هاب در دسترس نبود.",
    "worker_error": "خطای داخلی هاب پیش آمد.",
    "abandoned": "جواب به موقع نرسید.",
}


def skip_fa(reason: str | None, who: str = "") -> str:
    base = SKIP_FA.get(str(reason or "").split(":")[0], f"جایگاه جواب نداد ({reason}).")
    return f"{who}: {base}" if who else base


async def company_of(ctx: StepContext) -> Any:
    return await ctx.hub.companies.by_code(ctx.company)


async def check_unlocked(hub: Any) -> None:
    """Nothing leaves while the holding's kill switch is engaged."""
    async with hub.db.tx(await hub.companies.ids()) as tx:
        lock = await gate.holding_lock(tx)
    if lock is not None:
        raise StepFailed(skip_fa(gate.REASONS.get(lock, lock)), code="holding_locked")


def setting(ctx: StepContext, key: str, default: Any = None) -> Any:
    got = (ctx.step.get("settings") or {}).get(key)
    return default if got in (None, "") else got


def timeout_of(ctx: StepContext, default: int = 300) -> int:
    return int(ctx.step.get("timeout_s") or default)


def first_input(ctx: StepContext, key: str | None = None) -> Any:
    """The output of the named input step, else of the first one."""
    if key and key in ctx.inputs:
        return ctx.inputs[key]
    return next(iter(ctx.inputs.values()), None)


def input_with(ctx: StepContext, what: str, key: str | None = None) -> Any:
    """The named input, else the last input whose output has `what` (file_id or text)."""
    if key and key in ctx.inputs:
        return ctx.inputs[key]
    for out in reversed(list(ctx.inputs.values())):
        if getattr(out, what, None):
            return out
    return None


# ------------------------------------------------------------ the seat call --
async def ask_seat(
    ctx: StepContext, text: str, *, player: str = "gpt", timeout_s: int | None = None
) -> dict[str, Any]:
    """A text question to one substitute player's text seat; waits for the answer.

    Returns {"text", "tokens", "usd_equiv", "model", "player"}. The call is queued for the worker's
    web pass (one job per player at a time, 60 s apart) and read here until it is done, so the
    pace, the daily cap, the launch gate and the ledger are the substitutes' own. A skipped seat
    (signed out, limited, over its cap) is a plain failure, never another model.
    """
    hub = ctx.hub
    co = await company_of(ctx)
    who = {"gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}.get(player, player)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        found = await players.text_seat(tx, player)
        if found is None:
            raise StepFailed(skip_fa("off", who), code="seat_off")
        seat = found[1]["seat"]
        refused = await S.guard(tx, hub, seat, text)
        if refused is not None:
            raise StepFailed(
                f"{who}: متن شامل اطلاعات شخصی یا محرمانه است و به بیرون نمی‌رود.",
                code="policy_denied",
            )
        call = await S.seat_call(
            tx,
            hub,
            SERVICE,
            seat=seat,
            input_md=text,
            company_id=co.id,
            purpose=("lines", ctx.run_ref),
            player=player,
        )
    if call["state"] != "queued":
        raise StepFailed(skip_fa(call.get("state_reason"), who), code="seat_skipped")
    deadline = timeout_s if timeout_s is not None else timeout_of(ctx)
    waited = 0.0
    settled = False  # the call reached an end of its own; nothing to take back
    gave_up = False
    try:
        while True:
            async with hub.db.tx(await hub.companies.ids()) as tx:
                row = await tx.first(
                    "SELECT * FROM substitutes.calls WHERE id = :id", id=call["id"]
                )
                if row is not None and row["state"] == "done":
                    settled = True
                    answer = await S.full_text(tx, hub, row.get("result"))
                    tokens = int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0)
                    return {
                        "text": answer,
                        "tokens": tokens,
                        "usd_equiv": row.get("equiv_usd") or 0,
                        "model": row.get("model"),
                        "player": player,
                    }
            if row is not None and row["state"] in ("failed", "skipped", "cancelled"):
                settled = True
                raise StepFailed(
                    skip_fa(row.get("state_reason"), who), code="seat_failed", retry=True
                )
            if waited >= deadline:
                # ⟨2026-11-11⟩ the step stops waiting: its call ends too (`abandoned`, queued or
                # running), so it neither waits in the player's queue nor counts against the daily
                # cap; one that ended just now is read once more above
                ended = True
                if not gave_up:
                    gave_up = True
                    async with hub.db.tx(await hub.companies.ids()) as tx:
                        ended = await S.abandon(tx, hub, call["id"])
                if ended or row is None:
                    raise StepFailed(f"{who}: جواب به موقع نرسید.", code="timeout", retry=True)
                continue
            await sleep(POLL_S)
            waited += POLL_S
    finally:
        if not settled:  # timed out, cancelled by the engine's limit or broken off
            await abandon_call(hub, call["id"])


async def abandon_call(hub: Any, call_id: Any) -> None:
    """A seat call nobody waits for any more leaves the queue (the net under S.abandon, and the
    only way out when the step was cancelled mid-wait).

    Without this the web pass would still run it later, spend the owner's seat (its daily cap and
    ledger) on an answer nobody reads, and hold a step's retry behind it. A call already running
    is left to finish (or to S.abandon at the step's deadline); only a still-queued one is skipped.
    """
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await tx.exec(
                """UPDATE substitutes.calls
                   SET state = 'skipped', state_reason = 'abandoned', finished_at = now(),
                       input_md = NULL
                   WHERE id = :id AND state = 'queued'""",
                id=call_id,
            )
    except Exception as exc:  # noqa: BLE001 - the step's own failure is the one to report
        log.warning(
            "seat call not taken back", extra={"call": str(call_id), "error": type(exc).__name__}
        )


# ------------------------------------------------- the profile browser jobs --
class EgressWeb:
    """POST /v1/substitutes/web on egress (the worker's client is the same call)."""

    async def job(self, hub: Any, body: dict[str, Any], limit_s: float) -> dict[str, Any]:
        url = hub.settings.support_egress_url.rstrip("/") + "/v1/substitutes/web"
        try:
            async with httpx.AsyncClient(timeout=limit_s) as http:
                resp = await http.post(url, json=body)
            out = resp.json()
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "error": "off", "detail": "egress did not answer"}
        return out if isinstance(out, dict) else {"ok": False, "error": "failed"}


async def web_job(
    hub: Any,
    *,
    account: str,
    task: str,
    prompt: str,
    timeout_s: int,
    voice: str | None = None,
    style: str | None = None,
    limit: int | None = None,
    files: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """One job in a signed-in browser profile; the answer's `ok` is true or a StepFailed is raised."""
    await check_unlocked(hub)
    body: dict[str, Any] = {
        "account": account,
        "task": task,
        "prompt": prompt,
        "timeout_s": max(10, min(timeout_s, 900)),
    }
    if voice:
        body["voice"] = voice
    if style:
        body["style"] = style
    if limit:
        body["limit"] = limit
    if files:
        body["files"] = files
    client = WEB_OVERRIDE or EgressWeb()
    name = ACCOUNT_FA.get(account, account)
    answer: dict[str, Any] = {}
    for attempt in range(BUSY_TRIES):
        answer = await client.job(hub, body, body["timeout_s"] + 30)
        if answer.get("ok") or answer.get("error") != "busy":
            break
        if attempt < BUSY_TRIES - 1:
            await sleep(BUSY_WAIT_S)  # another job holds the profile: one at a time
    if answer.get("ok"):
        return answer
    err = str(answer.get("error") or "failed")
    step = str(answer.get("step") or "")
    if err == "expired":
        raise StepFailed(
            f"ورود حساب {name} منقضی شده؛ مالک باید با دستور ورود دوباره وارد شود "
            f"(make {account}-login).",
            code="expired",
        )
    if err == "recipe_failed":
        raise StepFailed(
            f"صفحه‌ی {name} طبق انتظار نبود (مرحله‌ی {step or '؟'}). دستور مرورگر باید اصلاح شود.",
            code="recipe_failed",
            retry=True,
        )
    if err == "timeout":
        raise StepFailed(f"{name} به موقع جواب نداد.", code="timeout", retry=True)
    if err == "busy":
        raise StepFailed(
            f"مرورگر {name} مشغول کار دیگری است؛ بعداً دوباره امتحان می‌شود.", retry=True
        )
    raise StepFailed(f"مرورگر هاب برای {name} خاموش یا در دسترس نیست.", code="browser_off")


# ------------------------------------------------------------- OpenBao --
async def bao_dict(hub: Any, path: str) -> dict[str, Any]:
    """A KV secret (path relative to the mount); {} when missing or OpenBao is unreachable."""
    bao = getattr(hub, "bao", None)
    if bao is None:
        return {}
    try:
        data = await bao.read_kv(path)
    except Exception as exc:  # noqa: BLE001 - a missing secret and a sealed vault read the same: not set
        log.info("secret not readable", extra={"path": path, "error": type(exc).__name__})
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------- files --
async def file_bytes(
    hub: Any, company_id: UUID, file_id: str, *, with_holding: bool = False
) -> tuple[bytes, dict[str, Any]]:
    """A file of the company (a step's output), or with `with_holding` of the holding too.

    A library asset's files are the owner's uploads, which POST /files keeps as the holding's, and a
    line may use the holding's assets (store.check_library): they are read with `with_holding`.
    """
    cos = [company_id]
    if with_holding:
        holding = (await hub.companies.holding()).id
        if holding not in cos:
            cos.append(holding)
    async with hub.db.tx(cos) as tx:
        row = await tx.first(
            """SELECT id, name, mime, storage_key, kind FROM files.files
               WHERE id = :id AND company_id = ANY(CAST(:cos AS uuid[]))""",
            id=UUID(str(file_id)),
            cos=[str(c) for c in cos],
        )
    if row is None:
        raise StepFailed("فایل این مرحله پیدا نشد.", code="file_missing")
    data: bytes = await hub.storage.get(str(row["storage_key"]))
    return data, row


def kind_of_mime(mime: str) -> str:
    return (
        mime.split("/", 1)[0]
        if mime.split("/", 1)[0] in ("image", "video", "audio")
        else "document"
    )


async def store_file(
    hub: Any,
    company_id: UUID,
    data: bytes,
    *,
    name: str,
    mime: str,
    duration_s: float | None = None,
) -> UUID:
    """A result as the company's file (the file store; the hub's own processing sees it later)."""
    key, sha = await hub.storage.put(data)
    async with hub.db.tx([company_id]) as tx:
        return await F.insert(
            tx,
            company_id=company_id,
            name=name,
            mime=mime,
            size=len(data),
            sha256=sha,
            storage_key=key,
            kind=kind_of_mime(mime),
            by_kind="service",
            by_code="lines",
            duration_s=duration_s,
        )


def decode_b64(file: dict[str, Any] | None) -> tuple[bytes, str, str]:
    """(bytes, name, mime) of an egress download, or a plain failure."""
    try:
        data = base64.b64decode(str((file or {}).get("b64") or ""), validate=True)
    except ValueError:
        data = b""
    if not data:
        raise StepFailed("فایلی از صفحه برنگشت.", code="no_file", retry=True)
    return (
        data,
        str((file or {}).get("name") or "file"),
        str((file or {}).get("mime") or "application/octet-stream"),
    )


def parse_json_object(text: str) -> dict[str, Any]:
    """The first JSON object in a model's answer (it may sit inside a code fence)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    return obj


def now() -> datetime:
    return datetime.now(UTC)
