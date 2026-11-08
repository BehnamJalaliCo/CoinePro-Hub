"""Prompt 21 part 3 (contract §29.9): a company's readiness for a working
group. Every check of §29.9 by rule, each failed one with its one-tap fix
(hire, hiring.open, envelope.set, connection.guide, series.propose,
media.on, lock.open, runner.check, group.resume); plain Persian only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import groups as GR
from hq_api.domain import humanize as H
from hq_api.hub import Hub

from .conftest import signed_put
from .p10_fakes import holding_switch


def checks(r: httpx.Response) -> dict[str, dict[str, Any]]:
    assert r.status_code == 200, r.text
    body = r.json()
    for c in body["checks"]:
        assert H.check(c["title_fa"]) == [] and H.check(c["detail_fa"]) == [], c
        # a fix only when it failed; ⟨2026-11-08⟩ a failed check may carry none when the step is
        # the technical team's (the membership that follows the Instagram registration)
        assert c["fix"] is None or not c["ok"], c
        if c["fix"]:
            assert H.check(c["fix"]["label_fa"]) == [] and c["fix"]["action"], c
    assert body["ready"] == all(c["ok"] for c in body["checks"])
    return {c["key"]: c for c in body["checks"]}


async def auto_hiring(su: Any) -> None:
    """§29.10 hiring open in mode auto, as migration 0037 leaves it (another
    test may have closed it)."""
    await su.execute(
        """INSERT INTO core.hiring (company_id, state, mode)
           SELECT id, 'open', 'auto' FROM core.companies WHERE kind = 'holding'
           ON CONFLICT (company_id) DO UPDATE SET state = 'open', mode = 'auto'"""
    )


async def test_every_check_and_its_fix_for_a_company_without_a_channel(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    await auto_hiring(su)
    async with holding_switch(su, "engaged"):
        r = await client.get(f"/api/v1/companies/{co['code']}/readiness", headers=owner,
                             params={"group": "content"})  # fmt: skip
    c = checks(r)
    assert r.json()["ready"] is False and r.json()["group"] == "content"
    # ⟨2026-11-08⟩ the owner: Instagram is IG-Hub for every company; no step of his for a channel
    assert c["group"]["ok"] is False and c["group"]["fix"] is None  # not a member yet
    assert "IG-Hub" in c["group"]["detail_fa"] and "تیم فنی" in c["group"]["detail_fa"]
    assert c["channels"]["ok"] is True and c["channels"]["fix"] is None
    assert c["channels"]["detail_fa"].startswith("اینستاگرام از راه IG-Hub")
    assert "media_tools" not in c  # no video tool, voice off: never a readiness item
    # the lead's seat is the media department's head; the others empty, each with `hire`
    assert c["seat:media_director"]["ok"] is True
    for seat, role in (("scriptwriter", "scriptwriter"), ("publisher", "publisher"),
                       ("content_analyst", "content_analyst"), ("visual_designer", "visual_designer"),
                       ("motion_designer", "motion_designer")):  # fmt: skip
        assert c[f"seat:{seat}"]["fix"] == {
            "action": "hire",
            "label_fa": c[f"seat:{seat}"]["fix"]["label_fa"],
            "target": f"{co['code']}:{role}",
        }
    assert "seat:video_director" not in c  # optional seats are no gap
    # ⟨21⟩ §29.10: hiring is automatic for every company from migration 0037 on
    assert c["hiring"]["ok"] is True
    assert c["envelope"]["fix"] == {"action": "envelope.set", "label_fa": "تعیین پاکت ماه",
                                    "target": co["code"]}  # fmt: skip
    assert c["players"]["fix"]["action"] == "lock.open"  # the holding is locked
    assert c["runner"]["ok"] is True  # no server the group reads through


async def test_a_member_with_channels_series_runner_and_envelope(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    ig, co = await new_company(), await new_company()
    c = co["code"]
    body = {"config": {"via": "ig_hub", "accounts": ["@shop"], "command": "cat /srv/ig/d.json",
                       "server": {"company": ig["code"], "name": "IG-Hub"}}}  # fmt: skip
    r = await signed_put(client, hub, owner_session, f"/api/v1/companies/{c}/connections/instagram",
                         body, "connection.config")  # fmt: skip
    assert r.status_code == 200, r.text
    async with holding_switch(su, "released"):
        await GR.tick(hub, only={co["id"]})  # it joins (a channel)
        got = checks(await client.get(f"/api/v1/companies/{c}/readiness", headers=h))
    assert got["group"]["ok"] and got["channels"]["ok"] and got["players"]["ok"]
    # IG-Hub is not paired yet: the runner check names it, with its fix
    assert got["runner"]["fix"] == {"action": "runner.check", "label_fa": "روشن کردن دستیار سرور",
                                    "target": f"{ig['code']}:IG-Hub"}  # fmt: skip
    assert "IG-Hub" in got["runner"]["detail_fa"]
    # Instagram needs no secret on the hub: with its command and accounts it is connected
    assert got["connection:instagram"]["ok"] is True
    assert (
        got["connection:instagram"]["detail_fa"] == "از راه IG-Hub خوانده و منتشر میشود (1 حساب)."
    )
    assert got["series:instagram"]["fix"] == {"action": "series.propose",
                                              "label_fa": "پیشنهاد سری انتشار",
                                              "target": f"{c}:instagram"}  # fmt: skip
    await su.execute(
        """INSERT INTO infra.servers (company_id, origin, name, state, last_seen_at)
           VALUES ($1, 'attached', 'IG-Hub', 'online', now())""",
        ig["id"],
    )
    await su.execute(
        """INSERT INTO media.series (company_id, title_fa, kind, targets, schedule, format, checks,
               max_per_day, status, digest, proposed_by_kind, proposed_by_code, sealed_at, sealed_digest)
           VALUES ($1, 'سری آزمایشی', 'reel', '[{"channel": "instagram"}]', 'FREQ=DAILY;BYHOUR=10',
                   '{}', ARRAY['qc'], 1, 'sealed', repeat('b', 64), 'agent', 'x', now(), repeat('b', 64))""",
        co["id"],
    )
    await su.execute(
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', 2000000)""",
        co["id"],
        c,
    )
    # a paused membership is a gap with its own fix
    await client.put(f"/api/v1/groups/content/members/{c}", headers=h, json={"state": "paused"})
    async with holding_switch(su, "released"):
        got = checks(await client.get(f"/api/v1/companies/{c}/readiness", headers=h))
    assert got["runner"]["ok"] and got["series:instagram"]["ok"] and got["envelope"]["ok"]
    assert got["group"]["fix"] == {"action": "group.resume", "label_fa": "روشن کردن عضویت",
                                   "target": f"content:{c}"}  # fmt: skip
    missing = await client.get(f"/api/v1/companies/{c}/readiness", headers=h,
                               params={"group": "nogroup"})  # fmt: skip
    assert missing.status_code == 404


