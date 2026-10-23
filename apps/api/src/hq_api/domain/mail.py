"""The holding mailbox of the legal counsel (prompt 13 §3.2, contract §22.4).

One service account, `mail` (/tools/accounts): its site is the provider's
domain, its policy names the mailbox (`inject.username`, the address) and may
name the IMAP and SMTP hosts (`mail`); the secret (an app password) is the
owner's, entered with `make account-secret KEY=mail` and read from OpenBao
for one call only. Every byte leaves through egress (POST /v1/mail/send and
/v1/mail/fetch), which reaches only that account's own hosts and ports.

Nothing here ever sends on its own: `send` is called for an email the owner
sealed (legal.deliver), `fetch` by the poller (legal.poll), which does
nothing while the holding is locked. The owner decided (§0.9 #6) that the
mailbox stays unconnected for now: without the account or its secret,
`configured()` is None and drafts stay cards.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any, Protocol

import httpx

from hq_api.db import Tx

log = logging.getLogger("hq_api.mail")

ACCOUNT = "mail"
SMTP_PORTS = (465, 587)  # implicit TLS, or STARTTLS (required)
IMAP_PORTS = (993,)  # implicit TLS only
FETCH_MAX = 50  # messages per poll
RAW_MAX = 25 * 1024 * 1024  # one message as egress hands it over


@dataclass(frozen=True)
class Account:
    """The mailbox as the code uses it (never the secret)."""

    key: str
    site: str
    address: str
    smtp_host: str
    smtp_port: int
    imap_host: str
    imap_port: int
    policy: dict[str, Any] = field(default_factory=dict)


@dataclass
class Sent:
    ok: bool
    code: str | None = None  # account_not_configured | send_error | blocked
    refused: list[str] = field(default_factory=list)


@dataclass
class Fetched:
    ok: bool
    code: str | None = None
    uidvalidity: int | None = None
    messages: list[tuple[int, bytes]] = field(default_factory=list)  # (uid, raw)


class Transport(Protocol):
    async def configured(self, hub: Any, tx: Tx) -> Account | None: ...

    async def send(self, hub: Any, account: Account, rcpt: list[str], raw: bytes) -> Sent: ...

    async def fetch(
        self, hub: Any, account: Account, since_uid: int, uidvalidity: int | None
    ) -> Fetched: ...


def _host(policy: dict[str, Any], key: str, site: str, prefix: str) -> str:
    return str(((policy.get("mail") or {}).get(key)) or f"{prefix}.{site}").lower().rstrip(".")


def _port(ports: list[int], allowed: tuple[int, ...]) -> int | None:
    for p in allowed:
        if p in ports:
            return p
    return None


async def account_row(tx: Tx) -> Account | None:
    """The `mail` account's metadata, when the owner added it (no secret here)."""
    r = await tx.first("SELECT key, site, policy FROM tools.accounts WHERE key = :k", k=ACCOUNT)
    if r is None:
        return None
    policy = r["policy"] if isinstance(r["policy"], dict) else {}
    inject = policy.get("inject") or {}
    address = str(inject.get("username") or "").strip()
    ports = [int(p) for p in policy.get("ports") or [] if isinstance(p, int)]
    smtp_port, imap_port = _port(ports, SMTP_PORTS), _port(ports, IMAP_PORTS)
    if "@" not in address or smtp_port is None or imap_port is None:
        return None  # not a mailbox (yet): no address, or no mail ports opened
    site = str(r["site"]).lower()
    return Account(
        key=ACCOUNT,
        site=site,
        address=address,
        smtp_host=_host(policy, "smtp_host", site, "smtp"),
        smtp_port=smtp_port,
        imap_host=_host(policy, "imap_host", site, "imap"),
        imap_port=imap_port,
        policy=policy,
    )


