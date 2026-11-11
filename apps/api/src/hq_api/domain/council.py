"""The council v2: outside advisors with a fact pack (contract §29.8).

Only for an outside question (market, competitors, trends, ideas, keywords
and SEO, ad copy, new markets, pricing) or when the owner asks («شورا»); an
inside question goes to the company's own Claude on its server (the
secretary, domain/dispatch.py), never to the council.

- **Roles** (`owner.settings.council_roles`, default): captain Claude (the
  council work's own assignee: splits the work, writes the plan), researcher
  Gemini (the web, with sources), numbers DeepSeek (costs and returns, checks
  the researcher), devil's advocate GPT (another angle, critique).
- **The fact pack** is built by code before the council from the hub's own
  data (the company's KPIs, revenue and funnel figures of the last week, its
  media items and posts, the week's spend, and the connections' daily
  figures when `growth.metrics_daily` exists): figures and titles only, every
  text masked; no secret, no personal data.
- **Three rounds:** 1 proposals (each with steps, cost and risk); 2 critique
  (each substitute that proposed sees the others' proposals); 3 the
  captain's plan, a table «چه کسی · چه کاری · تا کی» in 5–10 lines. Every
  member answers in Persian (§29.7: the substitutes' answers are checked
  where they arrive, domain/substitutes.py).
- **Output:** `plan_md` (humanized) with «اجرا کن» (POST
  /work/{id}/council/run), which makes an order of it; each member's answer
  stays under «جزئیات» (the members, the rounds).
A media council (images, video) keeps the v1 path (domain/players.py).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import humanize
from hq_common.redact import scrub

DEFAULT_ROLES = {"claude": "captain", "gemini": "researcher", "deepseek": "numbers", "gpt": "devil"}
ROLES = ("captain", "researcher", "numbers", "devil")
ROLE_FA = {
    "captain": "کاپیتان",
    "researcher": "پژوهشگر",
    "numbers": "عدد و منطق",
    "devil": "مخالف خلاق",
}
ROLE_TASK = {
    "captain": "کار را تقسیم کن و پیشنهاد خودت را بده؛ در دور سوم برنامه‌ی نهایی را تو مینویسی.",
    "researcher": "از وب بگرد: رقبا، روندها و نمونه‌های واقعی؛ هر ادعا با منبع و پیوند.",
    "numbers": "هزینه، بازده و حساب سرانگشتی را بنویس و عددهای پیشنهادهای دیگر را بسنج.",
    "devil": "زاویه‌ی دیگری را ببین، ایده‌ی متفاوت بده و ضعف هر پیشنهاد را بگو.",
}
PERSIAN = (
    "فقط به فارسی جواب بده (نام برندها و پیوندها به همان شکل). "
    "هیچ پیشنهادی برای ادامه‌ی گفت‌وگو یا پرسش پایانی ننویس."
)
PLAN_LINES = 14  # the plan the owner reads: 5–10 lines of table, a goal and a cost line
FIGURES = 40
POSTS = 10


def pack_ref(work_ref: str) -> str:
    """The fact pack of a council is named after its work: W-000094 -> FP-000094."""
    digits = re.sub(r"\D", "", work_ref) or "0"
    return f"FP-{digits}"


async def roles(tx: Tx) -> dict[str, str]:
    """{player: role} from the owner's settings (the default when unset)."""
    raw = await tx.scalar("SELECT council_roles FROM owner.settings WHERE id = 1")
    data = raw if isinstance(raw, dict) else json.loads(raw) if raw else {}
    out = {str(p): str(r) for p, r in (data or {}).items() if r in ROLES}
    return out or dict(DEFAULT_ROLES)


def _f(key: str, title: str, value: Any, source: str, at: Any) -> dict[str, Any]:
    if isinstance(value, float):
        value = round(value, 2)
    elif value is not None and not isinstance(value, int):
        try:
            num = float(value)
            value = int(num) if num.is_integer() else round(num, 2)
        except (TypeError, ValueError):
            value = scrub(str(value))[:100]
    return {
        "key": key,
        "title_fa": scrub(title)[:200],
        "value": value,
        "source": source,
        "at": at.isoformat() if isinstance(at, datetime) else str(at) if at else None,
    }


async def _exists(tx: Tx, table: str) -> bool:
    return bool(await tx.scalar("SELECT to_regclass(:t) IS NOT NULL", t=table))


