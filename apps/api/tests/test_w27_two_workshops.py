"""⟨2026-11-26⟩ Two workshops (the owner: «کارگاه دوم رو روی سرور تردیار راه بنداز»).

The holding may pair a second workshop. A work stays on the workshop its folder lives on; a flow's
NEW day goes to the online workshop with the fewest open jobs (the first one on a tie); the flows
whose package a hub-host script reads from the workshop's folder stay on the first workshop; every
other caller keeps the first one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import hands as HANDS
from hq_api.hub import Hub

from .test_p17_runners import pair, poll
from .test_w14_workshop import a_work, run_ask, workshop


async def second(client: httpx.AsyncClient, hub: Hub, owner: dict[str, Any]) -> dict[str, Any]:
    holding = await hub.companies.holding()
    rn = await pair(client, hub, owner, {"code": holding.code, "id": holding.id}, "workshop-2")
    rn["h"] = {**rn["h"], "X-HQ-Runner-Version": "0.3.6"}
    r = await poll(client, rn)
    assert r.status_code in (200, 204), r.text
    return rn


async def pick(hub: Hub, w: dict[str, Any] | None, spread: bool = False) -> str:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        s = await HANDS.workshop_server(tx, w, spread=spread)
    assert s is not None
    return str(s["name"])


async def test_a_flow_day_goes_to_the_least_busy_workshop_and_a_folder_never_moves(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    h = owner_session["headers"]
    first = await workshop(client, hub, owner_session, su, version="0.3.6")
    assert first["server"]["name"] == "workshop"
    await second(client, hub, owner_session)

    co = await new_company()
    w = await a_work(client, h, co["code"])
    wid = uuid.UUID(w["id"])

    def as_flow(key: str) -> dict[str, Any]:
        return {"id": wid, "run_meta": json.dumps({"flow": {"key": key}})}

    # Nothing open anywhere: the first workshop, for every caller.
    assert await pick(hub, None) == "workshop"
    assert await pick(hub, as_flow("prochart_reels"), spread=True) == "workshop"

    # A turn runs on the first workshop: a NEW flow day goes to the second one...
    who = await su.fetchval(
        """SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.id = $1""",
        wid,
    )
    r = await run_ask(client, who, {"brief": "x", "work": w["ref"]})
    assert r.status_code == 201 and r.json()["server"] == "workshop", r.text
    other = await a_work(client, h, co["code"])
    other_flow = {"id": uuid.UUID(other["id"]), "run_meta": {"flow": {"key": "prochart_reels"}}}
    assert await pick(hub, other_flow, spread=True) == "workshop-2"
    # ...but not a flow whose package the hub host reads from the first workshop's folder,
    for key in HANDS.HOST_BOUND_FLOWS:
        bound = {"id": uuid.UUID(other["id"]), "run_meta": {"flow": {"key": key}}}
        assert await pick(hub, bound, spread=True) == "workshop"
    # ...and never a work whose folder lives on the first one (spread or not).
    assert await pick(hub, as_flow("prochart_reels"), spread=True) == "workshop"
    # Callers that do not spread keep the first workshop.
    assert await pick(hub, other_flow) == "workshop"

    # The second workshop offline: nothing goes there.
    await su.execute("UPDATE infra.servers SET state = 'offline' WHERE name = 'workshop-2'")
    assert await pick(hub, other_flow, spread=True) == "workshop"


def test_the_flow_key_is_read_from_the_work() -> None:
    assert HANDS.flow_key_of({"run_meta": {"flow": {"key": "dotcoin_long"}}}) == "dotcoin_long"
    assert HANDS.flow_key_of({"run_meta": json.dumps({"flow": {"key": "x"}})}) == "x"
    assert HANDS.flow_key_of({"run_meta": "not json"}) is None
    assert HANDS.flow_key_of({"run_meta": None}) is None
    assert HANDS.flow_key_of(None) is None
