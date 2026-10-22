"""Prompt 10 §5 (the knowledge base, teaching, the shadow test, go-live), §7
(templates, lifecycle rules, NPS) and §11 (the overseer's protocols)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api.domain import desk, gate, kb, lifecycle, shadow
from hq_api.domain import oversight as O
from hq_api.domain import oversight_checks as C
from hq_api.domain import oversight_support as OS
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_common import charters, customer_mask

from .conftest import agent_headers, idem, step_up
from .p10_support import (
    article,
    fake_telegram,
    hire,
    holding_switch,
    inbound,
    make_live,
    process,
    seal_basics,
    send_all,
)

TEHRAN = ZoneInfo("Asia/Tehran")
WORDS = sorted(customer_mask.wordlist())
SEED = " ".join(WORDS[100:112])


# ------------------------------------------------------------------ §5 KB --
async def test_an_article_is_approved_only_with_step_up(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any]
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    r = await client.post(
        "/api/v1/support/kb", headers=h,
        json={"company": co["code"], "kind": "faq", "question_fa": "کارمزد معامله چقدر است؟",
              "answer_md": "کارمزد معامله 0.1 درصد است."},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["status"] == "proposed"
    ref, version = r.json()["ref"], r.json()["version"]
    r = await client.post(f"/api/v1/support/kb/{ref}/approve", headers=h, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    wrong = await step_up(hub, owner_session["session_id"], "support.kb", f"{ref}@{version + 1}")
    r = await client.post(f"/api/v1/support/kb/{ref}/approve", headers={**h, **wrong}, json={})
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"
    ok = await step_up(hub, owner_session["session_id"], "support.kb", f"{ref}@{version}")
    r = await client.post(f"/api/v1/support/kb/{ref}/approve", headers={**h, **ok}, json={})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    # A new version replaces it only when that one is approved in turn.
    r = await client.post(
        "/api/v1/support/kb", headers=h,
        json={"company": co["code"], "kind": "faq", "question_fa": "کارمزد معامله چقدر است؟",
              "answer_md": "کارمزد معامله 0.08 درصد است.", "ref": ref},
    )  # fmt: skip
    assert r.json()["version"] == version + 1
    listed = (await client.get(f"/api/v1/support/kb?company={co['code']}", headers=h)).json()
    assert {(a["version"], a["status"]) for a in listed if a["ref"] == ref} == {
        (version, "approved"), (version + 1, "proposed"),
    }  # fmt: skip


async def test_an_expired_article_no_longer_answers_by_itself(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    await seal_basics(hub, co["id"])
    a = await article(
        hub, co["id"], "ساعت کاری پشتیبانی چیست؟", "پشتیبانی هر روز از 9 تا 21 پاسخ میدهد."
    )
    await make_live(su, co["id"])
    await su.execute(
        "UPDATE support.kb_articles SET expires_at = now() - interval '1 day' WHERE id = $1",
        a["id"],
    )
    async with holding_switch(su, "released"), fake_telegram() as tg:
        msg = await inbound(hub, co["id"], "ساعت کاری پشتیبانی چیست؟")
        out = await process(hub, co["id"], msg["message"]["id"])
        await send_all(hub, co["id"], out.queued or [])
    assert out.result == "handoff" and out.reason == "no_kb"
    assert all("9 تا 21" not in c["text"] for c in tg.calls)
    async with hub.db.tx([co["id"]]) as tx:
        assert kb.status_of(await kb.load(tx, a["ref"])) == "expired"
        assert await kb.expire_due(tx) >= 1
        good, bad = await kb.cited(tx, co["id"], [f"{a['ref']}@{a['version']}"])
    assert good == [] and bad == [f"{a['ref']}@{a['version']}"]


async def test_the_owner_teaches_and_a_masked_proposal_is_made(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any],
    su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    await seal_basics(hub, co["id"])
    await make_live(su, co["id"])
    lead = await hire(su, co["code"], "support_lead")
    msg = await inbound(hub, co["id"], f"کمک! کلمات من: {SEED}")
    ref = msg["conversation"]["ref"]
    await su.execute(
        "UPDATE support.conversations SET state = 'waiting_owner', handoff_reason = 'no_kb', handoff_at = now() WHERE id = $1",
        msg["conversation"]["id"],
    )
    r = await client.post(
        f"/api/v1/support/conversations/{ref}/teach", headers={**owner, **idem()},
        json={"answer_md": "برای فعال شدن VIP مراحل را در اپ دنبال کنید.",
              "generalise": True},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["message"]["status"] == "queued" and out["message"]["author"] == "owner"
    art = out["article"]
    assert art["status"] == "proposed" and art["source"] == {"kind": "owner_answer", "ref": ref}
    assert art["answer_md"] == "برای فعال شدن VIP مراحل را در اپ دنبال کنید."
    assert all(w not in art["question_fa"] for w in SEED.split())
    # The support lead generalises it (a work item); nothing is approved without the owner.
    w = await su.fetchval(
        """SELECT count(*) FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code = $1 AND w.title LIKE '%' || $2 || '%'""",
        lead,
        art["ref"],
    )
    assert w == 1


def _export(pairs: int) -> bytes:
    msgs: list[dict[str, Any]] = []
    i = 0
    topics = [
        "رفرال من ثبت نشد",
        "حداقل موجودی VIP",
        "برداشت انجام نشد",
        "کارمزد چقدر است",
        "اپ باز نمیشود",
    ]
    for n in range(pairs):
        q = f"{topics[n % len(topics)]} شماره {n}"
        if n == 0:
            q += f" کلمات من {SEED} و کارت 4111 1111 1111 1111 و @someone_else"
        msgs.append(
            {
                "id": i,
                "type": "message",
                "from": "Customer",
                "from_id": f"user{1000 + n}",
                "text": q,
            }
        )
        msgs.append({"id": i + 1, "type": "message", "from": "Owner", "from_id": "user1",
                     "text": [f"پاسخ مالک به {n}", {"type": "bold", "text": " (مهم)"}]})  # fmt: skip
        i += 2
    return json.dumps(
        {"personal_information": {"user_id": 1},
         "chats": {"list": [{"name": "support", "type": "personal_chat", "messages": msgs}]}},
        ensure_ascii=False,
    ).encode()  # fmt: skip


async def _owner_file(hub: Hub, su: Any, data: bytes, name: str) -> Any:
    key, sha = await hub.storage.put(data)
    return await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key, created_by_kind,
               created_by_code)
           SELECT id, $1, 'application/json', $2, $3, $4, 'owner', 'owner'
           FROM core.companies WHERE kind = 'holding' RETURNING id""",
        name,
        len(data),
        sha,
        key,
    )


