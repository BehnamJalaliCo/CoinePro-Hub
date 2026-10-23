"""Prompt 14 (contract §23.5-§23.8, §23.11): retention, disposal and legal
holds; reminders; fixity; the system sources; the archivist and its cards;
and the launch gate: every archive schedule is rule-only (no model, no
outside call) and wakes no agent while the holding is locked."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.archive import fixity as FX
from hq_api.archive import reminders as RM
from hq_api.archive import retention as RT
from hq_api.archive import sources as SRC
from hq_api.hub import Hub
from hq_api.worker.archive_activities import ocr_queue

from .conftest import agent_headers, idem, step_up
from .p10_support import holding_switch
from .p14_support import fakes, filed, pdf, record, txf, upload

A = "/api/v1/archive"


@pytest.fixture(autouse=True)
async def _quiet_cards(su: Any, monkeypatch: Any) -> AsyncIterator[None]:
    """One pending disposal card at a time and one a week: a test starts with
    no other test's card pending and without the week's wait; its HQ-ARC runs
    end afterwards."""
    await su.execute(
        """UPDATE cartable.decisions SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
               decided_by_code = 'test' WHERE kind = 'archive_disposal' AND status = 'pending'"""
    )
    monkeypatch.setattr(RT, "CARD_EVERY", timedelta(0))
    yield
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now() FROM core.employees e
           WHERE e.id = r.employee_id AND r.state = 'running' AND r.reason = 'test' AND e.code IN ('HQ-ARC', 'HQ-LGL')"""
    )
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'queued' AND e.code IN ('HQ-ARC', 'HQ-LGL')"""
    )


async def _invoice(
    client: httpx.AsyncClient, owner: dict[str, str], co: str, day: str, party: str
) -> dict[str, Any]:
    fid = await upload(client, owner, pdf(f"invoice of {day}"), "application/pdf", "inv.pdf")
    r = await record(
        client,
        owner,
        scope=co,
        cls="invoice",
        title=f"فاکتور {day}",
        file_ids=[fid],
        metadata={"vendor": party, "date": day, "amount": {"amount": "10", "currency": "USD"}},
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def _party(client: httpx.AsyncClient, owner: dict[str, str], name: str) -> str:
    r = await client.post(
        f"{A}/parties", json={"kind": "provider", "name_fa": name}, headers={**owner, **idem()}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["ref"])


# ---------------------------------------------------- retention, disposal --
async def test_the_disposal_card_lists_only_unheld_records_and_its_seal_leaves_a_tombstone(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h, sid = owner_session["headers"], owner_session["session_id"]
    pt = await _party(client, h, f"تأمین‌کننده {co['code']}")
    async with fakes(ocr=False):
        old = await _invoice(client, h, co["code"], "2015-02-01", pt)
        held = await _invoice(client, h, co["code"], "2015-03-01", pt)
        fresh = await _invoice(
            client, h, co["code"], (date.today() - timedelta(days=30)).isoformat(), pt
        )
    assert old["retention"]["review_at"] == "2022-02-01" and old["retention"]["disposable"] is True
    assert fresh["retention"]["review_at"] > date.today().isoformat()
    # A legal hold (the owner's) on one of them; under it, any change but a
    # new version answers 423 held.
    hold = await client.post(
        f"{A}/holds",
        json={
            "title_fa": "توقیف دعوای فروشنده",
            "reason_md": "احتمال دعوا",
            "scope": {"records": [held["ref"]]},
        },
        headers={**h, **idem()},
    )
    assert hold.status_code == 201, hold.text
    assert hold.json()["records"] == 1 and hold.json()["record_refs"] == [held["ref"]]
    patch = await client.patch(
        f"{A}/records/{held['ref']}",
        json={"title_fa": "x"},
        headers={**h, "If-Match": str(held["version"])},
    )
    assert patch.status_code == 423 and patch.json()["code"] == "held"
    # The sweep: one card for the owner with the unheld, due record only.
    out = await RT.sweep(hub, txf(hub))
    assert out["card"], out
    card = await client.get(f"/api/v1/decisions/{out['card']}", headers=h)
    listed = {x["ref"] for x in card.json()["payload"]["records"]}
    assert old["ref"] in listed and held["ref"] not in listed and fresh["ref"] not in listed
    assert card.json()["kind"] == "archive_disposal" and card.json()["action_class"] == "A3"
    # A second sweep while the card waits makes no second card.
    assert (await RT.sweep(hub, txf(hub)))["card"] is None
    # The seal (decision.approve on the card's ref): files destroyed, a
    # tombstone with every file's hash, the bytes gone.
    key = await su.fetchval(
        """SELECT f.storage_key FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
           WHERE r.ref = $1""",
        old["ref"],
    )
    assert hub.storage.local_path(key).exists()
    bare = await client.post(
        f"/api/v1/decisions/{out['card']}/approve", json={}, headers={**h, **idem()}
    )
    assert bare.status_code == 403
    ok = await client.post(
        f"/api/v1/decisions/{out['card']}/approve",
        json={},
        headers={**h, **idem(), **await step_up(hub, sid, "decision.approve", out["card"])},
    )
    assert ok.status_code == 200, ok.text
    gone = await client.get(f"{A}/records/{old['ref']}", headers=h)
    g = gone.json()
    assert g["state"] == "disposed" and g["metadata"] == {}
    assert g["tombstone"]["decision"] == out["card"]
    assert g["tombstone"]["hashes"] == [
        {"name": "inv.pdf", "sha256": old["versions"][0]["files"][0]["sha256"]}
    ]
    assert g["versions"][0]["files"][0]["destroyed"] is True
    assert not hub.storage.local_path(key).exists()
    f = await su.fetchrow(
        "SELECT storage_key, wrapped_dek, text FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id WHERE r.ref = $1",
        old["ref"],
    )
    assert f["storage_key"] is None and f["text"] is None
    # The held one stays, whatever comes; a new version is still possible.
    assert (await client.get(f"{A}/records/{held['ref']}", headers=h)).json()["state"] == "filed"
    fid = await upload(client, h, pdf("corrected invoice"), "application/pdf", "inv2.pdf")
    nv = await client.post(
        f"{A}/records/{held['ref']}/versions", json={"file_ids": [fid]}, headers={**h, **idem()}
    )
    assert nv.status_code == 201, nv.text
    # Releasing the hold is the owner's, with its own passkey.
    rel = await client.post(f"{A}/holds/{hold.json()['ref']}/release", headers=h)
    assert rel.status_code == 403 and rel.json()["code"] == "step_up_required"
    rel = await client.post(
        f"{A}/holds/{hold.json()['ref']}/release",
        headers={**h, **await step_up(hub, sid, "archive.hold.release", hold.json()["ref"])},
    )
    assert rel.status_code == 200 and rel.json()["state"] == "released"
    due = await client.get(f"{A}/retention/due", headers=h)
    assert held["ref"] in {x["ref"] for x in due.json()}


async def test_a_record_held_between_the_card_and_its_seal_is_skipped(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    h, sid = owner_session["headers"], owner_session["session_id"]
    pt = await _party(client, h, f"فروشنده {co['code']}")
    async with fakes(ocr=False):
        rec = await _invoice(client, h, co["code"], "2014-05-05", pt)
    out = await RT.sweep(hub, txf(hub))
    assert out["card"]
    hold = await client.post(
        f"{A}/holds",
        json={
            "title_fa": "توقیف دیرهنگام",
            "reason_md": "تازه",
            "scope": {"classes": ["invoice"], "parties": [pt]},
        },
        headers={**h, **idem()},
    )
    assert hold.status_code == 201 and rec["ref"] in hold.json()["record_refs"]
    ok = await client.post(
        f"/api/v1/decisions/{out['card']}/approve",
        json={},
        headers={**h, **idem(), **await step_up(hub, sid, "decision.approve", out["card"])},
    )
    assert ok.status_code == 200, ok.text
    assert (await client.get(f"{A}/records/{rec['ref']}", headers=h)).json()["state"] == "filed"
    res = await client.get(f"/api/v1/resolutions/{ok.json()['resolution']}", headers=h)
    assert rec["ref"] in res.json()["body"] and "held" in res.json()["body"]


# --------------------------------------------------------------- reminders --
async def test_a_contract_ending_in_30_days_gets_one_cartable_reminder(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    pt = await _party(client, owner, f"طرف {co['code']}")
    end = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
    async with fakes(ocr=False):
        rec = await filed(
            client,
            owner,
            co["code"],
            cls="contract",
            title="قرارداد پشتیبانی",
            metadata={"counterparty": pt, "subject": "پشتیبانی", "start": "2026-01-01", "end": end},
        )
    out = await RM.run(hub, txf(hub))
    assert out["created"] >= 1, out
    n = await su.fetchrow(
        "SELECT level, title_fa FROM notify.notifications WHERE link_kind = 'archive_record' AND link_ref = $1",
        rec["ref"],
    )
    assert n is not None and n["level"] == "decision" and "end" in n["title_fa"]
    rows = await su.fetch(
        """SELECT m.id, m.lead_days, m.state FROM archive.reminders m JOIN archive.records r ON r.id = m.record_id
           WHERE r.ref = $1""",
        rec["ref"],
    )
    assert [(x["lead_days"], x["state"]) for x in rows] == [(30, "sent")]
    await RM.run(hub, txf(hub))  # once per threshold
    assert (
        await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE link_kind = 'archive_record' AND link_ref = $1",
            rec["ref"],
        )
        == 1
    )
    listed = await client.get(f"{A}/reminders", params={"scope": co["code"]}, headers=owner)
    item = next(x for x in listed.json() if x["record"] == rec["ref"])
    assert item["days_left"] == 30 and item["channel"] == "cartable" and item["to"] == "owner"
    done = await client.post(f"{A}/reminders/{item['id']}/done", headers=owner)
    assert done.status_code == 200 and done.json()["state"] == "done"
    assert rec["ref"] not in {
        x["record"] for x in (await client.get(f"{A}/reminders", headers=owner)).json()
    }


# ------------------------------------------------------------------ fixity --
async def test_a_tampered_file_raises_the_data_loss_alarm(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    async with fakes(ocr=False):
        rec = await filed(client, owner, co["code"], title="سند حساس", text="to be tampered with")
    key = await su.fetchval(
        "SELECT f.storage_key FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id WHERE r.ref = $1",
        rec["ref"],
    )
    path = hub.storage.local_path(key)
    path.write_bytes(path.read_bytes() + b"tampered")
    alarms = await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE level = 'urgent' AND link_kind = 'archive_fixity'"
    )
    events = await su.fetchval(
        "SELECT count(*) FROM core.outbox WHERE subject LIKE '%.fixity.failed'"
    )
    out = await FX.run(hub, txf(hub), "manual")
    assert rec["ref"] in {x["ref"] for x in out["failed"]}
    # One data-loss alarm (urgent) and one stream event per run with failures.
    assert (
        await su.fetchval(
            "SELECT count(*) FROM notify.notifications WHERE level = 'urgent' AND link_kind = 'archive_fixity'"
        )
        == alarms + 1
    )
    assert (
        await su.fetchval("SELECT count(*) FROM core.outbox WHERE subject LIKE '%.fixity.failed'")
        == events + 1
    )
    run = await su.fetchrow(
        "SELECT kind, checked, failed FROM archive.fixity_runs ORDER BY id DESC LIMIT 1"
    )
    assert run["kind"] == "manual" and rec["ref"] in run["failed"]
    last = await client.get(f"{A}/fixity", headers=owner)
    assert (
        rec["ref"] in last.json()["failed"]
        and last.json()["checked"] >= 1
        and last.json()["next_at"]
    )
    # Reading the tampered file is refused too (its hash is checked first).
    f = (await client.get(f"{A}/records/{rec['ref']}", headers=owner)).json()["versions"][0][
        "files"
    ][0]
    got = await client.get(f"{A}/records/{rec['ref']}/files/{f['file_id']}", headers=owner)
    assert got.status_code == 409


# ----------------------------------------------------------------- sources --
async def test_the_system_sources_file_the_hubs_own_records(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    # A resolution of an earlier month, a restore test, a closed case.
    two_months = datetime.now(UTC) - timedelta(days=62)
    await su.execute(
        """INSERT INTO cartable.resolutions (company_id, ref, title, body, sealed_by_kind, sealed_by_code, sealed_at)
           VALUES ($1, cartable.next_resolution_ref(), 'مصوبه‌ی آزمایشی بایگانی', 'متن مصوبه', 'owner', 'owner', $2)""",
        co["id"],
        two_months,
    )
    holding = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    await su.execute(
        """INSERT INTO backup.restore_tests (company_id, at, ok, duration_s, source, snapshot, notes)
           VALUES ($1, $2, true, 42, 'local', 'abcd1234', 'database set, files and PITR ok archive=AR-000001')
           ON CONFLICT DO NOTHING""",
        holding,
        datetime.now(UTC) - timedelta(days=95),
    )
    case = await client.post(
        "/api/v1/legal/cases",
        json={
            "company": co["code"],
            "title_fa": "اعتراض به مسدودی",
            "kind": "account_appeal",
            "brief_md": "شرح",
        },
        headers={**h, **idem()},
    )
    assert case.status_code == 201, case.text
    closed = await client.post(
        f"/api/v1/legal/cases/{case.json()['ref']}/close",
        json={"note_fa": "حل شد"},
        headers={**h, **idem()},
    )
    assert closed.status_code == 200, closed.text
    # Switched off, a source files nothing.
    off = await client.put(f"{A}/sources", json={"case_closed": False}, headers=h)
    assert (
        off.status_code == 200
        and not next(x for x in off.json() if x["key"] == "case_closed")["enabled"]
    )
    first = await SRC.run(hub, txf(hub))
    assert first["case_closed"] == "off"
    assert not await su.fetchval(
        "SELECT 1 FROM archive.records WHERE source_ref = $1", f"case:{case.json()['ref']}"
    )
    await client.put(f"{A}/sources", json={"case_closed": True}, headers=h)
    assert first["resolution_month"] >= 1, first
    out = await SRC.run(hub, txf(hub))
    assert out["case_closed"] >= 1, out
    rows = await su.fetch(
        """SELECT r.ref, r.class_key, r.state, r.source_kind, r.source_ref, r.metadata FROM archive.records r
           WHERE r.source_kind = 'system' AND r.company_id = $1 ORDER BY r.ref""",
        co["id"],
    )
    by = {x["class_key"]: x for x in rows}
    assert by["resolution_bundle"]["state"] == "filed" and by["resolution_bundle"][
        "source_ref"
    ].startswith(f"resolutions:{co['code']}:")
    assert json.loads(by["resolution_bundle"]["metadata"])["count"] == 1
    lc = by["legal_correspondence"]
    assert lc["source_ref"] == f"case:{case.json()['ref']}"
    rec = await client.get(f"{A}/records/{lc['ref']}", headers=h)
    assert rec.json()["source"]["kind"] == "system"
    assert any(
        x["to_kind"] == "case" and x["to_ref"] == case.json()["ref"] for x in rec.json()["links"]
    )
    f = rec.json()["versions"][0]["files"][0]
    assert f["mime"] == "application/pdf" and f["text_state"] == "text_layer"
    body = await client.get(f"{A}/records/{lc['ref']}/files/{f['file_id']}", headers=h)
    assert body.status_code == 200 and body.content.startswith(b"%PDF")
    # Once per event: another run files nothing new.
    again = await SRC.run(hub, txf(hub))
    assert again["case_closed"] == 0 and again["resolution_month"] == 0
    assert (
        await su.fetchval("SELECT count(*) FROM archive.records WHERE source_ref LIKE 'restore:%'")
        >= 1
    )


# --------------------------------------------------- the archivist, cards --
async def test_the_archivist_files_drafts_only_and_never_seals_declassifies_releases_or_disposes(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    lib = hub.charters
    arc = lib.get("archivist")
    assert arc is not None and arc.kind == "system" and arc.scope == "holding"
    assert {"archive.search", "archive.read", "archive.file", "archive.link"} <= set(arc.tools)
    assert "archive.hold" not in arc.tools
    assert {r for r, c in lib.roles.items() if "archive.hold" in c.tools} == {"legal_counsel"}
    emp = await su.fetchrow("SELECT kind, role, status FROM core.employees WHERE code = 'HQ-ARC'")
    assert dict(emp) == {"kind": "system", "role": "archivist", "status": "active"}
    async with holding_switch(su, "released"):
        a = await agent_headers("HQ-ARC")
        # Its own owner-only paths do not exist for it.
        async with fakes(ocr=False):
            rec = await filed(client, h, co["code"], title="سند مالک", text="owner's own")
        man = rec["versions"][0]["manifest_sha256"]
        for method, path, body in (
            ("POST", f"{A}/records/{rec['ref']}/seal", {"manifest_sha256": man}),
            ("PATCH", f"{A}/records/{rec['ref']}", {"level": "public"}),
            ("POST", f"{A}/holds/LH-0001/release", None),
            (
                "POST",
                f"{A}/records",
                {"scope": co["code"], "title_fa": "x", "file_ids": [], "file": True},
            ),
        ):
            r = await client.request(
                method, path, json=body, headers={**a, **idem(), "If-Match": "1"}
            )
            assert r.status_code in (401, 403), (path, r.status_code)
        # A hold is the counsel's tool alone.
        hold = await client.post(
            "/internal/v1/archive/holds",
            json={
                "title_fa": "x",
                "case": "LC-0001",
                "reason_md": "x",
                "scope": {"records": [rec["ref"]]},
            },
            headers={**a, **idem()},
        )
        assert hold.status_code == 403
        # archive.file: a draft, never filed by itself.
        fid = await upload(client, h, pdf("lease agreement"), "application/pdf", "lease.pdf")
        imp = await client.post(
            f"{A}/import", json={"scope": co["code"], "file_ids": [fid]}, headers={**h, **idem()}
        )
        (draft,) = imp.json()["records"]
        sug = await client.post(
            "/internal/v1/archive/records",
            headers={**a, **idem()},
            json={
                "scope": co["code"],
                "class": "other",
                "title_fa": "اجاره‌نامه",
                "file_ids": [fid],
                "metadata": {"subject": "اجاره"},
                "note_fa": "صفحه‌ی ۱",
            },
        )
        assert sug.status_code == 201, sug.text
        assert sug.json()["ref"] == draft and sug.json()["state"] == "draft"
        d = (await client.get(f"{A}/records/{draft}", headers=h)).json()
        assert d["state"] == "draft" and d["class"] is None
        assert d["suggestion"]["by"] == "archivist" and d["suggestion"]["class"] == "other"
        # A schema change is a card, applied only by the owner's seal.
        key = f"cites_{co['code'].lower()}"
        body = {"title_fa": "ارجاع می‌دهد به", "inverse_fa": "ارجاع‌شده در", "to_kinds": ["record"]}
        card = await client.post(
            "/internal/v1/decisions",
            headers={**a, **idem()},
            json={
                "kind": "archive_schema",
                "title": "پیوند تازه",
                "what": "x",
                "why": "y",
                "payload": {"part": "link_kinds", "key": key, "base_version": None, "body": body},
            },
        )
        assert card.status_code == 201, card.text
        assert card.json()["payload"]["impact"] == {"records": 0, "missing_required": 0}
        assert not await su.fetchval("SELECT 1 FROM archive.link_kinds WHERE key = $1", key)
        ref = card.json()["ref"]
        ok = await client.post(
            f"/api/v1/decisions/{ref}/approve",
            json={},
            headers={
                **h,
                **idem(),
                **await step_up(hub, owner_session["session_id"], "decision.approve", ref),
            },
        )
        assert ok.status_code == 200, ok.text
        assert (
            await su.fetchval("SELECT title_fa FROM archive.link_kinds WHERE key = $1", key)
            == body["title_fa"]
        )
        # A card whose row changed since is void.
        card2 = await client.post(
            "/internal/v1/decisions",
            headers={**a, **idem()},
            json={
                "kind": "archive_schema",
                "title": "تغییر پیوند",
                "what": "x",
                "why": "y",
                "payload": {
                    "part": "link_kinds",
                    "key": key,
                    "base_version": 1,
                    "body": {**body, "title_fa": "ب"},
                },
            },
        )
        assert card2.status_code == 201, card2.text
        await su.execute("UPDATE archive.link_kinds SET inverse_fa = 'دیگر' WHERE key = $1", key)
        void = await client.post(
            f"/api/v1/decisions/{card2.json()['ref']}/approve",
            json={},
            headers={
                **h,
                **idem(),
                **await step_up(
                    hub, owner_session["session_id"], "decision.approve", card2.json()["ref"]
                ),
            },
        )
        assert void.status_code == 409 and void.json()["code"] == "decision_not_pending"
        # Never a disposal card of its own.
        own = await client.post(
            "/internal/v1/decisions",
            headers={**a, **idem()},
            json={
                "kind": "archive_disposal",
                "title": "x",
                "payload": {"records": [{"ref": rec["ref"], "title_fa": "x"}]},
            },
        )
        assert own.status_code in (403, 422)


async def test_the_counsel_holds_what_its_case_concerns(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    async with holding_switch(su, "released"):
        lgl = await agent_headers("HQ-LGL")
        case = await client.post(
            "/internal/v1/legal/cases",
            headers={**lgl, **idem()},
            json={
                "company": co["code"],
                "title_fa": "اختلاف با شریک",
                "kind": "partner_dispute",
                "brief_md": "x",
            },
        )
        assert case.status_code == 201, case.text
        async with fakes(ocr=False):
            rec = await filed(
                client, h, co["code"], title="قرارداد مورد اختلاف", text="the contract"
            )
        r = await client.post(
            "/internal/v1/archive/holds",
            headers={**lgl, **idem()},
            json={
                "title_fa": "توقیف برای پرونده",
                "case": case.json()["ref"],
                "reason_md": "احتمال دعوا",
                "scope": {"records": [rec["ref"]]},
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["case"] == case.json()["ref"] and r.json()["records"] == 1
        other = await client.post(
            "/internal/v1/archive/holds",
            headers={**lgl, **idem()},
            json={
                "title_fa": "x",
                "case": "LC-9999",
                "reason_md": "x",
                "scope": {"records": [rec["ref"]]},
            },
        )
        assert other.status_code == 422
        hs = await client.get(f"{A}/holds", params={"state": "active"}, headers=h)
        assert r.json()["ref"] in {x["ref"] for x in hs.json()}


# --------------------------------------------------------- the launch gate --
async def test_the_archive_jobs_are_rule_only_and_wake_no_agent_while_the_holding_is_locked(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    """Reminders, fixity, the retention sweep, the OCR queue and the sources
    are rule-only: they run while the holding is locked (no model, no outside
    call), and whatever would wake an agent (the archivist's review, a role's
    reminder, the SRE's fixity item) waits: no work item, no queued run."""
    co = await new_company()
    h = owner_session["headers"]
    runs_before = await su.fetchval(
        "SELECT count(*) FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id WHERE e.code = 'HQ-ARC'"
    )
    work_before = await su.fetchval(
        "SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE e.code IN ('HQ-ARC')"
    )
    async with fakes() as (_v, ocr):
        assert ocr is not None
        rec = await filed(client, h, co["code"], title="یادداشت قدیمی", text="an old note")
        await su.execute(
            "UPDATE archive.records SET due_at = DATE '2020-01-01', trigger_at = DATE '2017-01-01' WHERE ref = $1",
            rec["ref"],
        )
        async with holding_switch(su, "engaged"):
            swept = await RT.sweep(hub, txf(hub))
            assert swept["deferred"] >= 1 and swept["review_items"] == 0
            rem = await RM.run(hub, txf(hub))
            assert isinstance(rem["created"], int)
            fx = await FX.run(hub, txf(hub), "manual")
            assert fx["sre_work"] is None
            q = await ocr_queue(hub, txf(hub))
            assert q["state"] in ("idle", "off", "busy") or q["done"] >= 0
            src = await SRC.run(hub, txf(hub))
            assert all(not str(v).startswith("failed") for v in src.values()), src
            assert (
                await su.fetchval(
                    "SELECT count(*) FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id WHERE e.code = 'HQ-ARC'"
                )
                == runs_before
            )
            assert (
                await su.fetchval(
                    "SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE e.code IN ('HQ-ARC')"
                )
                == work_before
            )
            # The worker's activities say the same through Temporal's names.
        async with holding_switch(su, "released"):
            after = await RT.sweep(hub, txf(hub))
            assert after["review_items"] == 1, after
            assert await su.fetchval(
                "SELECT review_work_ref IS NOT NULL FROM archive.records WHERE ref = $1", rec["ref"]
            )


async def test_the_worker_activities_and_schedules_exist(wk: dict[str, Any]) -> None:
    from hq_api.worker import schedules

    names = {d.id for d in schedules.fixed(datetime.now(UTC).time(), "Asia/Tehran")}
    assert {
        "hq-archive-daily",
        "hq-archive-fixity",
        "hq-archive-ocr",
        "hq-archive-sources",
    } <= names
    acts = wk["acts"].archive
    out = await acts.archive_ocr_queue()
    assert out["state"] in ("idle", "off") or out["done"] >= 0
