"""⟨1.20⟩ The hub run from the app (contract §38, the owner, 2026-11-06: «نمیشه که یبار توی آپ من بگم
یبارم بیام به تو بگم یبار تو به سرور بگی»): the hub-ops catalogue, its jobs, the dispatcher's routes
with its own token, the A3 seal, the kill switch, masking, RLS, the owner's services page, and the
capability brief's `technical` («nobody says دسترسی ندارم»)."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from hq_api.domain import capabilities as CAP
from hq_api.domain import hub_ops as H
from hq_api.errors import ApiError
from hq_api.hub import Hub

from .conftest import agent_headers, hubops_headers, idem, step_up, substitutes_headers
from .p10_fakes import holding_switch

PS = "table {{.Service}}\t{{.State}}\t{{.Health}}\t{{.Status}}"


# ------------------------------------------------------------ the catalogue --
def test_the_catalogue_builds_exact_commands_from_validated_arguments() -> None:
    c = H.check("logs", {"service": "api", "lines": 50, "since": "30m"})
    assert (c.cls, c.argv) == (
        "A0",
        ["infra/compose/hq.sh", "logs", "--no-color", "--tail", "50", "--since", "30m", "api"],
    )
    assert H.check("status", {}).argv == ["infra/compose/hq.sh", "ps", "--all", "--format", PS]
    assert H.check("restart", {"service": "worker"}).argv[-2:] == ["restart", "worker"]
    p = H.check("profile", {"name": "media", "on": True})
    assert (p.cls, p.argv) == ("A2", ["infra/hubops/profile.sh", "media", "on"])
    sealed = H.check("profile", {"name": "media", "on": True, "turn_off": ["tts", "ocr"]})
    assert sealed.cls == "A3" and sealed.argv == [
        "infra/hubops/profile.sh",
        "media",
        "on",
        "ocr",
        "tts",
    ]
    create = H.check(
        "n8n.create", {"name": "خبر روزانه", "workflow_json": {"nodes": [{"type": "x"}]}}
    )
    assert create.cls == "A3" and create.argv == ["infra/hubops/n8n.sh", "create", "@workflow_json"]
    assert H.check("n8n.executions", {"limit": 5, "workflow": "abc123"}).argv[-2:] == [
        "5",
        "abc123",
    ]
    assert H.check("backup", {}).argv == ["make", "backup-hourly"]
    # the digest binds the card to the op and its exact arguments
    assert H.digest("profile", {"a": 1, "b": 2}) == H.digest("profile", {"b": 2, "a": 1})
    assert H.digest("profile", {"a": 1}) != H.digest("restart", {"a": 1})
    # left out on purpose
    assert "deploy" not in H.OPS and "catalogue.refresh" not in H.OPS


@pytest.mark.parametrize(
    ("op", "args"),
    [
        ("logs", {"service": "api;rm -rf /"}),
        ("logs", {"service": "api", "lines": 501}),
        ("logs", {"service": "api", "since": "$(id)"}),
        ("logs", {"service": "api", "extra": 1}),
        ("restart", {"service": "postgres"}),
        ("restart", {"service": "openbao"}),
        ("restart", {"service": "caddy"}),
        ("restart", {"service": "api-migrate"}),
        ("profile", {"name": "media"}),
        ("profile", {"name": "nope", "on": True}),
        ("profile", {"name": "media", "on": "yes"}),
        ("profile", {"name": "media", "on": False, "turn_off": ["ocr"]}),
        ("n8n.activate", {"workflow": "a/b", "on": True}),
        ("n8n.create", {"name": "x", "workflow_json": {"nodes": []}}),
        ("nope", {}),
    ],
)
def test_bad_arguments_and_unknown_ops_are_422(op: str, args: dict[str, Any]) -> None:
    with pytest.raises(ApiError) as e:
        H.check(op, args)
    assert e.value.status == 422


@pytest.mark.parametrize(
    ("op", "word"),
    [
        ("ssh", "SSH"),
        ("ufw", "هتزنر"),
        ("iptables", "هتزنر"),
        ("unseal", "OpenBao"),
        ("chatgpt-web-login", "web-login"),
        ("n8n-secret", "make"),
        ("owner-enroll", "owner-"),
        ("reboot", "اجازه"),
        ("deploy", "deploy"),
        ("volume.delete", "پاک"),
    ],
)
def test_denied_ops_answer_the_owners_step(op: str, word: str) -> None:
    with pytest.raises(ApiError) as e:
        H.check(op, {})
    assert (e.value.status, e.value.code) == (403, "policy_denied")
    assert word in (e.value.message_fa or ""), e.value.message_fa


def test_mcp_is_not_switched_from_here() -> None:
    with pytest.raises(ApiError) as e:
        H.check("profile", {"name": "mcp", "on": True})
    assert e.value.status == 409 and "MCP" in (e.value.message_fa or "")


def test_only_the_over_budget_exit_says_there_is_no_room() -> None:
    job = {"op": "profile", "args": {"name": "media", "on": True}}
    assert H.result_fa(job, "refused") == "جا نیست؛ این‌ها جا را گرفته‌اند"
    # the dispatcher's own refusal (its allow-list) is not a memory answer
    assert H.result_fa(job, "refused", "not_allowed") == "اجراکننده‌ی هاب این کار را نپذیرفت"


def test_output_is_masked_and_capped() -> None:
    out = H.mask("DB_PASSWORD=hunter2\nAuthorization: Bearer abcdefghijklmnop1234\nok")
    assert "hunter2" not in out and "abcdefghijklmnop1234" not in out and "ok" in out
    big = H.mask("x" * 200_000 + "\nthe verdict")
    assert len(big.encode()) <= H.OUTPUT_MAX and big.endswith("the verdict")


# ------------------------------------------------------------------ helpers --
@asynccontextmanager
async def holding_agent(su: Any, role: str, kind: str = "employee") -> AsyncIterator[str]:
    """A fresh employee of the holding's AIOPS department with `role` (dismissed afterwards, so it
    takes no other test's work)."""
    holding = await su.fetchval("SELECT code FROM core.companies WHERE kind = 'holding'")
    code = f"{holding}-HJ{secrets.token_hex(2).upper()}"
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, role, title_fa, title_en, status)
           SELECT c.id, d.id, $1, $2, $3, 'نقش فنی', 'Technical role', 'active'
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'AIOPS'
           WHERE c.kind = 'holding'""",
        code,
        kind,
        role,
    )
    try:
        yield code
    finally:
        await su.execute(
            "UPDATE core.employees SET status = 'dismissed', dismissed_at = now() WHERE code = $1",
            code,
        )


async def claim(client: httpx.AsyncClient) -> dict[str, Any]:
    r = await client.post("/internal/v1/hubops/claim", headers=hubops_headers())
    assert r.status_code == 200, r.text
    return dict(r.json())


async def drain(client: httpx.AsyncClient, su: Any) -> None:
    """No other test's job left in the queue."""
    await su.execute(
        """UPDATE ops.hub_jobs SET state = 'failed', finished_at = now()
           WHERE state IN ('queued', 'running', 'awaiting_seal')"""
    )