async def fact_pack(tx: Tx, company_id: UUID, company_code: str) -> dict[str, Any]:
    """§29.8 `FactPack {company, at, figures, recent_posts, notes_fa}` from the
    hub's own data; figures and titles only, masked."""
    now = datetime.now(UTC)
    week = now - timedelta(days=7)
    figures: list[dict[str, Any]] = []
    notes: list[str] = []
    for k in await tx.all(
        """SELECT key, name_fa, unit, last_value, last_at FROM governance.kpis
           WHERE company_id = :co AND status = 'active' AND last_value IS NOT NULL
           ORDER BY scorecard DESC, key LIMIT 20""",
        co=company_id,
    ):
        title = k["name_fa"] + (f" ({k['unit']})" if k["unit"] else "")
        figures.append(_f(f"kpi.{k['key']}", title, k["last_value"], "kpi", k["last_at"]))
    rev = await tx.first(
        """SELECT count(*) AS days, COALESCE(sum(commission_usdt), 0) AS commission,
                  COALESCE(sum(new_invitees), 0) AS invitees, max(active_traders) AS traders,
                  max(day) AS last_day
           FROM revenue.days WHERE company_id = :co AND day >= :d""",
        co=company_id,
        d=week.date(),
    )
    if rev and rev["days"]:
        at = rev["last_day"]
        figures.append(_f("revenue.commission_7d", "کمیسیون ۷ روز گذشته (USDT)",
                          rev["commission"], "revenue", at))  # fmt: skip
        figures.append(_f("revenue.new_invitees_7d", "کاربر تازه‌ی ۷ روز گذشته",
                          rev["invitees"], "revenue", at))  # fmt: skip
        if rev["traders"] is not None:
            figures.append(_f("revenue.active_traders", "معامله‌گر فعال (بیشترین روز)",
                              rev["traders"], "revenue", at))  # fmt: skip
    for f in await tx.all(
        """SELECT stage, sum(count) AS n, max(day) AS at FROM growth.funnel_days
           WHERE company_id = :co AND day >= :d GROUP BY stage ORDER BY stage""",
        co=company_id,
        d=week.date(),
    ):
        figures.append(_f(f"funnel.{f['stage']}_7d", f"قیف، مرحله‌ی {f['stage']} در ۷ روز",
                          f["n"], "funnel", f["at"]))  # fmt: skip
    published = await tx.scalar(
        """SELECT count(*) FROM media.publish_log WHERE company_id = :co AND action = 'publish'
             AND outcome = 'ok' AND at >= :w""",
        co=company_id,
        w=week,
    )
    figures.append(_f("media.published_7d", "انتشار موفق در ۷ روز گذشته", int(published or 0),
                      "media", now))  # fmt: skip
    from hq_api.domain import spend

    used = sum(r["tokens"] for r in await spend.by_domain(tx, week, now, company_id))
    figures.append(_f("spend.tokens_7d", "مصرف ۷ روز گذشته (توکن)", int(used), "treasury", now))
    if await _exists(tx, "growth.metrics_daily"):
        # §29.12 the connections' daily figures (prompt 21 part 3), the latest day per key.
        # A key holds one row per subject (a channel, an account, a site): each subject is its
        # own figure, never one subject's value passed off as the company's.
        for m in await tx.all(
            """WITH latest AS (
                 SELECT kind, key, max(day) AS day FROM growth.metrics_daily
                 WHERE company_id = :co GROUP BY kind, key)
               SELECT m.kind, m.key, m.subject, m.value, m.day FROM growth.metrics_daily m
               JOIN latest l ON l.kind = m.kind AND l.key = m.key AND l.day = m.day
               WHERE m.company_id = :co ORDER BY m.kind, m.key, m.subject LIMIT 30""",
            co=company_id,
        ):
            key, title = f"{m['kind']}.{m['key']}", f"{m['kind']}: {m['key']}"
            if m["subject"]:
                subject = scrub(str(m["subject"]))[:80]
                key, title = f"{key}[{subject}]", f"{title} ({subject})"
            figures.append(_f(key, title, m["value"], str(m["kind"]), m["day"]))
    else:
        notes.append("هنوز اتصالی (سرچ‌کنسول، آنالیتیکس، اینستاگرام) عدد روزانه نمیدهد.")
    posts = [
        {
            "title_fa": scrub(p["title_fa"])[:200],
            "kind": p["kind"],
            "state": p["state"],
            "at": p["updated_at"].isoformat() if p["updated_at"] else None,
        }
        for p in await tx.all(
            """SELECT title_fa, kind, state, updated_at FROM media.items WHERE company_id = :co
               ORDER BY updated_at DESC NULLS LAST LIMIT :n""",
            co=company_id,
            n=POSTS,
        )
    ]
    if not posts:
        notes.append("این شرکت هنوز پست یا ریلزی در استودیوی رسانه ندارد.")
    return {
        "company": company_code,
        "at": now.isoformat(),
        "figures": figures[:FIGURES],
        "recent_posts": posts,
        "notes_fa": " ".join(notes),
    }


def pack_md(pack: dict[str, Any]) -> str:
    """The fact pack as the members read it (masked again)."""
    lines = [f"بسته‌ی واقعیت ({pack.get('company')}، {str(pack.get('at') or '')[:10]}):"]
    for f in pack.get("figures") or []:
        lines.append(
            f"- {f['title_fa']}: {f['value']} (منبع: {f['source']}، {str(f['at'] or '')[:10]})"
        )
    posts = pack.get("recent_posts") or []
    if posts:
        lines.append("پست‌ها و آیتم‌های اخیر رسانه:")
        lines.extend(f"- {p['title_fa']} ({p['kind']}، {p['state']})" for p in posts)
    if pack.get("notes_fa"):
        lines.append(str(pack["notes_fa"]))
    return scrub("\n".join(lines))


