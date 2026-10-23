"""Prompt 10 §1 (contract §19.0): the five schemas, the pseudonym, the masks
before storage, the retention job, OPA access; and the foundation the later
sections build on (the launch gate, the charters, topics, codes, kinds)."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable
from datetime import time
from typing import Any

import httpx
import pytest

from hq_api import errors, events
from hq_api.domain import gate
from hq_api.domain import support as S
from hq_api.errors import ApiError
from hq_api.hub import Hub
from hq_api.secrets import Secrets
from hq_api.worker import schedules
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.support_activities import SupportActivities
from hq_common import charters, customer_mask

WORDS = sorted(customer_mask.wordlist())
SEED = " ".join(WORDS[300:312])
KEY_HEX = hashlib.sha256(b"p10 test key").hexdigest()
P10_SCHEMAS = ["revenue", "support", "growth", "feedback", "intake"]


async def _inbound(hub: Hub, co: dict[str, Any], body: str, **kw: Any) -> dict[str, Any]:
    async with hub.db.tx([co["id"]]) as tx:
        return await S.store_inbound(
            tx,
            hub,
            company_id=co["id"],
            channel_kind=kw.pop("channel", "telegram_bot"),
            external_user_id=kw.pop("user", "1001"),
            body=body,
            **kw,
        )


async def test_a_seed_phrase_is_masked_before_storage_and_for_a_model(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    body = f"سلام، کلمات بازیابی من: {SEED} و کلید {KEY_HEX} لطفاً بررسی کنید"
    out = await _inbound(hub, co, body, handle="@ali_test", external_message_id="m-1")
    assert out["masked"] == ("private_key", "seed_phrase") and out["first_secret"]
    assert out["conversation"]["ref"].startswith("SC-") and not out["duplicate"]
    stored = await su.fetchrow(
        "SELECT body, masked, status, direction FROM support.messages WHERE id = $1",
        out["message"]["id"],
    )
    assert customer_mask.SEED in stored["body"] and customer_mask.KEY in stored["body"]
    assert all(w not in stored["body"] for w in SEED.split()) and KEY_HEX not in stored["body"]
    assert set(stored["masked"]) == {"seed_phrase", "private_key"}
    assert (stored["status"], stored["direction"]) == ("sent", "in")
    # Nothing raw anywhere in the database: the support tables hold only the masked text.
    raw_hits = await su.fetchval(
        """SELECT count(*) FROM support.messages WHERE body LIKE '%' || $1 || '%'""", SEED
    )
    assert raw_hits == 0
    async with hub.db.tx([co["id"]]) as tx:
        view = await S.model_view(tx, out["conversation"]["id"])
    assert len(view) == 1 and customer_mask.SEED in view[0]["body"]
    assert set(view[0]) == {"at", "direction", "author", "body"}  # no customer identity
    # A webhook retry with the same message id stores nothing twice.
    again = await _inbound(hub, co, body, external_message_id="m-1")
    assert again["duplicate"] and again["conversation"]["id"] == out["conversation"]["id"]
    assert (
        await su.fetchval(
            "SELECT count(*) FROM support.messages WHERE conversation_id = $1",
            out["conversation"]["id"],
        )
        == 1
    )
    # The raw handle and user id live in support.customers only; the subject is the HMAC.
    cust = await su.fetchrow(
        "SELECT handle, external_id, subject FROM support.customers WHERE id = $1",
        out["customer_id"],
    )
    assert (cust["handle"], cust["external_id"]) == ("@ali_test", "1001")
    assert cust["subject"] == out["subject"] == S.subject(hub, co["id"], "telegram_bot", "1001")


async def test_fx_sees_no_support_row_of_ty(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    ty, fx = await new_company(), await new_company()
    await _inbound(hub, ty, "سلام، کمک می‌خواهم")
    for table in ("support.customers", "support.conversations", "support.messages"):
        async with hub.db.tx([fx["id"]]) as tx:
            assert (
                await tx.scalar(f"SELECT count(*) FROM {table} WHERE company_id = :c", c=ty["id"])
                == 0
            )
        async with hub.db.tx([ty["id"]]) as tx:
            assert (
                await tx.scalar(f"SELECT count(*) FROM {table} WHERE company_id = :c", c=ty["id"])
                == 1
            )
    # An agent of FX, even FX's support agent, is refused TY's conversations (OPA).
    fx_agent = {
        "kind": "agent", "code": f"{fx['code']}-SALES-01", "role": "employee",
        "company": fx["code"], "department": "SALES", "status": "active", "scope": "company",
    }  # fmt: skip
    own = await hub.policy.query(
        "internal",
        {"principal": fx_agent, "op": "support.read",
         "target": {"company": fx["code"], "charter": "support_agent"}},
    )  # fmt: skip
    other = await hub.policy.query(
        "internal",
        {"principal": fx_agent, "op": "support.read",
         "target": {"company": ty["code"], "charter": "support_agent"}},
    )  # fmt: skip
    assert own.allow and not other.allow
    assert "support.read_not_permitted" in other.reasons


async def test_revenue_growth_and_feedback_hold_no_raw_handle_or_uid(su: Any) -> None:
    cols = await su.fetch(
        """SELECT table_schema || '.' || table_name || '.' || column_name AS c
           FROM information_schema.columns
           WHERE table_schema IN ('revenue', 'growth', 'feedback', 'intake')
             AND column_name ~ '(handle|uid|external_id|display_name|username|phone|email)'"""
    )
    assert [r["c"] for r in cols] == []
    # Every subject column holds an HMAC (hex 64), never a raw UID.
    subjects = await su.fetch(
        """SELECT c.table_schema AS s, c.table_name AS t FROM information_schema.columns c
           JOIN information_schema.tables x USING (table_schema, table_name)
           WHERE c.column_name = 'subject' AND x.table_type = 'BASE TABLE'
             AND c.table_schema = ANY($1::text[])""",
        P10_SCHEMAS,
    )
    named = {f"{r['s']}.{r['t']}" for r in subjects}
    assert {"revenue.invitees", "growth.rescue_cases", "growth.referral_checks"} <= named
    co = await su.fetchval("SELECT id FROM core.companies WHERE kind = 'holding'")
    with pytest.raises(Exception) as info:
        await su.execute(
            """INSERT INTO growth.rescue_cases (company_id, source, exchange, subject)
               VALUES ($1, 'product', 'lbank', '88123456')""",
            co,
        )
    assert getattr(info.value, "sqlstate", None) == "23514"


async def test_retention_purges_old_texts_keeps_the_rows_and_runs_while_locked(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    out = await _inbound(hub, co, "پیام تازه")
    conv = out["conversation"]["id"]
    made = []
    for days, text in ((181, "متن ۱۸۱ روزه"), (179, "متن ۱۷۹ روزه")):
        made.append(
            await su.fetchval(
                """INSERT INTO support.messages (company_id, conversation_id, at, direction, author,
                       body, status)
                   VALUES ($1, $2, now() - make_interval(days => $3), 'in', 'customer', $4, 'sent')
                   RETURNING id""",
                co["id"],
                conv,
                days,
                text,
            )
        )
    old, recent = made
    await su.execute("UPDATE support.conversations SET tags = ARRAY['vip'] WHERE id = $1", conv)
    holding = await su.fetchrow(
        """SELECT k.company_id, k.state FROM control.kill_switches k
           JOIN core.companies c ON c.id = k.company_id WHERE c.kind = 'holding'"""
    )
    await su.execute(
        "UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1",
        holding["company_id"],
    )
    try:
        async with hub.db.tx([co["id"]]) as tx:
            assert await gate.automation_lock(tx, co["id"]) == "holding"
        result = await SupportActivities(hub, lambda: _ScopedTx(hub)).support_retention()
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = $2 WHERE company_id = $1",
            holding["company_id"],
            holding["state"],
        )
    assert result["days"] == 180 and result["messages"] >= 1
    rows = {
        r["id"]: r
        for r in await su.fetch(
            "SELECT id, body, body_purged_at, status FROM support.messages WHERE conversation_id = $1",
            conv,
        )
    }
    assert len(rows) == 3  # every row stays
    assert rows[old]["body"] is None and rows[old]["body_purged_at"] is not None
    assert rows[old]["status"] == "sent"
    assert rows[recent]["body"] == "متن ۱۷۹ روزه" and rows[recent]["body_purged_at"] is None
    assert await su.fetchval("SELECT tags FROM support.conversations WHERE id = $1", conv) == [
        "vip"
    ]
    async with hub.db.tx([co["id"]]) as tx:
        assert [m["body"] for m in await S.model_view(tx, conv)] == ["متن ۱۷۹ روزه", "پیام تازه"]
    with pytest.raises(ValueError, match="at least 1"):
        async with hub.db.tx([co["id"]]) as tx:
            await S.purge_texts(tx, 0)


async def test_the_gate_reports_the_holding_and_the_company_lock(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    holding = await su.fetchrow(
        """SELECT k.company_id, k.state FROM control.kill_switches k
           JOIN core.companies c ON c.id = k.company_id WHERE c.kind = 'holding'"""
    )
    try:
        await su.execute(
            "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1",
            holding["company_id"],
        )
        async with hub.db.tx([co["id"]]) as tx:
            assert await gate.holding_lock(tx) is None
            assert await gate.automation_lock(tx, co["id"]) is None
            await gate.require_unlocked(tx, co["id"])
        await su.execute(
            "UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1", co["id"]
        )
        async with hub.db.tx([co["id"]]) as tx:
            assert await gate.holding_lock(tx) is None
            assert await gate.automation_lock(tx, co["id"]) == "company"
            assert await gate.automation_lock(tx) is None
        await su.execute(
            "UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1",
            holding["company_id"],
        )
        async with hub.db.tx([co["id"]]) as tx:
            assert await gate.holding_lock(tx) == "holding"
            assert await gate.automation_lock(tx, co["id"]) == "holding"
            with pytest.raises(gate.Locked) as info:
                await gate.require_unlocked(tx)
        assert info.value.lock == "holding"
        assert gate.skipped("holding", company="TY") == {
            "skipped": True,
            "reason": "holding_locked",
            "company": "TY",
        }
        assert gate.skipped("deploy_freeze")["reason"] == "deploy_freeze"
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = $2 WHERE company_id = $1",
            holding["company_id"],
            holding["state"],
        )
        await su.execute(
            "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", co["id"]
        )


async def test_no_pseudonym_without_the_key(hub: Hub, new_company: Callable[..., Any]) -> None:
    co = await new_company()
    keyless = dataclasses.replace(hub, secrets=Secrets())
    with pytest.raises(ApiError) as info:
        S.subject(keyless, co["id"], "telegram_bot", "1")
    assert (info.value.status, info.value.code) == (503, "not_ready")
    async with hub.db.tx([co["id"]]) as tx:
        with pytest.raises(ApiError):
            await S.store_inbound(
                tx, keyless, company_id=co["id"], channel_kind="telegram_bot",
                external_user_id="1", body="x",
            )  # fmt: skip
        assert (
            await tx.scalar(
                "SELECT count(*) FROM support.customers WHERE company_id = :c", c=co["id"]
            )
            == 0
        )
        with pytest.raises(ApiError):
            await S.channel(tx, co["id"], "sms")


async def test_settings_and_channels_start_with_their_defaults_and_guard_themselves(
    hub: Hub, new_company: Callable[..., Any], su: Any
) -> None:
    co, other = await new_company(), await new_company()
    async with hub.db.tx([co["id"]]) as tx:
        st = await S.settings(tx, co["id"])
        assert st["verbatim_threshold"] is None and st["feedback_threshold"] == 5
        ch = await S.channel(tx, co["id"], "telegram_bot")
        assert (ch["state"], ch["auto_send"], ch["live_since"]) == (
            "not_configured",
            "kb_verbatim",
            None,
        )
        assert (await S.channel(tx, co["id"], "telegram_bot"))["version"] == ch["version"]
    # Live only with a go-live card; thresholds only with a new card.
    for stmt, args in (
        (
            "UPDATE support.channels SET state = 'live', live_since = now() WHERE company_id = $1",
            (co["id"],),
        ),
        ("UPDATE support.settings SET verbatim_threshold = 0.8 WHERE company_id = $1", (co["id"],)),
    ):
        with pytest.raises(Exception) as info:
            await su.execute(stmt, *args)
        assert getattr(info.value, "sqlstate", None) in ("23514", "HQV01"), stmt
    # A versioned ref never crosses into another company (seal replay).
    ref = await su.fetchval(
        """INSERT INTO support.kb_articles (company_id, kind, question_fa, answer_md, sha256,
               proposed_by_kind, proposed_by_code) VALUES ($1, 'faq', 'س', 'ج', $2, 'owner', 'owner')
           RETURNING ref""",
        co["id"],
        "a" * 64,
    )
    with pytest.raises(Exception) as info:
        await su.execute(
            """INSERT INTO support.kb_articles (ref, version, company_id, kind, question_fa, answer_md,
                   sha256, proposed_by_kind, proposed_by_code)
               VALUES ($1, 2, $2, 'faq', 'س', 'ج', $3, 'owner', 'owner')""",
            ref,
            other["id"],
            "b" * 64,
        )
    assert getattr(info.value, "sqlstate", None) == "HQV01"


async def test_the_new_charters_are_seeded_and_nobody_is_hired(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    lib = charters.load()
    expected = {
        "support_lead": ("SALES", "claude-sonnet-5-5", "P2"),
        "support_agent": ("SALES", "claude-haiku-5-5", "P1"),
        "referral_rescue": ("SALES", "claude-haiku-5-5", "P2"),
        "revenue_analyst": ("FIN", "claude-haiku-5-5", "P3"),
    }
    for role, (dept, model, priority) in expected.items():
        c = lib.roles[role]
        assert (c.kind, c.scope, c.department, c.model, c.effort, c.priority) == (
            "employee", "company", dept, model, "high", priority,
        ), role  # fmt: skip
        assert c.version >= 1
        assert not [p for p in lib.problems if p.startswith(f"{role}:")]
    # No send tool for the rescue specialist; the support agent drafts only.
    assert not {"message.owner", "notify", "support.draft"} & set(lib.allowed("referral_rescue"))
    assert "support.draft" in lib.allowed("support_agent")
    roles = {r["role"]: r for r in (await client.get("/api/v1/roles", headers=owner)).json()}
    assert set(expected) <= set(roles) and roles["support_agent"]["priority"] == "P1"
    # Nobody is hired by the seed or the prompt (the support desk's own tests
    # make employees in their throwaway companies, "Test <code>").
    hired = await su.fetchval(
        """SELECT count(*) FROM core.employees e JOIN core.companies c ON c.id = e.company_id
           WHERE e.role = ANY($1::text[]) AND c.name NOT LIKE 'Test %'""",
        list(expected),
    )
    assert hired == 0


def test_topics_codes_and_the_retention_schedule() -> None:
    for topic in ("revenue", "support", "growth", "feedback"):
        assert topic in events.TOPICS
    assert events.TOPICS["growth"] == ("rescue.", "lifecycle.", "nps.")
    statuses = {
        "channel_not_live": 409, "shadow_not_passed": 409, "template_not_sealed": 409,
        "send_blocked": 422, "opted_out": 409, "send_limit": 429,
    }  # fmt: skip
    for code, status in statuses.items():
        assert errors.CODES[code][0] == status, code
    fixed = {d.id: d for d in schedules.fixed(time(8, 0), "Asia/Tehran")}
    retention = fixed[schedules.SUPPORT_RETENTION]
    assert retention.workflow == "SupportRetention" and not retention.paused
    cal = retention.spec.calendars[0]
    assert (cal.hour[0].start, cal.minute[0].start) == (4, 15)


async def test_the_new_decision_kinds_and_the_shadow_suites(su: Any) -> None:
    check = await su.fetchval(
        """SELECT pg_get_constraintdef(oid) FROM pg_constraint
           WHERE conname = 'decisions_kind_check' AND conrelid = 'cartable.decisions'::regclass"""
    )
    for kind in ("message_template", "lifecycle_rule", "support_go_live", "hire", "server_plan"):
        assert f"'{kind}'" in check, kind
    # Prompt 11: 0026 and 0026_1 re-add it NOT VALID with their kinds and the
    # head (0026_1) validates it; every card there fits the constraint.
    for kind in ("meeting_resolution", "charter_amendment", "knowledge_entry", "okr",
                 "risk_acceptance", "authority_change"):  # fmt: skip
        assert f"'{kind}'" in check, kind
    # ⟨1.6⟩ prompt 13's migration 0028 adds its kinds to the same CHECK NOT VALID
    # (the run sheet's rule for a rewritten kind CHECK); the head (0028_1)
    # validates it, and every row fits it.
    assert await su.fetchval(
        """SELECT convalidated FROM pg_constraint
           WHERE conname = 'decisions_kind_check' AND conrelid = 'cartable.decisions'::regclass"""
    )
    assert not await su.fetchval(
        """SELECT count(*) FROM cartable.decisions d WHERE NOT (d.kind = ANY (
               SELECT m[1] FROM pg_constraint c,
                      regexp_matches(pg_get_constraintdef(c.oid), '''([a-z0-9_]+)''', 'g') AS m
               WHERE c.conname = 'decisions_kind_check'
                 AND c.conrelid = 'cartable.decisions'::regclass))"""
    )
    suites = await su.fetchval(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'eval_suites_ref_check'"
    )
    assert "support-shadow-" in suites
    purposes = await su.fetchval(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'eval_runs_purpose_check'"
    )
    assert "'shadow'" in purposes
