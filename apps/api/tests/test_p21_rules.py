"""Prompt 21 part 2 (contract §29.3): the owner's rules from the app:
proposed -> sealed (🔏) -> applied by applies_to -> a new version -> the
first enforcement report 24 hours after the seal -> retired. Every rule a
test seals is retired again (the test database outlives a run)."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hq_api.domain import humanize
from hq_api.domain import oversight as OV
from hq_api.domain import rules as R
from hq_api.hub import Hub

from .conftest import idem, step_up


@pytest.fixture
async def made(client: httpx.AsyncClient, owner: dict[str, str]) -> AsyncIterator[list[str]]:
    refs: list[str] = []
    yield refs
    for ref in refs:
        await client.post(f"/api/v1/rules/{ref}/retire", headers=owner)


async def add(
    client: httpx.AsyncClient, owner: dict[str, str], text: str, made: list[str]
) -> dict[str, Any]:
    r = await client.post("/api/v1/rules", headers={**owner, **idem()}, json={"text": text})
    assert r.status_code == 201, r.text
    made.append(r.json()["ref"])
    return dict(r.json())


async def seal(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ref: str
) -> dict[str, Any]:
    su = await step_up(hub, owner_session["session_id"], "rule.seal", ref)
    r = await client.post(
        f"/api/v1/oversight/orders/{ref}/seal", headers={**owner_session["headers"], **su}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_the_owners_words_become_a_precise_rule() -> None:
    text = R.clean(
        "قانون تازه: لطفاً  از این به بعد هر خروجی منبع داشته باشد. ببین، عدد بی منبع نده"
    )
    assert text.splitlines() == ["از این به بعد هر خروجی منبع داشته باشد.", "عدد بی منبع نده."]
    assert R.needs_model(text) and not R.needs_model("هر خروجی منبع داشته باشد.")
    assert R.model_text({"routes": [{"text_fa": "هر خروجی منبع داشته باشد."}]})
    assert R.model_text({"routes": [{"text_fa": "Every output has a source."}]}) is None


async def test_a_rule_is_proposed_sealed_applied_by_whom_it_names_and_retired(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    made: list[str],
) -> None:
    owner = owner_session["headers"]
    tag = secrets.token_hex(3)
    ceo = await add(
        client, owner, f"قانون تازه: لطفاً مدیرعامل هیچ کاری را بی گزارش روزانه نبندد {tag}", made
    )
    assert ceo["status"] == "proposed" and ceo["applies_to"] == {"roles": ["ceo"]}
    assert "لطفاً" not in ceo["text_md"] and not ceo["text_md"].startswith("قانون")
    assert ceo["owner_text"].startswith("قانون تازه") and ceo["counts"]["runs"] == 0
    ty = await add(client, owner, f"در تریدیار هر پست هشدار ریسک داشته باشد {tag}", made)
    assert ty["applies_to"] == {"companies": ["TY"]}
    every = await add(client, owner, f"هیچ عددی بی منبع نوشته نشود {tag}", made)
    assert every["applies_to"] == "all"
    watch = await add(client, owner, f"ناظر هر روز خروجی‌های بی منبع را بشمارد {tag}", made)
    assert watch["applies_to"] == "overseer"
    # nothing applies before the seal; the seal is the 🔏 one (rule.seal or oversight.order)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert not any(o["ref"] == ceo["ref"] for o in await R.for_run(tx, "ceo", "ceo", "TY"))
    plain = await client.post(f"/api/v1/oversight/orders/{ceo['ref']}/seal", headers=owner)
    assert plain.status_code == 403
    for r in (ceo, ty, every, watch):
        assert (await seal(client, hub, owner_session, r["ref"]))["status"] == "sealed"

    async def refs(kind: str, role: str | None, company: str | None) -> set[str]:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            return {o["ref"] for o in await R.for_run(tx, kind, role, company)} & set(made)

    assert await refs("ceo", "ceo", "FX") == {ceo["ref"], every["ref"]}
    assert await refs("manager", "media_director", "TY") == {ty["ref"], every["ref"]}
    assert await refs("overseer", "overseer", "HQ") == {watch["ref"], every["ref"]}
    # the runner's call today names only the kind: all and the overseer's own
    async with hub.db.tx(await hub.companies.ids()) as tx:
        today = {o["ref"] for o in await OV.sealed_orders(tx, "ceo")} & set(made)
        section = OV.orders_section(await OV.sealed_orders(tx, "ceo", "ceo", "TY"))
    assert today == {every["ref"]}
    assert ceo["ref"] in section and ty["ref"] in section
    listed = {r["ref"]: r for r in (await client.get("/api/v1/rules", headers=owner)).json()}
    assert listed[ceo["ref"]]["status"] == "sealed" and "counts" in listed[ceo["ref"]]
    # the standing orders' list shows the widened applies_to too
    so = {o["ref"]: o for o in (await client.get("/api/v1/oversight/orders", headers=owner)).json()}
    assert so[ty["ref"]]["applies_to"] == {"companies": ["TY"]}
    # retired: it stops applying
    r = await client.post(f"/api/v1/rules/{ty['ref']}/retire", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "retired"
    assert await refs("manager", "media_director", "TY") == {every["ref"]}


async def test_a_new_version_is_sealed_and_keeps_the_old_one(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    made: list[str],
) -> None:
    owner = owner_session["headers"]
    r = await add(client, owner, f"هر گزارش منبع داشته باشد {secrets.token_hex(3)}", made)
    await seal(client, hub, owner_session, r["ref"])
    body = {
        "text_md": "هر گزارش و هر پست منبع داشته باشد.",
        "applies_to": {"roles": ["ceo", "cto"]},
    }
    plain = await client.put(f"/api/v1/rules/{r['ref']}", headers=owner, json=body)
    assert plain.status_code == 403  # 🔏
    su = await step_up(hub, owner_session["session_id"], "rule.seal", r["ref"])
    v2 = await client.put(f"/api/v1/rules/{r['ref']}", headers={**owner, **su}, json=body)
    assert v2.status_code == 200, v2.text
    out = v2.json()
    assert out["text_md"] == body["text_md"] and out["applies_to"] == {"roles": ["ceo", "cto"]}
    assert out["status"] == "sealed" and out["version"] > r["version"]
    assert (
        out["history"][-1]["text_md"] == r["text_md"] and out["history"][-1]["applies_to"] == "all"
    )
    await client.post(f"/api/v1/rules/{r['ref']}/retire", headers=owner)
    su = await step_up(hub, owner_session["session_id"], "rule.seal", r["ref"])
    again = await client.put(f"/api/v1/rules/{r['ref']}", headers={**owner, **su}, json=body)
    assert again.status_code == 409


async def test_the_first_enforcement_report_comes_24_hours_after_the_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    made: list[str],
) -> None:
    owner = owner_session["headers"]
    r = await add(client, owner, f"هیچ خروجی بی هشدار ریسک منتشر نشود {secrets.token_hex(3)}", made)
    await seal(client, hub, owner_session, r["ref"])
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await R.report_due(tx)
    assert (
        await su.fetchval("SELECT report_at FROM oversight.orders WHERE ref = $1", r["ref"]) is None
    )
    await su.execute(
        "UPDATE oversight.orders SET sealed_at = now() - interval '25 hours' WHERE ref = $1",
        r["ref"],
    )
    for status in ("open", "fixed"):  # two violations the overseer found, one fixed
        await su.execute(
            """INSERT INTO oversight.findings (company_id, severity, title_fa, evidence, status,
                   answerable_kind, answerable_code, raised_by_kind, raised_by_code, due_at)
               VALUES ($1, 'medium', 'تخلف از دستور مالک', $2::jsonb, $3, 'agent', 'TY-CEO',
                       'agent', 'HQ-OVR', now() + interval '1 day')""",
            holding.id,
            json.dumps([{"kind": "order", "ref": r["ref"]}]),
            status,
        )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await R.report_due(tx) >= 1
        assert await R.report_due(tx) == 0  # once
    row = await su.fetchrow(
        "SELECT report_at, report FROM oversight.orders WHERE ref = $1", r["ref"]
    )
    report = json.loads(row["report"])
    assert row["report_at"] is not None and (report["violations"], report["fixed"]) == (2, 1)
    note = await su.fetchrow(
        """SELECT level, title_fa, body_fa, link_kind FROM notify.notifications
           WHERE link_kind = 'rule' AND link_ref = $1""",
        r["ref"],
    )
    assert note["level"] == "report"
    assert humanize.check(note["title_fa"]) == [] and humanize.check(note["body_fa"]) == []
    assert "چه شد" in note["body_fa"] and "2 تخلف" in note["body_fa"]
    seen = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.rule.report' AND payload->>'ref' = $1",
        r["ref"],
    )
    assert seen == 1
    listed = {x["ref"]: x for x in (await client.get("/api/v1/rules", headers=owner)).json()}
    assert listed[r["ref"]]["counts"]["violations"] == 2 and listed[r["ref"]]["report_at"]
