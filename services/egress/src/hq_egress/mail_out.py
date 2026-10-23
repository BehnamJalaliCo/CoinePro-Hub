"""The legal mailbox's two calls (prompt 13 §3.2, contract §22.4): one sealed
message out over SMTP, the new messages in over IMAP. Code calls them (the
worker, on hq-egress-api), never an agent: the message was sealed by the owner
on its digest in the api, and the poller only reads.

    POST /v1/mail/send   {account, host, port, envelope_from, rcpt, raw_b64}
                         -> {outcome, code, data: {refused}, entries}
    POST /v1/mail/fetch  {account, host, port, since_uid, uidvalidity, max}
                         -> {outcome, code, data: {uidvalidity, messages: [{uid, raw_b64}]},
                             entries}

Rules: the host is the account's own site (`imap.<site>`, `smtp.<site>`, or
any name under it); the port is one of the account's own ports and one of
465 or 587 (SMTP) and 993 (IMAP); TLS always (implicit, or STARTTLS required
on 587) with the certificate checked against the public CAs for that name;
the name is resolved by the guard (public addresses only, never the hub or a
neighbour) and the connection is made to that checked address. The envelope
sender is the account's own address (its `inject.username`); the secret goes
only into the login, never into an entry, an answer or a log line. Messages
are read with BODY.PEEK (the mailbox's \\Seen flags are not touched).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import imaplib
import logging
import re
import smtplib
import socket
import ssl
import time
from typing import Any

import certifi
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hq_egress.accounts import Account, holds_secret, scrub
from hq_egress.guard import Blocked
from hq_egress.net import CALL_ENTRIES, Entry, track
from hq_egress.proxy import entries_json

log = logging.getLogger("hq_egress.mail")
router = APIRouter()

SMTP_PORTS = frozenset({465, 587})
IMAP_PORTS = frozenset({993})
RAW_MAX = 25 * 1024 * 1024  # one message, either way
FETCH_MAX = 50
TIMEOUT_S = 60
ADDRESS = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}$")


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Account
    host: str = Field(min_length=3, max_length=253)
    port: int
    envelope_from: str = Field(max_length=320)
    rcpt: list[str] = Field(min_length=1, max_length=40)
    raw_b64: str = Field(min_length=4, max_length=RAW_MAX * 4 // 3 + 8)


class FetchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Account
    host: str = Field(min_length=3, max_length=253)
    port: int
    since_uid: int = Field(ge=0)
    uidvalidity: int | None = None
    max: int = Field(default=FETCH_MAX, ge=1, le=FETCH_MAX)


class Refused(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _answer(
    outcome: str, data: Any, entries: list[Entry], code: str | None, secrets: list[str]
) -> JSONResponse:
    return JSONResponse(
        {
            "outcome": outcome,
            "code": code,
            "data": scrub(data, secrets),
            "entries": entries_json(entries),
        }
    )


def context() -> ssl.SSLContext:
    """The public CAs (certifi), the name checked, TLS 1.2 or later."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def check(account: Account, host: str, port: int, allowed: frozenset[int]) -> str:
    """The account's own host and port, or Refused."""
    name = host.lower().rstrip(".")
    if account.is_profile or account.inject.kind != "basic" or not account.inject.username:
        raise Refused("account_not_configured")
    if not account.covers(name):
        raise Refused("host_not_allowed")
    if port not in allowed or port not in account.ports_for(name):
        raise Refused("port_not_allowed")
    return name


# ------------------------------------------------- connections to one address --
class _SMTPS(smtplib.SMTP_SSL):
    """SMTP over implicit TLS, to the guard's checked address, the certificate
    checked for the real name."""

    def __init__(self, addr: str, host: str, port: int, ctx: ssl.SSLContext) -> None:
        self._addr = addr
        super().__init__(host=host, port=port, context=ctx, timeout=TIMEOUT_S)

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        raw = socket.create_connection((self._addr, port), timeout)
        return self.context.wrap_socket(raw, server_hostname=host)


class _SMTP(smtplib.SMTP):
    """SMTP on 587, to the checked address; STARTTLS is required (below)."""

    def __init__(self, addr: str, host: str, port: int) -> None:
        self._addr = addr
        super().__init__(host=host, port=port, timeout=TIMEOUT_S)

    def _get_socket(self, host: str, port: int, timeout: float) -> socket.socket:
        sock: socket.socket = socket.create_connection((self._addr, port), timeout)
        return sock


