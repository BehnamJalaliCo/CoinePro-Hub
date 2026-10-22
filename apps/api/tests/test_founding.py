"""Prompt 09 (contract §18.8): founding a company from a repository, its
server plan sealed on its digest, and the provisioner's runs (the api side;
the provisioner itself is tested in services/provisioner with a mock Hetzner)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import struct
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.domain import oversight_checks as OC
from hq_api.hub import Hub
from hq_common import provisioning as P

from .conftest import agent_headers, idem, provisioner_headers, step_up
from .test_agents import run, runs_of, step

pytestmark = pytest.mark.usefixtures("relay")
OWNER_NET = "198.51.100.7/32"
# A host key as a new server reports it (the key blob of an ed25519 key).
HOST_KEY_B64 = base64.b64encode(
    struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(range(32))
).decode()
DOC_KEYS = (
    "id", "ref", "founding", "company", "name", "type", "location", "image", "private_network",
    "firewall", "software", "work_user", "repo", "monthly_eur",
)  # fmt: skip


class FakeProvisioner:
    """The provisioner's small API (fork P9b): Hetzner's prices, the project."""

    def __init__(self) -> None:
        self.servers: list[dict[str, Any]] = []
        self.woken = 0
        self.priced: list[tuple[str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/pricing":
            t, loc = request.url.params["type"], request.url.params["location"]
            self.priced.append((t, loc))
            return httpx.Response(
                200,
                json={
                    "type": t,
                    "location": loc,
                    "currency": "EUR",
                    "server_monthly_net": "26.49",
                    "ipv4_monthly_net": "0.50",
                    "monthly_eur": "26.99",
                    "monthly_eur_gross": "32.12",
                    "vat_rate": "19.0",
                },
            )
        if request.url.path == "/v1/servers":
            return httpx.Response(200, json={"items": self.servers})
        if request.url.path == "/v1/wake":
            self.woken += 1
            return httpx.Response(202, json={"ok": True})
        return httpx.Response(404, json={"code": "not_found"})


@contextmanager
def provisioner_on(hub: Hub) -> Iterator[FakeProvisioner]:
    fake = FakeProvisioner()
    real = hub.settings
    hub.settings = replace(real, provisioner_url="http://provisioner.test")
    hub.provisioner_transport = httpx.MockTransport(fake.handle)  # type: ignore[attr-defined]
    try:
        yield fake
    finally:
        hub.settings = real
        hub.provisioner_transport = None  # type: ignore[attr-defined]


@pytest.fixture
async def ssh_sources(su: Any) -> Any:
    await su.execute(
        "UPDATE owner.settings SET provision_ssh_sources = $1 WHERE id = 1", [OWNER_NET]
    )
    yield
    await su.execute("UPDATE owner.settings SET provision_ssh_sources = '{}' WHERE id = 1")


def plan_body(company: str, **over: Any) -> dict[str, Any]:
    body = {
        "company": company,
        "name": f"{company.lower()}-app-1",
        "type": "cpx42",
        "location": "fsn1",
        "private_network": True,
        "firewall": [
            {"protocol": "tcp", "port": "22", "sources": [OWNER_NET], "note_fa": "SSH مالک"}
        ],
        "software": list(P.SOFTWARE),
        "work_user": company.lower() if len(company) > 1 else "ops",
        "repo": "behnamjalalico/nx-app",
    }
    body.update(over)
    return body


async def seal(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ref: str
) -> httpx.Response:
    h = owner_session["headers"]
    plan = (await client.get(f"/api/v1/provisioning/plans/{ref}", headers=h)).json()
    su_tok = await step_up(hub, owner_session["session_id"], "provision.seal", plan["digest"])
    return await client.post(f"/api/v1/provisioning/plans/{ref}/seal", headers={**h, **su_tok})


# ------------------------------------------------------------ §3 the plan --
async def test_a_plan_is_checked_priced_and_sealed_on_its_digest(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    ssh_sources: Any,
) -> None:
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    h = owner_session["headers"]
    # An unknown software key: refused before anything is stored.
    r = await client.post(
        "/internal/v1/provisioning/plans",
        headers={**cto, **idem()},
        json=plan_body(co, software=["docker", "quantum-db"]),
    )
    assert r.status_code == 422 and "quantum-db" in json.dumps(r.json()["fields"]), r.text
    with provisioner_on(hub) as fake:
        r = await client.post(
            "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
        )
        assert r.status_code == 201, r.text
        plan = r.json()
        # Hetzner's price (mock) through the provisioner: 26.49 + the IPv4's 0.50.
        assert plan["monthly_eur"] == "26.99" and fake.priced == [("cpx42", "fsn1")]
        assert plan["problems"] == [] and plan["state"] == "proposed"
        # The shared definition, both sides: the contract's plan fields only.
        assert plan["digest"] == P.digest({k: plan[k] for k in DOC_KEYS})
        card = (await client.get(f"/api/v1/decisions/{plan['decision_ref']}", headers=h)).json()
        assert card["kind"] == "server_plan" and card["action_class"] == "A3"
        # The cartable cannot seal it: only its digest can.
        su_tok = await step_up(hub, owner_session["session_id"], "decision.approve", card["ref"])
        r = await client.post(
            f"/api/v1/decisions/{card['ref']}/approve", headers={**h, **su_tok, **idem()}, json={}
        )
        assert r.status_code == 409
        # A step-up on another digest does not seal it.
        wrong = await step_up(hub, owner_session["session_id"], "provision.seal", "0" * 64)
        r = await client.post(
            f"/api/v1/provisioning/plans/{plan['ref']}/seal", headers={**h, **wrong}
        )
        assert r.status_code == 403
        r = await seal(client, hub, owner_session, plan["ref"])
        assert r.status_code == 200 and r.json()["state"] == "sealed", r.text
        assert fake.woken == 1
        status = await su.fetchval(
            "SELECT status FROM cartable.decisions WHERE ref = $1", card["ref"]
        )
        assert status == "approved"
        # Changed after the seal (a new version): the seal is void, a new card.
        r = await client.post(
            "/internal/v1/provisioning/plans",
            headers={**cto, **idem()},
            json={**plan_body(co, type="cpx52"), "ref": plan["ref"]},
        )
        revised = r.json()
        assert r.status_code == 201 and revised["state"] == "proposed", r.text
        assert revised["digest"] != plan["digest"] and revised["decision_ref"] != card["ref"]
        old = await step_up(hub, owner_session["session_id"], "provision.seal", plan["digest"])
        r = await client.post(
            f"/api/v1/provisioning/plans/{plan['ref']}/seal", headers={**h, **old}
        )
        assert r.status_code == 403  # the owner saw the old plan: not this one


async def test_no_build_without_a_seal_and_a_tampered_plan_loses_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    ssh_sources: Any,
) -> None:
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    with provisioner_on(hub):
        plan = (
            await client.post(
                "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
            )
        ).json()
        r = await client.get("/internal/v1/provisioning/runs/next", headers=provisioner_headers())
        assert r.status_code == 204  # proposed only: nothing to build
        assert (await seal(client, hub, owner_session, plan["ref"])).status_code == 200
        # Changed behind the seal (not through the api): never handed out.
        await su.execute("UPDATE provisioning.plans SET type = 'cpx62' WHERE ref = $1", plan["ref"])
        r = await client.get("/internal/v1/provisioning/runs/next", headers=provisioner_headers())
        assert r.status_code == 204
        row = await su.fetchrow(
            "SELECT state, sealed_digest FROM provisioning.plans WHERE ref = $1", plan["ref"]
        )
        assert (row["state"], row["sealed_digest"]) == ("proposed", None)
        assert await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_ref = $1", plan["ref"]
        )
    # Only the provisioner drives runs.
    for headers in (cto, {"Authorization": "Bearer test-service-token-" + "0" * 40}):
        r = await client.get("/internal/v1/provisioning/runs/next", headers=headers)
        assert r.status_code == 403, r.text


# --------------------------------------------- §2 founding, end to end --
async def test_a_repository_becomes_a_company_and_its_server(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    agents: Any,
    ssh_sources: Any,
) -> None:
    h, sid = owner_session["headers"], owner_session["session_id"]
    code = "N" + secrets.token_hex(2).upper().replace("0", "Q")[:4]
    r = await client.post(
        "/api/v1/foundings",
        headers={**h, **idem()},
        json={"source": {"kind": "repo", "repo": "behnamjalalico/nx-app"}},
    )
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["state"] == "auditing" and f["audit_work"] and f["workspace"] is None  # no runtime
    # §18.16: names and code null until the proposal, no plan yet, the brand missing until 9.1.
    assert (f["name_fa"], f["code"], f["plan"], f["plan_detail"]) == (None, None, None, None)
    assert f["brand"] == {"state": "missing", "version": None}
    assert f["source"] == {"kind": "repo", "repo": "behnamjalalico/nx-app", "brief_md": ""}
    # GET /foundings is a Page, newest first.
    page = (await client.get("/api/v1/foundings?limit=1", headers=h)).json()
    assert page["items"][0]["ref"] == f["ref"] and "next_cursor" in page
    auditor = await su.fetchval(
        """SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE w.ref = $1""",
        f["audit_work"],
    )
    assert auditor == "HQ-AIOPS-MGR"  # no platform SRE yet
    brief = await su.fetchval("SELECT brief FROM work.work WHERE ref = $1", f["audit_work"])
    assert "READ-ONLY" in brief and "github.read" in brief  # no execution without a runtime
    # The auditor's run (fake model) delivers the report with its five scores.
    row = [x for x in await runs_of(su, auditor) if x["state"] == "queued"][-1]
    evidence = [
        {"kind": "metric", "ref": axis, "note": f"{score}/10 because"}
        for axis, score in zip(("architecture", "quality", "security", "tests", "debt"), (7, 6, 5, 4, 6), strict=True)
    ]  # fmt: skip
    agents.fake.enqueue(
        auditor,
        step(
            "ممیزی",
            (
                "deliver",
                {
                    "work_ref": f["audit_work"],
                    "title_fa": "گزارش ممیزی",
                    "body_md": "## Architecture\nA FastAPI monolith.",
                    "evidence": evidence,
                },
            ),
        ),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["audit"]["scores"] == {
        "architecture": 7,
        "quality": 6,
        "security": 5,
        "tests": 4,
        "debt": 6,
    }
    assert "FastAPI" in f["audit"]["report_md"] and f["proposal_work"]
    # The AI Ops head's run proposes the company: one company_found card.
    row = [x for x in await runs_of(su, "HQ-AIOPS-MGR") if x["state"] == "queued"][-1]
    payload = {
        "founding": f["ref"], "code": code, "name_fa": "نکس", "name_en": "Nex",
        "departments": ["TECH", "GROWTH"],
        "kpis": [{"name_fa": "کاربر فعال", "target": "1000"}],
        "team": [{"role": "sre", "model": "claude-haiku-5-5", "monthly_usd": "4", "department": "TECH"}],
        "roadmap_md": "۹۰ روز", "monthly_usd": "40",
    }  # fmt: skip
    agents.fake.enqueue(
        "HQ-AIOPS-MGR",
        step(
            "پیشنهاد",
            (
                "propose",
                {
                    "kind": "company_found",
                    "title_fa": f"تأسیس {code}",
                    "what_md": "شرکت تازه",
                    "why_md": "ممیزی",
                    "risk": "medium",
                    "reversible": True,
                    "payload": payload,
                },
            ),
        ),
    )
    assert (await run(agents, row["id"]))["state"] == "done"
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["state"] == "proposed" and f["code"] == code and f["decision_ref"]
    assert f["proposal"]["departments"] == ["TECH", "GROWTH"]
    plan = f["plan_detail"]
    assert f["plan"] == plan["ref"]  # §18.16: a ref, the plan beside it
    assert plan["work_user"] == f"{code.lower()}-ops"  # a new account, never a system one
    assert plan["company"] == code and plan["state"] == "proposed"
    assert [r["sources"] for r in plan["firewall"]] == [[OWNER_NET]]  # SSH from the owner only
    assert any(
        "monthly_eur" in p for p in plan["problems"]
    )  # no price while the provisioner is off
    # Without the seal no company exists.
    assert not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", code)
    r = await client.post(
        f"/api/v1/decisions/{f['decision_ref']}/approve", headers={**h, **idem()}, json={}
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    assert not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", code)
    su_tok = await step_up(hub, sid, "decision.approve", f["decision_ref"])
    r = await client.post(
        f"/api/v1/decisions/{f['decision_ref']}/approve", headers={**h, **su_tok, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, f["decision_ref"], SYSTEM)
        assert (await D.apply_effect(tx, f["decision_ref"], SYSTEM))["changed"] is False
    hub.companies.invalidate()
    assert out["company"] == code and out["workspace"] == f"{code}-APP"
    # The company is DATA: its record, the proposal's departments, leadership, paused.
    co = await su.fetchrow("SELECT id, status, template FROM core.companies WHERE code = $1", code)
    assert (co["status"], co["template"]) == ("paused", "standard")
    depts = await su.fetch(
        "SELECT code FROM core.departments WHERE company_id = $1 ORDER BY code", co["id"]
    )
    assert [d["code"] for d in depts] == ["GROWTH", "TECH"]
    assert await su.fetchval("SELECT 1 FROM core.employees WHERE code = $1", f"{code}-CEO")
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["state"] == "sealed" and f["company"] == code
    assert f["plan_detail"]["decision_ref"]  # the plan's own card, for its own seal
    # The plan: priced through the provisioner, sealed on its digest, built.
    with provisioner_on(hub):
        assert (await seal(client, hub, owner_session, f["plan"])).status_code == 200
        r = await client.get("/internal/v1/provisioning/runs/next", headers=provisioner_headers())
    assert r.status_code == 200, r.text
    handed = r.json()["run"]
    rid = handed["id"]
    plan = handed["plan"]
    # What the provisioner checks before it touches anything: the same digest.
    assert P.digest(plan) == handed["sealed_digest"] == plan["digest"] and not P.problems(plan)
    assert [s["key"] for s in handed["steps"]][:3] == ["ssh-key", "firewall", "server"]
    assert handed["ssh_sources"] == [OWNER_NET]  # the provisioner checks SSH against them too
    pv = provisioner_headers()
    hid = secrets.randbelow(10**9) + 10_000  # a Hetzner server id
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(UTC) + timedelta(hours=5)).isoformat()  # capped to 60 minutes
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/callback",
        headers=pv,
        json={"token_sha256": hashlib.sha256(token.encode()).hexdigest(), "expires_at": expires},
    )
    assert r.status_code == 204, r.text
    left = await su.fetchval(
        "SELECT callback_expires_at - now() FROM provisioning.runs WHERE id = $1::uuid", rid
    )
    assert left <= timedelta(minutes=60)
    for key in ("ssh-key", "firewall", "server", "boot"):
        for state in ("running", "done"):
            r = await client.post(
                f"/internal/v1/provisioning/runs/{rid}/steps",
                headers=pv,
                json={"key": key, "state": state, "log_tail": [f"{key} {state}"]},
            )
            assert r.status_code == 204, r.text
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/server",
        headers=pv,
        json={
            "hetzner_id": hid,
            "name": plan["name"],
            "ipv4": "203.0.113.9",
            "ipv6": "2001:db8::9",
            "private_ip": "10.20.0.2",
            "labels": P.labels(plan, rid),
        },
    )
    assert r.status_code == 204, r.text
    report = {
        "run": rid, "plan": plan["ref"], "failed": False,
        "results": [{"key": k, "ok": True, "version": "v1", "note": None} for k in P.ordered(plan["software"])],
        "deploy_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOdeploy coinepro-deploy",
        "ssh_host_keys": [f"ssh-ed25519 {HOST_KEY_B64} root@nx", "ssh-ed25519 not-base64! x"],
    }  # fmt: skip
    for bad in ("x" * 43, ""):
        r = await client.post(
            "/api/v1/provisioning/callback",
            headers={"Authorization": f"Bearer {bad}"} if bad else {},
            json=report,
        )
        assert r.status_code == 401
    r = await client.post(
        "/api/v1/provisioning/callback", headers={"Authorization": f"Bearer {token}"}, json=report
    )
    assert r.status_code == 204, r.text
    again = await client.post(
        "/api/v1/provisioning/callback", headers={"Authorization": f"Bearer {token}"}, json=report
    )
    assert again.status_code == 401  # one use only
    got = (await client.get(f"/internal/v1/provisioning/runs/{rid}", headers=pv)).json()
    assert got["cloud_init"]["received_at"] and got["cloud_init"]["deploy_key"].startswith(
        "ssh-ed25519"
    )
    assert len(got["cloud_init"]["results"]) == len(P.ordered(plan["software"]))
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/finish",
        headers=pv,
        json={
            "state": "done",
            "login": {"ssh": f"ssh {plan['work_user']}@203.0.113.9", "then": ["claude"]},
        },
    )
    assert r.status_code == 204, r.text
    run_out = (await client.get(f"/api/v1/provisioning/runs/{rid}", headers=h)).json()
    assert run_out["state"] == "done" and run_out["login"]["then"] == ["claude"]
    assert [s["state"] for s in run_out["steps"]][:4] == ["done"] * 4
    # §18.16: the host key's fingerprint, as ssh shows it on the owner's first login.
    blob = base64.b64decode(HOST_KEY_B64)  # the invalid one is left out
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    assert run_out["server"]["host_keys"] == [{"type": "ssh-ed25519", "fingerprint_sha256": fp}]
    assert run_out["server"]["ipv4"] == "203.0.113.9"
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["state"] == "ready_for_login"
    price = f["plan_detail"]["price"]
    assert set(price) == {"server", "ipv4", "network", "source", "at"}
    assert (price["server"], price["ipv4"], price["network"]) == ("26.49", "0.50", "0.00")
    servers = (await client.get("/api/v1/infra/servers", headers=h)).json()["items"]
    assert any(s["hetzner_id"] == hid and s["company"] == code for s in servers)
    # The owner logged in: activation (🔏 on the ref) starts its CEO.
    r = await client.post(f"/api/v1/foundings/{f['ref']}/activate", headers=h)
    assert r.status_code == 403
    su_tok = await step_up(hub, sid, "founding.activate", f["ref"])
    r = await client.post(f"/api/v1/foundings/{f['ref']}/activate", headers={**h, **su_tok})
    assert r.status_code == 200 and r.json()["state"] == "active", r.text
    assert await su.fetchval("SELECT status FROM core.companies WHERE code = $1", code) == "active"
    start = await su.fetchval(
        """SELECT w.brief FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code = $1 ORDER BY w.created_at DESC LIMIT 1""",
        f"{code}-CEO",
    )
    assert "claude-haiku-5-5" in start  # the proposed team is the CEO's to hire
    types = {
        r["subject"].rsplit(".", 2)[-2] + "." + r["subject"].rsplit(".", 1)[-1]
        for r in await su.fetch("SELECT subject FROM core.outbox WHERE subject LIKE '%founding.updated' OR subject LIKE '%provision.step'")
    }  # fmt: skip
    assert {"founding.updated", "provision.step"} <= types
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = ANY($1) AND r.state = 'queued'""",
        ["HQ-AIOPS-MGR", f"{code}-CEO"],
    )


