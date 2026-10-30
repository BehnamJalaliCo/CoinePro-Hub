"""Publishing the media studio's items (prompt 13 §2.3, contract §22.2 step 8,
§22.7): by code, only through the official APIs (Telegram Bot API, Instagram
Graph API), from the worker through egress (POST /v1/media/publish).

- After the director's review: a sealed series with auto_publish, every check
  `pass` and every placement through an API -> `scheduled` at the series'
  next occurrence; anything else -> `waiting_owner` and a `media_publish` card
  (A3). Approving the card publishes it now (its effect); a Telegram channel
  story has no Bot API, so the owner posts that file by hand from the card
  (`external_id: "manual"`).
- The publisher asks the launch gate first (nothing while the holding is
  locked; an item of a locked company waits), and stops for the overseer's
  watch mode (the item becomes a card) and holds; the platform's own limit
  (Instagram: 50 API posts a day per account) answers `platform_limit`.
- Instagram fetches the file from a signed URL on hq.coinepro.com that is
  valid for that one file for at most 15 minutes (`/public/v1/media/<token>`);
  any other URL is 404.
- Unpublishing deletes through the same API where the platform allows it
  (a Telegram channel message); otherwise the row says `remove_by_hand`.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import struct
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

import httpx

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import decisions as D
from hq_api.domain import egress as G
from hq_api.domain import gate, oversight, recurrence
from hq_api.domain import studio as S
from hq_api.errors import ApiError

log = logging.getLogger("hq_api.studio.publish")

SIGNED_TTL_S = 15 * 60
INSTAGRAM_POLL_S = 10
INSTAGRAM_POLL_TRIES = 30
TG_CAPTION = 1024
IG_CAPTION = 2200
AI_LABEL = "ساخته‌شده با کمک هوش مصنوعی"
BY_CARD = "by_card"


# --------------------------------------------------------- signed URLs --
def _key(hub: Any) -> bytes:
    base = getattr(hub.secrets, "agent_token_key", None) or b""
    if not base:
        raise ApiError(503, "channel_not_configured", "no signing key")
    return hmac.new(base, b"hq-media-public-url-v1", hashlib.sha256).digest()


def sign(hub: Any, file_id: UUID, ttl_s: int = SIGNED_TTL_S, now: float | None = None) -> str:
    """A token for one file, valid ≤ 15 minutes."""
    exp = int((now or time.time()) + min(ttl_s, SIGNED_TTL_S))
    body = file_id.bytes + struct.pack(">I", exp)
    mac = hmac.new(_key(hub), body, hashlib.sha256).digest()[:18]
    return base64.urlsafe_b64encode(body + mac).decode().rstrip("=")


def verify(hub: Any, token: str, now: float | None = None) -> UUID | None:
    """The file of a valid token, else None (expired, forged, malformed)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", token or ""):
        return None
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    except ValueError:
        return None
    if len(raw) != 16 + 4 + 18:
        return None
    body, mac = raw[:20], raw[20:]
    if not hmac.compare_digest(mac, hmac.new(_key(hub), body, hashlib.sha256).digest()[:18]):
        return None
    (exp,) = struct.unpack(">I", body[16:20])
    if exp < (now or time.time()) or exp > (now or time.time()) + SIGNED_TTL_S + 5:
        return None
    return UUID(bytes=body[:16])


def public_url(hub: Any, file_id: UUID) -> str:
    origin = str(getattr(hub.settings, "public_origin", "") or "").rstrip("/")
    return f"{origin}/public/v1/media/{sign(hub, file_id)}"


# ------------------------------------------------------------ egress --
class Publisher(Protocol):
    async def call(
        self, hub: Any, call: dict[str, Any], files: list[tuple[str, bytes, str]]
    ) -> dict[str, Any]: ...