async def ask(
    client: httpx.AsyncClient, code: str, op: str, args: dict[str, Any] | None = None
) -> httpx.Response:
    return await client.post(
        "/internal/v1/hubops",
        headers=await agent_headers(code),
        json={"op": op, "args": args or {}},
    )


# ------------------------------------------------------------- end to end --
async def test_the_platform_sre_runs_an_op_through_the_dispatcher(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    await drain(client, su)
    async with holding_agent(su, "hub_platform_sre") as sre, holding_switch(su, "released"):
        r = await ask(client, sre, "logs", {"service": "api", "lines": 20})
        assert r.status_code == 201, r.text
        job = r.json()["job"]
        assert job["state"] == "queued" and job["ref"].startswith("HJ-") and job["class"] == "A0"
        # only the dispatcher's own token claims
        r = await client.post("/internal/v1/hubops/claim", headers=substitutes_headers())
        assert r.status_code == 403
        got = (await claim(client))["job"]
        assert got["ref"] == job["ref"] and got["op"] == "logs"
        assert got["argv"] == ["infra/compose/hq.sh", "logs", "--no-color", "--tail", "20", "api"]
        assert (await claim(client))["job"] is None  # one at a time
        r = await client.post(
            f"/internal/v1/hubops/{job['ref']}/done",
            headers=substitutes_headers(),
            json={"exit_code": 0, "output": "x"},
        )
        assert r.status_code == 403
        leaked = "api | ready\napi | HQ_API_TOKEN=s3cr3t-v4lue-xyz\n"  # gitleaks:allow - made up
        r = await client.post(
            f"/internal/v1/hubops/{job['ref']}/done",
            headers=hubops_headers(),
            json={"exit_code": 0, "output": leaked},
        )
        assert r.status_code == 200 and r.json()["state"] == "done", r.text
        r = await client.get(f"/internal/v1/hubops/{job['ref']}", headers=await agent_headers(sre))
        assert r.status_code == 200, r.text
        seen = r.json()["job"]
        assert seen["state"] == "done" and "api | ready" in seen["output"]
        assert "s3cr3t-v4lue-xyz" not in seen["output"]  # masked again on the hub
        # the owner's list, in plain Persian
        r = await client.get("/api/v1/hubops?limit=5", headers=owner)
        assert r.status_code == 200 and r.json()[0]["title_fa"] == "لاگ یک سرویس"
        audited = await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE target_kind = 'hub_job' AND target_ref = $1",
            job["ref"],
        )
        assert audited == 2  # asked, answered


