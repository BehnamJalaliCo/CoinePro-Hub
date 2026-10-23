"""POST /v1/mail/send and /v1/mail/fetch (prompt 13 §3.2): the legal
mailbox's one sealed message out and its new messages in, against a fake SMTP
and a fake IMAP server (no network: the connection classes are replaced; the
guard still checks every name, address and port)."""

from __future__ import annotations

import base64
import ipaddress
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from hq_egress import mail_out as MO
from hq_egress.app import State, build_app
from hq_egress.config import Settings
from hq_egress.guard import Guard
from hq_egress.proxy import Buckets

LOCAL = ipaddress.ip_network("127.0.0.1/32")
SECRET = "app-password-" + "z" * 12
USER = "legal@example.org"
SITES = {
    "smtp.example.org": ["93.184.216.34"],
    "imap.example.org": ["93.184.216.35"],
    "mail.evil.org": ["93.184.216.36"],
    "smtp.private.example.org": ["10.10.1.3"],
}


class Server:
    """What the fakes saw, and how they answer."""

    def __init__(self) -> None:
        self.connects: list[tuple[str, str, int]] = []
        self.logins: list[tuple[str, str]] = []
        self.mails: list[tuple[str, list[str], bytes]] = []
        self.starttls = True
        self.inbox: dict[int, bytes] = {}
        self.validity = 9
        self.flags_touched = False


SERVER = Server()


class FakeSMTP:
    def __init__(self, addr: str, host: str, port: int, ctx: Any = None) -> None:
        SERVER.connects.append((addr, host, port))
        self.tls = ctx is not None

    def ehlo(self) -> None: ...

    def has_extn(self, name: str) -> bool:
        return SERVER.starttls

    def starttls(self, context: Any) -> None:
        self.tls = True

    def login(self, user: str, secret: str) -> None:
        assert self.tls
        if secret != SECRET:
            import smtplib

            raise smtplib.SMTPAuthenticationError(535, b"bad")
        SERVER.logins.append((user, secret))

    def sendmail(self, frm: str, rcpt: list[str], raw: bytes) -> dict[str, Any]:
        SERVER.mails.append((frm, rcpt, raw))
        return {}

    def quit(self) -> None: ...

    def close(self) -> None: ...


class FakeIMAP:
    def __init__(self, addr: str, host: str, port: int, ctx: Any) -> None:
        SERVER.connects.append((addr, host, port))

    def login(self, user: str, secret: str) -> None:
        SERVER.logins.append((user, secret))

    def select(self, box: str, readonly: bool = False) -> None:
        assert readonly

    def response(self, code: str) -> tuple[str, list[bytes]]:
        return code, [str(SERVER.validity).encode()]

    def uid(self, command: str, *args: Any) -> tuple[str, list[Any]]:
        if command == "SEARCH":
            lo = int(args[1].split()[1].split(":")[0])
            found = [u for u in sorted(SERVER.inbox) if u >= lo] or sorted(SERVER.inbox)[-1:]
            return "OK", [b" ".join(str(u).encode() for u in found)]
        assert "PEEK" in args[1]  # never marks a message \\Seen
        uid = int(args[0])
        return "OK", [(f"{uid} (UID {uid} BODY[] {{n}}".encode(), SERVER.inbox[uid]), b")"]

    def logout(self) -> None: ...


