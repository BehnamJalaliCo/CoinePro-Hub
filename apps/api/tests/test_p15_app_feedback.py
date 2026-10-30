"""Prompt 15: the server side of the owner's feedback from the Android app
0.3.0 (contract §5.2 ⟨1.7.3⟩ and §24).

§1 deliverables seen, category and filed (nothing deleted); §2 lessons as a
Page, the stars roll-up before its first build, /transcribe while speech is
off, lifting a deploy freeze with the passkey, the reason in the control
history; §3 the audit chain's genesis anchor."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import audit
from hq_api.hub import Hub

from .conftest import idem, step_up


async def _deliverable(su: Any, company_id: Any, *, system: bool) -> dict[str, Any]:
    work = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
           VALUES ($1, 'event', 'p15 test work', 'service', 'system') RETURNING id""",
        company_id,
    )
    row = await su.fetchrow(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
               produced_with)
           SELECT $1, $2, e.id, 'خروجی آزمایشی', 'خلاصه', '# متن\nبدنه', '{}' FROM core.employees e
           WHERE e.company_id = $1 AND (e.code LIKE '%-SYS') = $3 AND e.kind <> 'ceo'
           ORDER BY e.code LIMIT 1 RETURNING id, ref, category""",
        company_id,
        work,
        system,
    )
    return dict(row)


# ------------------------------------------------------------------ §1 --
async def test_category_is_set_at_insert_and_the_seen_route_comes_before_ref(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    holding = await hub.companies.holding()
    report = await _deliverable(su, holding.id, system=True)
    work = await _deliverable(su, co["id"], system=False)
    assert report["category"] == "report" and work["category"] == "work"
    before = (await client.get("/api/v1/inbox/summary", headers=owner)).json()[
        "deliverables_unseen"
    ]
    # POST /deliverables/seen is not taken by /deliverables/{ref} (no 405)
    r = await client.post(
        "/api/v1/deliverables/seen",
        headers=owner,
        json={"refs": [report["ref"], work["ref"]], "seen": True},
    )
    assert r.status_code == 200 and r.json() == {"updated": 2}, r.text
    again = await client.post(
        "/api/v1/deliverables/seen", headers=owner, json={"refs": [report["ref"]], "seen": True}
    )
    assert again.json() == {"updated": 0}  # idempotent
    after = (await client.get("/api/v1/inbox/summary", headers=owner)).json()["deliverables_unseen"]
    assert after == before - 2
    seen = (await client.get(f"/api/v1/deliverables/{work['ref']}", headers=owner)).json()
    assert seen["seen_at"] and seen["category"] == "work" and seen["filed_as"] is None
    page = await client.get(
        "/api/v1/deliverables",
        headers=owner,
        params={"seen": "true", "category": "report", "limit": 200},
    )
    refs = {d["ref"] for d in page.json()["items"]}
    assert report["ref"] in refs and work["ref"] not in refs
    unseen = await client.get(
        "/api/v1/deliverables", headers=owner, params={"seen": "false", "limit": 200}
    )
    assert report["ref"] not in {d["ref"] for d in unseen.json()["items"]}
    back = await client.post(
        "/api/v1/deliverables/seen", headers=owner, json={"refs": [work["ref"]], "seen": False}
    )
    assert back.json() == {"updated": 1}


async def test_the_day_filters_use_the_owners_zone(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    holding = await hub.companies.holding()
    dl = await _deliverable(su, holding.id, system=True)
    tz = await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1")
    day = await su.fetchval(
        "SELECT (created_at AT TIME ZONE $2)::date FROM cartable.deliverables WHERE id = $1",
        dl["id"],
        tz,
    )
    on = await client.get(
        "/api/v1/deliverables", headers=owner,
        params={"from": day.isoformat(), "to": day.isoformat(), "limit": 200},
    )  # fmt: skip
    assert dl["ref"] in {d["ref"] for d in on.json()["items"]}
    before = await client.get(
        "/api/v1/deliverables", headers=owner, params={"to": "2020-01-01", "limit": 200}
    )
    assert dl["ref"] not in {d["ref"] for d in before.json()["items"]}


async def test_filing_makes_one_archive_draft_and_nothing_is_ever_deleted(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    holding = await hub.companies.holding()
    dl = await _deliverable(su, holding.id, system=True)
    r = await client.post(f"/api/v1/deliverables/{dl['ref']}/file", headers=owner)
    assert r.status_code == 200, r.text
    record = r.json()["record"]
    assert record.startswith("AR-")
    again = await client.post(f"/api/v1/deliverables/{dl['ref']}/file", headers=owner)
    assert again.json() == {"record": record}  # the same record, not a second one
    rec = await su.fetchrow(
        "SELECT state, class_key, source_kind FROM archive.records WHERE ref = $1", record
    )
    assert (
        rec["state"] == "draft" and rec["class_key"] == "report" and rec["source_kind"] == "owner"
    )
    link = await su.fetchval(
        """SELECT count(*) FROM archive.links l JOIN archive.records r ON r.id = l.record_id
           WHERE r.ref = $1 AND l.kind = 'about' AND l.to_kind = 'deliverable' AND l.to_ref = $2""",
        record,
        dl["ref"],
    )
    assert link == 1
    assert (await client.get(f"/api/v1/deliverables/{dl['ref']}", headers=owner)).json()[
        "filed_as"
    ] == record
    # only seen_at and filed_as may change; nothing is deleted
    for stmt, code in (
        ("UPDATE cartable.deliverables SET title = 'x' WHERE id = $1", "HQI01"),
        ("DELETE FROM cartable.deliverables WHERE id = $1", "HQA01"),
    ):
        with pytest.raises(Exception) as info:
            await su.execute(stmt, dl["id"])
        assert getattr(info.value, "sqlstate", None) == code, stmt


async def test_another_companys_scope_cannot_mark_a_deliverable_seen(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    a, b = await new_company(), await new_company()
    dl = await _deliverable(su, b["id"], system=False)
    async with hub.db.tx([a["id"]]) as tx:
        n = await tx.exec(
            "UPDATE cartable.deliverables SET seen_at = now() WHERE id = :id", id=dl["id"]
        )
    assert n == 0
    assert (
        await su.fetchval("SELECT seen_at FROM cartable.deliverables WHERE id = $1", dl["id"])
        is None
    )


# ------------------------------------------------------------------ §2 --
async def test_lessons_are_a_page(client: httpx.AsyncClient, owner: dict[str, str]) -> None:
    r = await client.get("/api/v1/lessons", headers=owner, params={"limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"items", "next_cursor"} and isinstance(body["items"], list)


async def test_the_rollup_before_its_first_build_is_200_and_empty(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    r = await client.get(
        "/api/v1/stars/rollup", headers=owner, params={"period": "week", "key": "2001-01-06"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["companies"] == [] and body["employees"] == [] and body["lessons"] == []
    assert body["key"] == "2001-01-06" and body["next_at"]


async def test_transcribe_answers_503_at_once_while_speech_is_off(
    hub: Hub, client: httpx.AsyncClient, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_url=""))
    r = await client.post(
        "/api/v1/transcribe",
        headers={**owner, "Content-Type": "audio/ogg"},
        content=b"OggS" + b"\0" * 64,
    )
    assert r.status_code == 503 and r.json()["code"] == "channel_not_configured", r.text
    meta = (await client.get("/api/v1/meta", headers=owner)).json()
    assert meta["speech"] == {"enabled": False}


async def test_lifting_a_freeze_takes_the_passkey_and_the_history_keeps_the_reason(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    h, sid = owner_session["headers"], owner_session["session_id"]
    url = "/api/v1/control/deploy-freeze"
    future, past = "2099-01-01T00:00:00Z", "2001-01-01T00:00:00Z"
    close = await client.post(
        url, headers=h, json={"company": co["code"], "until": future, "reason": "آزمون بستن"}
    )
    assert close.status_code == 200 and close.json()["active"] is True, (
        close.text
    )  # closing: no passkey
    lift = await client.post(
        url, headers=h, json={"company": co["code"], "until": past, "reason": "باز کردن"}
    )
    assert lift.status_code == 403, lift.text
    lift = await client.post(
        url,
        headers={**h, **await step_up(hub, sid, "deploy_freeze.lift", f"company:{co['code']}")},
        json={"company": co["code"], "until": past, "reason": "باز کردن"},
    )
    assert lift.status_code == 200 and lift.json()["active"] is False, lift.text
    ks = await client.post(
        "/api/v1/control/kill-switch",
        headers={**h, **idem()},
        json={"scope": f"company:{co['code']}", "state": "engaged", "reason": "دلیل توقف"},
    )
    assert ks.status_code == 200, ks.text
    rows = await su.fetch(
        """SELECT action, summary, step_up FROM audit.entries
           WHERE company_id = $1 AND action IN ('deploy_freeze.set', 'kill_switch.engage') ORDER BY seq""",
        co["id"],
    )
    summaries = [(r["action"], r["summary"], r["step_up"]) for r in rows]
    assert ("deploy_freeze.set", "active: آزمون بستن", False) in summaries
    assert ("deploy_freeze.set", "lifted: باز کردن", True) in summaries
    assert any(a == "kill_switch.engage" and s.endswith(": دلیل توقف") for a, s, _ in summaries)
    r = await client.get(
        "/api/v1/audit", headers=h, params={"company": co["code"], "action": "kill_switch.engage"}
    )
    assert any("دلیل توقف" in (e.get("summary") or "") for e in r.json()["items"])
    await client.post(
        "/api/v1/control/kill-switch",
        headers={
            **h,
            **idem(),
            **await step_up(hub, sid, "kill_switch.release", f"company:{co['code']}"),
        },
        json={"scope": f"company:{co['code']}", "state": "released", "reason": "پایان آزمون"},
    )


# ------------------------------------------------------------------ §3 --
async def test_the_genesis_anchor_is_not_a_break(hub: Hub, tmp_path: Path) -> None:
    good, bad = tmp_path / "good.jsonl", tmp_path / "bad.jsonl"
    good.write_text(
        json.dumps({"seq": 0, "hash": "0" * 64, "at": "2026-10-17T01:56:53+00:00"}) + "\n"
    )
    bad.write_text(
        json.dumps({"seq": 0, "hash": "f" * 64, "at": "2026-10-17T01:56:53+00:00"}) + "\n"
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ok = await audit.verify(tx, anchor_file=good)
        broken = await audit.verify(tx, anchor_file=bad)
        head = await tx.one(
            "SELECT last_seq AS seq, last_hash AS hash FROM audit.chain_head WHERE id = 1"
        )
    assert ok["anchor"] == "ok"
    assert broken["anchor"] == "mismatch" and broken["ok"] is False and broken["first_bad_seq"] == 0
    latest = tmp_path / "latest.jsonl"
    latest.write_text(json.dumps({"seq": head["seq"], "hash": head["hash"]}) + "\n")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert (await audit.verify(tx, anchor_file=latest))["anchor"] == "ok"