async def test_a_failed_checks_fix_is_one_tap(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    """§29.9 `POST /companies/{code}/readiness/fix`: `hire` fills the seat by
    automatic hiring (§29.10), a fix the app does itself answers unchanged,
    an unknown action is refused."""
    co = await new_company()
    await auto_hiring(su)
    url = f"/api/v1/companies/{co['code']}/readiness"
    await su.execute(  # automatic hiring stays inside the company's month envelope
        """INSERT INTO llm.budgets (company_id, scope_type, scope_ref, period, token_limit)
           VALUES ($1, 'company', $2, 'month', 2000000)""",
        co["id"],
        co["code"],
    )
    r = await client.post(f"{url}/fix", headers=owner,
                          json={"group": "content", "action": "hire", "target": f"{co['code']}:publisher"})  # fmt: skip
    c = checks(r)
    assert c["seat:publisher"]["ok"] is True, c["seat:publisher"]
    assert (
        await su.fetchval(
            """SELECT count(*) FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE c.code = $1 AND e.role = 'publisher' AND e.status = 'active'""",
            co["code"],
        )
        == 1
    )
    r = await client.post(f"{url}/fix", headers=owner,
                          json={"group": "content", "action": "connection.guide", "target": "instagram"})  # fmt: skip
    # (an app-side fix answers the readiness unchanged; ⟨2026-11-08⟩ `channels` is ok for every
    # company: Instagram through IG-Hub)
    assert r.status_code == 200 and checks(r)["channels"]["ok"] is True
    r = await client.post(f"{url}/fix", headers=owner, json={"action": "delete.everything"})
    assert r.status_code == 422
