"""Prompt 26, W8 (contract §37, v1.19): erasing for good, an agent's proposed erase, and the word
after delivery. The owner, 2026-11-06: «یه گزینه حذف هم داشته باشه که اصلا شاید یه سشن رو من
میخوام پاک کنم اصلا نباشه و قابلیت پاک کردن از بایگانی هم بذار».

- the preview counts exactly what the erase removes and changes nothing;
- a session erased, open or closed: everything of it gone (the order and its session answer 404,
  no list or office shows it), its works kept only as the ledgers' anchors with no word, the
  token ledger and the runs kept, the audit line written, a file destroyed only when unused, a
  structure it set up kept; the replay of the same key answers the same; the step-up is required;
- an archive record erased (a legal hold refuses it: 409 naming the hold) and one output erased;
- an agent proposes (only what it can read), the owner's seal erases, a rejection changes nothing,
  several erase cards are sealed together;
- the owner's word after delivery is a revision (the holder's root back to work).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.hub import Hub

from .conftest import agent_headers, idem, step_up
from .p14_support import filed
from .test_p21_routing_orders import deliver, report
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT, cards, refuse_queued, woken

ERASED = "پاک‌شده"


async def stored_file(hub: Hub, su: Any, company_id: Any, name: str) -> dict[str, Any]:
    """A stored file (its bytes in the storage and its row), as an upload leaves it."""
    data = f"{name} {uuid.uuid4().hex}".encode()
    key, sha = await hub.storage.put(data)
    fid = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
               created_by_kind, created_by_code)
           VALUES ($1, $2, 'text/plain', $3, $4, $5, 'owner', 'owner') RETURNING id""",
        company_id,
        name,
        len(data),
        sha,
        key,
    )
    return {"id": fid, "key": key}


def exists(hub: Hub, key: str) -> bool:
    return hub.storage.local_path(key).exists()


async def erase(
    client: httpx.AsyncClient,
    hub: Hub,
    sess: dict[str, Any],
    path: str,
    action: str,
    target: str,
    key: dict[str, str] | None = None,
) -> httpx.Response:
    su_h = await step_up(hub, sess["session_id"], action, target)
    return await client.post(path, headers={**sess["headers"], **(key or idem()), **su_h})


async def a_session(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, co: str
) -> dict[str, Any]:
    """An order its company's CEO holds, with the holder's plan, a step, a child work and its
    talk."""
    out = await post_order(client, owner, f"برای {co} برنامه‌ی سه ماه آینده را آماده کن {words()}")
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    h = await agent_headers(holder)
    r = await client.post(
        f"/internal/v1/orders/{out['ref']}/ack",
        headers=h,
        json={"plan_fa": "دو قدم", "steps": ["عددها", "گزارش"]},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/internal/v1/orders/{out['ref']}/progress", headers=h, json={"step_fa": "عددها آمد"}
    )
    assert r.status_code == 200, r.text
    child = await client.post(
        f"/internal/v1/work/{wid}/delegate",
        headers=h,
        json={"to": f"{co}-SALES-MGR", "title": "عددهای فروش"},
    )
    assert child.status_code == 201, child.text
    return {
        "ref": out["ref"],
        "talk": out["talk_ref"],
        "holder": holder,
        "work_ref": work_ref,
        "wid": wid,
        "child": child.json(),
    }


async def ledger_call(su: Any, company_id: Any, work_ref: str) -> uuid.UUID:
    """One row of the token ledger for the work, with its transcript (the prompt's words)."""
    cid = uuid.uuid4()
    await su.execute(
        """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, work_ref, task_class,
               priority, caller, status, input_tokens, output_tokens, cost_usd)
           VALUES ($1, now(), $2, 'agent:X', $3, 'general', 2, 'runner', 'ok', 100, 20, 0.01)""",
        cid,
        company_id,
        work_ref,
    )
    await su.execute(
        """INSERT INTO llm.transcripts (call_id, company_id, expires_at, request, response)
           VALUES ($1, $2, now() + interval '30 days', '{"prompt": "متن فرمان"}', 'جواب')""",
        cid,
        company_id,
    )
    return cid