class _IMAPS(imaplib.IMAP4_SSL):
    def __init__(self, addr: str, host: str, port: int, ctx: ssl.SSLContext) -> None:
        self._addr = addr
        super().__init__(host=host, port=port, ssl_context=ctx, timeout=TIMEOUT_S)

    def _create_socket(self, timeout: float | None) -> socket.socket:
        raw = socket.create_connection((self._addr, self.port), timeout)
        ctx: ssl.SSLContext = self.ssl_context
        return ctx.wrap_socket(raw, server_hostname=self.host)


# Tests replace these with fakes (no real server, no network).
SMTP_SSL_CLS: Any = _SMTPS
SMTP_CLS: Any = _SMTP
IMAP_CLS: Any = _IMAPS


def _send_blocking(
    addr: str, host: str, port: int, user: str, secret: str, rcpt: list[str], raw: bytes
) -> list[str]:
    ctx = context()
    if port == 465:
        conn = SMTP_SSL_CLS(addr, host, port, ctx)
    else:
        conn = SMTP_CLS(addr, host, port)
        conn.ehlo()
        if not conn.has_extn("starttls"):
            conn.close()
            raise Refused("starttls_required")
        conn.starttls(context=ctx)
        conn.ehlo()
    try:
        conn.login(user, secret)
        refused = conn.sendmail(user, rcpt, raw)
    finally:
        try:
            conn.quit()
        except (smtplib.SMTPException, OSError):
            conn.close()
    return sorted(refused)


def _uidvalidity(conn: Any) -> int | None:
    _, data = conn.response("UIDVALIDITY")
    try:
        return int(data[0]) if data and data[0] is not None else None
    except (TypeError, ValueError):
        return None


def _fetch_blocking(
    addr: str,
    host: str,
    port: int,
    user: str,
    secret: str,
    since: int,
    validity: int | None,
    limit: int,
) -> tuple[int | None, list[tuple[int, bytes]]]:
    conn = IMAP_CLS(addr, host, port, context())
    try:
        conn.login(user, secret)
        conn.select("INBOX", readonly=True)
        now = _uidvalidity(conn)
        if validity is not None and now is not None and now != validity:
            since = 0
        typ, data = conn.uid("SEARCH", None, f"UID {since + 1}:*")
        uids = (
            sorted(int(x) for x in (data[0] or b"").split() if x.isdigit()) if typ == "OK" else []
        )
        out: list[tuple[int, bytes]] = []
        for uid in [u for u in uids if u > since][:limit]:
            typ, parts = conn.uid("FETCH", str(uid), "(RFC822.SIZE BODY.PEEK[])")
            if typ != "OK":
                continue
            for part in parts or []:
                if (
                    isinstance(part, tuple)
                    and len(part) == 2
                    and isinstance(part[1], bytes | bytearray)
                ):
                    if len(part[1]) <= RAW_MAX:
                        out.append((uid, bytes(part[1])))
                    break
        return now, out
    finally:
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            conn.logout()


async def _address(state: Any, host: str, port: int) -> str:
    """The first checked address (a private or hub answer blocks the name)."""
    addrs: list[str] = await state.guard.addresses(host, port)
    return addrs[0]


