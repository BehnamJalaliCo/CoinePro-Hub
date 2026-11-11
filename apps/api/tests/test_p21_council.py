"""Prompt 21 part 2 (contract §29.7, §29.8): Persian only, and the council v2.

Every substitute player's answer to a work or a council must be Persian:
refused and asked again once with the instruction repeated, then the member
is `failed` with «پاسخ فارسی نبود». A web player's page residue is cut. The
council v2 runs three rounds (proposals, critique, the captain's plan) on a
fact pack without secrets, and «اجرا کن» makes an order of the plan. The
substitutes answer through the fake dispatcher body and a fake egress."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from hq_api.domain import humanize
from hq_api.domain import substitutes as S
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import FakeEgress, bench, claim, done, per_day
from .test_p18_players import by_player, council, order

SECRET = "sk-ant-api03-" + "abcdefghijklmnopqrstuvwxyz012345"  # a key shape, not a real one
GEMINI_TAIL = "\n\nمایلید جزئیات بیشتری درباره‌ی هر ایده بررسی کنیم؟ بله"


async def web_pass(hub: Hub, su: Any, *answers: dict[str, Any]) -> FakeEgress:
    await su.execute("UPDATE substitutes.players SET web_last_job_at = NULL")
    fake = FakeEgress(*answers)
    await S.web_jobs(hub, fake)
    return fake


def plain_everywhere(c: dict[str, Any]) -> None:
    """Every text of the council that reaches the owner passes humanize.check."""
    for m in [*c["members"], *(x for r in c["rounds"] for x in r["members"])]:
        if m.get("reason"):
            assert humanize.check(m["reason"]) == [], m["reason"]
    for text in (c.get("note_fa"), c.get("plan_md")):
        if text:
            assert humanize.check(text) == [], text


# ------------------------------------------------------------ language --
def test_a_web_players_page_residue_is_cut() -> None:
    assert S.cut_residue("سه ایده برای ریلز:\n۱. اول\n۲. دوم" + GEMINI_TAIL) == (
        "سه ایده برای ریلز:\n۱. اول\n۲. دوم"
    )
    assert (
        S.cut_residue("پاسخ کامل است. Would you like me to go on?\nYes\nCopy") == "پاسخ کامل است."
    )
    assert S.cut_residue("چرا کم شد؟ چون قیمت بالا رفت.") == "چرا کم شد؟ چون قیمت بالا رفت."
    assert S.cut_residue("مایلید ادامه بدهم؟") == "مایلید ادامه بدهم؟"  # nothing but residue: kept
    assert S.cut_residue("Shall I draft it?\nCopy\nYes") == "Shall I draft it?\nCopy\nYes"
    assert S.cut_residue("متن.\n\nآیا می‌خواهید جدول بسازم؟\n\nبله\n\nخیر\nکپی") == "متن."


def test_a_one_word_verdict_and_an_own_closing_question_are_not_residue() -> None:
    # a reply chip's word on its own is the answer's verdict, not the page's
    for text in (
        "آیا این طرح قانونی است؟ بررسی کردم.\n\nپاسخ کوتاه:\n\nخیر.",
        "Is the deal profitable?\n\nShort answer:\nNo.",
        "نتیجه‌گیری:\nبله",
    ):
        assert S.cut_residue(text) == text
    assert S.cut_residue("نتیجه‌گیری:\nبله\nCopy") == "نتیجه‌گیری:\nبله"
    # an offer starts a line or a sentence; a bare «می‌خواهید» is not an offer
    for text in (
        "سؤال کلیدی برای هیئت این است: مشتری واقعاً چه می‌خواهید؟",
        "The real question for the board: do you want growth or margin?",
        "پیشنهاد نهایی: کدام گزینه بهتر است اگر بخواهید سریع رشد کنید؟",
        "The open question: should I hire now or wait?",
    ):
        assert S.cut_residue(text) == text
    assert S.cut_residue("Answer here. Do you want me to expand?") == "Answer here."
    assert humanize.is_persian_answer("پاسخ فارسی با نام Gemini و https://example.com/a")
    assert not humanize.is_persian_answer("这是答案，价格两百万。")


async def test_a_chinese_answer_is_asked_again_once_then_fails_in_persian(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        w = await order(client, owner, co, mode="council", title="قیمت دوره‌ی تازه")
        job = (await claim(client))["job"]
        r = await done(client, job["id"], ok=True, text_md="这是答案，价格两百万。")
        assert r.status_code == 200 and r.json()["state"] == "queued", r.text
        m = by_player(await council(client, owner, w["id"]))["gpt"]
        assert m["state"] == "queued" and m["reason_code"] == "not_persian_retry"
        again = (await claim(client))["job"]
        assert again["id"] == job["id"] and "پاسخ قبلی تو فارسی نبود" in again["input_md"]
        r = await done(client, again["id"], ok=True, text_md="这是答案，价格两百万。")
        assert r.json()["state"] == "failed"
    c = await council(client, owner, w["id"])
    m = by_player(c)["gpt"]
    assert (m["state"], m["reason_code"], m["reason"]) == (
        "failed",
        "not_persian",
        "پاسخ فارسی نبود",
    )
    plain_everywhere(c)
    # a code review keeps the language its task asks for (never refused for it)
    call = await su.fetchrow("SELECT * FROM substitutes.calls WHERE id = $1::uuid", job["id"])
    assert call["lang_retried"] is True
    assert not S.needs_persian(
        {**dict(call), "purpose_kind": "decision"}, S.DoneIn(ok=True, text_md="x")
    )


# ------------------------------------------------------------- council --
async def test_the_council_v2_three_rounds_fact_pack_plan_and_run(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    code = co["code"]
    await su.execute(
        """INSERT INTO governance.kpis (company_id, key, card, name_fa, unit, direction, source,
               freshness_hours, origin, last_value, last_at)
           VALUES ($1, 'growth.followers', 'growth', $2, 'نفر', 'up', '{"kind": "manual"}', 24,
                   'owner', 1520, now())""",
        co["id"],
        f"فالوور اینستاگرام {SECRET}",
    )
    async with bench(su, hub, cli=("gpt",), web=("gemini",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        await per_day(su, "gemini", "content_draft", 5)
        w = await order(client, owner, code, mode="council", title="ایده‌ی محتوا برای بازار تازه")
        c = await council(client, owner, w["id"])
        assert c["round"] == 1 and c["roles"]["claude"] == "captain"
        m = by_player(c)
        assert (m["gpt"]["role"], m["gemini"]["role"], m["claude"]["role"]) == (
            "devil", "researcher", "captain",
        )  # fmt: skip
        assert m["deepseek"]["state"] == "skipped"
        # the fact pack: the hub's own figures, masked
        fp = await client.get(f"/api/v1/fact-packs/{c['fact_pack_ref']}", headers=owner)
        assert fp.status_code == 200, fp.text
        pack = fp.json()
        assert pack["company"] == code and SECRET not in json.dumps(pack, ensure_ascii=False)
        kpi = next(f for f in pack["figures"] if f["key"] == "kpi.growth.followers")
        assert kpi["value"] == 1520 and kpi["source"] == "kpi"
        assert any(f["key"] == "spend.tokens_7d" for f in pack["figures"])
        # round 1: proposals, each in its role, on the fact pack
        job = (await claim(client))["job"]
        assert "مخالف خلاق" in job["input_md"] and "بسته‌ی واقعیت" in job["input_md"]
        assert SECRET not in job["input_md"] and "1520" in job["input_md"]
        await done(client, job["id"], ok=True, text_md="پیشنهاد جی‌پی‌تی: هر روز یک ریلز کوتاه")
        fake = await web_pass(
            hub, su, {"ok": True, "text_md": "پیشنهاد جمنای: رقبا ریلز آموزشی دارند" + GEMINI_TAIL}
        )
        assert "پژوهشگر" in fake.calls[0]["prompt"]
        gem = await su.fetchval(
            """SELECT result->>'text_md' FROM substitutes.calls WHERE player = 'gemini'
                 AND purpose_kind = 'council' AND purpose_ref = $1 ORDER BY created_at DESC LIMIT 1""",
            w["ref"],
        )
        assert gem == "پیشنهاد جمنای: رقبا ریلز آموزشی دارند"  # the page's residue cut
        ceo = await agent_headers(f"{code}-CEO")
        r = await client.post(
            f"/internal/v1/work/{w['id']}/deliver",
            headers={**ceo, **idem()},
            json={"title": "پیشنهاد کاپیتان", "summary": "سری آموزشی", "body": "پیشنهاد Claude: سری آموزشی"},
        )  # fmt: skip
        assert r.status_code == 200, r.text
        # round 2: each substitute that proposed critiques the others
        c = await council(client, owner, w["id"])
        assert c["round"] == 2 and {x["player"] for x in c["members"]} == {"gpt", "gemini"}
        job = (await claim(client))["job"]
        assert "پیشنهاد جمنای" in job["input_md"] and "پیشنهاد Claude" in job["input_md"]
        assert "پیشنهاد جی‌پی‌تی" not in job["input_md"]
        await done(client, job["id"], ok=True, text_md="نقد جی‌پی‌تی: هزینه‌ی ریلز روزانه زیاد است")
        await web_pass(hub, su, {"ok": True, "text_md": "نقد جمنای: منبع عدد رقبا لازم است"})
    c = await council(client, owner, w["id"])
    assert c["round"] == 3 and c["state"] == "synthesising" and len(c["rounds"]) == 2
    syn = await su.fetchrow(
        """SELECT w.id, w.brief FROM work.councils k JOIN work.work w ON w.id = k.synthesis_work_id
           WHERE k.work_id = $1""",
        uuid.UUID(w["id"]),
    )
    for part in ("پیشنهاد جی‌پی‌تی", "پیشنهاد جمنای", "پیشنهاد Claude", "نقد جی‌پی‌تی", "نقد جمنای",
                 "چه کسی | چه کاری | تا کی"):  # fmt: skip
        assert part in syn["brief"], part
    plan = (
        "هدف: هر روز یک ریلز آموزشی برای بازار تازه.\n"
        "| چه کسی | چه کاری | تا کی |\n|---|---|---|\n"
        "| مدیر رسانه | برنامه‌ی سه ریلز | تا پنجشنبه |\n| نویسنده | سه سناریو با منبع | تا چهارشنبه |\n"
        "هزینه و ریسک: حدود 400 هزار توکن؛ ریسک تکرار موضوع."
    )
    r = await client.post(
        f"/internal/v1/work/{syn['id']}/deliver",
        headers={**ceo, **idem()},
        json={"title": "برنامه‌ی شورا", "summary": "برنامه", "body": plan},
    )
    assert r.status_code == 200, r.text
    c = await council(client, owner, w["id"])
    assert c["state"] == "done" and c["synthesis_ref"] == r.json()["deliverable"]
    assert "چه کسی" in c["plan_md"] and 5 <= len(c["plan_md"].splitlines()) <= 10
    plain_everywhere(c)
    # «اجرا کن»: the plan becomes an order of the company (its CEO splits it)
    early = await client.post(f"/api/v1/work/{w['id']}/council/run", headers={**owner, **idem()})
    assert early.status_code == 201, early.text
    out = early.json()
    assert out["ref"].startswith("F-") and out["route"]["companies"] == [code]
    assert out["route"]["mode"] == "single" and out["routes"][0]["to"] == f"{code}-CEO"
    text = await su.fetchval("SELECT text FROM owner.orders WHERE ref = $1", out["ref"])
    assert "مدیر رسانه" in text
    assert (await council(client, owner, w["id"]))["order_ref"] == out["ref"]
    again = await client.post(f"/api/v1/work/{w['id']}/council/run", headers={**owner, **idem()})
    assert again.status_code == 409
    # the hub's own route is no correction of the owner's
    assert not await su.fetchval(
        "SELECT 1 FROM owner.dispatch_memory WHERE order_ref = $1", out["ref"]
    )


async def test_council_roles_are_the_owners_setting(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    s = await client.get("/api/v1/owner/settings", headers=owner)
    roles = s.json()["council_roles"]
    assert roles == {
        "claude": "captain",
        "gemini": "researcher",
        "deepseek": "numbers",
        "gpt": "devil",
    }
    bad = await client.put(
        "/api/v1/owner/settings",
        headers={**owner, "If-Match": str(s.json()["version"])},
        json={"council_roles": {"claude": "king"}},
    )
    assert bad.status_code == 422
