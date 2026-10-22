"""Review 9.2 (contract §18.16): cancel closes everything and nothing of a
cancelled founding is sealed, created or built; a failed run returns the
founding to `sealed`; the reaper; the callback after a failure; plans of a
founding are the holding's; the JSON both apps read; nothing calls the
provisioner while it is off."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.domain import founding as F
from hq_api.hub import Hub

from .conftest import agent_headers, idem, provisioner_headers, step_up
from .test_founding import OWNER_NET, plan_body, provisioner_on, seal

pytestmark = pytest.mark.usefixtures("relay", "ssh_sources")
AIOPS = "HQ-AIOPS-MGR"


@pytest.fixture(name="ssh_sources")
async def ssh_sources_fixture(su: Any) -> Any:
    await su.execute(
        "UPDATE owner.settings SET provision_ssh_sources = $1 WHERE id = 1", [OWNER_NET]
    )
    yield
    await su.execute("UPDATE owner.settings SET provision_ssh_sources = '{}' WHERE id = 1")
    # The AI Ops head's runs these tests queued (their work is cancelled) and
    # the running one its token was minted for: not left for other tests.
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', error_code = 'test', finished_at = now()
           FROM core.employees e
           WHERE e.id = r.employee_id AND e.code = $1 AND r.state IN ('queued', 'running')""",
        AIOPS,
    )


def new_code() -> str:
    return "R" + secrets.token_hex(2).upper().replace("0", "Q")[:4]


async def idea(client: httpx.AsyncClient, h: dict[str, str]) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/foundings",
        headers={**h, **idem()},
        json={"source": {"kind": "idea", "brief_md": "یک سرویس تازه"}},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def propose(client: httpx.AsyncClient, ref: str, code: str, **extra: Any) -> httpx.Response:
    """The AI Ops head's company_found card for the founding."""
    payload = {
        "founding": ref, "code": code, "name_fa": "تازه", "name_en": "Fresh",
        "departments": ["TECH"], "monthly_usd": "10", **extra,
    }  # fmt: skip
    return await client.post(
        "/internal/v1/decisions",
        headers={**await agent_headers(AIOPS), **idem()},
        json={"kind": "company_found", "title": f"تأسیس {code}", "what": "شرکت تازه",
              "why": "ایده", "risk": "medium", "reversible": True, "payload": payload},
    )  # fmt: skip


async def approve(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ref: str
) -> httpx.Response:
    h = owner_session["headers"]
    tok = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    return await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **tok, **idem()}, json={}
    )


async def founded(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    """A founding sealed by the owner: its company exists (paused), its plan
    waits for its own seal."""
    h = owner_session["headers"]
    f, code = await idea(client, h), new_code()
    assert (await propose(client, f["ref"], code)).status_code == 201
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert (await approve(client, hub, owner_session, f["decision_ref"])).status_code == 200
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, f["decision_ref"], SYSTEM)
    hub.companies.invalidate()
    assert out["company"] == code, out
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["state"] == "sealed" and f["plan_detail"]["decision_ref"]
    return f, code


