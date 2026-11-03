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
        assert (c["fix"] is None) == c["ok"], c  # a fix exactly when it failed
        if c["fix"]:
            assert H.check(c["fix"]["label_fa"]) == [] and c["fix"]["action"], c
    assert body["ready"] == all(c["ok"] for c in body["checks"])
    return {c["key"]: c for c in body["checks"]}


async def test_every_check_and_its_fix_for_a_company_without_a_channel(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    async with holding_switch(su, "engaged"):
        r = await client.get(f"/api/v1/companies/{co['code']}/readiness", headers=owner,
                             params={"group": "content"})  # fmt: skip
    c = checks(r)
    assert r.json()["ready"] is False and r.json()["group"] == "content"
    assert c["group"]["fix"]["action"] == "connection.guide"  # no channel: not a member yet
    assert c["channels"]["fix"] == {"action": "connection.guide",
                                    "label_fa": "راهنمای افزودن کانال", "target": "instagram"}  # fmt: skip
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
    assert c["hiring"]["fix"]["action"] == "hiring.open"
    assert c["envelope"]["fix"] == {"action": "envelope.set", "label_fa": "تعیین پاکت ماه",
                                    "target": co["code"]}  # fmt: skip
    assert c["media_tools"]["fix"]["action"] == "media.on"  # render and voice are off here
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
