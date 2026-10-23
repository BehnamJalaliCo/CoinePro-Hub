"""Prompt 13 §1 and §5 (contract §22.1): a department's mandate, identity and
starting team; MEDIA for every company (new and existing, by migration, no
employee made); LEGAL and HQ-LGL for the holding; the identity in the prompt
of its own department only; the media charters' tools."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.domain import departments as DM
from hq_api.hub import Hub

from .conftest import step_up

MEDIA_TEAM = {
    "scriptwriter", "video_director", "motion_designer", "voice_producer", "visual_designer", "ui_designer",
}  # fmt: skip


async def _depts(client: httpx.AsyncClient, h: dict[str, str], code: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/companies/{code}/departments", headers=h)
    assert r.status_code == 200, r.text
    return {d["code"]: d for d in r.json()}


async def test_a_new_company_has_media_with_its_mandate_identity_and_team(
    client: httpx.AsyncClient, owner: dict[str, str], hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    depts = await _depts(client, owner, co["code"])
    media = depts["MEDIA"]
    assert media["name_fa"] == "رسانه و طراحی" and media["sort"] == 25
    assert media["manager"]["code"] == f"{co['code']}-MEDIA-MGR"
    assert media["mandate"]["model_ceiling"] == "claude-opus-5-5"
    assert {"media.item", "media.render", "media.voice"} <= set(media["mandate"]["tool_ceiling"])
    assert "media.review" not in media["mandate"]["tool_ceiling"]  # the director's alone
    assert not {"hire.decide", "role.decide", "message.owner"} & set(
        media["mandate"]["tool_ceiling"]
    )
    assert (
        media["mandate"]["from_fa"] and media["mandate"]["to_fa"] and media["mandate"]["outputs_fa"]
    )
    assert "IRANYekanX" in media["identity_md"]
    assert {t["role"] for t in media["team"]} == MEDIA_TEAM
    assert {t["role"] for t in media["team"] if t["first"]} == MEDIA_TEAM - {"ui_designer"}
    # The team lists only live charters: TECH's staged roles are not there yet.
    lib = hub.charters
    for d in depts.values():
        for t in d["team"]:
            assert lib.get(t["role"]) is not None, t
    assert [t["role"] for t in depts["TECH"]["team"]] == ["sre"]
    assert depts["GROWTH"]["team"] == []  # its charters are staged, not live
    tpl = (await client.get("/api/v1/templates", headers=owner)).json()
    std = next(t for t in tpl if t["key"] == "standard")
    bp = {d["code"]: d for d in std["blueprint"]}
    assert (
        bp["MEDIA"]["head_role"] == "media_director"
        and bp["MEDIA"]["mandate"]["model_ceiling"] == "claude-opus-5-5"
    )
    holding = next(t for t in tpl if t["key"] == "holding")
    assert {d["code"]: d["manager"] for d in holding["blueprint"]}["LEGAL"] is False


async def test_an_existing_company_gets_media_by_migration_and_no_employee(
    su: Any, hub: Hub, owner_db: Any
) -> None:
    """The data step of migration 0028 on a company made before it (no MEDIA)."""
    import importlib.util

    from hq_api.domain import templates

    from .conftest import random_code

    code = random_code("M")
    async with owner_db.raw() as tx:
        await tx.exec("SET LOCAL ROLE hq")
        row = await tx.one(
            """INSERT INTO core.companies (code, name, kind, name_fa, name_en, template)
               VALUES (:c, :c, 'company', :c, :c, 'standard') RETURNING id""",
            c=code,
        )
        before = [
            d["code"] for d in templates.template("standard")["departments"] if d["code"] != "MEDIA"
        ]
        await templates.apply(tx, row["id"], code, "standard", departments=before)
    hub.companies.invalidate()
    assert not await su.fetchval(
        "SELECT 1 FROM core.departments WHERE company_id = $1 AND code = 'MEDIA'", row["id"]
    )
    spec = importlib.util.spec_from_file_location(
        "m0028", "/api/migrations/versions/0028_media_studio.py"
    )
    assert spec is not None and spec.loader is not None
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    await su.execute(mig.DATA)
    await su.execute(mig.DATA)  # idempotent
    mgr = await su.fetchrow(
        """SELECT e.kind, e.role, e.activity, d.code AS dept FROM core.employees e
           JOIN core.departments d ON d.id = e.department_id WHERE e.code = $1""",
        f"{code}-MEDIA-MGR",
    )
    assert dict(mgr) == {
        "kind": "manager",
        "role": "media_director",
        "activity": "sleeping",
        "dept": "MEDIA",
    }
    threads = await su.fetch(
        "SELECT kind FROM msg.threads WHERE code = ANY($1)", [f"{code}-MEDIA-MGR", f"{code}-MEDIA"]
    )
    assert sorted(t["kind"] for t in threads) == ["department", "manager"]
    assert (
        await su.fetchval(
            "SELECT count(*) FROM core.employees WHERE company_id = $1 AND kind = 'employee'",
            row["id"],
        )
        == 0
    )


async def test_the_holding_has_legal_and_its_counsel_asleep(su: Any) -> None:
    row = await su.fetchrow(
        """SELECT e.kind, e.role, e.activity, e.status, d.code AS dept, e.reports_to,
                  (SELECT count(*) FROM core.employees m WHERE m.department_id = d.id AND m.kind = 'manager') AS managers
           FROM core.employees e JOIN core.departments d ON d.id = e.department_id
           JOIN core.companies c ON c.id = e.company_id
           WHERE c.kind = 'holding' AND e.code = c.code || '-LGL'"""
    )
    assert row is not None
    assert (row["kind"], row["role"], row["activity"], row["dept"]) == (
        "employee",
        "legal_counsel",
        "sleeping",
        "LEGAL",
    )
    assert row["managers"] == 0 and row["reports_to"] is None


async def test_the_identity_is_in_the_prompt_of_its_department_only(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    sql = "SELECT id FROM core.departments WHERE company_id = $1 AND code = $2"
    media = await su.fetchval(sql, co["id"], "MEDIA")
    tech = await su.fetchval(sql, co["id"], "TECH")
    async with hub.db.tx([co["id"]]) as tx:
        text, doc = await DM.identity(tx, media)
        other, other_doc = await DM.identity(tx, tech)
        none = await DM.identity(tx, None)
    assert (
        "رسانه و طراحی: آموزگار خوش‌سلیقه" in text and doc and doc.startswith(f"{co['code']}-MEDIA@")
    )
    assert (
        "رسانه و طراحی" not in other and other_doc and other_doc.startswith(f"{co['code']}-TECH@")
    )
    assert none == ("", None)


async def test_a_run_reads_its_departments_identity_after_the_charter_and_records_it(
    agents: Any, hub: Hub, new_company: Callable[..., Any], su: Any, client: httpx.AsyncClient,
    owner: dict[str, str],
) -> None:  # fmt: skip
    from .test_agents import order, run, runs_of, step

    co = (await new_company())["code"]
    w = await order(client, owner, co, title="یک برنامه‌ی انتشار پیشنهاد بده", brief="رسانه")
    await su.execute(
        """UPDATE work.work SET assignee_id = (SELECT id FROM core.employees WHERE code = $1)
           WHERE id = $2""",
        f"{co}-MEDIA-MGR",
        __import__("uuid").UUID(w["id"]),
    )
    queued = [r for r in await runs_of(su, f"{co}-MEDIA-MGR") if r["state"] == "queued"]
    assert queued
    agents.fake.enqueue(f"{co}-MEDIA-MGR", step("دیدم.", ("activity.set", {"state": "working"})))
    calls = len(agents.fake.calls)
    out = await run(agents, queued[-1]["id"])
    assert out["state"] in ("done", "failed"), out
    system = next(c.system for c in agents.fake.calls[calls:] if c.actor_ref == f"{co}-MEDIA-MGR")
    assert system is not None
    charter_at = system.index("# Your role")
    identity_at = system.index("# Your department: Media and Design (MEDIA)")
    assert charter_at < identity_at
    if "# Skills" in system:
        assert identity_at < system.index("# Skills")
    doc = await su.fetchval("SELECT identity_doc FROM agents.runs WHERE id = $1", queued[-1]["id"])
    assert doc and doc.startswith(f"{co}-MEDIA@")
    # Another department's run does not read it.
    cto = list(await runs_of(su, f"{co}-CEO"))
    assert cto  # the order woke the CEO first; its prompt has no department identity
    agents.fake.enqueue(f"{co}-CEO", step("دیدم.", ("activity.set", {"state": "working"})))
    calls = len(agents.fake.calls)
    await run(agents, cto[-1]["id"])
    ceo_system = next(c.system for c in agents.fake.calls[calls:] if c.actor_ref == f"{co}-CEO")
    assert ceo_system is not None and "# Your department:" not in ceo_system


async def test_the_owner_changes_a_mandate_sealed_on_the_body(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    d = (await _depts(client, h, co["code"]))["MEDIA"]
    body = {
        "mandate": {**d["mandate"], "to_fa": "هر روز یک ریلز درست"},
        "identity_md": "آرام و دقیق.",
    }
    path = f"/api/v1/companies/{co['code']}/departments/MEDIA/mandate"
    content = json.dumps(body, ensure_ascii=False).encode()
    r = await client.put(
        path,
        content=content,
        headers={**h, "If-Match": str(d["version"]), "Content-Type": "application/json"},
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_ = await step_up(
        hub, owner_session["session_id"], "department.mandate", hashlib.sha256(content).hexdigest()
    )
    r = await client.put(
        path,
        content=content,
        headers={**h, **su_, "If-Match": str(d["version"]), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["mandate"]["to_fa"] == "هر روز یک ریلز درست"
        and r.json()["identity_md"] == "آرام و دقیق."
    )
    bad = {
        "mandate": {**d["mandate"], "tool_ceiling": ["hire.decide", "nope.tool"]},
        "identity_md": "",
    }
    content = json.dumps(bad).encode()
    su_ = await step_up(
        hub, owner_session["session_id"], "department.mandate", hashlib.sha256(content).hexdigest()
    )
    r = await client.put(
        path,
        content=content,
        headers={
            **h,
            **su_,
            "If-Match": str(r.json()["version"]),
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 422
    assert set(r.json()["fields"]) == {"mandate.tool_ceiling.0", "mandate.tool_ceiling.1"}


@pytest.mark.parametrize("tool", ["media.review"])
def test_the_media_charters_tools_are_all_in_the_catalog(hub: Hub, tool: str) -> None:
    """§5: every tool of every charter is in tools.md; media.review is the media
    director's alone; email.draft and mail.read the legal counsel's alone."""
    lib = hub.charters
    assert not [p for p in lib.problems if "not in agents/tools.md" in p], lib.problems
    for role in (*MEDIA_TEAM, "media_director", "legal_counsel"):
        c = lib.get(role)
        assert c is not None, role
        assert all(t in lib.tools for t in c.tools)
    holders = {r for r, c in lib.roles.items() if tool in c.tools}
    assert holders == {"media_director"}
    assert {r for r, c in lib.roles.items() if "email.draft" in c.tools} == {"legal_counsel"}
    assert {r for r, c in lib.roles.items() if "mail.read" in c.tools} == {"legal_counsel"}
    assert lib.get("motion_designer").model == "claude-opus-5-5"  # type: ignore[union-attr]
    assert {"media.item", "media.render", "substitute.call"} <= set(
        lib.get("motion_designer").tools
    )  # type: ignore[union-attr]
