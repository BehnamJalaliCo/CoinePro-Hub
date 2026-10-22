"""The one door to a customer for a rule-sent message of the revenue and
growth half of prompt 10 (a rescue follow-up, §3.4): `growth.send_template`.

This half never writes a sender. The lifecycle/template sender of §7
(`hq_api.domain.growth.send_template`, built on the other half of the
prompt) is the only code that may send a template: it checks the sealed rule
and its sealed template version, opt-outs, quiet hours, the caps, Telegram's
own rules and the outbound guard, and records growth.sends. It is looked up
at call time, so either half can land first:

    await send_template(tx, hub, company_id=..., kind="rescue", subject=...,
                        dedupe_key="rescue:RC-000001:1", rescue_case_id=...,
                        variables={})
    -> {"status": "sent" | "blocked" | "skipped" | "no_channel" | "opted_out" | "failed",
        "reason": str | None, "template": "TM-0007@2" | None, ...}

Until §7's sender exists the answer is {"status": "skipped", "reason":
"no_sender"} and nothing is sent. Tests put a stub in with `using(stub)`.
"""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import Awaitable, Iterator
from typing import Any, Protocol
from uuid import UUID

from hq_api.db import Tx

SENDER_MODULE = "hq_api.domain.growth"
SENDER_NAME = "send_template"
STATUSES = ("sent", "blocked", "skipped", "no_channel", "opted_out", "failed")


class Sender(Protocol):
    def __call__(
        self,
        tx: Tx,
        hub: Any,
        *,
        company_id: UUID,
        kind: str,
        subject: str,
        dedupe_key: str,
        rescue_case_id: UUID | None = None,
        variables: dict[str, str] | None = None,
    ) -> Awaitable[dict[str, Any]]: ...


_override: list[Sender] = []


@contextlib.contextmanager
def using(sender: Sender) -> Iterator[None]:
    """A stand-in sender (tests)."""
    _override.append(sender)
    try:
        yield
    finally:
        _override.pop()


def _growth_sender() -> Sender | None:
    try:
        module = importlib.import_module(SENDER_MODULE)
    except ImportError:
        return None
    fn = getattr(module, SENDER_NAME, None)
    return fn if callable(fn) else None


async def send_template(
    tx: Tx,
    hub: Any,
    *,
    company_id: UUID,
    kind: str,
    subject: str,
    dedupe_key: str,
    rescue_case_id: UUID | None = None,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    sender = _override[-1] if _override else _growth_sender()
    if sender is None:
        return {"status": "skipped", "reason": "no_sender", "template": None}
    out = await sender(
        tx,
        hub,
        company_id=company_id,
        kind=kind,
        subject=subject,
        dedupe_key=dedupe_key,
        rescue_case_id=rescue_case_id,
        variables=variables or {},
    )
    if not isinstance(out, dict) or out.get("status") not in STATUSES:
        return {"status": "failed", "reason": "bad_sender_answer", "template": None}
    return out