async def card_status(su: Any, ref: str) -> str:
    return str(await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", ref))


# ------------------------------------------------------------- §1.2 cancel --
async def test_cancel_while_proposed_founds_nothing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h = owner_session["headers"]
    # A plan named on the card must be the founding's own (§4: never ignored).
    f, code = await idea(client, h), new_code()
    r = await propose(client, f["ref"], code, plan="PV-9999")
    assert r.status_code == 422 and "payload.plan" in r.text, r.text
    # Cancelled with its card pending: the card is withdrawn, approving it is 409.
    assert (await propose(client, f["ref"], code)).status_code == 201
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["state"] == "proposed" and f["plan_detail"]["state"] == "proposed"
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 200 and r.json()["state"] == "cancelled", r.text
    assert await card_status(su, f["decision_ref"]) == "withdrawn"
    listed = (
        await client.get("/api/v1/decisions?status=withdrawn&kind=company_found", headers=h)
    ).json()  # §4: the kind filter takes the founding kinds
    assert f["decision_ref"] in [d["ref"] for d in listed["items"]]
    r = await approve(client, hub, owner_session, f["decision_ref"])
    assert r.status_code == 409 and r.json()["code"] == "decision_not_pending"
    assert not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", code)
    # The race: the card approved, then the founding cancelled before its effect ran.
    f, code = await idea(client, h), new_code()
    assert (await propose(client, f["ref"], code)).status_code == 201
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert (await approve(client, hub, owner_session, f["decision_ref"])).status_code == 200
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        out = await D.apply_effect(tx, f["decision_ref"], SYSTEM)
    assert out["company"] is None and "cancelled" in out["skipped"]
    assert not await su.fetchval("SELECT 1 FROM core.companies WHERE code = $1", code)
    f = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert f["state"] == "cancelled" and f["company"] is None  # never back to sealed
    status = await su.fetchval("SELECT status FROM work.work WHERE ref = $1", f["proposal_work"])
    assert status == "cancelled"


async def test_cancel_while_sealed_builds_nothing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h = owner_session["headers"]
    pv = provisioner_headers()
    # Its plan's server_plan card pending: withdrawn; the plan cannot be sealed.
    f, _ = await founded(client, hub, owner_session)
    card = f["plan_detail"]["decision_ref"]
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 200, r.text
    assert await card_status(su, card) == "withdrawn"
    with provisioner_on(hub):
        r = await seal(client, hub, owner_session, f["plan"])
        assert r.status_code == 409 and "cancelled" in r.text, r.text
    # Its plan sealed but not built yet: proposed again, never handed out.
    f, _ = await founded(client, hub, owner_session)
    with provisioner_on(hub):
        assert (await seal(client, hub, owner_session, f["plan"])).status_code == 200
        r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
        assert r.status_code == 200, r.text
        plan = (await client.get(f"/api/v1/provisioning/plans/{f['plan']}", headers=h)).json()
        assert plan["state"] == "proposed" and plan["decision_ref"] is None
        for _ in range(2):
            r = await client.get("/internal/v1/provisioning/runs/next", headers=pv)
            assert r.status_code == 204, r.text
    runs = await su.fetchval(
        """SELECT count(*) FROM provisioning.runs r JOIN provisioning.plans p ON p.id = r.plan_id
           WHERE p.ref = $1""",
        f["plan"],
    )
    assert runs == 0  # no server for a cancelled founding


async def test_a_failed_build_returns_the_founding_to_sealed(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h = owner_session["headers"]
    pv = provisioner_headers()
    f, _ = await founded(client, hub, owner_session)
    with provisioner_on(hub):
        assert (await seal(client, hub, owner_session, f["plan"])).status_code == 200
        rid = (await client.get("/internal/v1/provisioning/runs/next", headers=pv)).json()["run"][
            "id"
        ]
    token = secrets.token_urlsafe(32)
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/callback",
        headers=pv,
        json={"token_sha256": hashlib.sha256(token.encode()).hexdigest(),
              "expires_at": (datetime.now(UTC) + timedelta(minutes=60)).isoformat()},
    )  # fmt: skip
    assert r.status_code == 204
    # Building: no cancel.
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 409
    # The boot step timed out: the run fails, the founding is sealed again.
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/finish",
        headers=pv,
        json={"state": "failed", "error": {"step": "boot", "code": "error"}},
    )
    assert r.status_code == 204
    got = (await client.get(f"/api/v1/foundings/{f['ref']}", headers=h)).json()
    assert got["state"] == "sealed"
    # The server's report still arrives after that failure (§2.3): it is kept.
    report = {"run": rid, "plan": f["plan"], "failed": False, "results": [], "ssh_host_keys": []}
    r = await client.post(
        "/api/v1/provisioning/callback", headers={"Authorization": f"Bearer {token}"}, json=report
    )
    assert r.status_code == 204, r.text
    got = (await client.get(f"/internal/v1/provisioning/runs/{rid}", headers=pv)).json()
    assert got["state"] == "failed" and got["cloud_init"]["received_at"]
    # A failed run's step reports are refused (its next try is a resume).
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/steps", headers=pv,
        json={"key": "boot", "state": "done", "log_tail": []},
    )  # fmt: skip
    assert r.status_code == 409
    # Now cancel is allowed; a cancelled founding's run is never resumed.
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/provisioning/runs/{rid}/resume", headers={**h, **idem()})
    assert r.status_code == 409 and "cancelled" in r.text, r.text
    r = await client.get("/internal/v1/provisioning/runs/next", headers=pv)
    assert r.status_code == 204