@pytest.fixture
async def egress(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in SITES:
            raise OSError("no such name")
        return SITES[host]

    monkeypatch.setattr(MO, "SMTP_SSL_CLS", FakeSMTP)
    monkeypatch.setattr(MO, "SMTP_CLS", FakeSMTP)
    monkeypatch.setattr(MO, "IMAP_CLS", FakeIMAP)
    SERVER.__init__()  # type: ignore[misc]
    guard = Guard(hub_hosts=frozenset({"hq.coinepro.com"}), resolver=resolve)
    settings = Settings(api_clients=(LOCAL,), hub_hosts=frozenset({"hq.coinepro.com"}))
    state = State(settings, guard, Buckets())
    transport = httpx.ASGITransport(app=build_app(state), client=("127.0.0.1", 5555))
    async with httpx.AsyncClient(transport=transport, base_url="http://egress") as c:
        yield c


def account(**over: Any) -> dict[str, Any]:
    return {"key": "mail", "site": "example.org", "secret": SECRET,
            "inject": {"kind": "basic", "username": USER}, "ports": [465, 587, 993], **over}  # fmt: skip


def send_body(**over: Any) -> dict[str, Any]:
    raw = b"From: legal@example.org\r\nTo: support@example.com\r\nSubject: Appeal\r\n\r\nHello"
    return {"account": account(), "host": "smtp.example.org", "port": 465, "envelope_from": USER,
            "rcpt": ["support@example.com"], "raw_b64": base64.b64encode(raw).decode(), **over}  # fmt: skip


async def test_the_sealed_message_leaves_once_to_the_checked_address(
    egress: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    r = await egress.post("/v1/mail/send", json=send_body())
    out = r.json()
    assert out["outcome"] == "ok" and out["data"] == {"refused": []}, out
    assert SERVER.connects == [("93.184.216.34", "smtp.example.org", 465)]
    assert SERVER.logins == [(USER, SECRET)] and len(SERVER.mails) == 1
    frm, rcpt, raw = SERVER.mails[0]
    assert frm == USER and rcpt == ["support@example.com"] and raw.endswith(b"Hello")
    (entry,) = out["entries"]
    assert (entry["tool"], entry["method"], entry["host"], entry["class"]) == (
        "mail.send",
        "SMTP",
        "smtp.example.org",
        "A3",
    )
    assert SECRET not in r.text and SECRET not in caplog.text
    # 587 needs STARTTLS: a server without it is refused before the login.
    SERVER.starttls = False
    r = await egress.post("/v1/mail/send", json=send_body(port=587))
    assert r.json()["code"] == "starttls_required" and len(SERVER.logins) == 1


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"host": "mail.evil.org"}, "host_not_allowed"),
        ({"port": 25}, "port_not_allowed"),
        ({"account": account(ports=[993])}, "port_not_allowed"),
        ({"envelope_from": "ceo@example.org"}, "sender_not_allowed"),
        ({"rcpt": ["not an address"]}, "rcpt_not_allowed"),
        ({"raw_b64": "!!!!"}, "bad_message"),
        ({"host": "smtp.private.example.org"}, "private_address"),
        ({"account": account(inject={"kind": "bearer"})}, "account_not_configured"),
    ],
)
async def test_anything_outside_the_account_is_refused_before_it_leaves(
    egress: httpx.AsyncClient, over: dict[str, Any], code: str
) -> None:
    r = await egress.post("/v1/mail/send", json=send_body(**over))
    out = r.json()
    assert out["outcome"] == "blocked" and out["code"].startswith(code), out
    assert SERVER.connects == [] and SERVER.mails == []
    assert SECRET not in r.text


async def test_a_wrong_password_is_account_not_configured(egress: httpx.AsyncClient) -> None:
    r = await egress.post(
        "/v1/mail/send", json=send_body(account=account(secret="wrong-" + "x" * 10))
    )
    assert r.json()["code"] == "account_not_configured" and SERVER.mails == []


async def test_new_messages_come_in_read_only_after_the_cursor(egress: httpx.AsyncClient) -> None:
    SERVER.inbox = {
        4: b"Message-ID: <a@x>\r\n\r\nold",
        7: b"Message-ID: <b@x>\r\n\r\nnew",
        8: b"Message-ID: <c@x>\r\n\r\nthe password " + SECRET.encode(),
    }
    body = {"account": account(), "host": "imap.example.org", "port": 993, "since_uid": 5,
            "uidvalidity": 9, "max": 10}  # fmt: skip
    r = await egress.post("/v1/mail/fetch", json=body)
    out = r.json()
    assert out["outcome"] == "ok" and out["data"]["uidvalidity"] == 9, out
    got = {m["uid"]: base64.b64decode(m["raw_b64"]) for m in out["data"]["messages"]}
    assert set(got) == {7} and got[7].endswith(b"new")  # 8 held the secret: dropped
    assert SERVER.connects == [("93.184.216.35", "imap.example.org", 993)]
    assert SECRET not in r.text
    # Past the last one, IMAP answers the last message again: it is not new.
    r = await egress.post("/v1/mail/fetch", json={**body, "since_uid": 8})
    assert r.json()["data"]["messages"] == []
    # A rebuilt mailbox (another UIDVALIDITY) is read from the start.
    SERVER.validity = 10
    r = await egress.post("/v1/mail/fetch", json=body)
    assert {m["uid"] for m in r.json()["data"]["messages"]} == {4, 7}
    bad = await egress.post("/v1/mail/fetch", json={**body, "port": 143})
    assert bad.json()["code"] == "port_not_allowed"