# ============================================================ §37.1 a session ==
async def test_a_session_is_erased_for_good_and_only_the_ledgers_stay(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    company = await new_company()
    co = company["code"]
    s = await a_session(client, owner, su, co)
    ref, talk = s["ref"], s["talk"]
    child_id = uuid.UUID(s["child"]["id"])
    # the child's output carries a file only it has and one an order that stays carries too
    only = await stored_file(hub, su, company["id"], "only.txt")
    shared = await stored_file(hub, su, company["id"], "shared.txt")
    voice = await stored_file(hub, su, company["id"], "order-voice.txt")
    r = await client.post(
        f"/internal/v1/work/{child_id}/deliver",
        headers={**await agent_headers(f"{co}-SALES-MGR"), **idem()},
        json={"title": "عددهای فروش ماه", "summary": "خلاصه", "body": "متن",
              "attachments": [str(only["id"]), str(shared["id"])]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    output = r.json()["deliverable"]
    other = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    await su.execute(
        "UPDATE owner.orders SET file_id = $1 WHERE ref = $2", shared["id"], other["ref"]
    )
    await su.execute("UPDATE owner.orders SET file_id = $1 WHERE ref = $2", voice["id"], ref)
    # a pending card of its work, the owner's own line, a structure it set up, the token ledger
    card = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
               proposer_code, work_id)
           VALUES ($1, 'proposal', 'A1', 'یک پیشنهاد روی فرمان', 'agent', $2, $3) RETURNING ref""",
        company["id"],
        s["holder"],
        s["wid"],
    )
    r = await client.post(f"/api/v1/orders/{ref}/tasks", headers=owner, json={"title_fa": "نمودار"})
    assert r.status_code == 201, r.text
    conv_id = await su.fetchval("SELECT id FROM talk.conversations WHERE ref = $1", talk)
    first_turn = await su.fetchval(
        "SELECT id FROM talk.turns WHERE conversation_id = $1 ORDER BY n LIMIT 1", conv_id
    )
    await su.execute(
        """INSERT INTO talk.cards (conversation_id, turn_id, company_id, kind, title_fa, body_fa,
               payload, state, made)
           SELECT id, $2, company_id, 'group', 'گروه کاری محتوا', '', '{}', 'done', '{content}'
           FROM talk.conversations WHERE id = $1""",
        conv_id,
        first_turn,
    )
    call = await ledger_call(su, company["id"], s["work_ref"])
    r = await client.post(
        f"/internal/v1/orders/{ref}/ask",
        headers=await agent_headers(s["holder"]),
        json={"question_fa": "گزارش ماهانه یا هفتگی؟"},
    )
    assert r.status_code == 200, r.text
    groups_before = await su.fetchval("SELECT count(*) FROM growth.groups")
    turns = await su.fetchval("SELECT count(*) FROM talk.turns WHERE conversation_id = $1", conv_id)
    works = [s["work_ref"], s["child"]["ref"]]
    refs = [ref, talk, *works, card, output]
    notes = await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_ref = ANY($1::text[])", refs
    )
    runs = await su.fetchval(
        """SELECT count(*) FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE w.ref = ANY($1::text[])""",
        works,
    )
    assert turns >= 2 and notes >= 1 and runs >= 1

    # the preview: exactly what goes, what stays; nothing changes
    r = await client.get(f"/api/v1/orders/{ref}/erase/preview", headers=owner)
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["ref"] == ref and pv["kind"] == "session" and pv["title_fa"]
    assert pv["counts"] == {
        "turns": turns, "files": 2, "outputs": 1, "works": 2, "notifications": notes,
    }  # fmt: skip
    assert any("گروه کاری" in k for k in pv["keeps_fa"])
    assert any("ممیزی" in k for k in pv["keeps_fa"]) and any("خزانه" in k for k in pv["keeps_fa"])
    assert await su.fetchval("SELECT count(*) FROM owner.orders WHERE ref = $1", ref) == 1
    assert (
        await su.fetchval("SELECT count(*) FROM talk.turns WHERE conversation_id = $1", conv_id)
        == turns
    )
    assert await su.fetchval("SELECT count(*) FROM work.work WHERE erased_at IS NOT NULL AND ref = ANY($1::text[])", works) == 0  # fmt: skip
    r = await client.get("/api/v1/orders/F-99999/erase/preview", headers=owner)
    assert r.status_code == 404 and r.json()["message_fa"]

    # the seal is required, and the key
    r = await client.post(f"/api/v1/orders/{ref}/erase", headers={**owner, **idem()})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    r = await erase(
        client, hub, owner_session, f"/api/v1/orders/{ref}/erase", "session.erase", "F-0000"
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    su_h = await step_up(hub, owner_session["session_id"], "session.erase", ref)
    r = await client.post(f"/api/v1/orders/{ref}/erase", headers={**owner, **su_h})
    assert r.status_code == 422  # Idempotency-Key

    key = idem()
    r = await erase(
        client, hub, owner_session, f"/api/v1/orders/{ref}/erase", "session.erase", ref, key
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ref": ref, "erased": pv["counts"]}
    again = await client.post(f"/api/v1/orders/{ref}/erase", headers={**owner, **key})
    assert again.status_code == 200 and again.headers.get("Idempotent-Replay") == "true"
    assert again.json() == r.json()

    # gone: the order, its session, talk, plan, output, card, notifications, transcripts
    assert (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).status_code == 404
    assert (
        await client.get(f"/api/v1/talk/conversations/{talk}", headers=owner)
    ).status_code == 404
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "x"}
    )
    assert r.status_code == 404
    assert ref not in await cards(client, owner, "all")
    office = (await client.get("/api/v1/office", headers=owner)).json()
    assert ref not in [c["ref"] for c in office["sessions"]]
    listed = (await client.get("/api/v1/orders?limit=200", headers=owner)).json()["items"]
    assert ref not in [o["ref"] for o in listed]
    for table, col, val in (
        ("owner.orders", "ref", ref), ("owner.order_reports", "ref", ref),
        ("owner.session_tasks", "ref", ref), ("talk.conversations", "ref", talk),
        ("cartable.deliverables", "ref", output), ("cartable.decisions", "ref", card),
        ("talk.turns", "conversation_id", conv_id), ("talk.cards", "conversation_id", conv_id),
    ):  # fmt: skip
        assert not await su.fetchval(f"SELECT count(*) FROM {table} WHERE {col} = $1", val), table
    assert not await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_ref = ANY($1::text[])", refs
    )
    assert not await su.fetchval("SELECT count(*) FROM llm.transcripts WHERE call_id = $1", call)
    assert not await su.fetchval(
        """SELECT count(*) FROM agents.steps s JOIN agents.runs r ON r.id = s.run_id
           JOIN work.work w ON w.id = r.work_id WHERE w.ref = ANY($1::text[])""",
        works,
    )
    # the ledgers stay with no word: the works (hidden from every app role), their events, the
    # runs and the token ledger
    rows = await su.fetch(
        "SELECT title, brief, status, erased_at FROM work.work WHERE ref = ANY($1::text[])", works
    )
    assert len(rows) == 2
    assert all(w["erased_at"] and w["title"] == ERASED and w["brief"] == ERASED for w in rows)
    assert {w["status"] for w in rows} <= {"cancelled", "delivered", "done"}
    events = await su.fetch(
        """SELECT e.data FROM work.work_events e JOIN work.work w ON w.id = e.work_id
           WHERE w.ref = ANY($1::text[])""",
        works,
    )
    assert events and all(json.loads(e["data"]) == {"text_fa": ERASED} for e in events)
    assert (await client.get(f"/api/v1/work/{s['wid']}", headers=owner)).status_code == 404
    assert (
        await su.fetchval(
            """SELECT count(*) FROM agents.runs r JOIN work.work w ON w.id = r.work_id
               WHERE w.ref = ANY($1::text[])""",
            works,
        )
        == runs
    )
    assert not await su.fetchval(
        """SELECT count(*) FROM agents.runs r JOIN work.work w ON w.id = r.work_id
           WHERE w.ref = ANY($1::text[]) AND r.state IN ('queued', 'running')""",
        works,
    )
    assert await su.fetchval("SELECT cost_usd FROM llm.calls WHERE id = $1", call) is not None
    # a file goes only when nothing that stays uses it; its bytes after the commit
    left = {r["id"] for r in await su.fetch("SELECT id FROM files.files WHERE id = ANY($1::uuid[])",
                                            [only["id"], shared["id"], voice["id"]])}  # fmt: skip
    assert left == {shared["id"]}
    assert (
        not exists(hub, only["key"])
        and not exists(hub, voice["key"])
        and exists(hub, shared["key"])
    )
    assert await su.fetchval(
        "SELECT count(*) FROM archive.destroy_queue WHERE why = 'erase' AND ref = $1 AND done_at IS NOT NULL",
        ref,
    ) == 2  # fmt: skip
    # the structure it set up stays; one audit line, sealed, with the counts
    assert await su.fetchval("SELECT count(*) FROM growth.groups") == groups_before
    audit = await su.fetch(
        """SELECT action_class, step_up, summary FROM audit.entries
           WHERE action = 'session.erase' AND target_ref = $1""",
        ref,
    )
    assert len(audit) == 1 and audit[0]["action_class"] == "A3" and audit[0]["step_up"]
    assert json.loads(audit[0]["summary"]) == {"ref": ref, "erased": pv["counts"]}
    # the other order (it uses the shared file) is untouched
    assert (
        await client.get(f"/api/v1/orders/{other['ref']}/report", headers=owner)
    ).status_code == 200


async def test_a_closed_session_is_erased_from_the_sessions_archive(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    [route] = out["routes"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    await client.post(
        f"/internal/v1/work/{wid}/progress",
        headers=await agent_headers(route["to"]),
        json={"note": "تمام", "pct": 100},
    )
    assert (await deliver(client, route["to"], wid, "گزارش هفته")).status_code == 200
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "ok"}
    )
    assert r.status_code == 200 and r.json()["session"]["state"] == "closed"
    r = await client.post(f"/api/v1/orders/{ref}/hide", headers=owner)
    assert r.status_code == 200
    assert ref in await cards(client, owner, "all")
    pv = (await client.get(f"/api/v1/orders/{ref}/erase/preview", headers=owner)).json()
    assert pv["counts"]["outputs"] == 1 and pv["counts"]["works"] == 1
    r = await erase(client, hub, owner_session, f"/api/v1/orders/{ref}/erase", "session.erase", ref)
    assert r.status_code == 200, r.text
    assert r.json()["erased"] == pv["counts"]
    assert ref not in await cards(client, owner, "all")
    assert (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).status_code == 404
    w = await su.fetchrow("SELECT status, title, erased_at FROM work.work WHERE id = $1", wid)
    assert w["status"] == "delivered" and w["title"] == ERASED and w["erased_at"]
    # erased twice: 404, nothing more
    r = await erase(client, hub, owner_session, f"/api/v1/orders/{ref}/erase", "session.erase", ref)
    assert r.status_code == 404


# ===================================================== §37.2 archive, one output ==
async def test_an_archive_record_is_erased_now_unless_a_legal_hold_keeps_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = (await new_company())["code"]
    rec = await filed(client, owner, co, title=f"قرارداد آزمایشی {uuid.uuid4().hex[:6]}")
    ref = rec["ref"]
    keys = [
        r["storage_key"]
        for r in await su.fetch(
            """SELECT f.storage_key FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
               WHERE r.ref = $1""",
            ref,
        )
    ]
    assert keys and all(exists(hub, k) for k in keys)
    pv = (await client.get(f"/api/v1/archive/records/{ref}/erase/preview", headers=owner)).json()
    assert pv["kind"] == "archive_record" and pv["counts"]["files"] == len(keys)
    assert "به دستور مدیر کل" in pv["keeps_fa"][0]
    # a legal hold: 409 naming it, nothing changes
    r = await client.post(
        "/api/v1/archive/holds",
        headers={**owner, **idem()},
        json={"title_fa": "پرونده‌ی آزمایشی", "reason_md": "بررسی", "scope": {"records": [ref]}},
    )
    assert r.status_code == 201, r.text
    hold = r.json()["ref"]
    pv = (await client.get(f"/api/v1/archive/records/{ref}/erase/preview", headers=owner)).json()
    assert "پرونده‌ی آزمایشی" in pv["keeps_fa"][0]
    r = await erase(
        client, hub, owner_session, f"/api/v1/archive/records/{ref}/erase", "archive.erase", ref
    )
    assert r.status_code == 409 and "پرونده‌ی آزمایشی" in r.json()["message_fa"]
    assert hold in r.json()["detail"]
    assert await su.fetchval("SELECT state FROM archive.records WHERE ref = $1", ref) != "disposed"
    su_h = await step_up(hub, owner_session["session_id"], "archive.hold.release", hold)
    r = await client.post(
        f"/api/v1/archive/holds/{hold}/release", headers={**owner, **idem(), **su_h}, json={}
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/archive/records/{ref}/erase", headers={**owner, **idem()})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    r = await erase(
        client, hub, owner_session, f"/api/v1/archive/records/{ref}/erase", "archive.erase", ref
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ref": ref, "erased": {**pv["counts"], "files": len(keys)}}
    row = await su.fetchrow(
        "SELECT state, title_fa, metadata FROM archive.records WHERE ref = $1", ref
    )
    assert (
        row["state"] == "disposed"
        and row["title_fa"] == ERASED
        and json.loads(row["metadata"]) == {}
    )
    tomb = await su.fetchrow(
        "SELECT title_fa, class_key, hashes, decision_ref, dates FROM archive.tombstones WHERE ref = $1",
        ref,
    )
    assert tomb["title_fa"] == "به دستور مدیر کل" and tomb["class_key"] is None
    assert json.loads(tomb["hashes"]) == [] and tomb["decision_ref"] == "owner"
    assert set(json.loads(tomb["dates"])) == {"erased_at"}
    assert not any(exists(hub, k) for k in keys)
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'archive.erase' AND target_ref = $1", ref
    ) == 1  # fmt: skip
    r = await erase(
        client, hub, owner_session, f"/api/v1/archive/records/{ref}/erase", "archive.erase", ref
    )
    assert r.status_code == 404


async def test_one_output_is_erased_and_its_work_stays(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    [route] = out["routes"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", route["work_ref"])
    f = await stored_file(hub, su, company["id"], "draft.txt")
    title = f"پیش‌نویس گزارش {uuid.uuid4().hex[:6]}"
    r = await client.post(
        f"/internal/v1/work/{wid}/deliver",
        headers={**await agent_headers(route["to"]), **idem()},
        json={"title": "خروجی ناقص: " + title, "summary": "خلاصه", "attachments": [str(f["id"])]},
    )
    assert r.status_code == 200, r.text
    output = r.json()["deliverable"]
    rep = await report(client, owner, ref)
    assert [o["ref"] for o in rep["outputs"]] == [output]
    pv = (await client.get(f"/api/v1/deliverables/{output}/erase/preview", headers=owner)).json()
    assert pv["kind"] == "output" and pv["counts"]["outputs"] == 1 and pv["counts"]["files"] == 1
    assert (
        await su.fetchval("SELECT count(*) FROM cartable.deliverables WHERE ref = $1", output) == 1
    )
    r = await erase(
        client, hub, owner_session, f"/api/v1/deliverables/{output}/erase", "output.erase", output
    )
    assert r.status_code == 200, r.text
    assert r.json()["erased"]["outputs"] == 1
    assert not await su.fetchval(
        "SELECT count(*) FROM cartable.deliverables WHERE ref = $1", output
    )
    assert not await su.fetchval("SELECT count(*) FROM files.files WHERE id = $1", f["id"])
    assert not exists(hub, f["key"])
    assert await su.fetchval("SELECT title FROM work.work WHERE id = $1", wid) != ERASED
    rep = await report(client, owner, ref)
    assert rep["outputs"] == []
    whats = [x["what_fa"] for x in rep["steps"]]
    assert "خروجی پاک شد" in whats and not any(title in w for w in whats)
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'output.erase' AND target_ref = $1", output
    ) == 1  # fmt: skip


# ============================================================ §37.3 an agent proposes ==
async def test_an_agent_proposes_the_owner_seals_or_rejects(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    s = await a_session(client, owner, su, co)
    ref = s["ref"]
    holder = await agent_headers(s["holder"])
    body = {"kind": "session", "ref": ref, "why_fa": "مدیر کل گفت این جلسه را پاک کن"}
    r = await client.post("/internal/v1/erase/propose", headers=holder, json=body)
    assert r.status_code == 422  # Idempotency-Key
    # another company's CEO cannot read this order: refused
    r = await client.post(
        "/internal/v1/erase/propose",
        headers={**await agent_headers(f"{other}-CEO"), **idem()},
        json=body,
    )
    assert r.status_code == 403
    r = await client.post(
        "/internal/v1/erase/propose",
        headers={**holder, **idem()},
        json={**body, "ref": "AR-000001"},
    )
    assert r.status_code == 422
    r = await client.post("/internal/v1/erase/propose", headers={**holder, **idem()}, json=body)
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["kind"] == "erase" and card["status"] == "pending" and card["action_class"] == "A3"
    assert card["payload"]["kind"] == "session" and card["payload"]["ref"] == ref
    assert (
        card["payload"]["counts"]["works"] == 2 and card["owner_visible"] and not card["reversible"]
    )
    assert await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_kind = 'decision' AND link_ref = $1",
        card["ref"],
    ) == 1  # fmt: skip
    # one card at a time for the same thing
    r = await client.post("/internal/v1/erase/propose", headers={**holder, **idem()}, json=body)
    assert r.status_code == 409 and card["ref"] in r.json()["message_fa"]
    # rejected: nothing changes
    r = await client.post(
        f"/api/v1/decisions/{card['ref']}/reject",
        headers={**owner, **idem()},
        json={"reason": "نه"},
    )
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).status_code == 200
    # proposed again and sealed (🔏 decision.approve on the card's ref): erased
    r = await client.post("/internal/v1/erase/propose", headers={**holder, **idem()}, json=body)
    assert r.status_code == 201, r.text
    card = r.json()
    r = await client.post(
        f"/api/v1/decisions/{card['ref']}/approve", headers={**owner, **idem()}, json={}
    )
    assert r.status_code == 403  # the seal
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", card["ref"])
    r = await client.post(
        f"/api/v1/decisions/{card['ref']}/approve", headers={**owner, **idem(), **su_h}, json={}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["effect_status"] == "applied"
    assert (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).status_code == 404
    audit = await su.fetchval(
        "SELECT summary FROM audit.entries WHERE action = 'session.erase' AND target_ref = $1", ref
    )
    assert json.loads(audit)["card"] == card["ref"]


async def test_outputs_proposed_one_card_each_and_sealed_together(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    s = await a_session(client, owner, su, co)
    child_id = uuid.UUID(s["child"]["id"])
    mgr = f"{co}-SALES-MGR"
    outs = []
    for title in ("پیش‌نویس یک", "پیش‌نویس دو"):
        r = await client.post(
            f"/internal/v1/work/{child_id}/deliver",
            headers={**await agent_headers(mgr), **idem()},
            json={"title": "خروجی ناقص: " + title, "summary": "خلاصه"},
        )
        assert r.status_code == 200, r.text
        outs.append(r.json()["deliverable"])
    # a manager of another company reads neither
    r = await client.post(
        "/internal/v1/erase/propose",
        headers={**await agent_headers(f"{other}-CEO"), **idem()},
        json={"kind": "output", "ref": outs[0], "why_fa": "پاکش کن"},
    )
    assert r.status_code == 403
    refs = []
    for o in outs:
        r = await client.post(
            "/internal/v1/erase/propose",
            headers={**await agent_headers(s["holder"]), **idem()},
            json={"kind": "output", "ref": o, "why_fa": "مدیر کل گفت این دو خروجی را پاک کن"},
        )
        assert r.status_code == 201, r.text
        refs.append((r.json()["ref"], r.json()["version"]))
    r = await client.get("/api/v1/decisions/batchable", headers=owner)
    assert r.status_code == 200
    assert {x for x, _ in refs} <= {i["ref"] for i in r.json()["items"]}
    items = [{"ref": x, "version": v} for x, v in sorted(refs)]
    target = hashlib.sha256(
        json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    su_h = await step_up(hub, owner_session["session_id"], "decision.batch", target)
    r = await client.post(
        "/api/v1/decisions/batch/approve",
        headers={**owner, **idem(), **su_h},
        json={"items": items},
    )
    assert r.status_code == 200, r.text
    assert not await su.fetchval(
        "SELECT count(*) FROM cartable.deliverables WHERE ref = ANY($1::text[])", outs
    )
    assert await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'output.erase' AND target_ref = ANY($1::text[])",
        outs,
    ) == 2  # fmt: skip
    # the work and the order stay
    assert (await client.get(f"/api/v1/orders/{s['ref']}/report", headers=owner)).status_code == 200


# ========================================================= §37.4 a word after delivery ==
async def test_the_owners_word_after_delivery_is_a_revision(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    owner = owner_session["headers"]
    co = (await new_company())["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    ref, talk = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    h = await agent_headers(holder)
    await client.post(
        f"/internal/v1/work/{wid}/progress", headers=h, json={"note": "تمام", "pct": 100}
    )
    assert (await deliver(client, holder, wid, "گزارش فروش")).status_code == 200
    assert (await report(client, owner, ref))["session"]["badge"] == "ready"
    await refuse_queued(su, work_ref)
    r = await client.post(
        f"/api/v1/orders/{ref}/reply",
        headers={**owner, **idem()},
        json={"text": "یک نمودار ماهانه هم اضافه کن"},
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["session"]["badge"] == "moving" and rep["state"] == "in_progress"
    whats = [x["what_fa"] for x in rep["steps"]]
    assert "یک نمودار ماهانه هم اضافه کن" in whats[-2] and "دوباره باز شد" in whats[-1]
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "in_progress"
    assert (await woken(su, ref))[-1] == work_ref
    assert await su.fetchval(
        "SELECT count(*) FROM work.work_events WHERE work_id = $1 AND kind = 'reopened'", wid
    ) == 1  # fmt: skip
    # delivered again: ready again; the word from a card in the session's talk works the same
    assert (await deliver(client, holder, wid, "گزارش فروش با نمودار")).status_code == 200
    assert (await report(client, owner, ref))["session"]["badge"] == "ready"
    from hq_api.talk import store

    conv = await su.fetchrow("SELECT id, company_id FROM talk.conversations WHERE ref = $1", talk)
    turn = await su.fetchval(
        "SELECT id FROM talk.turns WHERE conversation_id = $1 ORDER BY n LIMIT 1", conv["id"]
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        card = await store.add_card(
            tx, conversation_id=conv["id"], turn_id=turn, company_id=conv["company_id"],
            kind="order", title_fa="رنگ نمودار", body_fa="رنگ نمودار را سبز کن",
            payload={"text": "رنگ نمودار را سبز کن"},
        )  # fmt: skip
    await refuse_queued(su, work_ref)
    r = await client.post(
        f"/api/v1/talk/cards/{card['id']}/run", json={}, headers={**owner, **idem()}
    )
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT status FROM work.work WHERE id = $1", wid) == "in_progress"
    # closed: the word asks to reopen first
    await client.post(
        f"/internal/v1/work/{wid}/progress", headers=h, json={"note": "تمام", "pct": 100}
    )
    assert (await deliver(client, holder, wid, "گزارش نهایی")).status_code == 200
    r = await client.post(
        f"/api/v1/orders/{ref}/close", headers={**owner, **idem()}, json={"verdict": "ok"}
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/orders/{ref}/reply", headers={**owner, **idem()}, json={"text": "یک چیز دیگر"}
    )
    assert r.status_code == 409 and r.json()["message_fa"]
    # a cancelled session reopened: its root back to work (work.reopen; the closed-work guard)
    other = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    r = await client.post(
        f"/api/v1/orders/{other['ref']}/close",
        headers={**owner, **idem()},
        json={"verdict": "cancel"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/orders/{other['ref']}/reopen", headers=owner)
    assert r.status_code == 200, r.text
    assert (
        await su.fetchval(
            "SELECT status FROM work.work WHERE ref = $1", other["routes"][0]["work_ref"]
        )
        == "in_progress"
    )