# ------------------------------------------------- §2.3 reaper, callback --
async def test_the_reaper_fails_a_run_the_provisioner_went_quiet_on(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Any,
) -> None:
    h = owner_session["headers"]
    pv = provisioner_headers()
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    with provisioner_on(hub):
        plan = (
            await client.post(
                "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
            )
        ).json()
        assert (await seal(client, hub, owner_session, plan["ref"])).status_code == 200
        rid = (await client.get("/internal/v1/provisioning/runs/next", headers=pv)).json()["run"][
            "id"
        ]
    await client.post(
        f"/internal/v1/provisioning/runs/{rid}/steps", headers=pv,
        json={"key": "ssh-key", "state": "running", "log_tail": []},
    )  # fmt: skip
    # Quiet for less than its time: nothing happens.
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert rid not in await F.reap_stale_runs(tx, hub.settings.provision_quiet_s)
    # The provisioner was restarted mid-run: quiet for 80 minutes.
    await su.execute(
        "UPDATE provisioning.runs SET updated_at = now() - interval '80 minutes' WHERE id = $1::uuid",
        rid,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert rid in await F.reap_stale_runs(tx, hub.settings.provision_quiet_s)
    run = (await client.get(f"/api/v1/provisioning/runs/{rid}", headers=h)).json()
    assert run["state"] == "failed" and run["error"] == {"step": "ssh-key", "code": "error"}
    assert run["steps"][0]["state"] == "failed" and "reaped" in run["steps"][0]["log_tail"][-1]
    # Resumable on the same seal.
    r = await client.post(f"/api/v1/provisioning/runs/{rid}/resume", headers={**h, **idem()})
    assert r.status_code == 200 and r.json()["state"] == "queued", r.text
    # A refused build (e.g. Hetzner answered with a root password) is never resumed (§4).
    again = (await client.get("/internal/v1/provisioning/runs/next", headers=pv)).json()["run"]
    assert again["id"] == rid
    r = await client.post(
        f"/internal/v1/provisioning/runs/{rid}/finish",
        headers=pv,
        json={"state": "failed", "error": {"step": "server", "code": "refused"}},
    )
    assert r.status_code == 204
    r = await client.post(f"/api/v1/provisioning/runs/{rid}/resume", headers={**h, **idem()})
    assert r.status_code == 409 and "refused" in r.text


# ------------------------------------------------ §2.4 a founding's plans --
async def test_a_company_cto_never_plans_for_a_founding(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    f = await idea(client, h)
    for founding in (f["ref"], "C-9999"):  # a real one and none: the same answer, no leak
        r = await client.post(
            "/internal/v1/provisioning/plans",
            headers={**cto, **idem()},
            json={**plan_body(co), "founding": founding},
        )
        assert r.status_code == 403 and r.json()["code"] == "policy_denied", r.text
    # Nor for another company.
    other = (await new_company())["code"]
    r = await client.post(
        "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(other)
    )
    assert r.status_code == 403
    # A holding role writes the founding's plan.
    r = await client.post(
        "/internal/v1/provisioning/plans",
        headers={**await agent_headers(AIOPS), **idem()},
        json={**plan_body(new_code()), "founding": f["ref"]},
    )
    assert r.status_code == 201, r.text
    r = await client.post(f"/api/v1/foundings/{f['ref']}/cancel", headers={**h, **idem()})
    assert r.status_code == 200


# ---------------------------------------------- §2.1 SSH, §4 a declined card --
async def test_ssh_from_outside_the_owners_addresses_is_not_sealed(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, new_company: Any
) -> None:
    h = owner_session["headers"]
    co = (await new_company())["code"]
    cto = await agent_headers(f"{co}-TECH-MGR")
    wide = [
        {"protocol": "tcp", "port": "22", "sources": [OWNER_NET]},
        {"protocol": "tcp", "port": "1-65535", "sources": ["0.0.0.0/0", "::/0"]},
    ]
    with provisioner_on(hub):
        for fw in (wide, [{"protocol": "tcp", "port": "22", "sources": ["203.0.113.0/24"]}]):
            plan = (
                await client.post(
                    "/internal/v1/provisioning/plans",
                    headers={**cto, **idem()},
                    json=plan_body(co, firewall=fw),
                )
            ).json()
            assert plan["problems"], plan
            r = await seal(client, hub, owner_session, plan["ref"])
            assert r.status_code == 422 and r.json()["code"] == "plan_invalid", r.text
        # A declined card: its plan is not sealed until a new version has a new card.
        plan = (
            await client.post(
                "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
            )
        ).json()
        assert plan["problems"] == []
        r = await client.post(
            f"/api/v1/decisions/{plan['decision_ref']}/reject",
            headers={**h, **idem()},
            json={"reason": "نه"},
        )
        assert r.status_code == 200, r.text
        r = await seal(client, hub, owner_session, plan["ref"])
        assert r.status_code == 409 and "rejected" in r.text, r.text
        revised = (
            await client.post(
                "/internal/v1/provisioning/plans",
                headers={**cto, **idem()},
                json={**plan_body(co, type="cpx52"), "ref": plan["ref"]},
            )
        ).json()
        assert revised["decision_ref"] not in (None, plan["decision_ref"])
        assert (await seal(client, hub, owner_session, plan["ref"])).status_code == 200
        r = await client.get("/internal/v1/provisioning/runs/next", headers=provisioner_headers())
        assert r.json()["run"]["plan"]["ref"] == plan["ref"]  # not left for another test


# ------------------------------------------------------ HQ_PROVISIONING off --
async def test_while_the_provisioner_is_off_nothing_is_called(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any, new_company: Any
) -> None:
    """HQ_PROVISIONING off (the default): the api has no PROVISIONER_URL, so
    nothing is priced, listed or woken (and the provisioner, the only reader
    of the Hetzner token, does not run)."""
    assert hub.settings.provisioner_url == ""
    calls: list[str] = []
    hub.provisioner_transport = httpx.MockTransport(  # type: ignore[attr-defined]
        lambda req: calls.append(str(req.url)) or httpx.Response(500)
    )
    try:
        h = owner_session["headers"]
        co = (await new_company())["code"]
        cto = await agent_headers(f"{co}-TECH-MGR")
        before = await su.fetchval("SELECT count(*) FROM infra.inventory")
        plan = (
            await client.post(
                "/internal/v1/provisioning/plans", headers={**cto, **idem()}, json=plan_body(co)
            )
        ).json()
        assert plan["monthly_eur"] is None and any("monthly_eur" in p for p in plan["problems"])
        plan = (await client.get(f"/api/v1/provisioning/plans/{plan['ref']}", headers=h)).json()
        assert plan["monthly_eur"] is None
        r = await seal(client, hub, owner_session, plan["ref"])
        assert r.status_code == 409 and r.json()["code"] == "price_unknown"
        assert (await client.get("/api/v1/infra/servers", headers=h)).status_code == 200
        async with hub.db.tx(await hub.companies.ids()) as tx:
            assert await F.refresh_inventory(tx, hub.settings.provisioner_url) is None
        assert await su.fetchval("SELECT count(*) FROM infra.inventory") == before
        assert calls == []
    finally:
        hub.provisioner_transport = None  # type: ignore[attr-defined]