async def test_the_history_becomes_a_private_masked_suite_of_at_most_100(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any],
    su: Any,
) -> None:  # fmt: skip
    co, other = await new_company(), await new_company()
    fid = await _owner_file(hub, su, _export(130), "result.json")
    r = await client.post(
        "/api/v1/support/history", headers=owner, json={"company": co["code"], "file_id": str(fid)}
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["state"], out["format"], out["pairs_found"], out["cases_kept"]) == (
        "done", "telegram_json", 130, 100,
    )  # fmt: skip
    assert len(out["topics"]) >= 4 and out["suite"] == f"support-shadow-{co['code']}@1"
    suite = await su.fetchrow(
        "SELECT company_id, cases FROM academy.eval_suites WHERE ref = $1",
        f"support-shadow-{co['code']}",
    )
    cases = json.loads(suite["cases"])
    assert suite["company_id"] == co["id"] and len(cases) == 100
    raw = json.dumps(cases, ensure_ascii=False)
    assert "4111 1111 1111 1111" not in raw and "@someone_else" not in raw
    assert SEED not in raw and "[seed-phrase]" in raw
    assert "پاسخ مالک به 0 (مهم)" in raw  # the owner's answer is the truth
    # It never leaves the company: another company's scope does not see it.
    async with hub.db.tx([other["id"]]) as tx:
        assert not await tx.scalar(
            "SELECT 1 FROM academy.eval_suites WHERE ref = :r", r=f"support-shadow-{co['code']}"
        )


