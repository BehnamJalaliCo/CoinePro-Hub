"""Readiness of a company for a working group (contract §29.9 ⟨1.11⟩).

`GET /companies/{code}/readiness?group=content`: every check by rule, each
failed one with its one-tap fix:

    group            the group is on and the company's membership is not paused
                     (fix group.resume)
    seat:<seat>      each required seat filled by an active employee (fix hire:
                     automatic hiring, §29.10)
    hiring           hiring open and automatic (fix hiring.open, 🔏)
    envelope         the company's month envelope set (fix envelope.set)
    channels         at least one publishing channel (fix connection.guide);
                     ⟨2026-11-08⟩ Instagram counts for every company: through
                     IG-Hub, registered by the technical team, never a step of
                     the owner's
    connection:<k>   each publishing channel connected (fix connection.guide);
                     Instagram is always «through IG-Hub» (no fix, never «not
                     connected»: the owner's decision, 2026-11-08)
    series:<k>       at least one sealed series per channel (fix series.propose)
    players          Claude can take the work (the holding is not locked); the
                     substitute players that are ready are named
    runner           the servers the group reads through are online (IG-Hub for
                     Instagram; the company's own attached servers) (fix runner.check)

Every text is the owner's plain Persian (§29.7). ⟨2026-11-08⟩ the owner: no `media_tools` check
any more (⟨2026-11-09⟩ video is made by the workshop, §43, and voice is off: neither is a readiness
item or a step of his).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from hq_api.db import Tx
from hq_api.domain import connections as CN
from hq_api.domain import gate
from hq_api.domain import groups as GR
from hq_api.domain import humanize as H


class Fix(BaseModel):
    action: str
    label_fa: str
    target: str


class Check(BaseModel):
    key: str
    ok: bool
    title_fa: str
    detail_fa: str
    fix: Fix | None


class Readiness(BaseModel):
    company: str
    group: str
    ready: bool
    checks: list[Check]


def _check(key: str, ok: bool, title: str, detail: str, fix: Fix | None = None) -> Check:
    return Check(
        key=key,
        ok=ok,
        title_fa=H.humanize(title),
        detail_fa=H.humanize(detail),
        fix=None if ok else fix,
    )


async def _servers_needed(
    tx: Tx, company: Any, conns: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    from hq_api.domain import servers as SV

    found = await tx.all(
        SV.SERVER_SQL
        + " WHERE s.company_id = :co AND s.origin = 'attached' AND s.state <> 'revoked'",
        co=company.id,
    )
    ig = conns.get("instagram")
    if ig is not None and (ig.get("config") or {}).get("via") == "ig_hub":
        srv = (ig.get("config") or {}).get("server") or {}
        try:
            row = await SV.load_server(
                tx, srv.get("name") or "IG-Hub", company=srv.get("company") or "IG"
            )
        except Exception:  # noqa: BLE001 - not paired yet
            row = {"name": srv.get("name") or "IG-Hub", "company": srv.get("company") or "IG",
                   "state": None, "last_seen_at": None, "missing": True}  # fmt: skip
        if all(r.get("id") != row.get("id") for r in found):
            found.append({**row, "ig_hub": True})
    return found


async def check(tx: Tx, hub: Any, company: Any, group_key: str) -> Readiness:
    from hq_api.domain import hiring
    from hq_api.domain import players as PL
    from hq_api.domain import servers as SV

    grow = await GR.row_of(tx, group_key)
    g = GR.render(grow)
    name = company.name_fa if getattr(company, "name_fa", None) else company.code
    checks: list[Check] = []
    m = await tx.first(
        GR.MEMBER_SQL + " WHERE m.group_id = :g AND m.company_id = :co", g=grow["id"], co=company.id
    )
    on = g.state == "on" and m is not None and m["state"] == "on"
    ig_server = CN.ig_hub()["server"]
    checks.append(
        _check(
            "group",
            on,
            f"عضویت در «{g.title_fa}»",
            "روشن است و روال‌ها اجرا میشوند."
            if on
            else (
                "عضویت شرکت متوقف شده است."
                if m is not None
                # ⟨2026-11-08⟩ Instagram through IG-Hub is every company's first channel; the
                # technical team registers it and the company joins by itself: no step of the owner's
                else "شرکت هنوز عضو نیست؛ با ثبت حساب اینستاگرام از راه "
                f"{ig_server} به دست تیم فنی خودکار عضو میشود."
            ),
            Fix(action="group.resume", label_fa="روشن کردن عضویت", target=f"{g.key}:{company.code}")
            if m is not None
            else None,
        )
    )
    # seats: each required one filled by an active employee
    holders = await GR.seat_holders(tx, company.id, sorted({s.role for s in g.seats}))
    for s in g.seats:
        if s.optional:
            continue
        emp = holders.get(s.role)
        checks.append(
            _check(
                f"seat:{s.seat}",
                emp is not None,
                f"جایگاه {s.title_fa}",
                "پر است." if emp else "هنوز کسی در این جایگاه نیست.",
                Fix(
                    action="hire",
                    label_fa=f"استخدام {s.title_fa}",
                    target=f"{company.code}:{s.role}",
                ),
            )
        )
    # hiring automatic (§29.10)
    h_state, h_mode = await hiring.state(tx), await hiring.mode(tx)
    auto = h_state == "open" and h_mode == "auto"
    checks.append(
        _check(
            "hiring",
            auto,
            "استخدام خودکار",
            "باز و خودکار است."
            if auto
            else ("استخدام باز است ولی خودکار نیست." if h_state == "open" else "استخدام بسته است."),
            Fix(action="hiring.open", label_fa="روشن کردن استخدام خودکار", target="holding"),
        )
    )
    # the month's envelope
    env = next((e for e in await hiring.envelopes(tx) if e.company == company.code), None)
    has_env = env is not None and bool(env.tokens_month)
    checks.append(
        _check(
            "envelope",
            has_env,
            "پاکت بودجه‌ی ماه",
            "تعیین شده است." if has_env else "برای این ماه پاکت بودجه‌ای تعیین نشده است.",
            Fix(action="envelope.set", label_fa="تعیین پاکت ماه", target=company.code),
        )
    )
    # channels, connections, sealed series
    conns = await CN.rows_of(tx, company.id)
    channels = [k for k in CN.PUBLISHING if k in conns]
    # ⟨2026-11-08⟩ the owner: Instagram, for every company, is read and published through IG-Hub;
    # a company without a channel row has it all the same (the technical team registers the
    # accounts here), so the owner never reads «no channel» or a step of his own for it
    checks.append(
        _check(
            "channels",
            True,
            "کانال انتشار",
            "، ".join(CN.LABEL_FA[k] for k in channels)
            if channels
            else CN.IG_HUB_TEAM_FA.format(server=ig_server) + ".",
        )
    )
    sealed = await tx.all(
        "SELECT targets FROM media.series WHERE company_id = :co AND status = 'sealed'",
        co=company.id,
    )
    sealed_channels = {
        str(t.get("channel")) for r in sealed for t in r["targets"] or [] if isinstance(t, dict)
    }
    for k in channels:
        row = conns[k]
        st = CN.state_of(k, row)
        if k == "instagram":
            # ⟨2026-11-08⟩ always through IG-Hub: the accounts when registered, else the technical
            # team's registration; never «not connected», never a fix for the owner
            checks.append(
                _check(f"connection:{k}", True, f"اتصال {CN.LABEL_FA[k]}", CN.ig_hub_line(row))
            )
        else:
            need = CN.missing(k, row.get("config") or {}, bool(row.get("secret_set")))
            detail = (
                "وصل است."
                if st == "connected"
                else (
                    row.get("last_error_fa")
                    if st == "error"
                    else "هنوز لازم است: " + "، ".join(need) + "."
                )
            )
            checks.append(
                _check(
                    f"connection:{k}",
                    st == "connected",
                    f"اتصال {CN.LABEL_FA[k]}",
                    str(detail or ""),
                    Fix(action="connection.guide", label_fa="راهنمای وصل کردن", target=k),
                )
            )
        ok = k in sealed_channels or (k == "instagram" and "runner" in sealed_channels)
        checks.append(
            _check(
                f"series:{k}",
                ok,
                f"سری انتشار مُهرشده برای {CN.LABEL_FA[k]}",
                "دست‌کم یک سری مُهرشده هست." if ok else "هنوز هیچ سری انتشار مُهرشده‌ای نیست.",
                Fix(
                    action="series.propose",
                    label_fa="پیشنهاد سری انتشار",
                    target=f"{company.code}:{k}",
                ),
            )
        )
    # (⟨2026-11-08⟩ no `media_tools` check: the hub has no video tool and voice is off, by the
    # owner's decision; neither is his step)
    # the players: Claude takes the work unless the holding is locked
    lock = await gate.holding_lock(tx)
    ready = []
    for p in PL.SUBSTITUTES:
        try:
            if await PL.availability(tx, p) is None:
                ready.append(PL.PLAYER_FA.get(p, p))
        except Exception:  # noqa: BLE001, S112 - a substitute not readable: not counted ready
            continue
    checks.append(
        _check(
            "players",
            lock is None,
            "بازیکن‌ها",
            ("Claude آماده است" + ("؛ آماده‌های دیگر: " + "، ".join(ready) if ready else "") + ".")
            if lock is None
            else "کلید توقف هلدینگ روشن است؛ هیچ بازیکنی کار نمیگیرد.",
            Fix(action="lock.open", label_fa="باز کردن قفل", target="holding"),
        )
    )
    # the runners the group reads through
    servers = await _servers_needed(tx, company, conns)
    down = [r for r in servers if r.get("missing") or SV.state_of(r) != "online"]
    checks.append(
        _check(
            "runner",
            not down,
            "دستیار سرور",
            ("روشن است." if servers else "این کارگروه سروری از این شرکت لازم ندارد.")
            if not down
            else "خاموش یا وصل‌نشده: "
            + "، ".join(
                str(r.get("name")) if r.get("ig_hub") else f"{name} · {r.get('name')}"
                for r in down[:3]
            )
            + ".",
            Fix(
                action="runner.check",
                label_fa="روشن کردن دستیار سرور",
                target=f"{down[0].get('company') or company.code}:{down[0].get('name')}"
                if down
                else "",
            ),
        )
    )
    return Readiness(
        company=company.code, group=g.key, ready=all(c.ok for c in checks), checks=checks
    )
