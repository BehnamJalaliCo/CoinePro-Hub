"""Prompt 13 §3 (contract §22.4, §22.7): the holding's legal counsel. Cases
and their timeline; an email is sent only by the owner's seal, exactly once
(a fake SMTP); a change after the owner saw it is a new card; a reply reaches
its case and wakes the counsel, unrelated mail is not stored; the counsel
reaches its own cases only; the mailbox password is never in an answer or a
log; the poller does nothing while the holding is locked."""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import AsyncIterator, Callable
from email import policy as email_policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Any

import httpx
import pytest

from hq_api.domain import legal as L
from hq_api.domain import mail as MAIL
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx

from .conftest import agent_headers, idem, step_up
from .p10_support import holding_switch

ADDRESS = "legal@example.org"


class FakeMail:
    """The mailbox: a fake SMTP that records every message, and a fake IMAP
    inbox the test fills."""

    def __init__(self, configured: bool = True) -> None:
        self.on = configured
        self.sent: list[tuple[list[str], bytes]] = []
        self.inbox: list[tuple[int, bytes]] = []
        self.fetches = 0
        self.uidvalidity = 7

    async def configured(self, hub: Any, tx: Any) -> MAIL.Account | None:
        if not self.on:
            return None
        return await MAIL.account_row(tx)

    async def send(self, hub: Any, account: MAIL.Account, rcpt: list[str], raw: bytes) -> MAIL.Sent:
        self.sent.append((rcpt, raw))
        return MAIL.Sent(True)

    async def fetch(
        self, hub: Any, account: MAIL.Account, since_uid: int, uidvalidity: int | None
    ) -> MAIL.Fetched:
        self.fetches += 1
        return MAIL.Fetched(
            True, uidvalidity=self.uidvalidity, messages=[m for m in self.inbox if m[0] > since_uid]
        )


@pytest.fixture
async def mailbox(su: Any) -> AsyncIterator[FakeMail]:
    """The `mail` account's metadata (the secret would be the owner's) and
    the fake mailbox; the holding released for the agents' writes."""
    await su.execute(
        """INSERT INTO tools.accounts (key, site, title_fa, companies, policy)
           VALUES ('mail', 'example.org', 'صندوق حقوقی', NULL, $1::jsonb)
           ON CONFLICT (key) DO UPDATE SET site = EXCLUDED.site, policy = EXCLUDED.policy""",
        json.dumps({"inject": {"kind": "basic", "username": ADDRESS}, "ports": [465, 993]}),
    )
    fake = FakeMail()
    MAIL.OVERRIDE = fake
    try:
        async with holding_switch(su, "released"):
            yield fake
    finally:
        MAIL.OVERRIDE = None


def txf(hub: Hub) -> Callable[[], Any]:
    return lambda: _ScopedTx(hub)