class EgressMail:
    """Production: the account's secret is read from OpenBao for this call
    only and handed to egress with the call (never logged, never stored)."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def configured(self, hub: Any, tx: Tx) -> Account | None:
        acct = await account_row(tx)
        if acct is None:
            return None
        from hq_api.domain import egress as G

        return acct if await G.has_secret(hub.bao, ACCOUNT) else None

    async def _account_json(self, hub: Any, acct: Account) -> dict[str, Any] | None:
        from hq_api.domain import egress as G

        secret = await G.read_secret(hub.bao, ACCOUNT)
        if not secret:
            return None
        return {
            "key": acct.key,
            "site": acct.site,
            "secret": secret,
            "inject": {"kind": "basic", "username": acct.address},
            "ports": sorted({acct.smtp_port, acct.imap_port}),
        }

    async def _post(self, hub: Any, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
        url = hub.settings.support_egress_url.rstrip("/") + path
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=90) as http:
                resp = await http.post(url, json=body)
            out = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("mail call failed", extra={"error": type(exc).__name__})
            return None
        return out if isinstance(out, dict) else None

    async def send(self, hub: Any, account: Account, rcpt: list[str], raw: bytes) -> Sent:
        acct = await self._account_json(hub, account)
        if acct is None:
            return Sent(False, "account_not_configured")
        out = await self._post(
            hub,
            "/v1/mail/send",
            {
                "account": acct,
                "host": account.smtp_host,
                "port": account.smtp_port,
                "envelope_from": account.address,
                "rcpt": rcpt,
                "raw_b64": base64.b64encode(raw).decode(),
            },
        )
        del acct
        if out is None:
            return Sent(False, "send_error")
        if out.get("outcome") != "ok":
            return Sent(False, str(out.get("code") or "send_error")[:40])
        data = out.get("data") or {}
        return Sent(True, refused=[str(x) for x in data.get("refused") or []][:20])

    async def fetch(
        self, hub: Any, account: Account, since_uid: int, uidvalidity: int | None
    ) -> Fetched:
        acct = await self._account_json(hub, account)
        if acct is None:
            return Fetched(False, "account_not_configured")
        out = await self._post(
            hub,
            "/v1/mail/fetch",
            {
                "account": acct,
                "host": account.imap_host,
                "port": account.imap_port,
                "since_uid": since_uid,
                "uidvalidity": uidvalidity,
                "max": FETCH_MAX,
            },
        )
        del acct
        if out is None:
            return Fetched(False, "fetch_failed")
        if out.get("outcome") != "ok":
            return Fetched(False, str(out.get("code") or "fetch_failed")[:40])
        data = out.get("data") or {}
        msgs: list[tuple[int, bytes]] = []
        for m in data.get("messages") or []:
            try:
                raw = base64.b64decode(str(m["raw_b64"]), validate=True)
            except (KeyError, ValueError, TypeError):
                continue
            if len(raw) <= RAW_MAX:
                msgs.append((int(m["uid"]), raw))
        return Fetched(True, uidvalidity=data.get("uidvalidity"), messages=msgs)


# Tests put a fake mailbox here (a fake SMTP and IMAP); production uses egress.
OVERRIDE: Transport | None = None


def transport() -> Transport:
    return OVERRIDE or EgressMail()


def build(
    *,
    from_addr: str,
    to: list[str],
    cc: list[str],
    subject: str,
    body_md: str,
    message_id: str,
    in_reply_to: str | None,
    references: list[str],
    attachments: list[tuple[str, str, bytes]],
    now: datetime | None = None,
) -> bytes:
    """The exact message the owner sealed, as RFC 5322 bytes (UTF-8 text)."""
    m = EmailMessage()
    m["From"] = from_addr
    m["To"] = ", ".join(to)
    if cc:
        m["Cc"] = ", ".join(cc)
    m["Subject"] = subject
    m["Message-ID"] = message_id
    m["Date"] = format_datetime(now or datetime.now(UTC))
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
    if references:
        m["References"] = " ".join(references)
    m["Auto-Submitted"] = "no"  # every message is the owner's sealed act
    m.set_content(body_md, subtype="plain", charset="utf-8")
    for name, mime, data in attachments:
        main, _, sub = mime.partition("/")
        m.add_attachment(data, maintype=main or "application", subtype=sub or "octet-stream",
                         filename=name)  # fmt: skip
    return bytes(m)