class EgressPublisher:
    """POST /v1/media/publish on egress (the worker is on hq-egress-api)."""

    async def call(
        self, hub: Any, call: dict[str, Any], files: list[tuple[str, bytes, str]]
    ) -> dict[str, Any]:
        url = hub.settings.support_egress_url.rstrip("/") + "/v1/media/publish"
        meta = [
            {
                "part": f"file{i}",
                "name": f"file{i}",
                "mime": mime,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for i, (_, data, mime) in enumerate(files)
        ]
        form = {"call": json.dumps({**call, "files": meta}, ensure_ascii=False)}
        parts = {f"file{i}": (f"file{i}", data, mime) for i, (_, data, mime) in enumerate(files)}
        try:
            async with httpx.AsyncClient(timeout=180) as http:
                resp = await http.post(url, data=form, files=parts or None)
            out = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("media publish call failed", extra={"error": type(exc).__name__})
            return {"outcome": "error", "code": "publish_error", "data": {}}
        return (
            out
            if isinstance(out, dict)
            else {"outcome": "error", "code": "publish_error", "data": {}}
        )


OVERRIDE: Publisher | None = None  # tests put a fake Telegram / Instagram here


def publisher() -> Publisher:
    return OVERRIDE or EgressPublisher()


# --------------------------------------------------- after the review --
async def placements(tx: Tx, hub: Any, item: dict[str, Any]) -> list[dict[str, Any]]:
    """Each target: through the API or by the owner's hand, and what blocks it."""
    out: list[dict[str, Any]] = []
    for t in S.targets_of(item):
        row = {
            "channel": t["channel"],
            "placement": t["placement"],
            "account": t["account"],
            "via": "manual" if t["placement"] in S.MANUAL_PLACEMENTS else "api",
            "blocked": None,
        }
        if t["channel"] == "runner":
            # ⟨1.8⟩ the company's own product API on its paired server (§26.1b)
            row["via"] = "runner"
            row["server"], row["command"] = t.get("server"), t.get("command")
            srv = await tx.first(
                """SELECT state FROM infra.servers WHERE company_id = :co AND origin = 'attached'
                     AND lower(name) = lower(:n)""",
                co=item["company_id"],
                n=t.get("server") or "",
            )
            if srv is None or srv["state"] == "revoked":
                row["blocked"] = "server_unavailable"
        elif row["via"] == "api":
            acct = await tx.first("SELECT key FROM tools.accounts WHERE key = :k", k=t["account"])
            if acct is None or not await G.has_secret(getattr(hub, "bao", None), t["account"]):
                row["blocked"] = "account_not_configured"
            elif (lim := S.PER_24H.get(t["channel"])) is not None and await used_24h(
                tx, t["account"]
            ) >= lim:
                row["blocked"] = "platform_limit"
        out.append(row)
    return out


async def after_review(tx: Tx, hub: Any, item: dict[str, Any]) -> None:
    rows = await placements(tx, hub, item)
    failed = [c["key"] for c in item.get("checks") or [] if c.get("result") == "fail"]
    sealed = (
        item.get("series_status") == "sealed"
        and item.get("series_auto_publish")
        and item.get("series_digest") == item.get("series_sealed_digest")
        and not item["one_off"]
    )
    why = None
    if item["one_off"]:
        why = "one_off"
    elif failed:
        why = "check_failed"
    elif item.get("series_status") != "sealed":
        why = "not_sealed"
    elif not item.get("series_auto_publish"):
        why = "not_auto"
    elif any(r["via"] == "manual" for r in rows):
        why = "no_api"
    elif any(r["blocked"] for r in rows):
        why = next(r["blocked"] for r in rows if r["blocked"])
    elif await oversight.watch_on(tx):
        why = "watch_mode"
    if sealed and why is None:
        at = await schedule_at(tx, item)
        await tx.exec(
            "UPDATE media.items SET state = 'scheduled', publish_at = :at, state_note_fa = NULL WHERE id = :id",
            id=item["id"],
            at=at,
        )
        await events.emit(tx, item["company"], "media.item", item["ref"], {"state": "scheduled"})
        return
    await card(tx, item, why or "not_auto", rows)


async def card(
    tx: Tx, item: dict[str, Any], why: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """A media_publish card (A3): approving it publishes the item now."""
    explain = {
        "one_off": "یک‌باره است؛ یک‌باره‌ها همیشه کارت‌اند.",
        "check_failed": "یک یا چند چک رد شد؛ بی مُهر تو منتشر نمیشود.",
        "not_sealed": "برنامه‌اش مُهرشده نیست (یا بعد از مُهر عوض شده).",
        "not_auto": "برنامه‌اش انتشار خودکار ندارد.",
        "no_api": "یکی از جاهای انتشار راه رسمی ندارد (استوری کانال تلگرام): فایل را خودت بگذار.",
        "account_not_configured": "حساب یکی از جاها هنوز کلید ندارد.",
        "platform_limit": "سقف خود پلتفرم امروز پر است.",
        "watch_mode": "حالت نگهبان روشن است؛ هر انتشار کارت توست.",
        "publish_failed": "انتشار خودکار نشد؛ خطای هر جا در کارت هست.",
    }.get(why, why)
    payload = {
        "item": item["ref"],
        "series": item.get("series_ref"),
        "kind": item["kind"],
        "title_fa": item["title_fa"],
        "why": why,
        "placements": rows,
        "render": {"file": str(item["render_file_id"])} if item.get("render_file_id") else None,
        "checks": item.get("checks") or [],
    }
    din = D.DecisionIn(
        kind="media_publish",
        title=f"انتشار {item['ref']}: {item['title_fa']}"[:300],
        what=f"آیتم **{item['ref']}** ({item['kind']})"
        + (f" از برنامه‌ی **{item['series_ref']}**" if item.get("series_ref") else "")
        + " آماده‌ی انتشار است: "
        + "، ".join(f"{r['placement']} ({r['via']})" for r in rows),
        why=explain,
        risk="low" if why in ("one_off", "not_auto", "no_api") else "medium",
        payload=payload,
    )
    thread = await tx.scalar(
        """SELECT t.code FROM msg.threads t JOIN core.employees e ON e.id = t.employee_id
           JOIN core.departments d ON d.id = e.department_id
           WHERE e.company_id = :co AND d.code = 'MEDIA' AND e.kind = 'manager' LIMIT 1""",
        co=item["company_id"],
    )
    d = await D.propose(
        tx,
        S.SERVICE,
        company_id=item["company_id"],
        company_code=item["company"],
        body=din,
        thread_code=thread,
    )
    await tx.exec(
        """UPDATE media.items SET state = 'waiting_owner', decision_id = :d, publish_at = NULL,
               publish = CAST(:p AS jsonb), state_note_fa = :n WHERE id = :id""",
        id=item["id"],
        d=d["id"],
        p=S.canonical(
            [
                {
                    "channel": r["channel"],
                    "placement": r["placement"],
                    "at": None,
                    "external_id": None,
                    "url": None,
                    "error": r["blocked"] or ("no_api" if r["via"] == "manual" else None),
                }
                for r in rows
            ]
        ),
        n=explain,
    )
    await events.emit(
        tx,
        item["company"],
        "media.item",
        item["ref"],
        {"state": "waiting_owner", "decision": d["ref"]},
    )
    return d


async def card_approved(tx: Tx, d: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """The card's effect (A3, sealed): the item is published now by the worker."""
    item = await S.load_item(tx, p["item"], lock=True)
    if item["state"] not in ("waiting_owner", "held"):
        return {"item": item["ref"], "state": item["state"]}
    meta = {**(item.get("render_meta") or {}), BY_CARD: d["ref"]}
    await tx.exec(
        """UPDATE media.items SET state = 'scheduled', publish_at = now(), decision_id = :d,
               render_meta = CAST(:m AS jsonb), state_note_fa = NULL WHERE id = :id""",
        id=item["id"],
        d=d["id"],
        m=S.canonical(meta),
    )
    await events.emit(
        tx, item["company"], "media.item", item["ref"], {"state": "scheduled", "decision": d["ref"]}
    )
    return {"item": item["ref"], "state": "scheduled"}


# ------------------------------------------------------------ publish --
async def used_24h(tx: Tx, account: str) -> int:
    n = await tx.scalar(
        """SELECT count(*) FROM media.publish_log WHERE account = :a AND action = 'publish'
             AND outcome = 'ok' AND via = 'api' AND at > now() - interval '24 hours'""",
        a=account,
    )
    return int(n or 0)


def caption_of(item: dict[str, Any], channel: str) -> str:
    from hq_api.domain import studio_checks as K

    script = str((item.get("script") or {}).get("text_fa") or "")
    cap = K.parts(script).get("کپشن") or "\n".join(script.strip().splitlines()[:3])
    cap = re.sub(r"[*_`#>\[\]]", "", cap).strip()
    if channel == "telegram":
        return (cap[: TG_CAPTION - len(AI_LABEL) - 2] + "\n\n" + AI_LABEL).strip()
    return cap[:IG_CAPTION]


def telegram_chat(site: str | None) -> str | None:
    s = (site or "").strip()
    if re.fullmatch(r"-100[0-9]{5,15}", s) or re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{3,31}", s):
        return s
    m = re.fullmatch(r"https?://t\.me/c/([0-9]{5,15})/?", s)
    if m:
        return f"-100{m.group(1)}"
    m = re.fullmatch(r"https?://t\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?", s)
    return f"@{m.group(1)}" if m else None


def instagram_user(site: str | None) -> str | None:
    s = (site or "").strip().lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9_.]{1,30}", s):
        return s.lower()
    m = re.fullmatch(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]{1,30})/?", s)
    return m.group(1).lower() if m else None


def channel_of(acct: dict[str, Any]) -> str | None:
    """Where a publishing account posts: its policy's `inject.username` (the
    Telegram channel, "@name" or "-100…"; the Instagram page's username), as
    the owner sets it with the account (the account's `site` is the API's host)."""
    policy = acct.get("policy") or {}
    if isinstance(policy, str):
        policy = json.loads(policy or "{}")
    name = ((policy.get("inject") or {}).get("username") or "").strip()
    return name or None


async def publish_due(hub: Any, only: str | None = None, limit: int = 5) -> dict[str, Any]:
    """Every scheduled item whose time came (or the one `only`): through the
    official APIs; nothing while the holding is locked."""
    done: list[str] = []
    waiting: dict[str, str] = {}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        if (lock := await gate.holding_lock(tx)) is not None:
            return gate.skipped(lock)
        rows = await tx.all(
            S.ITEM_SQL
            + """ WHERE i.state = 'scheduled' AND i.publish_at <= now()
                    AND (CAST(:only AS text) IS NULL OR i.ref = :only)
                  ORDER BY i.publish_at LIMIT :lim FOR UPDATE OF i SKIP LOCKED""",
            only=only,
            lim=limit,
        )
        batch = []
        for item in rows:
            if (lock := await gate.automation_lock(tx, item["company_id"])) is not None:
                waiting[item["ref"]] = gate.REASONS.get(lock, lock)
                continue
            by_card = (item.get("render_meta") or {}).get(BY_CARD)
            if not by_card:
                sealed = (
                    item.get("series_status") == "sealed"
                    and item.get("series_auto_publish")
                    and item.get("series_digest") == item.get("series_sealed_digest")
                )
                if not sealed or await oversight.watch_on(tx):
                    # The seal no longer covers it, or the overseer watches: a card.
                    await card(
                        tx,
                        item,
                        "watch_mode" if sealed else "not_sealed",
                        await placements(tx, hub, item),
                    )
                    continue
                if await _published_today(tx, item) >= int(item.get("series_max_per_day") or 1):
                    await tx.exec(
                        "UPDATE media.items SET publish_at = :at WHERE id = :id",
                        id=item["id"],
                        at=await _next_occurrence(
                            tx, item, datetime.now(UTC) + timedelta(minutes=1)
                        ),
                    )
                    waiting[item["ref"]] = "max_per_day"
                    continue
            if await _held(tx, item):
                waiting[item["ref"]] = "held"
                continue
            # Claimed for 30 minutes (a lease): no other publisher takes it while
            # this one works; a publisher that died leaves it to the next sweep.
            await tx.exec(
                "UPDATE media.items SET publish_at = now() + interval '30 minutes' WHERE id = :id",
                id=item["id"],
            )
            batch.append((item, await placements(tx, hub, item)))
    for item, rows in batch:
        await _publish_one(hub, item, rows)
        done.append(item["ref"])
    return {"published": done, "waiting": waiting}


async def _held(tx: Tx, item: dict[str, Any]) -> bool:
    for s in item.get("steps") or []:
        if s.get("work") and await oversight.held(tx, "work", s["work"]):
            return True
    return bool(
        item.get("decision_ref") and await oversight.held(tx, "decision", item["decision_ref"])
    )


async def _published_today(tx: Tx, item: dict[str, Any]) -> int:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(await S.owner_zone(tx))
    day = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    n = await tx.scalar(
        """SELECT count(DISTINCT l.item_id) FROM media.publish_log l
           WHERE l.series_id = (SELECT series_id FROM media.items WHERE id = :i)
             AND l.action = 'publish' AND l.outcome = 'ok' AND l.at >= :d""",
        i=item["id"],
        d=day,
    )
    return int(n or 0)


async def _next_occurrence(tx: Tx, item: dict[str, Any], after: datetime) -> datetime:
    tz = await S.owner_zone(tx)
    found = recurrence.occurrences(
        recurrence.parse(item["series_schedule"]), tz, after, after + timedelta(days=62), limit=1
    )
    return found[0] if found else after + timedelta(days=1)


async def schedule_at(tx: Tx, item: dict[str, Any]) -> datetime:
    """When a reviewed item of a sealed series goes out: its schedule's next
    occurrence in the owner's zone (the series' times are publishing times)."""
    return await _next_occurrence(tx, item, datetime.now(UTC))


async def _publish_one(hub: Any, item: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    by_card = (item.get("render_meta") or {}).get(BY_CARD)
    results = []
    for r in rows:
        if r["via"] == "manual":
            # The owner posts it from the card (the card's approval says so).
            results.append(
                {
                    **r,
                    "outcome": "ok" if by_card else "skipped",
                    "external_id": "manual" if by_card else None,
                    "url": None,
                    "error": None if by_card else "no_api",
                }
            )
            continue
        if r["blocked"]:
            results.append(
                {**r, "outcome": "error", "external_id": None, "url": None, "error": r["blocked"]}
            )
            continue
        if r["via"] == "runner":
            # ⟨1.8⟩ queued below as a `publish` job; its result comes back later
            results.append(
                {**r, "outcome": "queued", "external_id": None, "url": None, "error": None}
            )
            continue
        try:
            out = await _send(hub, item, r)
        except Exception:
            log.exception("publish failed", extra={"item": item["ref"]})
            out = {"outcome": "error", "error": "publish_error"}
        results.append({**r, **out})
    async with hub.db.tx([item["company_id"]]) as tx:
        cur = await S.load_item(tx, item["ref"], lock=True)
        decision = cur.get("decision_id")
        now = datetime.now(UTC)
        for x in results:
            if x["outcome"] == "queued":
                x["job"] = await _queue_runner(tx, item, x)
                if x["job"] is not None:
                    continue
                x.update(outcome="error", error=x.get("error") or "server_unavailable")
            await tx.exec(
                """INSERT INTO media.publish_log (company_id, item_id, series_id, action, channel, placement,
                       account, via, outcome, external_id, url, error, by_kind, by_code, decision_id)
                   VALUES (:co, :i, :s, 'publish', :ch, :pl, :a, :via, :o, :x, :u, :e, :bk, :bc, :d)""",
                co=item["company_id"],
                i=item["id"],
                s=item["series_id"],
                ch=x["channel"],
                pl=x["placement"],
                a=x["account"],
                via=x["via"],
                o=x["outcome"],
                x=x.get("external_id"),
                u=x.get("url"),
                e=x.get("error"),
                bk="owner" if by_card else "service",
                bc="owner" if by_card else "media",
                d=decision if by_card else None,
            )
        publish = [
            {
                "channel": x["channel"],
                "placement": x["placement"],
                "at": now if x["outcome"] == "ok" else None,
                "external_id": x.get("external_id"),
                "url": x.get("url"),
                "error": x.get("error"),
                **({"job": x["job"]} if x.get("job") else {}),
            }
            for x in results
        ]
        if any(x["outcome"] == "queued" for x in results):
            # ⟨1.8⟩ waiting for the runners' answers (runner_published finishes it);
            # the lease keeps the publisher from taking it again meanwhile.
            await tx.exec(
                """UPDATE media.items SET publish = CAST(:p AS jsonb),
                       publish_at = now() + interval '7 days' WHERE id = :id""",
                id=item["id"],
                p=S.canonical(publish),
            )
            await events.emit(
                tx,
                item["company"],
                "media.item",
                item["ref"],
                {"state": "scheduled", "waiting": "runner"},
            )
            return
        ok = all(x["outcome"] == "ok" for x in results)
        limited = [x for x in results if x.get("error") == "platform_limit"]
        if ok:
            state, note = "published", None
        elif (
            limited
            and not by_card
            and all(x["outcome"] == "ok" or x.get("error") == "platform_limit" for x in results)
        ):
            retry = max(int(x.get("retry_after") or 0) for x in limited) or 900
            await tx.exec(
                """UPDATE media.items SET state = 'scheduled', publish = CAST(:p AS jsonb),
                       publish_at = now() + make_interval(secs => :r) WHERE id = :id""",
                id=item["id"],
                r=max(900, retry),
                p=S.canonical(publish),
            )
            await events.emit(
                tx,
                item["company"],
                "media.item",
                item["ref"],
                {"state": "scheduled", "error": "platform_limit"},
            )
            return
        elif any(x["outcome"] == "ok" for x in results):
            state, note = (
                "published",
                "آنچه راه رسمی داشت منتشر شد؛ جای دیگر: "
                + "، ".join(
                    f"{x['placement']} ({x.get('error')})" for x in results if x["outcome"] != "ok"
                ),
            )
        else:
            await tx.exec(
                "UPDATE media.items SET publish = CAST(:p AS jsonb) WHERE id = :id",
                id=item["id"],
                p=S.canonical(publish),
            )
            cur = await S.load_item(tx, item["ref"], lock=True)
            await card(
                tx,
                cur,
                "publish_failed",
                [
                    {
                        **{k: x[k] for k in ("channel", "placement", "account", "via")},
                        "blocked": x.get("error"),
                    }
                    for x in results
                ],
            )
            return
        await tx.exec(
            "UPDATE media.items SET state = :st, publish = CAST(:p AS jsonb), state_note_fa = :n WHERE id = :id",
            id=item["id"],
            st=state,
            p=S.canonical(publish),
            n=note,
        )
        await events.emit(tx, item["company"], "media.item", item["ref"], {"state": state})


async def _queue_runner(tx: Tx, item: dict[str, Any], x: dict[str, Any]) -> str | None:
    """⟨1.8⟩ A `publish` job on the target server's runner (contract §26.1b):
    the rendered files (the runner fetches them from signed hub URLs, minted
    when it takes the job), the caption and the sealed command. None (with
    x["error"]) when the server cannot take it now."""
    from hq_api.domain import servers as SV

    outs = [o for o in item.get("outputs") or [] if o.get("placement") == x["placement"]]
    if not outs:
        x["error"] = "no_render"
        return None
    try:
        server = await SV.load_server(tx, str(x.get("server") or ""), company=item["company"])
        j = await SV.create_job(
            tx,
            server=server,
            kind="publish",
            args={
                "item": item["ref"],
                "kind": item["kind"],
                "placement": x["placement"],
                "command": x.get("command") or "",
                "caption": caption_of(item, "instagram"),
                "title_fa": item["title_fa"],
                "files": [
                    {
                        "file_id": str(o["file_id"]),
                        "name": o.get("name"),
                        "mime": _mime(o),
                        "kind": o.get("kind"),
                    }
                    for o in outs[:10]
                ],
            },
            actor_kind="service",
            actor_code="media",
            summary=f"انتشار {item['ref']} ({x['placement']})",
            timeout_s=900,
        )
    except ApiError as exc:
        x["error"] = (
            exc.code if exc.code in ("company_locked", "not_found") else "server_unavailable"
        )
        if x["error"] == "not_found":
            x["error"] = "server_unavailable"
        return None
    return str(j["id"])


async def runner_published(
    tx: Tx, j: dict[str, Any], ok: bool, external_id: str | None, url: str | None,
    error: str | None,
) -> None:  # fmt: skip
    """⟨1.8⟩ A publish job ended: its row of the item and of the publish log;
    once no runner is pending, the item is published (or its card raised)."""
    ref = (j["args"] or {}).get("item")
    if not ref:
        return
    item = await S.load_item(tx, str(ref), lock=True)
    entries = list(item.get("publish") or [])
    mine = next((e for e in entries if e.get("job") == str(j["id"])), None)
    if mine is None or mine.get("at") or mine.get("error"):
        return
    mine.update(
        at=datetime.now(UTC).isoformat() if ok else None,
        external_id=external_id,
        url=url,
        error=None if ok else (error or "publish_error")[:40],
    )
    by_card = (item.get("render_meta") or {}).get(BY_CARD)
    await tx.exec(
        """INSERT INTO media.publish_log (company_id, item_id, series_id, action, channel, placement,
               account, via, outcome, external_id, url, error, by_kind, by_code, decision_id)
           VALUES (:co, :i, :s, 'publish', 'runner', :pl, :a, 'runner', :o, :x, :u, :e, :bk, :bc, :d)""",
        co=item["company_id"],
        i=item["id"],
        s=item.get("series_id"),
        pl=mine["placement"],
        a=next(
            (
                t["account"]
                for t in S.targets_of(item)
                if t["channel"] == "runner" and t["placement"] == mine["placement"]
            ),
            "runner-unknown",
        ),
        o="ok" if ok else "error",
        x=external_id,
        u=url,
        e=None if ok else re.sub(r"[^a-z_]", "_", (error or "publish_error").lower())[:40],
        bk="owner" if by_card else "service",
        bc="owner" if by_card else "media",
        d=item.get("decision_id") if by_card else None,
    )
    pending = [e for e in entries if e.get("job") and not e.get("at") and not e.get("error")]
    await tx.exec(
        "UPDATE media.items SET publish = CAST(:p AS jsonb) WHERE id = :id",
        id=item["id"],
        p=S.canonical(entries),
    )
    if pending:
        return
    good = [e for e in entries if e.get("at")]
    if good:
        bad = [e for e in entries if not e.get("at")]
        note = (
            "آنچه راه داشت منتشر شد؛ جای دیگر: "
            + "، ".join(f"{e['placement']} ({e.get('error')})" for e in bad)
            if bad
            else None
        )
        await tx.exec(
            """UPDATE media.items SET state = 'published', publish_at = NULL, state_note_fa = :n
               WHERE id = :id""",
            id=item["id"],
            n=note,
        )
        await events.emit(tx, item["company"], "media.item", item["ref"], {"state": "published"})
        return
    cur = await S.load_item(tx, item["ref"], lock=True)
    await card(
        tx,
        cur,
        "publish_failed",
        [
            {
                "channel": e["channel"],
                "placement": e["placement"],
                "account": next(
                    (t["account"] for t in S.targets_of(cur) if t["placement"] == e["placement"]),
                    "runner-unknown",
                ),
                "via": "runner" if e["channel"] == "runner" else "api",
                "blocked": e.get("error"),
            }
            for e in entries
        ],
    )


async def _account(hub: Any, key: str) -> tuple[dict[str, Any] | None, str | None]:
    async with hub.db.raw() as tx:
        row = await tx.first(
            "SELECT key, site, companies, policy FROM tools.accounts WHERE key = :k", k=key
        )
    return row, await G.read_secret(getattr(hub, "bao", None), key)


async def _send(hub: Any, item: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    acct, token = await _account(hub, r["account"])
    if acct is None or not token:
        return {"outcome": "error", "error": "account_not_configured"}
    outs = [o for o in item.get("outputs") or [] if o.get("placement") == r["placement"]]
    if not outs:
        return {"outcome": "error", "error": "no_render"}
    pub = publisher()
    if r["channel"] == "telegram":
        chat = telegram_chat(channel_of(acct))
        if chat is None:
            return {"outcome": "error", "error": "account_not_configured"}
        files = [
            (o["name"], await _bytes(hub, item["company_id"], o["file_id"]), _mime(o))
            for o in outs[:10]
        ]
        cap = caption_of(item, "telegram")
        payload: dict[str, Any]
        if len(files) > 1:
            payload = {
                "chat_id": chat,
                "media": [
                    {
                        "type": "video" if o.get("kind") == "video" else "photo",
                        "media": f"attach://file{i}",
                        **({"caption": cap} if i == 0 else {}),
                    }
                    for i, o in enumerate(outs[:10])
                ],
            }
            method = "sendMediaGroup"
        elif outs[0].get("kind") == "video":
            payload = {
                "chat_id": chat,
                "caption": cap,
                "video": "attach://file0",
                "supports_streaming": True,
                "width": outs[0].get("width"),
                "height": outs[0].get("height"),
                "duration": round(float(outs[0].get("duration_s") or 0)),
            }
            method = "sendVideo"
        else:
            payload = {"chat_id": chat, "caption": cap, "photo": "attach://file0"}
            method = "sendPhoto"
        out = await pub.call(
            hub,
            {"channel": "telegram", "method": method, "token": token, "payload": payload},
            files,
        )
        del token
        if out.get("outcome") != "ok":
            return {
                "outcome": "error",
                "error": _code(out),
                "retry_after": (out.get("data") or {}).get("retry_after"),
            }
        data = out.get("data") or {}
        mid = data.get("message_id") or (data.get("message_ids") or [None])[0]
        name = chat[1:] if chat.startswith("@") else None
        return {
            "outcome": "ok",
            "external_id": str(mid) if mid is not None else None,
            "url": f"https://t.me/{name}/{mid}" if name and mid is not None else None,
            "error": None,
        }
    # Instagram: the account itself, a container per file from its signed URL, then publish.
    me = await pub.call(
        hub, {"channel": "instagram", "method": "me", "token": token, "payload": {}}, []
    )
    if me.get("outcome") != "ok":
        return {"outcome": "error", "error": _code(me)}
    user = (me.get("data") or {}).get("user_id")
    want = instagram_user(channel_of(acct))
    if want and str((me.get("data") or {}).get("username") or "").lower() != want:
        return {"outcome": "error", "error": "account_mismatch"}
    lim = await pub.call(
        hub,
        {
            "channel": "instagram",
            "method": "limit",
            "token": token,
            "payload": {"ig_user_id": user},
        },
        [],
    )
    if lim.get("outcome") != "ok":
        return {
            "outcome": "error",
            "error": _code(lim),
            "retry_after": (lim.get("data") or {}).get("retry_after"),
        }
    cap = caption_of(item, "instagram")
    media_type = {"instagram_reel": "REELS", "instagram_story": "STORIES"}.get(
        r["placement"], "IMAGE"
    )

    async def container(o: dict[str, Any], extra: dict[str, Any]) -> str | None:
        key = "video_url" if o.get("kind") == "video" else "image_url"
        mt = media_type if (media_type != "IMAGE" or o.get("kind") != "video") else "REELS"
        body = {
            "ig_user_id": user,
            "media_type": mt,
            key: public_url(hub, UUID(o["file_id"])),
            **extra,
        }
        got = await pub.call(
            hub, {"channel": "instagram", "method": "create", "token": token, "payload": body}, []
        )
        if got.get("outcome") != "ok":
            raise _Fail(_code(got), (got.get("data") or {}).get("retry_after"))
        cid = str((got.get("data") or {}).get("id") or "")
        for _ in range(INSTAGRAM_POLL_TRIES):
            st = await pub.call(
                hub,
                {
                    "channel": "instagram",
                    "method": "status",
                    "token": token,
                    "payload": {"container_id": cid},
                },
                [],
            )
            code = str((st.get("data") or {}).get("status_code") or "")
            if st.get("outcome") != "ok" or code in ("ERROR", "EXPIRED"):
                raise _Fail("publish_error", None)
            if code in ("FINISHED", "PUBLISHED"):
                return cid
            await asyncio.sleep(INSTAGRAM_POLL_S)
        raise _Fail("publish_error", None)

    try:
        if item["kind"] == "carousel" and len(outs) > 1:
            kids = [await container(o, {"is_carousel_item": True}) for o in outs[:10]]
            got = await pub.call(
                hub,
                {
                    "channel": "instagram",
                    "method": "create",
                    "token": token,
                    "payload": {
                        "ig_user_id": user,
                        "media_type": "CAROUSEL",
                        "children": kids,
                        "caption": cap,
                    },
                },
                [],
            )
            if got.get("outcome") != "ok":
                raise _Fail(_code(got), None)
            cid: str | None = str((got.get("data") or {}).get("id") or "")
        else:
            cid = await container(outs[0], {"caption": cap} if media_type != "STORIES" else {})
        done = await pub.call(
            hub,
            {
                "channel": "instagram",
                "method": "publish",
                "token": token,
                "payload": {"ig_user_id": user, "creation_id": cid},
            },
            [],
        )
        if done.get("outcome") != "ok":
            raise _Fail(_code(done), (done.get("data") or {}).get("retry_after"))
        media_id = str((done.get("data") or {}).get("id") or "")
        link = await pub.call(
            hub,
            {
                "channel": "instagram",
                "method": "permalink",
                "token": token,
                "payload": {"media_id": media_id},
            },
            [],
        )
        url = (link.get("data") or {}).get("permalink") if link.get("outcome") == "ok" else None
        return {"outcome": "ok", "external_id": media_id, "url": url, "error": None}
    except _Fail as f:
        return {"outcome": "error", "error": f.code, "retry_after": f.retry_after}


class _Fail(Exception):
    def __init__(self, code: str, retry_after: Any) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def _code(out: dict[str, Any]) -> str:
    code = str(out.get("code") or "publish_error")
    return code if code in ("platform_limit", "no_channel", "auth_failed") else "publish_error"


def _mime(o: dict[str, Any]) -> str:
    if o.get("kind") == "video":
        return "video/mp4"
    return str(
        o.get("mime") or ("image/png" if str(o.get("name", "")).endswith("png") else "image/jpeg")
    )


async def _bytes(hub: Any, company_id: UUID, file_id: str) -> bytes:
    async with hub.db.tx([company_id]) as tx:
        key = await tx.scalar(
            "SELECT storage_key FROM files.files WHERE id = :id", id=UUID(file_id)
        )
    data: bytes = await hub.storage.get(key)
    return data


# ---------------------------------------------------------- unpublish --
async def request_unpublish(tx: Tx, item: dict[str, Any], step_up_id: UUID) -> dict[str, Any]:
    if item["state"] != "published":
        raise ApiError(409, "validation_failed", f"{item['ref']} is {item['state']}")
    meta = {
        **(item.get("render_meta") or {}),
        "unpublish": {"at": datetime.now(UTC), "step_up": str(step_up_id)},
    }
    await tx.exec(
        """UPDATE media.items SET render_meta = CAST(:m AS jsonb),
               state_note_fa = 'حذف از پلتفرم‌ها در جریان است.' WHERE id = :id""",
        id=item["id"],
        m=S.canonical(meta),
    )
    return await S.load_item(tx, item["ref"])


async def unpublish_due(hub: Any) -> dict[str, Any]:
    """Unpublish requests (the owner's, sealed): through the same API where the
    platform allows it. The owner's own act: it runs while locked too (it only
    takes down), but never while a company's lock would stop its sends."""
    done = []
    async with hub.db.tx(await hub.companies.ids()) as tx:
        rows = await tx.all(
            S.ITEM_SQL
            + " WHERE i.state = 'published' AND i.render_meta ? 'unpublish' FOR UPDATE OF i SKIP LOCKED LIMIT 5"
        )
    for item in rows:
        results = []
        for p in item.get("publish") or []:
            if not p.get("external_id") or p.get("error") == "removed":
                results.append({**p})
                continue
            err = "remove_by_hand"
            if p["channel"] == "telegram" and p["external_id"] != "manual":
                acct, token = await _account(hub, S.account_key("telegram", item["company"]))
                chat = telegram_chat(channel_of(acct)) if acct else None
                if token and chat:
                    out = await publisher().call(
                        hub,
                        {
                            "channel": "telegram",
                            "method": "deleteMessage",
                            "token": token,
                            "payload": {"chat_id": chat, "message_id": int(p["external_id"])},
                        },
                        [],
                    )
                    err = "removed" if out.get("outcome") == "ok" else "remove_by_hand"
            results.append({**p, "error": err})
        async with hub.db.tx([item["company_id"]]) as tx:
            cur = await S.load_item(tx, item["ref"], lock=True)
            if cur["state"] != "published" or "unpublish" not in (cur.get("render_meta") or {}):
                continue  # another pass took it down already
            for p in results:
                await tx.exec(
                    """INSERT INTO media.publish_log (company_id, item_id, series_id, action, channel, placement,
                           account, via, outcome, external_id, error, by_kind, by_code)
                       VALUES (:co, :i, :s, 'unpublish', :ch, :pl, :a, :via, :o, :x, :e, 'owner', 'owner')""",
                    co=item["company_id"],
                    i=item["id"],
                    s=item["series_id"],
                    ch=p["channel"],
                    pl=p["placement"],
                    a=S.account_key(p["channel"], item["company"]),
                    via="manual" if p.get("external_id") == "manual" else "api",
                    o="ok" if p.get("error") == "removed" else "error",
                    x=p.get("external_id"),
                    e=p.get("error"),
                )
            meta = {k: v for k, v in (item.get("render_meta") or {}).items() if k != "unpublish"}
            by_hand = [p["placement"] for p in results if p.get("error") == "remove_by_hand"]
            note = "از پلتفرم‌ها برداشته شد." + (
                f" این‌ها را خودت بردار: {'، '.join(by_hand)}." if by_hand else ""
            )
            await tx.exec(
                """UPDATE media.items SET state = 'rejected', publish = CAST(:p AS jsonb),
                       render_meta = CAST(:m AS jsonb), state_note_fa = :n WHERE id = :id""",
                id=item["id"],
                p=S.canonical(results),
                m=S.canonical(meta),
                n=note,
            )
            await events.emit(
                tx,
                item["company"],
                "media.item",
                item["ref"],
                {"state": "rejected", "unpublished": True},
            )
        done.append(item["ref"])
    return {"unpublished": done}


# ------------------------------------------------------------- limits --
async def limits(tx: Tx, bao: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    companies = await tx.all(
        "SELECT id, code FROM core.companies WHERE kind = 'company' AND status = 'active' ORDER BY code"
    )
    for c in companies:
        for channel in ("telegram", "instagram"):
            key = S.account_key(channel, c["code"])
            per = S.PER_24H[channel]
            used = await used_24h(tx, key)
            oldest = await tx.scalar(
                """SELECT min(at) FROM media.publish_log WHERE account = :a AND action = 'publish'
                     AND outcome = 'ok' AND via = 'api' AND at > now() - interval '24 hours'""",
                a=key,
            )
            acct = await tx.first("SELECT key FROM tools.accounts WHERE key = :k", k=key)
            configured = acct is not None and await G.has_secret(bao, key)
            note = None if configured else "حساب هنوز تنظیم نشده (make account-secret)."
            if per is not None and used >= per:
                note = "سقف ۲۴ ساعته‌ی خود پلتفرم پر است."
            out.append(
                {
                    "account": key,
                    "channel": channel,
                    "company": c["code"],
                    "per_24h": per,
                    "used_24h": used,
                    "resets_at": (oldest + timedelta(hours=24))
                    if (per is not None and used >= per and oldest)
                    else None,
                    "note_fa": note,
                }
            )
    return out


async def check_limit_now(tx: Tx, account: str, channel: str) -> None:
    """429 platform_limit (with Retry-After) when the platform's own limit is full."""
    per = S.PER_24H.get(channel)
    if per is None or await used_24h(tx, account) < per:
        return
    oldest = await tx.scalar(
        """SELECT min(at) FROM media.publish_log WHERE account = :a AND action = 'publish'
             AND outcome = 'ok' AND via = 'api' AND at > now() - interval '24 hours'""",
        a=account,
    )
    retry = (
        max(60, int(((oldest + timedelta(hours=24)) - datetime.now(UTC)).total_seconds()))
        if oldest
        else 3600
    )
    raise ApiError(
        429,
        "platform_limit",
        f"{account}: {per} posts in 24 hours",
        headers={"Retry-After": str(retry)},
    )