@router.post("/v1/mail/send")
async def send(a: SendIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    secrets = a.account.secrets()
    entries: list[Entry] = []
    token = CALL_ENTRIES.set(entries)
    try:
        host = check(a.account, a.host, a.port, SMTP_PORTS)
        sender = a.envelope_from.strip()
        if sender.lower() != str(a.account.inject.username).lower() or not ADDRESS.match(sender):
            raise Refused("sender_not_allowed")
        if any(not ADDRESS.match(r.strip()) for r in a.rcpt):
            raise Refused("rcpt_not_allowed")
        try:
            raw = base64.b64decode(a.raw_b64, validate=True)
        except ValueError as exc:
            raise Refused("bad_message") from exc
        if len(raw) > RAW_MAX:
            raise Refused("too_large")
        addr = await _address(state, host, a.port)
    except Refused as r:
        track(
            Entry(
                "mail.send", "SMTP", a.host[:255], kind="connect", blocked_reason=r.code, cls="A3"
            )
        )
        return _answer("blocked", None, entries, r.code, secrets)
    except Blocked as b:
        track(
            Entry(
                "mail.send", "SMTP", a.host[:255], kind="connect", blocked_reason=b.reason, cls="A3"
            )
        )
        return _answer("blocked", None, entries, b.reason, secrets)
    finally:
        CALL_ENTRIES.reset(token)
    entry = Entry("mail.send", "SMTP", host, kind="connect", bytes_out=len(raw), cls="A3")
    entries.append(entry)
    start = time.monotonic()
    try:
        refused = await asyncio.wait_for(
            asyncio.to_thread(
                _send_blocking, addr, host, a.port, str(a.account.inject.username),
                str(a.account.secret), [r.strip() for r in a.rcpt], raw,
            ),
            timeout=TIMEOUT_S * 2,
        )  # fmt: skip
    except Refused as r:
        entry.blocked_reason = r.code
        return _answer("blocked", None, entries, r.code, secrets)
    except smtplib.SMTPAuthenticationError:
        entry.status, entry.blocked_reason = 535, "auth_failed"
        return _answer("error", None, entries, "account_not_configured", secrets)
    except smtplib.SMTPRecipientsRefused:
        entry.status = 550
        return _answer("error", None, entries, "rcpt_refused", secrets)
    except (smtplib.SMTPException, OSError, TimeoutError, ssl.SSLError) as exc:
        log.warning("mail.send failed: %s", type(exc).__name__)
        entry.blocked_reason = "send_error"
        return _answer("error", None, entries, "send_error", secrets)
    finally:
        entry.ms = int((time.monotonic() - start) * 1000)
    entry.status = 250
    return _answer("ok", {"refused": refused}, entries, None, secrets)


@router.post("/v1/mail/fetch")
async def fetch(a: FetchIn, request: Request) -> JSONResponse:
    state = request.app.state.egress
    secrets = a.account.secrets()
    entries: list[Entry] = []
    token = CALL_ENTRIES.set(entries)
    try:
        host = check(a.account, a.host, a.port, IMAP_PORTS)
        addr = await _address(state, host, a.port)
    except Refused as r:
        track(Entry("mail.fetch", "IMAP", a.host[:255], kind="connect", blocked_reason=r.code))
        return _answer("blocked", None, entries, r.code, secrets)
    except Blocked as b:
        track(Entry("mail.fetch", "IMAP", a.host[:255], kind="connect", blocked_reason=b.reason))
        return _answer("blocked", None, entries, b.reason, secrets)
    finally:
        CALL_ENTRIES.reset(token)
    entry = Entry("mail.fetch", "IMAP", host, kind="connect", cls="A0")
    entries.append(entry)
    start = time.monotonic()
    try:
        validity, msgs = await asyncio.wait_for(
            asyncio.to_thread(
                _fetch_blocking, addr, host, a.port, str(a.account.inject.username),
                str(a.account.secret), a.since_uid, a.uidvalidity, a.max,
            ),
            timeout=TIMEOUT_S * 3,
        )  # fmt: skip
    except imaplib.IMAP4.error:
        entry.blocked_reason = "auth_failed"
        return _answer("error", None, entries, "account_not_configured", secrets)
    except (OSError, TimeoutError, ssl.SSLError) as exc:
        log.warning("mail.fetch failed: %s", type(exc).__name__)
        entry.blocked_reason = "fetch_failed"
        return _answer("error", None, entries, "fetch_failed", secrets)
    finally:
        entry.ms = int((time.monotonic() - start) * 1000)
    entry.status = 200
    entry.bytes_in = sum(len(m) for _, m in msgs)
    # The raw messages go as base64, which is never scrubbed as text: a
    # message holding a form of the secret is dropped instead (7.1's rule).
    kept = [(u, m) for u, m in msgs if not holds_secret(m, secrets)]
    data = {
        "uidvalidity": validity,
        "messages": [{"uid": u, "raw_b64": base64.b64encode(m).decode()} for u, m in kept],
    }
    return _answer("ok", data, entries, None, secrets)
