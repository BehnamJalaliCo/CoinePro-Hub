"""The support desk's foundation (prompt 10 §1, contract §19.0 and §19.3).

What every later part of prompt 10 builds on:
  subject(hub, company_id, channel, external_id)
                      the customer pseudonym (hq_common.pseudonym with
                      kv/support/pseudonym); 503 not_ready without the key
  settings(tx, company_id), channel(tx, company_id, kind)
                      the company's support settings / one channel, created
                      with their defaults on first use (a new company needs
                      no seed)
  store_inbound(...)  a customer's message: masked (hq_common.customer_mask)
                      BEFORE it is written, the customer (support.customers is
                      the only table with a raw handle or user id), the open
                      conversation (SC-000001) and the message; a webhook
                      retry with the same external id stores nothing twice
  model_view(tx, conversation_id)
                      the conversation as a model may read it: masked again
                      (defence in depth), purged texts left out
  purge_texts(tx, days)
                      the retention job (§1.4): every text a customer wrote
                      that is older than SUPPORT_RETENTION_DAYS is removed; the
                      rows, times, states and tags stay

Customer data never leaves its company: every query here runs inside the
caller's company scope (RLS), and nothing returns a raw handle but the
customer row itself.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_common import customer_mask, pseudonym

CHANNELS = ("telegram_business", "telegram_bot", "chatwoot", "product_bot", "mystery")
HANDOFF_REASONS = ("no_kb", "low_confidence", "blocked", "asked_for_human", "complaint", "security")


def subject(hub: Any, company_id: UUID | str, channel: str, external_id: str) -> str:
    """The pseudonym of one customer of one company (prompt 10 §1.2)."""
    try:
        return pseudonym.subject(
            hub.secrets.support_pseudonym_key, str(company_id), channel, str(external_id)
        )
    except pseudonym.KeyMissing as exc:
        raise ApiError(
            503, "not_ready", "the customer pseudonym key is not loaded (kv/support/pseudonym)"
        ) from exc


async def settings(tx: Tx, company_id: UUID | str) -> dict[str, Any]:
    await tx.exec(
        "INSERT INTO support.settings (company_id) VALUES (:co) ON CONFLICT DO NOTHING",
        co=company_id,
    )
    return await tx.one("SELECT * FROM support.settings WHERE company_id = :co", co=company_id)


async def channel(tx: Tx, company_id: UUID | str, kind: str) -> dict[str, Any]:
    if kind not in CHANNELS:
        raise ApiError(422, "validation_failed", f"unknown channel {kind}")
    await tx.exec(
        "INSERT INTO support.channels (company_id, kind) VALUES (:co, :k) ON CONFLICT DO NOTHING",
        co=company_id,
        k=kind,
    )
    return await tx.one(
        "SELECT * FROM support.channels WHERE company_id = :co AND kind = :k", co=company_id, k=kind
    )


async def store_inbound(
    tx: Tx,
    hub: Any,
    *,
    company_id: UUID | str,
    channel_kind: str,
    external_user_id: str,
    body: str,
    external_message_id: str | None = None,
    handle: str | None = None,
    display_name: str | None = None,
    lang: str = "fa",
    at: datetime | None = None,
    external: dict[str, Any] | None = None,
    mystery: bool = False,
) -> dict[str, Any]:
    """Masks and stores one customer message. Returns {customer_id, subject,
    conversation, message, masked: (kinds...), duplicate: bool,
    first_secret: bool} — `first_secret`: a secret was masked and the
    conversation has not had its safety line yet (§19.6 "Inbound")."""
    if channel_kind not in CHANNELS:
        raise ApiError(422, "validation_failed", f"unknown channel {channel_kind}")
    masked = customer_mask.mask(body[:8000])
    sub = subject(hub, company_id, channel_kind, external_user_id)
    customer = await tx.one(
        """INSERT INTO support.customers (company_id, channel, external_id, subject, handle,
                                          display_name, lang, started_at)
           VALUES (:co, :ch, :ext, :sub, :handle, :name, :lang, now())
           ON CONFLICT (company_id, channel, external_id) DO UPDATE
               SET last_seen_at = now(),
                   handle = COALESCE(EXCLUDED.handle, support.customers.handle),
                   display_name = COALESCE(EXCLUDED.display_name, support.customers.display_name),
                   started_at = COALESCE(support.customers.started_at, now())
           RETURNING id""",
        co=company_id,
        ch=channel_kind,
        ext=str(external_user_id).strip(),
        sub=sub,
        handle=handle[:128] if handle else None,
        name=display_name[:200] if display_name else None,
        lang=lang if lang.isascii() and lang.isalpha() and 2 <= len(lang) <= 3 else "fa",
    )
    conv = await tx.first(
        """SELECT * FROM support.conversations
           WHERE customer_id = :c AND state <> 'closed' FOR UPDATE""",
        c=customer["id"],
    )
    if conv is None:
        conv = await tx.one(
            """INSERT INTO support.conversations (company_id, channel, customer_id, mystery, external)
               VALUES (:co, :ch, :c, :mystery, CAST(:ext AS jsonb))
               ON CONFLICT (customer_id) WHERE state <> 'closed' DO UPDATE SET updated_at = now()
               RETURNING *""",
            co=company_id,
            ch=channel_kind,
            c=customer["id"],
            mystery=mystery,
            ext=json.dumps(external or {}),
        )
    message = await tx.first(
        """INSERT INTO support.messages (company_id, conversation_id, at, direction, author, body,
                                         masked, status, external_id, sent_at)
           VALUES (:co, :conv, COALESCE(CAST(:at AS timestamptz), now()), 'in', 'customer', :body,
                   :masked, 'sent', :ext, COALESCE(CAST(:at AS timestamptz), now()))
           ON CONFLICT (conversation_id, direction, external_id) WHERE external_id IS NOT NULL
           DO NOTHING
           RETURNING *""",
        co=company_id,
        conv=conv["id"],
        at=at,
        body=masked.text,
        masked=list(masked.kinds),
        ext=external_message_id[:128] if external_message_id else None,
    )
    if message is not None:
        conv = await tx.one(
            """UPDATE support.conversations SET last_message_at = :at,
                   state = CASE WHEN state = 'answered' THEN 'open' ELSE state END
               WHERE id = :id RETURNING *""",
            id=conv["id"],
            at=message["at"],
        )
    return {
        "customer_id": customer["id"],
        "subject": sub,
        "conversation": conv,
        "message": message,
        "masked": masked.kinds,
        "duplicate": message is None,
        "first_secret": message is not None
        and masked.needs_safety_line
        and conv["safety_sent_at"] is None,
    }


async def model_view(
    tx: Tx, conversation_id: UUID | str, *, limit: int = 30
) -> list[dict[str, Any]]:
    """The last `limit` messages of a conversation, oldest first, as a model
    may read them: what was received or sent, bodies masked again, purged
    ones left out, no customer identity (direction and author only)."""
    rows = await tx.all(
        """SELECT at, direction, author, body FROM (
               SELECT at, direction, author, body FROM support.messages
               WHERE conversation_id = :c AND body IS NOT NULL AND status = 'sent'
               ORDER BY at DESC LIMIT :n) m
           ORDER BY at""",
        c=conversation_id,
        n=max(1, min(limit, 100)),
    )
    return [
        {
            "at": r["at"].isoformat(),
            "direction": r["direction"],
            "author": r["author"],
            "body": customer_mask.mask(r["body"]).text,
        }
        for r in rows
    ]


async def purge_texts(tx: Tx, days: int) -> dict[str, int]:
    """The retention job (prompt 10 §1.4): the texts customers wrote, older
    than `days`, are removed; every row, time, state and tag stays. Rule-only
    (no model, no outside call), so it runs while the hub is locked too."""
    if days < 1:
        raise ValueError("retention days must be at least 1")
    return {
        "messages": await tx.exec(
            """UPDATE support.messages SET body = NULL, body_purged_at = now()
               WHERE at < now() - make_interval(days => :d) AND body IS NOT NULL""",
            d=days,
        ),
        "nps_comments": await tx.exec(
            """UPDATE growth.nps_responses SET comment = NULL, comment_purged_at = now()
               WHERE at < now() - make_interval(days => :d) AND comment IS NOT NULL""",
            d=days,
        ),
        "feedback_quotes": await tx.exec(
            """UPDATE feedback.signals SET quote = NULL, quote_purged_at = now()
               WHERE at < now() - make_interval(days => :d) AND quote IS NOT NULL""",
            d=days,
        ),
        "feedback_items": await tx.exec(
            """UPDATE feedback.items SET quotes = '[]'
               WHERE last_seen < now() - make_interval(days => :d) AND quotes <> '[]'""",
            d=days,
        ),
        "intake_events": await tx.exec(
            """UPDATE intake.events SET data = '{}', data_purged_at = now()
               WHERE received_at < now() - make_interval(days => :d) AND data_purged_at IS NULL""",
            d=days,
        ),
        "nonces": await tx.exec("DELETE FROM intake.nonces WHERE expires_at < now()"),
    }
