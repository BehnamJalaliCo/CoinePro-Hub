"""Shared setup for the support desk tests (prompt 10 §4-§7, §9, §11): a fake
Telegram (no real call ever leaves), live channels made the way a sealed
go-live card makes them, sealed basic templates, approved articles, the
holding switch held open or engaged for one test."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from hq_api.domain import desk, kb, lifecycle
from hq_api.domain import support as S
from hq_api.hub import Hub


class FakeTelegram:
    """Stands in for egress -> Telegram: records what would have been sent."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.answer = desk.SendResult(True)

    async def send(
        self, hub: Any, *, company: str, channel: dict[str, Any], conv: dict[str, Any], text: str
    ) -> desk.SendResult:
        self.calls.append({"company": company, "channel": channel["kind"], "text": text})
        return desk.SendResult(
            self.answer.ok, self.answer.code, external_id=str(len(self.calls))
        )


@contextlib.asynccontextmanager
async def fake_telegram() -> AsyncIterator[FakeTelegram]:
    fake = FakeTelegram()
    desk.OVERRIDE = fake
    try:
        yield fake
    finally:
        desk.OVERRIDE = None


@contextlib.asynccontextmanager
async def holding_switch(su: Any, state: str) -> AsyncIterator[None]:
    """The holding's kill switch `released` (the hub launched) or `engaged`
    for one test, restored afterwards."""
    row = await su.fetchrow(
        """SELECT k.company_id, k.state FROM control.kill_switches k
           JOIN core.companies c ON c.id = k.company_id WHERE c.kind = 'holding'"""
    )
    await su.execute(
        "UPDATE control.kill_switches SET state = $2 WHERE company_id = $1", row["company_id"], state
    )
    try:
        yield
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = $2 WHERE company_id = $1",
            row["company_id"],
            row["state"],
        )


async def make_live(
    su: Any,
    company_id: UUID,
    kind: str = "telegram_bot",
    *,
    auto_send: str = "kb_verbatim",
    verbatim: float = 0.9,
    grounded: float = 0.8,
) -> None:
    """What a sealed support_go_live card leaves behind (the test's shortcut)."""
    d = await su.fetchval(
        """INSERT INTO cartable.decisions (company_id, kind, action_class, title, proposer_kind,
               proposer_code, status, decided_at, payload)
           VALUES ($1, 'support_go_live', 'A3', 'go live (test)', 'service', 'support', 'approved',
                   now(), '{}') RETURNING id""",
        company_id,
    )
    await su.execute(
        "INSERT INTO support.channels (company_id, kind) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        company_id,
        kind,
    )
    await su.execute(
        """UPDATE support.channels SET state = 'live', live_since = now(), go_live_decision_id = $3,
               auto_send = $4 WHERE company_id = $1 AND kind = $2""",
        company_id,
        kind,
        d,
        auto_send,
    )
    await su.execute(
        "INSERT INTO support.settings (company_id) VALUES ($1) ON CONFLICT DO NOTHING", company_id
    )
    await su.execute(
        """UPDATE support.settings SET verbatim_threshold = $2, grounded_threshold = $3,
               thresholds_decision_id = $4 WHERE company_id = $1""",
        company_id,
        verbatim,
        grounded,
        d,
    )


async def seal_basics(hub: Hub, company_id: UUID) -> dict[str, str]:
    """The company's seeded holding_reply and safety templates, sealed."""
    out: dict[str, str] = {}
    async with hub.db.tx([company_id]) as tx:
        await lifecycle.ensure_seed(tx, company_id)
        for purpose in ("holding_reply", "safety"):
            t = await tx.one(
                """SELECT * FROM growth.templates WHERE company_id = :co AND purpose = :p
                   ORDER BY version DESC LIMIT 1""",
                co=company_id,
                p=purpose,
            )
            if t["status"] != "sealed":
                t = await lifecycle.seal_template(tx, t["ref"], t["version"], step_up_id=None)
            out[purpose] = t["body_fa"]
    return out


async def article(
    hub: Hub,
    company_id: UUID,
    question: str,
    answer: str,
    *,
    kind: str = "faq",
    key: str | None = None,
    links: list[dict[str, Any]] | None = None,
    codes: list[dict[str, Any]] | None = None,
    variants: list[str] | None = None,
    approve: bool = True,
) -> dict[str, Any]:
    async with hub.db.tx([company_id]) as tx:
        row = await kb.propose(
            tx, company_id=company_id, kind=kind, key=key, question_fa=question, answer_md=answer,
            links=links, codes=codes, variants=variants, by_kind="owner", by_code="owner",
        )  # fmt: skip
        if approve:
            row = await kb.approve(tx, row["ref"], row["version"], step_up_id=None, expiry_days=180)
    return row


async def inbound(
    hub: Hub,
    company_id: UUID,
    body: str,
    *,
    user: str = "7001",
    channel: str = "telegram_bot",
    message_id: str | None = None,
) -> dict[str, Any]:
    async with hub.db.tx([company_id]) as tx:
        return await S.store_inbound(
            tx, hub, company_id=company_id, channel_kind=channel, external_user_id=user,
            body=body, external_message_id=message_id, handle="@cust_test",
            external={"chat_id": int(user) if user.isdigit() else 1},
        )  # fmt: skip


async def process(hub: Hub, company_id: UUID, message_id: Any) -> desk.Outcome:
    async with hub.db.tx([company_id]) as tx:
        return await desk.process(tx, hub, message_id)


async def send_all(hub: Hub, company_id: UUID, ids: list[Any]) -> list[dict[str, Any]]:
    out = []
    for mid in ids:
        async with hub.db.tx([company_id]) as tx:
            out.append(await desk.send(tx, hub, mid))
    return out


async def hire(su: Any, company: str, role: str, dept: str = "SALES", n: int = 1) -> str:
    code = f"{company}-{dept}-{n:02d}"
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role)
           SELECT c.id, d.id, $1, 'employee', $3, $3, $3
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = $4
           WHERE c.code = $2""",
        code,
        company,
        role,
        dept,
    )
    return code


async def llm_calls(su: Any) -> int:
    return int(await su.fetchval("SELECT count(*) FROM llm.calls"))


def j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v
