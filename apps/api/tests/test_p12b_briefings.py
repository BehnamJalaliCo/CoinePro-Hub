"""Prompt 12 §4 (contract §21.4): the spoken script, the briefings and the TTS
one-shot's api, the CEOs' weekly letters; nothing generated while the
holding is locked."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api import speech as SP
from hq_api.domain import briefings as B
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.mgmt_activities import MgmtActivities

from .conftest import TTS_TOKEN, agent_headers, idem
from .p10_support import holding_switch

TTS = {"Authorization": f"Bearer {TTS_TOKEN}"}


# ------------------------------------------------------------ the script --
CASES = [
    ("۱.۶M توکن", "یک و شش دهم میلیون توکن"),
    ("$4.20", "چهار دلار و بیست سنت"),
    ("$0.05", "پنج سنت"),
    ("$12", "دوازده دلار"),
    ("$1.6M", "یک و شش دهم میلیون دلار"),
    ("15%", "پانزده درصد"),
    ("۱۲٫۵٪", "دوازده و پنج دهم درصد"),
    ("1,234", "هزار و دویست و سی و چهار"),
    ("1000", "هزار"),
    ("2026", "دو هزار و بیست و شش"),
    ("0.25", "بیست و پنج صدم"),
    ("1405/08/01", "یکم آبان هزار و چهارصد و پنج"),
    ("۱۴۰۵/۰۸/۰۳", "سوم آبان هزار و چهارصد و پنج"),
    ("2026-10-22", "سی‌ام مهر هزار و چهارصد و پنج"),
    ("1405-08", "آبان هزار و چهارصد و پنج"),
    ("09:30", "ساعت نه و سی دقیقه"),
    ("10:00", "ساعت ده"),
    ("12.50 USD", "دوازده دلار و پنجاه سنت"),
    ("claude-opus-5-5", "اپوس پنج و نیم"),
    ("1,000,000", "یک میلیون"),
    ("21", "بیست و یک"),
    ("-3", "منفی سه"),
]


@pytest.mark.parametrize(("text", "spoken"), CASES)
def test_numbers_dates_and_money_are_read_as_persian_words(text: str, spoken: str) -> None:
    out = SP.fa_speech_script(text)
    assert out.rstrip(".") == spoken
    SP.assert_spoken(out)


def test_the_script_drops_markdown_reads_refs_and_codes_and_keeps_no_digit() -> None:
    text = (
        "# گزارش صبحگاهی — 22 مهر 1405 (2026-10-22)\n\n"
        "> نسخه‌ی قاعده‌محور\n\n"
        "| شرکت | توکن دیروز | هزینه (USD) |\n|---|---|---|\n| تریدیار (TY) | 1600000 | 4.2 |\n"
        "- **کارتابل:** D-000123 و W-000045 منتظرند؛ TY-CEO و HQ-TECH-MGR خبر دارند.\n"
        "- [سند](https://example.com/x) با Opus؛ 3 کار ۲ خروجی، 7.5% هدررفت، PR-082 فعال.\n"
    )
    out = SP.fa_speech_script(
        text,
        refs={"D-000123": "خرید سرور تازه"},
        codes={"TY-CEO": "مدیرعامل تریدیار"},
        companies={"TY": "تریدیار", "HQ": "ستاد"},
    )
    SP.assert_spoken(out)
    assert not re.search(r"[0-9۰-۹]", out)
    assert "#" not in out and "**" not in out and "|" not in out and "https" not in out
    assert "خرید سرور تازه" in out and "کار شماره‌ی چهل و پنج" in out
    assert "مدیرعامل تریدیار" in out and "مدیر فنی ستاد" in out
    assert "یک میلیون و ششصد هزار" in out and "هفت و پنج دهم درصد" in out
    assert "پروتکل شماره‌ی هشتاد و دو" in out
    assert "سی‌ام مهر هزار و چهارصد و پنج" in out
    assert SP.word_count("یک دو  سه") == 3


def test_words_of_large_and_ordinal_numbers() -> None:
    assert SP.int_words(0) == "صفر"
    assert SP.int_words(1_000_001) == "یک میلیون و یک"
    assert SP.int_words(2_500_000_000) == "دو میلیارد و پانصد میلیون"
    assert [SP.ordinal_words(n) for n in (1, 2, 3, 13, 23, 30, 31)] == [
        "یکم", "دوم", "سوم", "سیزدهم", "بیست و سوم", "سی‌ام", "سی و یکم",
    ]  # fmt: skip
    assert SP.decimal_words("0.000000123") == "صفر"  # beyond a millionth is rounded away
    assert SP.money_words("-2.5") == "منفی دو دلار و پنجاه سنت"
    assert SP.spell("TY2") == "تی وای دو"


# ------------------------------------------------------------ briefings --
def _day() -> date:
    """A day no earlier run used (the test database outlives a run)."""
    return date(2040, 1, 1) + timedelta(days=secrets.randbelow(200_000))


async def _deliverable(su: Any, company_id: Any) -> dict[str, Any]:
    work = await su.fetchval(
        """INSERT INTO work.work (company_id, kind, title, created_by_kind, created_by_code)
           VALUES ($1, 'event', 'Morning report (test)', 'service', 'system') RETURNING id""",
        company_id,
    )
    row = await su.fetchrow(
        """INSERT INTO cartable.deliverables (company_id, work_id, producer_id, title, summary, body,
               produced_with)
           SELECT $1, $2, e.id, 'گزارش صبحگاهی', 's', 'b', '{}' FROM core.employees e
           WHERE e.company_id = $1 AND e.kind = 'system' LIMIT 1 RETURNING id, ref""",
        company_id,
        work,
    )
    return dict(row)


async def test_tts_off_makes_a_text_briefing_and_the_locked_holding_makes_none(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    holding = await hub.companies.holding()
    day = _day()
    dl = await _deliverable(su, holding.id)
    text = "# گزارش\n- 3 تصمیم در انتظار، $4.20 هزینه‌ی دیروز."
    async with holding_switch(su, "engaged"), hub.db.tx(await hub.companies.ids()) as tx:
        assert await B.morning(tx, hub.settings, holding, dl, text, day) is None
    async with holding_switch(su, "released"), hub.db.tx(await hub.companies.ids()) as tx:
        row = await B.morning(tx, hub.settings, holding, dl, text, day)
        assert row is not None and row["audio_state"] == "off" and row["script"] is None
        assert row["text_md"] == text  # the text stands as it is
        assert await B.morning(tx, hub.settings, holding, dl, text, day) is None  # once a day
    r = await client.get(f"/api/v1/briefings/{row['ref']}", headers=owner)
    assert r.status_code == 200 and r.json()["audio_state"] == "off" and r.json()["audio"] is None
    latest = await client.get("/api/v1/briefings/latest?kind=morning", headers=owner)
    assert latest.status_code == 200
    page = await client.get("/api/v1/briefings?kind=morning&limit=1", headers=owner)
    assert page.status_code == 200 and len(page.json()["items"]) == 1
    meta = (await client.get("/api/v1/meta", headers=owner)).json()
    assert meta["tts"]["engine"] == "piper" and meta["tts"]["license"].startswith("CC0")
    assert meta["tts"]["enabled"] is False


async def test_the_tts_one_shot_claims_a_pending_briefing_and_sends_its_ogg(
    hub: Hub, su: Any, client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    holding = await hub.companies.holding()
    dl = await _deliverable(su, holding.id)
    on = replace(hub.settings, tts=True)
    async with holding_switch(su, "released"):
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await tx.exec(
                "UPDATE reports.briefings SET audio_state = 'off', script = NULL WHERE audio_state = 'pending'"
            )
            row = await B.morning(tx, on, holding, dl, "۲ کارت و $1.50 هزینه.", _day())
        assert row is not None and row["audio_state"] == "pending"
        assert "دو کارت و یک دلار و پنجاه سنت هزینه" in row["script"]
        assert (await client.post("/internal/v1/tts/claim", headers=owner)).status_code in (
            401,
            403,
        )
        job = await client.post("/internal/v1/tts/claim", headers=TTS)
        assert job.status_code == 200 and job.json()["ref"] == row["ref"]
        assert not re.search(r"[0-9]", job.json()["script"])
        bad = await client.post(
            f"/internal/v1/tts/{row['id']}/done",
            headers={**TTS, "Content-Type": "audio/ogg"},
            content=b"RIFF....",
        )
        assert bad.status_code == 422
        done = await client.post(
            f"/internal/v1/tts/{row['id']}/done?duration_s=3.5",
            headers={**TTS, "Content-Type": "audio/ogg"},
            content=b"OggS" + b"\0" * 200,
        )
        assert done.status_code == 200, done.text
        body = done.json()
        assert body["audio_state"] == "ready" and body["audio"]["mime"] == "audio/ogg"
        assert body["voice"]["voice"] == "fa_IR-amir-medium"
        again = await client.post(
            f"/internal/v1/tts/{row['id']}/done",
            headers={**TTS, "Content-Type": "audio/ogg"},
            content=b"OggS",
        )
        assert again.status_code == 409
        assert (await client.post("/internal/v1/tts/claim", headers=TTS)).status_code == 204


async def test_nothing_is_spoken_while_the_holding_is_locked(
    hub: Hub, su: Any, client: httpx.AsyncClient
) -> None:
    holding = await hub.companies.holding()
    dl = await _deliverable(su, holding.id)
    on = replace(hub.settings, tts=True)
    async with holding_switch(su, "released"), hub.db.tx(await hub.companies.ids()) as tx:
        row = await B.morning(tx, on, holding, dl, "یک خط.", _day())
    assert row is not None and row["audio_state"] == "pending"
    async with holding_switch(su, "engaged"):
        assert (await client.post("/internal/v1/tts/claim", headers=TTS)).status_code == 204
    async with holding_switch(su, "released"):
        for _ in range(B.TTS_MAX_ATTEMPTS):
            job = await client.post("/internal/v1/tts/claim", headers=TTS)
            assert job.status_code == 200
            f = await client.post(
                f"/internal/v1/tts/{job.json()['id']}/fail", headers=TTS, json={"error": "no voice"}
            )
            assert f.status_code == 204
        state = await su.fetchval(
            "SELECT audio_state FROM reports.briefings WHERE id = $1", row["id"]
        )
        assert state == "failed"


# ------------------------------------------------------- the weekly letter --
def test_figures_are_compared_after_normalising() -> None:
    figures = B.numbers_of('```json\n{"usd": "12.50", "n": 1,200, "pct": 7}\n```')
    assert {"12.5", "1200", "7"} <= figures
    assert B.unsourced("۱۲٫۵ دلار و 1,200 توکن", figures) == []
    assert B.unsourced("1. اول\n2. دوم: 999 توکن", figures) == ["999"]


async def test_the_ceo_letter_is_sent_back_once_then_marked_with_a_finding(
    hub: Hub,
    su: Any,
    client: httpx.AsyncClient,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    saturday = date(2031, 4, 5)
    assert saturday.weekday() == 5
    at = datetime(2031, 4, 5, 9, 5, tzinfo=UTC) - timedelta(hours=3, minutes=30)  # 09:05 Tehran
    acts = MgmtActivities(hub, lambda: _ScopedTx(hub))
    async with holding_switch(su, "engaged"):
        assert (await acts.ceo_letters(at.isoformat()))["skipped"] is True
    async with holding_switch(su, "released"):
        early = await acts.ceo_letters((at - timedelta(hours=1)).isoformat())
        assert early.get("reason") == "not_the_hour"
        out = await acts.ceo_letters(at.isoformat())
        assert out["week"] == saturday.isoformat() and out["letters"]
        assert (await acts.ceo_letters(at.isoformat()))["letters"] == []  # once a week
        letter = await su.fetchrow(
            "SELECT * FROM reports.ceo_letters WHERE company_id = $1 AND week = $2",
            co["id"],
            saturday,
        )
        assert letter is not None and letter["ceo_code"] == f"{co['code']}-CEO"
        work_id = letter["work_id"]
        ceo = await agent_headers(f"{co['code']}-CEO")
        long = " ".join(["کلمه"] * 601)
        r = await client.post(
            f"/internal/v1/work/{work_id}/deliver",
            headers={**ceo, **idem()},
            json={"title": "نامه", "body": long},
        )
        assert r.status_code == 422  # at most 600 words (not an attempt)
        bad = {"title": "نامه‌ی هفتگی", "body": "این هفته 98765 کاربر تازه آمدند."}
        r = await client.post(
            f"/internal/v1/work/{work_id}/deliver", headers={**ceo, **idem()}, json=bad
        )
        assert r.status_code == 422 and "98765" in r.text
        row = await su.fetchrow(
            "SELECT state, attempts, unsourced FROM reports.ceo_letters WHERE id = $1", letter["id"]
        )
        assert row["state"] == "returned" and row["attempts"] == 1 and row["unsourced"] == ["98765"]
        r = await client.post(
            f"/internal/v1/work/{work_id}/deliver", headers={**ceo, **idem()}, json=bad
        )
        assert r.status_code == 200, r.text
        dref = r.json()["deliverable"]
        title = await su.fetchval("SELECT title FROM cartable.deliverables WHERE ref = $1", dref)
        assert title.startswith(B.UNSOURCED)
        row = await su.fetchrow(
            "SELECT state, finding_ref, briefing_id FROM reports.ceo_letters WHERE id = $1",
            letter["id"],
        )
        assert row["state"] == "published" and row["finding_ref"] and row["briefing_id"]
        b = (
            await client.get(
                f"/api/v1/briefings/latest?kind=ceo_letter&company={co['code']}", headers=owner
            )
        ).json()
        assert b["deliverable_ref"] == dref and b["text_md"].startswith(B.UNSOURCED)
        assert b["period"] == {"from": "2031-03-29", "to": "2031-04-04"}


async def test_a_sourced_letter_is_published_as_it_is(
    hub: Hub, su: Any, client: httpx.AsyncClient, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    at = datetime(2031, 5, 3, 6, 0, tzinfo=UTC)  # Saturday 09:30 Tehran
    acts = MgmtActivities(hub, lambda: _ScopedTx(hub))
    async with holding_switch(su, "released"):
        await acts.ceo_letters(at.isoformat())
        letter = await su.fetchrow(
            "SELECT * FROM reports.ceo_letters WHERE company_id = $1 AND week = $2",
            co["id"],
            date(2031, 5, 3),
        )
        ceo = await agent_headers(f"{co['code']}-CEO")
        good = {"title": "نامه‌ی هفتگی", "body": "این هفته 0 حادثه داشتیم و همه‌چیز آرام بود."}
        r = await client.post(
            f"/internal/v1/work/{letter['work_id']}/deliver", headers={**ceo, **idem()}, json=good
        )
        assert r.status_code == 200, r.text
        row = await su.fetchrow(
            "SELECT state, finding_ref, attempts FROM reports.ceo_letters WHERE id = $1",
            letter["id"],
        )
        assert row["state"] == "published" and row["finding_ref"] is None and row["attempts"] == 1