async def _run(hub: Hub, whub: Hub, co: dict[str, Any], res: list[dict[str, Any]]) -> Any:
    """A shadow run queued by the api and finished by the worker (its role)."""
    async with hub.db.tx([co["id"]]) as tx:
        row = await shadow.queue_run(
            tx, hub, company_id=co["id"], company=co["code"], by_kind="owner", by_code="owner"
        )
    async with whub.db.tx([co["id"]]) as tx:
        return await shadow.finish(tx, whub, row["id"], res)


async def test_go_live_cards_only_on_a_clean_pass_and_the_seal_makes_the_channel_live(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, wk: dict[str, Any],
) -> None:  # fmt: skip
    co = await new_company()
    await seal_basics(hub, co["id"])
    await su.execute(
        "INSERT INTO support.channels (company_id, kind, state) VALUES ($1, 'telegram_bot', 'shadow')",
        co["id"],
    )
    fid = await _owner_file(hub, su, _export(20), "result.json")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await shadow.import_history(
            tx, hub, company_id=co["id"], company=co["code"], file_id=fid, by="owner"
        )

    def results(correct: int, total: int = 100, wrong_code: int = 0) -> list[dict[str, Any]]:
        rows = [{"case": f"S{i:03d}", "verdict": "correct", "path": "verbatim", "score": 0.95}
                for i in range(correct)]  # fmt: skip
        rows += [{"case": f"S{i:03d}", "verdict": "partial", "path": "handoff"}
                 for i in range(correct, total)]  # fmt: skip
        for r in rows[:wrong_code]:
            r.update(verdict="wrong", wrong_code=True)
        return rows

    async def run(res: list[dict[str, Any]]) -> shadow.ShadowReport:
        report: shadow.ShadowReport = await _run(hub, wk["hub"], co, res)
        return report

    r89 = await run(results(89))
    assert not r89.pass_ and r89.decisions == []
    r90bad = await run(results(91, wrong_code=1))
    assert (r90bad.correct, r90bad.wrong_codes, r90bad.pass_, r90bad.decisions) == (
        90,
        1,
        False,
        [],
    )
    ok = await run(results(90))
    assert ok.pass_ and len(ok.decisions) == 1
    assert ok.proposed_verbatim_threshold == 0.95 and ok.proposed_auto_send == "kb_verbatim"
    card = await su.fetchrow(
        "SELECT kind, payload, action_class FROM cartable.decisions WHERE ref = $1", ok.decisions[0]
    )
    payload = json.loads(card["payload"])
    assert card["kind"] == "support_go_live" and payload["channel"] == "telegram_bot"
    assert payload["shadow_report"]["pass"] is True and payload["verbatim_threshold"] == 0.95
    h = owner_session["headers"]
    ref = ok.decisions[0]
    r = await client.post(f"/api/v1/decisions/{ref}/approve", headers={**h, **idem()}, json={})
    assert r.status_code == 403  # sealed with step-up only
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve", headers={**h, **su_h, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    ch = await su.fetchrow(
        "SELECT state, live_since, go_live_decision_id, auto_send FROM support.channels WHERE company_id = $1 AND kind = 'telegram_bot'",
        co["id"],
    )
    assert (
        ch["state"] == "live" and ch["live_since"] is not None and ch["auto_send"] == "kb_verbatim"
    )
    st = await su.fetchrow(
        "SELECT verbatim_threshold, grounded_threshold FROM support.settings WHERE company_id = $1",
        co["id"],
    )
    assert float(st["verbatim_threshold"]) == 0.95


async def test_a_newer_shadow_run_supersedes_the_card(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, wk: dict[str, Any],
) -> None:  # fmt: skip
    co = await new_company()
    await seal_basics(hub, co["id"])
    await su.execute(
        "INSERT INTO support.channels (company_id, kind, state) VALUES ($1, 'telegram_bot', 'shadow')",
        co["id"],
    )
    fid = await _owner_file(hub, su, _export(5), "result.json")
    good = [{"case": "S001", "verdict": "correct", "path": "verbatim", "score": 0.97}]
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await shadow.import_history(
            tx, hub, company_id=co["id"], company=co["code"], file_id=fid, by="owner"
        )
    rep = await _run(hub, wk["hub"], co, good)
    await _run(hub, wk["hub"], co, [{**good[0], "verdict": "wrong"}])
    ref = rep.decisions[0]
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", ref)
    r = await client.post(
        f"/api/v1/decisions/{ref}/approve",
        headers={**owner_session["headers"], **su_h, **idem()},
        json={},
    )
    assert r.status_code == 409
    assert (
        await su.fetchval(
            "SELECT state FROM support.channels WHERE company_id = $1 AND kind = 'telegram_bot'",
            co["id"],
        )
        == "shadow"
    )