async def test_an_idea_cancel_and_a_failed_run_that_resumes(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
    ssh_sources: Any,
) -> None:
    h = owner_session["headers"]
    bad = await client.post(
        "/api/v1/foundings", headers={**h, **idem()}, json={"source": {"kind": "idea"}}
    )
    assert bad.status_code == 422
    f = (
        await client.post(
            "/api/v1/foundings",
            headers={**h, **idem()},
            json={"source": {"kind": "idea", "brief_md": "یک بازار آنلاین کتاب"}},
        )
    ).json()
    assert f["state"] == "auditing" and f["audit_work"] is None and f["proposal_work"]
    assert f["source"] == {"kind": "idea", "repo": None, "brief_md": "یک بازار آنلاین کتاب"}
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    # Cancel closes its work too (§18.16): the proposal is no one's job any more.
    status = await su.fetchval("SELECT status FROM work.work WHERE ref = $1", f["proposal_work"])
    assert status == "cancelled"
    # A run that failed at a step continues from there, on the same sealed plan.
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    with provisioner_on(hub):
        plan = (
            await client.post(
                "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
            )
        ).json()
        assert (await seal(client, hub, owner_session, plan["ref"])).status_code == 200
        pv = provisioner_headers()
        rid = (await client.get("/internal/v1/provisioning/runs/next", headers=pv)).json()["run"][
            "id"
        ]
        await client.post(
            f"/internal/v1/provisioning/runs/{rid}/steps", headers=pv,
            json={"key": "ssh-key", "state": "done", "log_tail": ["key ok"]},
        )  # fmt: skip
        await client.post(
            f"/internal/v1/provisioning/runs/{rid}/steps", headers=pv,
            json={"key": "firewall", "state": "failed", "log_tail": ["error: Hetzner said no"]},
        )  # fmt: skip
        r = await client.post(
            f"/internal/v1/provisioning/runs/{rid}/finish",
            headers=pv,
            json={"state": "failed", "error": {"step": "firewall", "code": "error"}},
        )
        assert r.status_code == 204
        assert (await client.get(f"/api/v1/provisioning/runs/{rid}", headers=h)).json()[
            "state"
        ] == "failed"
        r = await client.post(f"/api/v1/provisioning/runs/{rid}/resume", headers={**h, **idem()})
        assert r.status_code == 200 and r.json()["state"] == "queued", r.text
        again = (await client.get("/internal/v1/provisioning/runs/next", headers=pv)).json()["run"]
        assert again["id"] == rid
        assert {s["key"]: s["state"] for s in again["steps"]}["ssh-key"] == "done"  # not made twice


