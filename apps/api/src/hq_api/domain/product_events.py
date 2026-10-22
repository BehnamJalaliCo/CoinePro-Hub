"""What a product's own events do once stored (prompt 10 §3, §9; contract
§19.2, §19.8; CR-009, CR-010). routes/intake.py stores each event masked,
its UID as the pseudonym `uid:<exchange>`, and hands it to the handler of
its kind (intake.APPLIERS = this module's APPLIERS); the handler's answer is
the event's state.

  referral_failed     opens the referral rescue case (once per company,
                      exchange and subject); follow-ups stay behind the gate
                      and a sealed rescue rule (domain/rescue.py)
  referral_verified   the product's own check said "our invitee": an open
                      case of that subject is closed `rescued`
  signup, vip_activated
                      counted by the funnel's signup and vip_active stages
                      (domain/funnel.py reads accepted and applied events)
  uid_submitted       nothing more: the UID only gives the pseudonym

Rule-only: a database write, no model and no outside call, so a handler
runs while the holding is locked (the intake webhook verifies and stores;
nothing is sent from here). support_message is the desk's (routes/intake.py).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import rescue as R

Applier = Callable[[Tx, Any, UUID, dict[str, Any]], Awaitable[str | None]]


async def referral(tx: Tx, hub: Any, company_id: UUID, ev: dict[str, Any]) -> str | None:
    state, _ = await R.apply_referral_event(
        tx, company_id, await hub.companies.code_of(company_id), ev
    )
    return state


async def counted(tx: Tx, hub: Any, company_id: UUID, ev: dict[str, Any]) -> str | None:
    return "applied"


APPLIERS: dict[str, Applier] = {
    "referral_failed": referral,
    "referral_verified": referral,
    "signup": counted,
    "vip_activated": counted,
    "uid_submitted": counted,
}
