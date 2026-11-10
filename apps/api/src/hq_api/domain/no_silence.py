"""No silence (the owner, 2026-11-05: «یه کارگروه فرستادم برای استخدام هیچ خبری نشد. به مدیرعامل پیام میدم خبری نمیشه»).

Two places where the holding used to drop the owner's intent without a word:

- **An owner's message that nobody answered.** The sweep (the worker's `requeue_runs`, every few minutes) finds each
  thread whose last message is the owner's, older than `QUIET` and younger than a day, and tells the owner once, in
  plain Persian, why: the run was refused (a kill switch, the day's cap, the budget…), the employee is busy or
  inactive, or the thread has nobody to answer it. One notice per message (linked to the thread).
- **A working group's empty seat that automatic hiring could not fill.** `groups.reconcile_members` keeps the reason
  on the seat (`blocked`), and the owner is told once a day per company and reason, with what fixes it.

Rule-based, no model. Every text passes `humanize` in `notify.raise_notification` (contract §29.7).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import notify

log = logging.getLogger("hq_api.no_silence")

QUIET = timedelta(minutes=5)

# A run's refusal (agents.runner) in the owner's words: why, and what fixes it.
RUN_WHY_FA: dict[str, tuple[str, str]] = {
    "locked": (
        "کلید توقف یا قفل انتشار روشن است.",
        "با خاموش کردن کلید توقف، پیام خودکار دوباره فرستاده میشود.",
    ),
    "daily_cap": (
        "سقف توکن امروز پر شده است.",
        "فردا خودکار جواب میدهد، یا سقف روزانه را در خزانه بالا ببرید.",
    ),
    "budget_used_up": ("بودجه‌ی این کار تمام شده است.", "بودجه‌ی کار را در گزارش فرمان بیشتر کنید."),
    "budget_usd": (
        "بودجه‌ی دلاری این کار تمام شده است.",
        "بودجه‌ی کار را در گزارش فرمان بیشتر کنید.",
    ),
    "usd_used": ("بودجه‌ی دلاری این کار تمام شده است.", "بودجه‌ی کار را در گزارش فرمان بیشتر کنید."),
    "no_charter": ("منشور این نقش پیدا نشد.", "مدیر فنی هلدینگ باید منشور را برگرداند."),
    "employee_inactive": (
        "این کارمند فعال نیست.",
        "کارمند را فعال کنید یا پیام را به مدیر دیگری بدهید.",
    ),
    "runtime_not_configured": (
        "موتور اجرای ایجنت‌ها روی هاب آماده نیست.",
        "مدیر فنی هلدینگ باید آن را راه بیندازد.",
    ),
    "talk_loop": (
        "این کار بی‌خروجی دور خودش چرخید و نگه داشته شد.",
        "در گزارش فرمان آن را دوباره روشن کنید.",
    ),
    # ⟨2026-11-09⟩ «با من»
    "owner_turn": (
        "این جلسه «با من» است و منتظر جواب شماست.",
        "در جلسه جواب بدهید یا «ادامه بده» را بزنید.",
    ),
}
RUN_WHY_DEFAULT = ("جواب آماده نشد.", "از «گفتگو» بپرسید چه شده؛ گزارش کامل آنجاست.")

# An automatic hire refused (hiring.auto_fill): the ApiError's code.
HIRE_WHY_FA: dict[str, tuple[str, str]] = {
    "envelope_required": (
        "برای این ماه پاکت بودجه‌ی شرکت تعیین نشده است.",
        "در صفحه‌ی شرکت «تعیین پاکت ماه» را بزنید؛ استخدام خودکار بعدش انجام میشود.",
    ),
    "envelope_exceeded": (
        "پاکت ماه شرکت برای این استخدام جا ندارد.",
        "پاکت ماه شرکت را بزرگ‌تر کنید.",
    ),
    "hiring_closed": (
        "استخدام خودکار خاموش است.",
        "در تنظیمات استخدام، حالت «خودکار» را روشن کنید.",
    ),
    "locked": (
        "کلید توقف این شرکت روشن است.",
        "با خاموش کردن کلید توقف، کارگروه دوباره کار میکند.",
    ),
}
HIRE_WHY_DEFAULT = ("استخدام خودکار انجام نشد.", "در صفحه‌ی کارگروه، جایگاه خالی را ببینید.")


def hire_why(code: str | None) -> dict[str, str]:
    why, fix = HIRE_WHY_FA.get(code or "", HIRE_WHY_DEFAULT)
    return {"code": code or "unknown", "why_fa": why, "fix_fa": fix}


async def _told_since(tx: Tx, company_id: UUID, link_kind: str, link_ref: str, since: Any) -> bool:
    return bool(
        await tx.scalar(
            """SELECT 1 FROM notify.notifications
               WHERE company_id = :co AND link_kind = :lk AND link_ref = :lr AND created_at >= :since
               LIMIT 1""",
            co=company_id,
            lk=link_kind,
            lr=link_ref,
            since=since,
        )
    )


async def tell_seat_blocked(
    tx: Tx,
    company_id: UUID,
    company_code: str,
    group_key: str,
    group_title: str,
    seat_title: str,
    code: str | None,
) -> bool:
    """Once a day per company, group and reason: why the seat stays empty and what fixes it."""
    w = hire_why(code)
    title = f"کارگروه «{group_title}» در {company_code}: جایگاه «{seat_title}» خالی ماند"
    if await tx.scalar(
        """SELECT 1 FROM notify.notifications
           WHERE company_id = :co AND link_kind = 'group' AND link_ref = :g AND title_fa = :t
             AND created_at > now() - interval '24 hours' LIMIT 1""",
        co=company_id,
        g=group_key,
        t=title,
    ):
        return False
    await notify.raise_notification(
        tx,
        company_id=company_id,
        company_code=company_code,
        level="report",
        title_fa=title,
        body_fa=f"{w['why_fa']} {w['fix_fa']}",
        link_kind="group",
        link_ref=group_key,
        domain="business",
        owner_action=True,
    )
    return True


async def sweep_unanswered(tx: Tx, *, limit: int = 20) -> int:
    """Every owner's message still without an answer after QUIET gets one notice with the reason."""
    rows = await tx.all(
        """SELECT t.id AS thread_id, t.code AS thread, t.kind, t.company_id, c.code AS company,
                  t.employee_id, e.status AS emp_status, e.title_fa AS emp_title,
                  m.ref, m.created_at
           FROM msg.threads t
           JOIN core.companies c ON c.id = t.company_id
           LEFT JOIN core.employees e ON e.id = t.employee_id
           JOIN LATERAL (SELECT author_kind, ref, created_at FROM msg.messages
                          WHERE thread_id = t.id ORDER BY seq DESC LIMIT 1) m ON true
           WHERE m.author_kind = 'owner'
             AND m.created_at < now() - make_interval(secs => :quiet)
             AND m.created_at > now() - interval '24 hours'
           ORDER BY m.created_at LIMIT :l""",
        quiet=int(QUIET.total_seconds()),
        l=limit,
    )
    told = 0
    for r in rows:
        if await _told_since(tx, r["company_id"], "thread", r["thread"], r["created_at"]):
            continue
        who = r["emp_title"] or "این گفت‌وگو"
        if r["employee_id"] is None:
            why, fix = (
                "این گفت‌وگو کارمندی ندارد که جواب بدهد.",
                "پیام را به مدیر همان بخش یا مدیرعامل بدهید.",
            )
        elif r["emp_status"] != "active":
            why, fix = RUN_WHY_FA["employee_inactive"]
        else:
            run = await tx.first(
                """SELECT state, error_code, queued_at FROM agents.runs
                   WHERE thread_id = :t AND queued_at >= CAST(:since AS timestamptz) - interval '1 minute'
                   ORDER BY queued_at DESC LIMIT 1""",
                t=r["thread_id"],
                since=r["created_at"],
            )
            if run is None:
                why, fix = "پیام به کسی نرسید.", "مدیر فنی هلدینگ باید صف پیام‌ها را ببیند."
            elif run["state"] == "refused" or run["state"] == "failed":
                why, fix = RUN_WHY_FA.get(run["error_code"] or "", RUN_WHY_DEFAULT)
            elif run["state"] == "queued":
                busy = await tx.scalar(
                    """SELECT 1 FROM agents.runs WHERE employee_id = :e AND state = 'running'
                         AND trigger NOT IN ('talk', 'direct') LIMIT 1""",
                    e=r["employee_id"],
                )
                if busy:
                    why, fix = (
                        f"{who} مشغول کار دیگری است و پیام شما در صف است.",
                        "تمام که شد جواب میدهد.",
                    )
                else:
                    why, fix = "پیام در صف مانده است.", "مدیر فنی هلدینگ باید صف اجرا را ببیند."
            elif run["state"] == "running":
                continue  # it is being answered now
            else:
                why, fix = "جواب نوشته شد ولی در گفت‌وگو نیامد.", "از «گفتگو» بپرسید چه شده."
        await notify.raise_notification(
            tx,
            company_id=r["company_id"],
            company_code=r["company"],
            level="report",
            title_fa=f"پیام شما به {who} هنوز جواب نگرفته است",
            body_fa=f"{why} {fix}",
            link_kind="thread",
            link_ref=r["thread"],
            domain="business",
            owner_action=True,
        )
        told += 1
    return told
