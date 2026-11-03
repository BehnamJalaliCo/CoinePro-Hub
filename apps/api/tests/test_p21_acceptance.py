"""Prompt 21's acceptance in one path (the plan's step 4, the builder's stage D):
the owner's clip order of prompt 20 goes through the secretary to the media
department (never AI operations), its report answers at once in plain Persian,
the content working group runs for the company that has a channel, and a
technical finding raised meanwhile never reaches the owner's lists or home."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import groups as GR
from hq_api.domain import humanize as H
from hq_api.domain import oversight as O
from hq_api.hub import Hub

from .p10_fakes import holding_switch
from .test_p21_groups import TEHRAN, at, channel
from .test_p21_secretary import (
    CLIP,
    ig,
    no_model,  # noqa: F401 - a fixture here too
    post_order,
    preview,
    work_of,
)

pytestmark = pytest.mark.usefixtures("no_model")


async def test_the_tradeyar_clip_order_end_to_end(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    await ig(su, new_company)
    # 1. the secretary: media department, reels, one player, a budget from the table
    route = await preview(client, owner, CLIP)
    assert (route["department"], route["output_kind"], route["mode"]) == ("MEDIA", "reel", "single")
    out = await post_order(client, owner, CLIP)
    root = out["routes"][0]
    assert root["to"].endswith("-MEDIA-MGR")
    w = await work_of(su, root["work_ref"])
    assert w["dept"] == "MEDIA" and w["status"] in ("queued", "in_progress")

    # 2. the order report answers at once, in plain Persian
    r = await client.get(f"/api/v1/orders/{out['ref']}/report", headers=owner)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["state"] not in ("delivered", "failed", "cancelled")
    assert rep["steps"], rep
    texts = [s["what_fa"] for s in rep["steps"]] + [s["who_fa"] for s in rep["steps"]]
    texts += [b["title_fa"] for b in rep["blockers"]] + [b["detail_fa"] for b in rep["blockers"]]
    for t in texts:
        assert H.check(t) == [], t

    # 3. TradeYar's content group: the signal channel makes it a member; the plan runs
    ty = await su.fetchrow("SELECT id, code FROM core.companies WHERE code = 'TY'")
    assert ty is not None
    await channel(client, hub, owner_session, "TY")
    # a day no earlier run used (the routines run once per period; the database outlives a run)
    day = datetime.now(TEHRAN).date() + timedelta(days=secrets.randbelow(3000) + 30)
    async with holding_switch(su, "released"):
        await GR.tick(hub, now=at(day, 3, 0), only={ty["id"]})
        ran = await GR.tick(hub, now=at(day, 8, 0), only={ty["id"]})
    assert ran["queued"] >= 1, ran
    members = (await client.get("/api/v1/groups/content/members", headers=owner)).json()
    mine = next(m for m in members if m["company"] == "TY")
    assert mine["state"] == "on"

    # 4. a technical finding of TradeYar goes to its CTO, not to the owner
    async with hub.db.tx(await hub.companies.ids()) as tx:
        tech, _ = await O.raise_finding(
            tx, company_id=ty["id"], company_code="TY", severity="high",
            title_fa="گواهی سایت در حال انقضاست", kind="security", by_code="HQ-OVR", by_kind="agent",
        )  # fmt: skip
    assert tech["owner_visible"] is False and tech["routed_to"].startswith("TY-")
    mine = await client.get("/api/v1/oversight/findings?company=TY", headers=owner)
    assert tech["ref"] not in {f["ref"] for f in mine.json()["items"]}
    home = (await client.get("/api/v1/home", headers=owner)).json()
    assert all("گواهی" not in (n.get("title_fa") or "") for n in home["critical"])
    for line in home["morning"]:
        assert H.check(line) == [], line