async def test_an_operation_waits_for_the_kill_switch(client: httpx.AsyncClient, su: Any) -> None:
    await drain(client, su)
    async with holding_agent(su, "hub_platform_sre") as sre:
        async with holding_switch(su, "released"):
            r = await ask(client, sre, "status")
            assert r.status_code == 201, r.text
        async with holding_switch(su, "engaged"):
            out = await claim(client)
            assert out["job"] is None and out.get("skipped") == "holding_locked"
        async with holding_switch(su, "released"):
            assert (await claim(client))["job"]["ref"] == r.json()["job"]["ref"]


async def test_an_a3_op_is_the_owners_sealed_card(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    await drain(client, su)
    wf = {"nodes": [{"type": "n8n-nodes-base.cron", "name": "هر صبح"}], "connections": {}}
    head = await su.fetchval(  # the holding's one AI operations head (its department's manager)
        """SELECT e.code FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE c.kind = 'holding' AND e.role = 'aiops_head' AND e.status = 'active'"""
    )
    assert head
    async with holding_switch(su, "released"):
        r = await ask(client, head, "n8n.create", {"name": "خبر صبح", "workflow_json": wf})
        assert r.status_code == 201, r.text
        job = r.json()["job"]
        assert job["state"] == "awaiting_seal" and job["decision_ref"].startswith("D-")
        assert job["args"]["workflow_json"] == "(the sealed workflow)"
        assert (await claim(client))["job"] is None  # nothing runs before the seal
        h = owner_session["headers"]
        d = (await client.get(f"/api/v1/decisions/{job['decision_ref']}", headers=h)).json()
        assert d["kind"] == "hub_op" and d["action_class"] == "A3"
        assert d["payload"]["digest"] == H.digest(
            "n8n.create", {"name": "خبر صبح", "workflow_json": wf}
        )
        r = await client.post(
            f"/api/v1/decisions/{job['decision_ref']}/approve", json={}, headers={**h, **idem()}
        )
        assert r.status_code in (403, 428), r.text  # 🔏 first
        tok = await step_up(
            hub, owner_session["session_id"], "decision.approve", job["decision_ref"]
        )
        r = await client.post(
            f"/api/v1/decisions/{job['decision_ref']}/approve",
            json={},
            headers={**h, **tok, **idem()},
        )
        assert r.status_code == 200, r.text
        got = (await claim(client))["job"]
        assert got["ref"] == job["ref"] and got["argv"][-1] == "@workflow_json"
        assert got["args"]["workflow_json"] == wf  # the dispatcher writes it to a file
        # a rejected card: the job is refused, nothing runs
        await drain(client, su)
        r = await ask(client, head, "profile", {"name": "media", "on": True, "turn_off": ["ocr"]})
        ref = r.json()["job"]["decision_ref"]
        r = await client.post(
            f"/api/v1/decisions/{ref}/reject", json={"reason": "نه"}, headers={**h, **idem()}
        )
        assert r.status_code == 200, r.text
        state = await su.fetchval("SELECT state FROM ops.hub_jobs WHERE decision_ref = $1", ref)
        assert state == "refused" and (await claim(client))["job"] is None


async def test_who_may_and_who_is_told_whom_to_ask(
    client: httpx.AsyncClient, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    mgr = f"{co['code']}-TECH-MGR"  # a company's CTO: its own servers, never the hub
    r = await ask(client, mgr, "status")
    assert r.status_code == 403 and r.json()["code"] == "policy_denied"
    assert "AIOPS" in r.json()["message_fa"]
    async with holding_agent(su, "hub_platform_sre") as sre:
        r = await ask(client, sre, "ssh")
        assert r.status_code == 403 and "SSH" in r.json()["message_fa"]
        r = await ask(client, sre, "restart", {"service": "postgres"})
        assert r.status_code == 422
        # another technical role's job is not the requester's
        async with holding_agent(su, "hub_platform_sre") as other, holding_switch(su, "released"):
            ref = (await ask(client, sre, "status")).json()["job"]["ref"]
            r = await client.get(f"/internal/v1/hubops/{ref}", headers=await agent_headers(other))
            assert r.status_code == 404


async def test_hub_jobs_stay_the_holdings(
    client: httpx.AsyncClient, hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    async with holding_agent(su, "hub_platform_sre") as sre, holding_switch(su, "released"):
        assert (await ask(client, sre, "status")).status_code == 201
    co = await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        assert await tx.scalar("SELECT count(*) FROM ops.hub_jobs") == 0
        assert await tx.scalar("SELECT count(*) FROM ops.hub_snapshot") == 0
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    async with hub.db.tx([holding]) as tx:
        assert await tx.scalar("SELECT count(*) FROM ops.hub_jobs") >= 1
    with pytest.raises(Exception):  # noqa: B017 - never deleted
        await su.execute("DELETE FROM ops.hub_jobs")


# ---------------------------------------------------- the owner's services page --
SNAPSHOT = {
    "profile": "full",
    "memory": {"total_mb": 15608, "budget_mb": 12486, "caps_mb": 12156, "free_mb": 330},
    "switches": {"media": "off", "tts": "on", "ocr": "on", "automations": "on", "mcp": "off"},
    "services": [
        {"service": "api", "profiles": [], "cap_mb": 512, "one_shot": False, "state": "running",
         "mem_used_mb": 300.5},
        {"service": "media-render", "profiles": ["media"], "cap_mb": 512, "one_shot": True,
         "state": "absent"},
        {"service": "tts", "profiles": ["tts"], "cap_mb": 320, "one_shot": True, "state": "absent"},
        {"service": "ocr", "profiles": ["ocr"], "cap_mb": 768, "one_shot": False, "state": "running",
         "mem_used_mb": 120.0},
        {"service": "n8n", "profiles": ["automations"], "cap_mb": 512, "one_shot": False,
         "state": "running"},
    ],
}  # fmt: skip


async def test_the_services_page_switches_through_the_same_jobs(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    await drain(client, su)
    await su.execute("DELETE FROM ops.hub_snapshot")
    r = await client.get("/api/v1/hub/services", headers=owner)
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["memory"] is None and page["at"] is None
    media = next(s for s in page["services"] if s["key"] == "media")
    assert media["can_toggle"] is False and media["note_fa"]
    r = await client.post("/internal/v1/hubops/snapshot", headers=hubops_headers(), json=SNAPSHOT)
    assert r.status_code == 200, r.text
    page = (await client.get("/api/v1/hub/services", headers=owner)).json()
    assert page["memory"] == {
        "total_mb": 15608,
        "budget_mb": 12486,
        "caps_mb": 12156,
        "free_mb": 330,
    }
    by = {s["key"]: s for s in page["services"]}
    assert (
        by["media"]["state"] == "off"
        and by["media"]["can_toggle"]
        and by["media"]["mem_cap_mb"] == 512
    )
    assert by["ocr"]["state"] == "on" and by["ocr"]["mem_used_mb"] == 120.0
    assert by["mcp"]["can_toggle"] is False
    assert by["api"]["optional"] is False and by["api"]["state"] == "on"
    assert "media-render" not in by  # an optional service's own containers are under its key
    r = await client.post("/api/v1/hub/services/media", headers=owner, json={"on": True})
    assert r.status_code == 422 and "Idempotency-Key" in r.json()["fields"], r.text
    key = idem()
    r = await client.post("/api/v1/hub/services/media", headers={**owner, **key}, json={"on": True})
    assert r.status_code == 202, r.text
    job = r.json()
    assert job["state"] == "queued" and job["op"] == "profile" and job["blocking"] == []
    again = await client.post(
        "/api/v1/hub/services/media", headers={**owner, **key}, json={"on": True}
    )
    assert again.json()["ref"] == job["ref"]  # the same job
    page = (await client.get("/api/v1/hub/services", headers=owner)).json()
    assert next(s for s in page["services"] if s["key"] == "media")["state"] == "starting"
    got = (await claim(client))["job"]
    assert got["ref"] == job["ref"] and got["argv"] == ["infra/hubops/profile.sh", "media", "on"]
    r = await client.post(
        f"/internal/v1/hubops/{job['ref']}/done",
        headers=hubops_headers(),
        json={"exit_code": 3, "output": "warning: HQ_MEDIA=on ignored (182 MiB over the budget)"},
    )
    assert r.json()["state"] == "refused"
    r = await client.get(f"/api/v1/hub/jobs/{job['ref']}", headers=owner)
    out = r.json()
    assert out["state"] == "refused" and out["result_fa"] == "جا نیست؛ این‌ها جا را گرفته‌اند"
    assert [b["key"] for b in out["blocking"]] == ["ocr", "automations", "tts"]  # largest first
    # one tap: «ocr را خاموش کن و media را روشن کن»
    r = await client.post(
        "/api/v1/hub/services/media",
        headers={**owner, **idem()},
        json={"on": True, "turn_off": ["ocr"]},
    )
    assert r.status_code == 202 and r.json()["state"] == "queued"  # the owner's word: no card
    got = (await claim(client))["job"]
    assert got["argv"] == ["infra/hubops/profile.sh", "media", "on", "ocr"]
    r = await client.post(
        f"/internal/v1/hubops/{got['ref']}/done", headers=hubops_headers(), json={"exit_code": 0}
    )
    out = (await client.get(f"/api/v1/hub/jobs/{got['ref']}", headers=owner)).json()
    assert out["state"] == "done" and out["result_fa"] == "روشن شد"
    r = await client.post(
        "/api/v1/hub/services/mcp", headers={**owner, **idem()}, json={"on": True}
    )
    assert r.status_code == 409
    switched = await su.fetchval(
        "SELECT count(*) FROM owner.interactions WHERE action = 'hub_service.switch' AND target_ref = 'media'"
    )
    assert switched >= 2


# ------------------------------------------------------- nobody says no access --
async def test_the_brief_says_who_does_the_technical_work(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    lib = hub.charters
    assert lib is not None
    media = lib.get("media_director")
    assert media is not None
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(
            tx, co["id"], n8n_up=False, role="media_director", tools=media.tools, scope=media.scope
        )
    tech = b["technical"]
    # the media director works on its own company's servers (none paired here), not on the hub
    assert (
        tech["hub_ops"] is False and "server.exec" in tech["server_tools"] and tech["servers"] == []
    )
    assert "work.request" in tech["ask"] and "the hub" in tech["ask"]
    # a role with neither: whom to ask, by code
    plain = next(
        c for r, c in sorted(lib.roles.items())
        if c.scope == "company" and c.kind == "employee" and "hub.ops" not in c.tools
        and not any(t in c.tools for t in CAP.SERVER_TOOLS)
    )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(
            tx, co["id"], n8n_up=False, role=plain.role, tools=plain.tools, scope=plain.scope
        )
    tech = b["technical"]
    assert tech["hub_ops"] is False and tech["server_tools"] == []
    cto = await su.fetchval(
        "SELECT code FROM core.employees WHERE company_id = $1 AND role = 'cto' AND status = 'active'",
        co["id"],
    )
    assert "work.request" in tech["ask"] and "servers of your company" in tech["ask"]
    assert (cto or "your company's CEO") in tech["ask"] and "the hub" in tech["ask"]
    assert "hub" in b["how"] and "hub.ops" in b["how"]["hub"]
    sre = lib.get("hub_platform_sre")
    assert sre is not None
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(
            tx, holding, n8n_up=False, role="hub_platform_sre", tools=sre.tools, scope=sre.scope
        )
    tech = b["technical"]
    assert tech["hub_ops"] is True and "server.exec" in tech["server_tools"]
    # a company's CTO holds server tools for its own servers but not the hub
    cto_c = lib.get("cto")
    assert cto_c is not None and "hub.ops" in cto_c.tools
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(
            tx, co["id"], n8n_up=False, role="cto", tools=cto_c.tools, scope="company"
        )
    assert b["technical"]["hub_ops"] is False and "AI" in b["technical"]["ask"]
    # by the employee's code alone (a talk persona without a charter)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        b = await CAP.brief(tx, co["id"], n8n_up=False, employee_code=f"{co['code']}-CEO")
    assert "ask" in b["technical"]
