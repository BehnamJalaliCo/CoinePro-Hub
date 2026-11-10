"""⟨1.31⟩ §50 A standing routine from one sentence («کارمند ۲۴ ساعته»).

The owner's decision (2026-11-10): «کارمند ۲۴ ساعته» is not a hire. It is a standing routine,
made from one sentence he says in a session: no card, no passkey, and no «کارگروه از این جلسه»
to go through first. A routine is an automation (§31.7) of the plainest kind: a **schedule**
whose actions only make work for a role of the company or tell the owner something. That is
all inside the hub and switched off with one tap, so his sentence is the seal. Anything more
(an event or a number as the trigger, a line run, an ad paused, an n8n flow) is still an
automation he seals.

Two ways in, one result:
- he says it himself: `POST /api/v1/routines {sentence_fa, company?, order?}`;
- the holder of his session hears it and calls `automation.propose`: when his own words in
  that open session ask for something standing (a word of repetition), the same sentence is
  made `on` in that request instead of `proposed`.

The work a routine makes runs inside the company's month envelope like any other work.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import automations as AU
from hq_api.domain import order_report as OR
from hq_api.domain import recurrence
from hq_api.principal import Principal

ROUTINE_ACTIONS = ("work.create", "notify.owner", "notify.lead")
OWNER_FA = "مدیر کل"
SYSTEM_FA = "سامانه"
MADE_FA = "روال دائمی ساخته شد: {what}"
MADE_FOR_FA = "روال دائمی به خواست مدیر کل ساخته شد: {what}"
NOT_ROUTINE_FA = (
    "این جمله یک روال زمان‌دار ساده نیست (مثلاً «هر روز ساعت ۹ رتبه‌های سئوی پروچارت را ببین و "
    "خلاصه بده»). قاعده‌ای که با یک رویداد یا عدد شروع میشود یا خط تولید و تبلیغ را تغییر میدهد، "
    "از «خودکارسازی» با مُهر شما ساخته میشود."
)
# his own words that ask for something standing: a word of repetition
_WORDS = (
    "هر روز", "هرروز", "روزانه", "هر شب", "هر صبح", "هر هفته", "هفتگی", "هر ماه", "ماهانه",
    "هر ساعت", "ساعتی", "24 ساعته", "شبانه روز", "شبانه‌روز", "دائمی", "دایمی", "همیشه",
    "روال", "مرتب", "every day", "daily", "every week", "weekly", "hourly", "every hour",
    "monthly", "24/7",
)  # fmt: skip
_EVERY = re.compile(r"هر\s+\S+\s+(?:ساعت|روز|هفته|ماه|دقیقه)")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


SessionRoutine = OR.SessionRoutine


def is_routine(rule: dict[str, Any] | None) -> bool:
    """A schedule whose actions only make work or tell someone: what one sentence may start."""
    if not isinstance(rule, dict) or (rule.get("trigger") or {}).get("kind") != "schedule":
        return False
    acts = rule.get("actions") or []
    return bool(acts) and all(a.get("kind") in ROUTINE_ACTIONS for a in acts)


def asks_for_a_routine(said: list[str]) -> bool:
    text = " ".join(said).replace("ي", "ی").replace("ك", "ک").translate(_DIGITS).lower()
    text = " ".join(text.split())
    return any(w in text for w in _WORDS) or _EVERY.search(text) is not None


def next_run(rrule: str, tz: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    try:
        found = recurrence.occurrences(
            recurrence.parse(rrule), tz, now + timedelta(seconds=1), now + timedelta(days=40)
        )
    except Exception:  # noqa: BLE001 - a rule the calendar cannot read has no next time to show
        return None
    return found[0] if found else None


def _j(v: Any) -> dict[str, Any]:
    got = json.loads(v) if isinstance(v, str) else v
    return dict(got) if isinstance(got, dict) else {}


def view(
    row: dict[str, Any], company: str | None, titles: dict[str, str] | None, tz: str
) -> SessionRoutine:
    rule = _j(row["rule"])
    rrule = str((rule.get("trigger") or {}).get("rrule") or "")
    scope_company = company if row.get("scope") == "company" else None
    try:
        when = AU.when_fa(rrule)
    except Exception:  # noqa: BLE001 - shown without its time rather than not at all
        when = ""
    what = "؛ ".join(AU.action_fa(a, scope_company, titles) for a in rule.get("actions") or [])
    return SessionRoutine(
        ref=row["ref"],
        company=scope_company,
        sentence_fa=row["sentence_fa"],
        when_fa=when,
        preview_fa=what,
        state=row["state"],
        next_at=next_run(rrule, tz) if row["state"] == "on" else None,
        last_run_at=row.get("last_run_at"),
        runs=int(row.get("runs") or 0),
        order=_j(row.get("source")).get("order"),
        note_fa=row.get("last_error_fa"),
    )


async def make(
    tx: Tx,
    *,
    company_id: UUID,
    scoped: bool,
    sentence: str,
    rule: dict[str, Any],
    order: str | None,
    by: Principal,
) -> dict[str, Any]:
    """The routine, `on` from now (only what comes after counts, as after a seal)."""
    return dict(
        await tx.one(
            """INSERT INTO growth.automations (company_id, scope, sentence_fa, rule, n8n_workflow,
                   state, sealed_at, event_cursor, source)
               VALUES (:co, :sc, :s, CAST(:r AS jsonb), NULL, 'on', now(), :cur,
                       CAST(:src AS jsonb))
               RETURNING *""",
            co=company_id,
            sc="company" if scoped else "holding",
            s=sentence,
            r=json.dumps(rule, ensure_ascii=False),
            cur=await AU.max_outbox(tx),
            src=json.dumps(
                {
                    "order": order,
                    "by": "owner" if by.kind == "owner" else str(by.code),
                    "routine": True,
                },
                ensure_ascii=False,
            ),
        )
    )


async def of_order(tx: Tx, ref: str, titles: dict[str, str] | None = None) -> list[SessionRoutine]:
    """The standing routines asked for in a session, newest first."""
    from hq_api.domain.gov_common import owner_tz

    rows = await tx.all(
        """SELECT a.*, c.code AS company_code FROM growth.automations a
           JOIN core.companies c ON c.id = a.company_id
           WHERE a.source ->> 'order' = :r ORDER BY a.created_at DESC LIMIT 20""",
        r=ref,
    )
    if not rows:
        return []
    tz = await owner_tz(tx)
    return [view(dict(r), r["company_code"], titles, tz) for r in rows]


async def say(tx: Tx, order: str | None, text: str, *, owner: bool) -> None:
    """One line in the session the routine was asked in."""
    if not order:
        return
    rep = await OR.ensure(tx, order)
    if rep is None:
        return
    line = {
        "at": datetime.now(UTC).isoformat(),
        "who_fa": OWNER_FA if owner else SYSTEM_FA,
        "what_fa": text[:500],
    }
    await OR._append_steps(tx, rep["id"], [line])