def _role(roles_: dict[str, str], player: str) -> str:
    return roles_.get(player) or ("captain" if player == "claude" else "devil")


def proposal_prompt(
    w: dict[str, Any], player: str, roles_: dict[str, str], pack: dict[str, Any]
) -> str:
    """Round 1: one concrete proposal (steps, cost, risk) in the member's role."""
    role = _role(roles_, player)
    return (
        f"شورای مشاوران هلدینگ، دور ۱ از ۳ (پیشنهاد). نقش تو: {ROLE_FA[role]}. {ROLE_TASK[role]}\n\n"
        f"پرسش مدیر کل:\n{w['title']}\n{w.get('brief') or ''}\n\n{pack_md(pack)}\n\n"
        "یک پیشنهاد مشخص بده با این بخش‌ها: «گام‌ها» (شماره‌دار)، «هزینه» (به عدد)، «ریسک»، «منبع». "
        "روی همین بسته‌ی واقعیت نظر بده، نه در خلأ؛ آنچه نمیدانی را بگو.\n" + PERSIAN
    )


def captain_brief(w: dict[str, Any], roles_: dict[str, str], pack: dict[str, Any]) -> str:
    """The council work's brief for the captain's own run (round 1)."""
    return (
        f"{w.get('brief') or ''}\n\n---\nشورای مشاوران (دور ۱ از ۳): تو کاپیتان شورا هستی. "
        f"{ROLE_TASK['captain']} پیشنهادت را با بخش‌های «گام‌ها»، «هزینه»، «ریسک» تحویل بده. "
        "بقیه‌ی اعضا هم‌زمان پیشنهاد میدهند و در دور ۲ نقد میکنند.\n\n" + pack_md(pack)
    )[:48_000]


def critique_prompt(
    w: dict[str, Any],
    player: str,
    roles_: dict[str, str],
    pack: dict[str, Any],
    proposals: list[tuple[str, str, str]],
) -> str:
    """Round 2: the member reads the others' proposals and critiques them."""
    role = _role(roles_, player)
    others = "\n\n".join(
        f"## {ROLE_FA[_role(roles_, p)]} ({name})\n{text[:6000]}" for p, name, text in proposals
    )
    return (
        f"شورای مشاوران هلدینگ، دور ۲ از ۳ (نقد). نقش تو: {ROLE_FA[role]}. {ROLE_TASK[role]}\n\n"
        f"پرسش مدیر کل:\n{w['title']}\n\n{pack_md(pack)}\n\nپیشنهادهای دیگر اعضا:\n{others}\n\n"
        "هر پیشنهاد را در چند خط نقد کن: چه درست است، چه کم دارد، کدام عدد یا ادعا نادرست یا "
        "بی‌منبع است، و چه چیزی را نگه میداری. در آخر یک خط: بهترین ترکیب به نظر تو.\n" + PERSIAN
    )


def plan_brief(
    w: dict[str, Any],
    roles_: dict[str, str],
    pack: dict[str, Any],
    proposals: list[tuple[str, str, str]],
    critiques: list[tuple[str, str, str]],
    skipped: list[str],
) -> str:
    """Round 3: the captain's plan (a child work of the council's assignee)."""

    def block(items: list[tuple[str, str, str]]) -> str:
        return (
            "\n\n".join(
                f"## {ROLE_FA[_role(roles_, p)]} ({name})\n{text}" for p, name, text in items
            )
            or "(هیچ)"
        )

    return (
        "شورای مشاوران، دور ۳ از ۳: برنامه‌ی کاپیتان.\n"
        f"پرسش مدیر کل: {w['title']}\n\n{pack_md(pack)}\n\n"
        f"# پیشنهادها (دور ۱)\n{block(proposals)}\n\n# نقدها (دور ۲)\n{block(critiques)}\n\n"
        + (f"اعضایی که جواب ندادند: {'، '.join(skipped)}\n\n" if skipped else "")
        + "خروجی تو یک برنامه‌ی اجرایی است، نه نظر کلی، در ۵ تا ۱۰ خط:\n"
        "1. یک خط هدف.\n"
        "2. یک جدول Markdown با سه ستون «چه کسی | چه کاری | تا کی» (نقش‌ها و بخش‌ها به فارسی، "
        "تاریخ یا مهلت روشن).\n"
        "3. یک خط «هزینه و ریسک».\n"
        "فقط فارسی؛ هیچ شناسه، کد کارمند، نام ابزار یا اصطلاح انگلیسی فنی ننویس. خلاصه‌ی پاسخ هر "
        "عضو لازم نیست: آن‌ها در جزئیات میمانند."
    )[:48_000]


def plan_of(body: str) -> str:
    """The plan the owner reads: plain Persian (§29.7), at most PLAN_LINES lines."""
    text = humanize.humanize(body or "")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[:PLAN_LINES])[:20_000]