# ------------------------------------------------------------- PR-063 --
async def test_pr063_finds_servers_without_a_sealed_plan(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    ssh_sources: Any,
) -> None:
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    with provisioner_on(hub) as fake:
        plan = (
            await client.post(
                "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
            )
        ).json()
        assert (await seal(client, hub, owner_session, plan["ref"])).status_code == 200
        r = await client.get("/internal/v1/provisioning/runs/next", headers=provisioner_headers())
        assert r.status_code == 200
        ours = {**P.labels({"ref": plan["ref"], "company": co})}
        fake.servers = [
            {"id": 9001, "name": f"{co.lower()}-app-1", "status": "running", "ipv4": "203.0.113.20",
             "labels": ours, "ours": True, "plan": ours[P.LABEL_PLAN]},
            {"id": 9002, "name": "someone-elses", "status": "running", "ipv4": "203.0.113.21",
             "labels": {}, "ours": False, "plan": None},
            {"id": 9003, "name": "rogue", "status": "running", "ipv4": "203.0.113.22",
             "labels": {"managed-by": "coinepro-hq", "coinepro-hq/plan": "pv-9999"}, "ours": True},
        ]  # fmt: skip
        inv = (await client.get("/api/v1/infra/servers", headers=owner_session["headers"])).json()
        assert inv["inventory"]["ok"] is True and len(inv["inventory"]["servers"]) == 3
    async with hub.db.tx(await hub.companies.ids()) as tx:
        holding = await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")
        companies = {
            r["code"]: r["id"] for r in await tx.all("SELECT id, code FROM core.companies")
        }
        ctx = OC.CheckCtx(tx, holding["id"], holding["code"], companies, datetime.now(UTC), {})
        checked = await OC.CHECKS["PR-063"](ctx)
    keys = sorted(p.key for p in checked.problems)
    assert keys == ["server-9002", "server-9003"]  # ours with its sealed plan is fine