async def test_the_shadow_run_waits_while_the_holding_is_locked(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    from hq_api.worker.activities import _ScopedTx
    from hq_api.worker.desk_activities import DeskActivities

    co = await new_company()
    fid = await _owner_file(hub, su, _export(3), "result.json")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await shadow.import_history(
            tx, hub, company_id=co["id"], company=co["code"], file_id=fid, by="owner"
        )
        run = await shadow.queue_run(
            tx, hub, company_id=co["id"], company=co["code"], by_kind="owner", by_code="owner"
        )
    acts = DeskActivities(
        hub, None, lambda: _ScopedTx(hub)
    )  # no router at all: nothing may call it
    async with holding_switch(su, "engaged"):
        out = await acts.shadow_run(str(run["id"]))
    assert out["skipped"] is True and out["reason"] == "holding_locked"
    row = await su.fetchrow(
        "SELECT state, skipped_reason FROM support.shadow_runs WHERE id = $1", run["id"]
    )
    assert (row["state"], row["skipped_reason"]) == ("skipped", "holding_locked")


def test_the_history_parsers_and_the_thresholds() -> None:
    csv_pairs = shadow.parse_csv("سوال,جواب\nسلام چطور ثبت نام کنم؟,از اپ\n,خالی\n".encode())
    assert csv_pairs == [("سلام چطور ثبت نام کنم؟", "از اپ")]
    one_chat = json.dumps(
        {"type": "personal_chat", "messages": [
            {"type": "message", "from_id": "user9", "text": "سؤال"},
            {"type": "message", "from_id": "user1", "text": "جواب"},
            {"type": "service", "from_id": "user1", "text": "x"},
        ]}
    ).encode()  # fmt: skip
    assert shadow.parse_telegram(one_chat) == [("سؤال", "جواب")]
    vt, gt = shadow.thresholds(
        [
            {"path": "verbatim", "score": 0.81, "verdict": "wrong"},
            {"path": "verbatim", "score": 0.86, "verdict": "correct"},
            {"path": "verbatim", "score": 0.99, "verdict": "correct"},
            {"path": "draft", "confidence": 0.7, "verdict": "correct"},
        ]
    )
    assert (vt, gt) == (0.86, 0.7)
    assert shadow.judge_code(("asks_secret",)) == (True, False)
    assert shadow.judge_code(("unknown_code",)) == (False, True)


# ------------------------------------------------------------ §7 lifecycle --
async def _sealed_rule(
    hub: Hub, company_id: Any, kind: str, *, limits: dict[str, Any] | None = None
) -> dict[str, Any]:
    async with hub.db.tx([company_id]) as tx:
        await lifecycle.ensure_seed(tx, company_id)
        t = await tx.one(
            "SELECT * FROM growth.templates WHERE company_id = :co AND purpose = :p ORDER BY version DESC LIMIT 1",
            co=company_id,
            p=kind,
        )
        if t["status"] != "sealed":
            t = await lifecycle.seal_template(tx, t["ref"], t["version"], step_up_id=None)
        r = await lifecycle.create_rule(
            tx, company_id=company_id, kind=kind, template_ref=t["ref"], template_version=t["version"],
            channel="telegram_bot", trigger=None, limits=limits, by_kind="owner", by_code="owner",
        )  # fmt: skip
        return await lifecycle.seal_rule(tx, r["ref"], r["version"], step_up_id=None)


async def test_an_unsealed_rule_sends_nothing(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    await make_live(su, co["id"])
    msg = await inbound(hub, co["id"], "سلام")
    async with holding_switch(su, "released"), hub.db.tx([co["id"]]) as tx:
        await lifecycle.ensure_seed(tx, co["id"])
        out = await lifecycle.send_template(
            tx, hub, company_id=co["id"], purpose="csat", dedupe_key="u-1",
            conversation_id=msg["conversation"]["id"],
        )  # fmt: skip
        assert (out["status"], out["reason"]) == ("skipped", "no_active_rule")
        rule = await tx.one(
            "SELECT ref, version FROM growth.rules WHERE company_id = :co AND kind = 'csat'",
            co=co["id"],
        )
        with pytest.raises(ApiError) as info:
            await lifecycle.seal_rule(tx, rule["ref"], rule["version"], step_up_id=None)
        assert info.value.code == "template_not_sealed"
    assert not await su.fetchval(
        "SELECT count(*) FROM support.messages WHERE conversation_id = $1 AND direction = 'out'",
        msg["conversation"]["id"],
    )


async def test_the_owner_makes_a_rule_without_any_agent_and_seals_it_with_step_up(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any]
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    t = await client.post(
        "/api/v1/growth/templates", headers=h,
        json={"company": co["code"], "purpose": "rescue", "body_fa": "سلام {name}، ثبت‌نام با رفرال ما را فراموش نکنید.",
              "variables": ["name"]},
    )  # fmt: skip
    assert t.status_code == 201 and t.json()["status"] == "proposed"
    t = t.json()
    r = await client.post(
        "/api/v1/growth/rules", headers=h,
        json={"company": co["code"], "kind": "rescue", "template": f"{t['ref']}@{t['version']}"},
    )  # fmt: skip
    assert r.status_code == 201 and r.json()["status"] == "proposed"
    rule = r.json()
    su_r = await step_up(
        hub, owner_session["session_id"], "growth.rule", f"{rule['ref']}@{rule['version']}"
    )
    r = await client.post(
        f"/api/v1/growth/rules/{rule['ref']}/seal", headers={**h, **su_r}, json={}
    )
    assert r.status_code == 409 and r.json()["code"] == "template_not_sealed"
    r = await client.post(f"/api/v1/growth/templates/{t['ref']}/seal", headers=h, json={})
    assert r.status_code == 403
    su_t = await step_up(hub, owner_session["session_id"], "growth.template", t["seal_target"])
    r = await client.post(
        f"/api/v1/growth/templates/{t['ref']}/seal", headers={**h, **su_t}, json={}
    )
    assert r.status_code == 200 and r.json()["status"] == "sealed"
    r = await client.post(f"/api/v1/growth/rules/{rule['ref']}/seal", headers=h, json={})
    assert r.status_code == 403
    su_r = await step_up(
        hub, owner_session["session_id"], "growth.rule", f"{rule['ref']}@{rule['version']}"
    )
    r = await client.post(
        f"/api/v1/growth/rules/{rule['ref']}/seal", headers={**h, **su_r}, json={}
    )
    assert r.status_code == 200 and r.json()["status"] == "active"
    r = await client.post(f"/api/v1/growth/rules/{rule['ref']}/pause", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "paused"
    su_r = await step_up(
        hub, owner_session["session_id"], "growth.rule", f"{rule['ref']}@{rule['version']}"
    )
    r = await client.post(
        f"/api/v1/growth/rules/{rule['ref']}/resume", headers={**h, **su_r}, json={}
    )
    assert r.status_code == 200 and r.json()["status"] == "active"
    rules = (await client.get(f"/api/v1/growth/rules?company={co['code']}", headers=h)).json()
    assert {r["kind"] for r in rules} >= {"rescue", "csat", "nps"}  # the seeded ones, proposed


async def test_a_template_seal_never_fits_the_same_text_in_another_company(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any]
) -> None:  # fmt: skip
    ty, fx = await new_company(), await new_company()
    h = owner_session["headers"]
    body = "از ۱ تا ۵ به پاسخ ما چه نمره‌ای میدهید؟"
    made = {}
    for co in (ty, fx):
        r = await client.post(
            "/api/v1/growth/templates",
            headers=h,
            json={"company": co["code"], "purpose": "csat", "body_fa": body},
        )
        made[co["code"]] = r.json()
    t_ty, t_fx = made[ty["code"]], made[fx["code"]]
    assert t_ty["sha256"] == t_fx["sha256"] and t_ty["ref"] != t_fx["ref"]
    su_ty = await step_up(hub, owner_session["session_id"], "growth.template", t_ty["seal_target"])
    r = await client.post(
        f"/api/v1/growth/templates/{t_fx['ref']}/seal", headers={**h, **su_ty}, json={}
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_invalid"


async def test_quiet_hours_the_daily_cap_and_opt_out(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    await seal_basics(hub, co["id"])
    await make_live(su, co["id"])
    await _sealed_rule(hub, co["id"], "csat", limits={"daily_cap": 1, "per_customer_days": 1})
    a = await inbound(hub, co["id"], "سلام", user="8101")
    b = await inbound(hub, co["id"], "سلام", user="8102")
    # Today in Tehran (the sends' own rows carry the real time): 23:00 last
    # night is quiet, 10:00 this morning is not.
    morning = datetime.combine(
        datetime.now(TEHRAN).date(), datetime.min.time(), TEHRAN
    ) + timedelta(hours=10)
    night = morning - timedelta(hours=11)
    async with holding_switch(su, "released"), fake_telegram():
        async with hub.db.tx([co["id"]]) as tx:
            out = await lifecycle.send_template(
                tx, hub, company_id=co["id"], purpose="csat", dedupe_key="csat:a",
                conversation_id=a["conversation"]["id"], now=night,
            )  # fmt: skip
            assert (out["status"], out["reason"], out["message_id"]) == (
                "queued",
                "quiet_hours",
                None,
            )
            assert await lifecycle.retry_queued(tx, hub, now=morning) == 1
            again = await lifecycle.send_template(
                tx, hub, company_id=co["id"], purpose="csat", dedupe_key="csat:a",
                conversation_id=a["conversation"]["id"], now=morning,
            )  # fmt: skip
            assert again["status"] == "queued" and again["message_id"]  # sent in the morning, once
            capped = await lifecycle.send_template(
                tx, hub, company_id=co["id"], purpose="csat", dedupe_key="csat:b",
                conversation_id=b["conversation"]["id"], now=morning,
            )  # fmt: skip
            assert (capped["status"], capped["reason"]) == ("queued", "daily_cap")
        body = await su.fetchval(
            "SELECT body FROM support.messages WHERE id = $1", again["message_id"]
        )
        assert (
            desk.SAFETY_DEFAULT.split("؛")[0] in body
        )  # every lifecycle message carries the safety line
        stop = await inbound(hub, co["id"], "لغو", user="8102", message_id="stop-1")
        res = await process(hub, co["id"], stop["message"]["id"])
        assert res.result == "opted_out"
        async with hub.db.tx([co["id"]]) as tx:
            later = await lifecycle.send_template(
                tx, hub, company_id=co["id"], purpose="csat", dedupe_key="csat:b2",
                conversation_id=b["conversation"]["id"], now=morning + timedelta(days=2),
            )  # fmt: skip
    assert (later["status"], later["reason"]) == ("skipped", "opted_out")


async def test_a_new_template_version_pauses_its_rules(
    hub: Hub, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    rule = await _sealed_rule(hub, co["id"], "nps")
    async with hub.db.tx([co["id"]]) as tx:
        tref, tver = rule["template_ref"], rule["template_version"]
        await lifecycle.propose_template(
            tx, company_id=co["id"], purpose="nps", body_fa="نسخه‌ی تازه: از ۰ تا ۱۰؟",
            variables=[], by_kind="owner", by_code="owner", ref=tref,
        )  # fmt: skip
        r = await lifecycle.rule(tx, rule["ref"])
        assert (r["status"], r["paused_reason"]) == ("paused", "template_new_version")
        assert not await lifecycle.current_sealed(tx, tref, tver)


async def test_closing_asks_for_csat_and_the_reply_is_its_score(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], new_company: Callable[..., Any],
    su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    await seal_basics(hub, co["id"])
    await make_live(su, co["id"])
    await _sealed_rule(hub, co["id"], "csat", limits={"quiet_hours": ["00:00", "00:00"]})
    msg = await inbound(hub, co["id"], "سلام، مشکلم حل شد؟", user="8701")
    ref = msg["conversation"]["ref"]
    async with holding_switch(su, "released"), fake_telegram() as tg:
        r = await client.post(f"/api/v1/support/conversations/{ref}/close", headers=owner)
        assert r.status_code == 200 and r.json()["state"] == "closed"
        asked = await su.fetchrow(
            """SELECT m.id, m.template, c.csat_asked_at FROM support.messages m
               JOIN support.conversations c ON c.id = m.conversation_id
               WHERE c.ref = $1 AND m.direction = 'out' AND m.author = 'rule'""",
            ref,
        )
        assert asked and asked["template"] and asked["csat_asked_at"] is not None
        await send_all(hub, co["id"], [asked["id"]])
        assert len(tg.calls) == 1
        assert (
            await su.fetchval("SELECT status FROM growth.sends WHERE message_id = $1", asked["id"])
            == "sent"
        )
        reply = await inbound(hub, co["id"], "۴", user="8701", message_id="csat-1")
        out = await process(hub, co["id"], reply["message"]["id"])
    assert out.result == "csat"
    assert await su.fetchval("SELECT csat FROM support.conversations WHERE ref = $1", ref) == 4
    # The reply opened no new support case: its carrier conversation is closed again.
    assert (
        await su.fetchval(
            "SELECT state FROM support.conversations WHERE id = $1", reply["conversation"]["id"]
        )
        == "closed"
    )


async def test_the_nps_score_and_a_wave(hub: Hub, new_company: Callable[..., Any], su: Any) -> None:
    assert lifecycle.nps_score(5, 3, 2) == 30
    assert lifecycle.nps_score(0, 0, 0) is None
    assert lifecycle.nps_score(0, 0, 4) == -100
    co = await new_company()
    await seal_basics(hub, co["id"])
    await make_live(su, co["id"])
    await _sealed_rule(hub, co["id"], "nps")
    for n in range(4):
        await inbound(hub, co["id"], "سلام", user=f"86{n:02d}")
    now = datetime(2026, 10, 2, 12, 0, tzinfo=TEHRAN)  # Q4's wave (the rrule fired 1 Oct 10:00)
    async with holding_switch(su, "released"), fake_telegram():
        async with hub.db.tx([co["id"]]) as tx:
            opened = await lifecycle.nps_due(tx, hub, now=now)
        ref = f"NP-2026Q4-{co['code']}"
        assert ref in opened
        scores = {"8600": "10 عالی بود", "8601": "9", "8602": "۳ کند بود", "8603": "7"}
        for user, text in scores.items():
            m = await inbound(hub, co["id"], text, user=user, message_id=f"nps-{user}")
            assert (await process(hub, co["id"], m["message"]["id"])).result == "nps"
        async with hub.db.tx([co["id"]]) as tx:
            w = await tx.one("SELECT * FROM growth.nps_waves WHERE ref = :r", r=ref)
            closed = await lifecycle.close_wave(tx, hub, w)
    assert (closed["promoters"], closed["passives"], closed["detractors"]) == (2, 1, 1)
    assert closed["score"] == 25 and closed["comments_to_feedback"] == 2
    quotes = await su.fetch(
        "SELECT source_ref, quote FROM feedback.signals WHERE company_id = $1", co["id"]
    )
    assert {q["source_ref"] for q in quotes} == {ref} and len(quotes) == 2


async def test_an_agents_template_card_is_sealed_by_the_owner(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    lead = await hire(su, co["code"], "support_lead")
    async with holding_switch(su, "released"):
        r = await client.post(
            "/internal/v1/decisions", headers={**await agent_headers(lead), **idem()},
            json={"kind": "message_template", "title": "قالب بهتر نجات",
                  "payload": {"template": {"purpose": "rescue", "body_fa": "سلام، ثبت‌نام با رفرال ما مزیت VIP دارد."}}},
        )  # fmt: skip
    assert r.status_code == 201, r.text
    card = r.json()
    t = card["payload"]["template"]
    assert t["status"] == "proposed" and card["payload"]["sha256"] == t["sha256"]
    su_h = await step_up(hub, owner_session["session_id"], "decision.approve", card["ref"])
    r = await client.post(
        f"/api/v1/decisions/{card['ref']}/approve",
        headers={**owner_session["headers"], **su_h, **idem()},
        json={},
    )
    assert r.status_code == 200, r.text
    assert (
        await su.fetchval(
            "SELECT status FROM growth.templates WHERE ref = $1 AND version = $2",
            t["ref"],
            t["version"],
        )
        == "sealed"
    )


# ------------------------------------------------------------ §11 overseer --
async def test_the_support_protocols_are_seeded_paused_and_pr043_defers_without_a_live_channel(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await O.seed_protocols(tx, holding.id, charters.load().root)
    rows = {
        r["ref"]: r["status"]
        for r in await su.fetch(
            "SELECT ref, status FROM oversight.current_protocols WHERE ref = ANY($1::text[])",
            ["PR-043", "PR-101", "PR-102", "PR-103", "PR-104"],
        )
    }
    assert rows == dict.fromkeys(("PR-043", "PR-101", "PR-102", "PR-103", "PR-104"), "paused")
    live = await su.fetchval(
        "SELECT count(*) FROM support.channels WHERE state = 'live' AND kind <> 'mystery'"
    )
    async with holding_switch(su, "engaged"), hub.db.tx(await hub.companies.ids()) as tx:
        assert await OS.GATES["PR-043"](tx) == ("skipped", "holding_locked")
    async with holding_switch(su, "released"), hub.db.tx(await hub.companies.ids()) as tx:
        verdict = await OS.GATES["PR-043"](tx)
    if live == 0:
        assert verdict == ("deferred", "no company has a live support channel")
    else:
        assert verdict is None
    assert "PR-101" in C.CHECKS and "PR-103" in C.CHECKS and "PR-102" in C.PRECHECKS
    assert "PR-104" in C.CHECKS


async def test_pr104_finds_an_answer_that_cites_an_expired_article(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    """PR-104 by code: an automatic answer citing an article version that had
    expired when it was sent is a finding; a current one is not."""
    co = await new_company()
    good = await article(hub, co["id"], "ساعت کاری پشتیبانی؟", "هر روز ۹ تا ۱۸.")
    old = await article(hub, co["id"], "کارمزد برداشت؟", "طبق جدول کارمزد.")
    await su.execute(
        "UPDATE support.kb_articles SET expires_at = now() - interval '1 hour' WHERE id = $1",
        old["id"],
    )
    msg = await inbound(hub, co["id"], "سلام")
    for ref in (f"{good['ref']}@{good['version']}", f"{old['ref']}@{old['version']}"):
        await su.execute(
            """INSERT INTO support.messages (company_id, conversation_id, direction, author, body, status,
                   sent_at, kb_refs)
               VALUES ($1, $2, 'out', 'rule', 'پاسخ', 'sent', now(), ARRAY[$3])""",
            co["id"], msg["conversation"]["id"], ref,
        )  # fmt: skip
    holding = await hub.companies.holding()
    companies = {c.code: c.id for c in await hub.companies.all() if c.status == "active"}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ctx = C.CheckCtx(tx, holding.id, holding.code, companies, datetime.now(UTC), {})
        checked = await C.CHECKS["PR-104"](ctx)
    mine = [p for p in checked.problems if p.company == co["code"]]
    assert len(mine) == 1 and mine[0].key.endswith(f"{old['ref']}@{old['version']}")


async def test_pr101_finds_an_automatic_message_with_an_unapproved_link(
    hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    msg = await inbound(hub, co["id"], "سلام")
    await su.execute(
        """INSERT INTO support.messages (company_id, conversation_id, direction, author, body, status, sent_at)
           VALUES ($1, $2, 'out', 'agent', 'ثبت‌نام: https://lbank.com/ref/FAKE99', 'sent', now())""",
        co["id"],
        msg["conversation"]["id"],
    )
    holding = await hub.companies.holding()
    companies = {c.code: c.id for c in await hub.companies.all() if c.status == "active"}
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ctx = C.CheckCtx(tx, holding.id, holding.code, companies, datetime.now(UTC), {})
        checked = await C.CHECKS["PR-101"](ctx)
    mine = [p for p in checked.problems if p.company == co["code"]]
    assert len(mine) == 1 and mine[0].key.startswith("msg:")
    async with hub.db.tx([co["id"]]) as tx:
        assert await gate.automation_lock(tx, co["id"]) in (None, "holding")