async def _case(client: httpx.AsyncClient, lgl: dict[str, str], company: str) -> dict[str, Any]:
    r = await client.post(
        "/internal/v1/legal/cases",
        headers={**lgl, **idem()},
        json={
            "company": company,
            "title_fa": "محدودیت پاسخ دایرکت اینستاگرام",
            "kind": "platform_restriction",
            "brief_md": "اینستاگرام پاسخ دایرکت را محدود کرده است.",
            "counterpart": {"name": "Meta", "channel": "email", "address": "support@example.com"},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _draft(
    client: httpx.AsyncClient, lgl: dict[str, str], ref: str, body: str = "Dear team,\nPlease review."
) -> dict[str, Any]:
    r = await client.post(
        f"/internal/v1/legal/cases/{ref}/emails",
        headers={**lgl, **idem()},
        json={
            "to": ["Support@Example.com"],
            "cc": [],
            "subject": "Appeal: direct message replies limited",
            "body_md": body,
            "lang": "en",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _approve(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ref: str, target: str
) -> httpx.Response:
    seal = await step_up(hub, owner_session["session_id"], "decision.approve", target)
    return await client.post(
        f"/api/v1/decisions/{ref}/approve",
        headers={**owner_session["headers"], **seal, **idem()},
        json={},
    )


def _reply(to_mid: str, body: str, *, sender: str = "support@example.com") -> bytes:
    m = EmailMessage()
    m["From"] = sender
    m["To"] = ADDRESS
    m["Subject"] = "Re: Appeal: direct message replies limited"
    m["Message-ID"] = f"<{secrets.token_hex(8)}@example.com>"
    m["In-Reply-To"] = to_mid
    m["References"] = to_mid
    m.set_content(body)
    return bytes(m)


# ----------------------------------------------------------------- the seat --
async def test_the_holding_has_legal_and_hq_lgl_in_thread_l(su: Any) -> None:
    lgl = await su.fetchrow(
        """SELECT e.kind, e.role, e.activity, d.code AS dept, t.code AS thread, t.kind AS tkind
           FROM core.employees e JOIN core.departments d ON d.id = e.department_id
           JOIN msg.threads t ON t.employee_id = e.id WHERE e.code = 'HQ-LGL'"""
    )
    assert dict(lgl) == {"kind": "employee", "role": "legal_counsel", "activity": "sleeping",
                         "dept": "LEGAL", "thread": "L", "tkind": "legal"}  # fmt: skip
    # LEGAL has no manager (head: false), and nothing was made for one.
    assert not await su.fetchval("SELECT 1 FROM core.employees WHERE code = 'HQ-LEGAL-MGR'")
    assert not await su.fetchval("SELECT 1 FROM msg.threads WHERE code = 'HQ-LEGAL'")


async def test_the_owner_in_thread_l_wakes_the_counsel_and_only_it_answers_there(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    r = await client.post(
        "/api/v1/threads/L/messages", headers={**owner, **idem()}, json={"body": "وضعیت پرونده؟"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["message"]["ref"].startswith("L-")
    queued = await su.fetchrow(
        """SELECT r.priority FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           JOIN msg.threads t ON t.id = r.thread_id
           WHERE e.code = 'HQ-LGL' AND t.code = 'L' AND r.state = 'queued'"""
    )
    assert queued is not None and queued["priority"] == "P2"
    async with holding_switch(su, "released"):
        ok = await client.post(
            "/internal/v1/threads/L/messages",
            headers={**await agent_headers("HQ-LGL"), **idem()},
            json={"body": "پرونده در انتظار پاسخ است.", "links": {}},
        )
        assert ok.status_code == 201, ok.text
        other = await client.post(
            "/internal/v1/threads/L/messages",
            headers={**await agent_headers("HQ-PA"), **idem()},
            json={"body": "x"},
        )
        assert other.status_code == 403


# -------------------------------------------------------------- the email --
async def test_an_email_leaves_only_by_the_seal_and_exactly_once(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
    wk: dict[str, Any],
    su: Any,
) -> None:
    co = await new_company()
    lgl = await agent_headers("HQ-LGL")
    case = await _case(client, lgl, co["code"])
    assert case["ref"].startswith("LC-") and case["company"] == co["code"] and case["counsel"] == "HQ-LGL"
    out = await _draft(client, lgl, case["ref"])
    assert out["from"] == ADDRESS and out["state"] == "waiting_seal"
    d = (await client.get(f"/api/v1/decisions/{out['decision']}", headers=owner_session["headers"])).json()
    assert (d["kind"], d["action_class"], d["status"]) == ("email_send", "A3", "pending")
    p = d["payload"]
    assert p["to"] == ["support@example.com"] and p["from"] == ADDRESS and p["digest"] == out["digest"]
    assert p["digest"] == L.digest({
        "from_addr": p["from"], "to_addrs": p["to"], "cc_addrs": p["cc"], "subject": p["subject"],
        "body_md": p["body_md"], "attachments": p["attachments"], "lang": p["lang"],
    })  # fmt: skip
    assert mailbox.sent == []  # a draft is a card, nothing more
    # The seal is bound to the message digest, not to the card's ref.
    no = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve", headers={**owner_session["headers"], **idem()}, json={}
    )
    assert no.status_code == 403 and no.json()["code"] == "step_up_required"
    wrong = await _approve(client, hub, owner_session, d["ref"], d["ref"])
    assert wrong.status_code == 403 and wrong.json()["code"] == "step_up_invalid"
    amended = await client.post(
        f"/api/v1/decisions/{d['ref']}/approve",
        headers={**owner_session["headers"], **idem()},
        json={"amendments": {"subject": "x"}},
    )
    assert amended.status_code == 422
    ok = await _approve(client, hub, owner_session, d["ref"], out["digest"])
    assert ok.status_code == 200, ok.text
    assert mailbox.sent == []  # the worker's effect sends it, after the lock checks
    done = await wk["acts"].decision_apply_effect(d["ref"])
    assert done["effect"] == "applied" and done["email"] == "sent"
    again = await wk["acts"].decision_apply_effect(d["ref"])
    assert again["changed"] is False
    assert len(mailbox.sent) == 1
    rcpt, raw = mailbox.sent[0]
    msg = BytesParser(policy=email_policy.default).parsebytes(raw)
    assert rcpt == ["support@example.com"] and msg["From"] == ADDRESS and msg["To"] == "support@example.com"
    assert msg["Subject"] == p["subject"] and msg.get_body().get_content().strip() == p["body_md"].strip()
    full = (await client.get(f"/api/v1/legal/cases/{case['ref']}", headers=owner_session["headers"])).json()
    assert full["status"] == "waiting_reply"
    (email,) = [e for e in full["emails"] if e["direction"] == "out"]
    assert email["state"] == "sent" and email["message_id"] == msg["Message-ID"]
    assert [t["kind"] for t in full["timeline"]][-1] == "email_out"
    # The audit has the send (A3) once.
    n = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'legal.email_send' AND target_ref = $1", case["ref"]
    )
    assert n == 1


async def test_a_change_after_the_owner_saw_it_is_a_new_card(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
) -> None:
    co = await new_company()
    lgl = await agent_headers("HQ-LGL")
    case = await _case(client, lgl, co["code"])
    first = await _draft(client, lgl, case["ref"], "Version one.")
    second = await _draft(client, lgl, case["ref"], "Version two, after the owner read it.")
    assert first["decision"] != second["decision"] and first["digest"] != second["digest"]
    old = (await client.get(f"/api/v1/decisions/{first['decision']}", headers=owner_session["headers"])).json()
    assert old["status"] == "withdrawn"
    late = await _approve(client, hub, owner_session, first["decision"], first["digest"])
    assert late.status_code == 409 and late.json()["code"] == "decision_not_pending"
    assert (await _approve(client, hub, owner_session, second["decision"], second["digest"])).status_code == 200
    full = (await client.get(f"/api/v1/legal/cases/{case['ref']}", headers=owner_session["headers"])).json()
    states = {e["digest"]: e["state"] for e in full["emails"]}
    assert states == {first["digest"]: "superseded", second["digest"]: "queued"}


async def test_without_a_connected_mailbox_a_draft_stays_a_card(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
) -> None:
    """Owner decision §0.9 #6: no mailbox yet; the card can be read, its seal
    is refused before anything changes (409 account_not_configured)."""
    mailbox.on = False
    co = await new_company()
    lgl = await agent_headers("HQ-LGL")
    case = await _case(client, lgl, co["code"])
    out = await _draft(client, lgl, case["ref"])
    r = await _approve(client, hub, owner_session, out["decision"], out["digest"])
    assert r.status_code == 409 and r.json()["code"] == "account_not_configured"
    d = (await client.get(f"/api/v1/decisions/{out['decision']}", headers=owner_session["headers"])).json()
    assert d["status"] == "pending" and mailbox.sent == []


async def test_reject_reopens_the_case_and_closing_waits_for_the_seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
    su: Any,
) -> None:
    co = await new_company()
    lgl = await agent_headers("HQ-LGL")
    case = await _case(client, lgl, co["code"])
    out = await _draft(client, lgl, case["ref"])
    h = owner_session["headers"]
    shut = await client.post(f"/api/v1/legal/cases/{case['ref']}/close", headers={**h, **idem()}, json={})
    assert shut.status_code == 409
    r = await client.post(
        f"/api/v1/decisions/{out['decision']}/reject",
        headers={**h, **idem()},
        json={"reason": "لحن تندتر از لازم است", "reason_code": "quality"},
    )
    assert r.status_code == 200, r.text
    full = (await client.get(f"/api/v1/legal/cases/{case['ref']}", headers=h)).json()
    assert full["status"] == "open" and full["emails"][0]["state"] == "rejected"
    woke = await su.fetchrow(
        """SELECT w.run_meta FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code = 'HQ-LGL' AND w.title LIKE $1 ORDER BY w.created_at DESC LIMIT 1""",
        f"{case['ref']}:%",
    )
    assert woke is not None and json.loads(woke["run_meta"])["task_class"] == "legal_case"
    closed = await client.post(
        f"/api/v1/legal/cases/{case['ref']}/close", headers={**h, **idem()}, json={"note_fa": "حل شد"}
    )
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    assert mailbox.sent == []


# --------------------------------------------------------------- replies --
async def test_a_reply_reaches_its_case_and_wakes_the_counsel_unrelated_mail_does_not(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
    wk: dict[str, Any],
    su: Any,
) -> None:
    await su.execute("UPDATE legal.mailbox SET last_uid = 0, uidvalidity = NULL WHERE account = 'mail'")
    co = await new_company()
    lgl = await agent_headers("HQ-LGL")
    case = await _case(client, lgl, co["code"])
    out = await _draft(client, lgl, case["ref"])
    assert (await _approve(client, hub, owner_session, out["decision"], out["digest"])).status_code == 200
    await wk["acts"].decision_apply_effect(out["decision"])
    sent_mid = BytesParser(policy=email_policy.default).parsebytes(mailbox.sent[-1][1])["Message-ID"]
    mailbox.inbox = [
        (101, _reply(sent_mid, "We reviewed your account. Call +98 912 345 6789 or write ali@example.net.")),
        (102, _reply("<not-ours@example.com>", "A newsletter.")),
        (103, b"Subject: no headers at all\r\n\r\nspam"),
    ]
    got = await L.poll(hub, txf(hub))
    assert got["ok"] and got["matched"] == [case["ref"]] and got["ignored"] == 2 and got["last_uid"] == 103
    full = (await client.get(f"/api/v1/legal/cases/{case['ref']}", headers=owner_session["headers"])).json()
    inbound = [e for e in full["emails"] if e["direction"] == "in"]
    assert len(inbound) == 1 and inbound[0]["state"] == "received"
    assert "912 345 6789" not in inbound[0]["body_md"] and "ali@example.net" not in inbound[0]["body_md"]
    assert full["status"] == "open" and full["timeline"][-1]["kind"] == "email_in"
    woke = await su.fetchrow(
        """SELECT w.priority, w.run_meta FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code = 'HQ-LGL' AND w.title LIKE $1 ORDER BY w.created_at DESC LIMIT 1""",
        f"{case['ref']}: پاسخ%",
    )
    assert woke["priority"] == "P2" and json.loads(woke["run_meta"])["task_class"] == "legal_email"
    # Unrelated mail is not stored anywhere.
    assert not await su.fetchval("SELECT 1 FROM legal.emails WHERE message_id = '<not-ours@example.com>'")
    # Polling again finds nothing new (the cursor moved on).
    again = await L.poll(hub, txf(hub))
    assert again["matched"] == [] and again["ignored"] == 0
    # The counsel reads the case's mail, masked.
    mail = await client.get(f"/internal/v1/legal/cases/{case['ref']}/mail", headers=lgl)
    assert mail.status_code == 200 and len(mail.json()["emails"]) == 2


async def test_the_poller_does_nothing_while_the_holding_is_locked(
    hub: Hub, su: Any, mailbox: FakeMail, wk: dict[str, Any]
) -> None:
    async with holding_switch(su, "engaged"):
        out = await wk["acts"].legal_voice.legal_mail_poll()
    assert out == {"skipped": True, "reason": "holding_locked"}
    assert mailbox.fetches == 0
    mailbox.on = False
    unconfigured = await L.poll(hub, txf(hub))
    assert unconfigured == {"skipped": True, "reason": "account_not_configured"} and mailbox.fetches == 0


# ------------------------------------------------------------- the scope --
async def test_the_counsel_reaches_only_its_own_cases(
    client: httpx.AsyncClient,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    r = await client.post(
        "/api/v1/legal/cases",
        headers={**h, **idem()},
        json={"company": co["code"], "title_fa": "بازبینی قرارداد همکاری", "kind": "contract_review",
              "brief_md": "قرارداد را بخوان."},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["counsel"] == "HQ-LGL" and case["opened_by"]["kind"] == "owner"
    woke = await su.fetchrow(
        """SELECT w.priority, w.run_meta FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
           WHERE e.code = 'HQ-LGL' AND w.title LIKE $1""",
        f"{case['ref']}:%",
    )
    assert woke["priority"] == "P2" and json.loads(woke["run_meta"])["task_class"] == "legal_case"
    code = "HQ-LEGAL-77"  # a second counsel (the test database outlives a run: made once)
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, role)
           SELECT c.id, d.id, $1, 'employee', 'مشاور دوم', 'Second counsel', 'legal_counsel'
           FROM core.companies c JOIN core.departments d ON d.company_id = c.id AND d.code = 'LEGAL'
           WHERE c.kind = 'holding' ON CONFLICT (code) DO NOTHING""",
        code,
    )
    other = await agent_headers(code)
    assert (await client.get(f"/internal/v1/legal/cases/{case['ref']}/mail", headers=other)).status_code == 404
    note = await client.post(
        f"/internal/v1/legal/cases/{case['ref']}/notes",
        headers={**other, **idem()},
        json={"kind": "note", "summary_fa": "x"},
    )
    assert note.status_code == 404
    lgl = await agent_headers("HQ-LGL")
    mine = await client.post(
        f"/internal/v1/legal/cases/{case['ref']}/notes",
        headers={**lgl, **idem()},
        json={"kind": "note", "summary_fa": "مهلت اعتراض", "deadline": {"at": "2031-01-05T09:00:00Z",
              "what_fa": "پایان مهلت اعتراض"}},
    )  # fmt: skip
    assert mine.status_code == 200 and mine.json()["deadlines"][0]["what_fa"] == "پایان مهلت اعتراض"
    # A company's employee has no legal tool at all.
    ceo = await agent_headers(f"{co['code']}-CEO")
    denied = await client.get(f"/internal/v1/legal/cases/{case['ref']}/mail", headers=ceo)
    assert denied.status_code == 403


async def test_a_ceo_asks_the_holdings_counsel_through_a_work_item(
    client: httpx.AsyncClient, new_company: Callable[..., Any], su: Any
) -> None:
    co = await new_company()
    async with holding_switch(su, "released"):
        ceo = await agent_headers(f"{co['code']}-CEO")
        r = await client.post(
            "/internal/v1/work",
            headers={**ceo, **idem()},
            json={"company": "HQ", "department": "LEGAL", "title": "اعتراض به محدودیت پیج",
                  "brief": "پیج ما محدود شد؛ راه‌ها را پیدا کن."},
        )  # fmt: skip
        assert r.status_code == 201, r.text
        assignee = await su.fetchval(
            """SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id
               WHERE w.ref = $1""",
            r.json()["work"]["ref"],
        )
        assert assignee == "HQ-LGL"
        # Only LEGAL: any other department of the holding is still refused.
        bad = await client.post(
            "/internal/v1/work",
            headers={**ceo, **idem()},
            json={"company": "HQ", "department": "AIOPS", "title": "x", "brief": "y"},
        )
        assert bad.status_code == 403


async def test_a_form_is_an_a3_card_the_owner_submits(
    client: httpx.AsyncClient, new_company: Callable[..., Any], su: Any
) -> None:
    async with holding_switch(su, "released"):
        r = await client.post(
            "/internal/v1/decisions",
            headers={**await agent_headers("HQ-LGL"), **idem()},
            json={"kind": "a3_action", "title": "فرم اعتراض حساب", "what": "فرم مرکز راهنما",
                  "why": "LC-0001", "risk": "low", "reversible": True,
                  "payload": {"action": "form_submit", "target": "https://help.example.com/appeal",
                              "preview": "| field | value | source |"}},
        )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["action_class"] == "A3" and r.json()["payload"]["action"] == "form_submit"


# --------------------------------------------------------- the password --
class FakeBao:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    async def read_kv(self, path: str) -> dict[str, Any]:
        return {"secret": self.secret} if path == "tools/accounts/mail" else {}


async def test_the_mailbox_password_never_shows(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    mailbox: FakeMail,
    caplog: pytest.LogCaptureFixture,
) -> None:
    password = "app-pass-" + secrets.token_hex(8)
    seen: list[dict[str, Any]] = []

    def egress(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        if request.url.path == "/v1/mail/fetch":
            return httpx.Response(200, json={"outcome": "error", "code": "upstream_error", "data": None})
        return httpx.Response(200, json={"outcome": "ok", "data": {"refused": []}})

    real = MAIL.EgressMail(httpx.MockTransport(egress))
    MAIL.OVERRIDE = real
    bao, hub.bao = hub.bao, FakeBao(password)
    caplog.set_level(logging.DEBUG)
    try:
        co = await new_company()
        lgl = await agent_headers("HQ-LGL")
        case = await _case(client, lgl, co["code"])
        out = await _draft(client, lgl, case["ref"])
        assert (await _approve(client, hub, owner_session, out["decision"], out["digest"])).status_code == 200
        sent = await L.deliver(hub, txf(hub), out["decision"])
        assert sent["email"] == "sent"
        polled = await L.poll(hub, txf(hub))
        assert polled == {"ok": False, "error": "upstream_error"}
        assert [s["account"]["secret"] for s in seen] == [password, password]  # only to egress
        assert seen[0]["host"] == "smtp.example.org" and seen[0]["port"] == 465
        assert seen[1]["host"] == "imap.example.org" and seen[1]["port"] == 993
        answers = [
            (await client.get(f"/api/v1/legal/cases/{case['ref']}", headers=owner_session["headers"])).text,
            (await client.get(f"/api/v1/decisions/{out['decision']}", headers=owner_session["headers"])).text,
            (await client.get(f"/internal/v1/legal/cases/{case['ref']}/mail", headers=lgl)).text,
            (await client.get("/api/v1/tools/accounts", headers=owner_session["headers"])).text,
        ]
        assert all(password not in a for a in answers)
        assert password not in caplog.text
    finally:
        hub.bao = bao
        MAIL.OVERRIDE = mailbox
