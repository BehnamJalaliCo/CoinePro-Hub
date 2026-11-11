"""Prompt 19.2: the catalogue is strictly structured end to end. One fenced
JSON object per section of a fixed schema; the hub parses it tolerantly,
coerces cells to strings, checks every row's width, asks the server once
more when the answer broke the schema, and as a last resort keeps the
readable prose as notes: raw JSON never reaches prose, the deliverable or
the archive PDF. Catalogues stored before are rebuilt from their answers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.archive import pdf
from hq_api.domain import catalogue as CAT
from hq_api.hub import Hub

from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p17_runners import pair, poll, take

pytestmark = pytest.mark.usefixtures("relay")

SHAPE = {"key", "title_fa", "summary_fa", "tables", "notes_fa", "count"}
RAW_JSON = re.compile(r'"[a-z_]+"\s*:|\[\[|```|^\s*[{\[]', re.M)

GOOD = {
    "title_fa": "داده‌ها",
    "summary_fa": "یک پایگاه داده و دو جدول.",
    "count": 2,
    "tables": [{"title_fa": "جدول‌ها", "columns": ["نام", "ردیف‌ها", "اندازه"],
                "rows": [["users", 1520, "12 MB"], ["orders", None, {"size": "3 MB"}]]}],
    "notes_fa": ["محتوای هیچ ردیفی خوانده نشد."],
}  # fmt: skip

# what the owner saw in TradeYar's catalogue: a JSON fragment inside Persian prose
MESSY = (
    "پشتیبان‌ها بررسی شد و فایل‌های زیر پیدا شد: "
    '"rows": [["backup_verification.json", "2026-10-30", "سالم"], ["db.dump", "2026-10-29", "سالم"]] '
    "و پشتیبان دیروز هم سالم است.\n\nهیچ گواهی‌ای در ۳۰ روز آینده منقضی نمیشود."
)


def fenced(obj: Any) -> str:
    return "در ادامه کاتالوگ آمده است.\n```json\n" + json.dumps(obj, ensure_ascii=False) + "\n```"


def prose_of(sec: dict[str, Any]) -> str:
    return "\n".join([sec.get("summary_fa") or "", *sec["notes_fa"]])


# ---------------------------------------------------------------- parsing --
def test_a_fenced_answer_is_read_and_every_cell_is_a_string() -> None:
    sec, errors = CAT.parse_answer("data", fenced(GOOD))
    assert errors == [] and set(sec) == SHAPE
    t = sec["tables"][0]
    assert t["columns"] == ["نام", "ردیف‌ها", "اندازه"]
    assert t["rows"] == [["users", "1520", "12 MB"], ["orders", "", "size: 3 MB"]]
    assert sec["count"] == 2 and sec["notes_fa"] == ["محتوای هیچ ردیفی خوانده نشد."]
    assert sec["title_fa"] == CAT.SECTION_FA["data"]  # the hub's title, never the model's


def test_a_bare_object_after_prose_is_found_and_the_prose_never_leaks() -> None:
    sec, errors = CAT.parse_answer("data", "خلاصه‌ی من:\n" + json.dumps(GOOD, ensure_ascii=False))
    assert errors == [] and sec["tables"][0]["rows"][0][0] == "users"
    assert "خلاصه‌ی من" not in prose_of(sec)


def test_rows_of_the_wrong_width_are_errors_and_still_kept_whole() -> None:
    bad = {
        **GOOD,
        "tables": [{"title_fa": "t", "columns": ["a", "b"], "rows": [["1"], ["1", "2", "3"]]}],
    }
    sec, errors = CAT.parse_answer("data", fenced(bad))
    assert any("do not have exactly 2 cells" in e for e in errors)
    t = sec["tables"][0]
    assert t["columns"] == ["a", "b", "ستون ۳"] and t["rows"] == [["1", "", ""], ["1", "2", "3"]]
    assert all(len(r) == len(t["columns"]) for r in t["rows"])


def test_json_in_the_prose_is_an_error_and_is_taken_out() -> None:
    bad = {**GOOD, "summary_fa": MESSY}
    sec, errors = CAT.parse_answer("data", fenced(bad))
    assert any("summary_fa" in e for e in errors)
    assert "پشتیبان دیروز هم سالم است" in sec["summary_fa"]
    assert not RAW_JSON.search(sec["summary_fa"]) and "backup_verification" not in sec["summary_fa"]


def test_an_answer_with_no_json_keeps_its_prose_as_notes_and_its_markdown_tables() -> None:
    text = MESSY + "\n\n### گواهی‌ها\n| دامنه | انقضا |\n|---|---|\n| a.example.com | 2027-01-02 |\n"
    sec, errors = CAT.parse_answer("risks", text)
    assert errors and set(sec) == SHAPE
    assert sec["notes_fa"][0] == CAT.NOT_STRUCTURED_FA
    assert any("پشتیبان دیروز هم سالم است" in n for n in sec["notes_fa"])
    assert not RAW_JSON.search(prose_of(sec)) and "|" not in prose_of(sec)
    assert sec["tables"] == [{"title_fa": "گواهی‌ها", "columns": ["دامنه", "انقضا"],
                              "rows": [["a.example.com", "2027-01-02"]]}]  # fmt: skip


def test_a_broken_fenced_block_says_why() -> None:
    sec, errors = CAT.parse_answer("risks", '```json\n{"summary_fa": "x", "tables": [ }\n```')
    assert errors and "does not parse" in errors[0]
    assert sec["tables"] == [] and sec["notes_fa"] == [CAT.UNREADABLE_FA]


def test_a_section_stored_before_19_2_is_served_in_the_one_shape() -> None:
    old = {"key": "products", "title_fa": "محصولات و سرویس‌ها",
           "summary_md": "خلاصه " + fenced(GOOD), "notes_md": "اول\n\nدوم",
           "tables": [{"title_fa": None, "columns": ["a"], "rows": [[1], [None]]}], "count": 2}  # fmt: skip
    got = CAT.CatalogueSection.model_validate(CAT.stored(old)).model_dump()
    assert set(got) == SHAPE and got["notes_fa"] == ["اول", "دوم"]
    assert got["summary_fa"] == "خلاصه در ادامه کاتالوگ آمده است."  # the JSON is gone
    assert got["tables"][0]["rows"] == [["1"], [""]]


def test_the_deliverable_is_rendered_from_the_structure() -> None:
    sec, _ = CAT.parse_answer("data", fenced({**GOOD, "summary_fa": MESSY}))
    body = CAT.markdown("TY", CAT.merged([{**sec, "server": "s1", "server_name": "app-1"}]), None)
    assert "| نام | ردیف‌ها | اندازه |\n| --- | --- | --- |\n| users | 1520 | 12 MB |" in body
    assert "| orders | — | size: 3 MB |" in body
    assert "- محتوای هیچ ردیفی خوانده نشد." in body
    assert "backup_verification" not in body and '"rows"' not in body and "```" not in body


def test_the_pdf_draws_real_tables_with_the_header_on_every_page() -> None:
    rows = [[f"svc-{i}", "سرویس گزارش روزانه", "running"] for i in range(150)]
    sec, _ = CAT.parse_answer("products", fenced({"summary_fa": "همه", "tables": [
        {"title_fa": "سرویس‌ها", "columns": ["نام", "شرح", "وضعیت"], "rows": rows}]}))  # fmt: skip
    body = CAT.markdown("TY", CAT.merged([{**sec, "server": "s", "server_name": "a"}]), None)
    blocks = pdf.blocks_of("کاتالوگ", body)
    tables = [b for b in blocks if b[0] == "table"]
    assert len(tables) == 1 and tables[0][1] == ["نام", "شرح", "وضعیت"] and len(tables[0][2]) == 150
    assert not any(b[0] == "text" and "|" in b[1] for b in blocks)  # no table printed as text
    pages = pdf.pages_of("کاتالوگ", body)
    assert len(pages) >= 3
    for page in pages[1:]:  # every page that goes on with the table starts with its header
        heads = [op for op in page if op[0] == "t" and op[5] and op[4] == pdf.TSIZE]
        assert [op[3] for op in heads[:3]] == ["نام", "شرح", "وضعیت"]
    cells = [op[3] for p in pages for op in p if op[0] == "t"]
    assert "svc-149" in cells and sum(1 for p in pages for op in p if op[0] == "r") > 450
    svg = pdf.page_svg(pages[0], 1, len(pages), "f")
    assert "<rect" in svg and "‫" in svg  # Persian lines embedded right to left


def test_a_wide_table_is_drawn_record_by_record() -> None:
    cols = [f"c{i}" for i in range(10)]
    body = (
        "| "
        + " | ".join(cols)
        + " |\n|"
        + "---|" * 10
        + "\n| "
        + " | ".join(f"v{i}" for i in range(10))
        + " |"
    )
    pages = pdf.pages_of("t", body)
    rects = [op for op in pages[0] if op[0] == "r"]
    assert len(rects) == 2 * 10  # a header (c0 | v0) and nine rows of two cells
    texts = [op[3] for op in pages[0] if op[0] == "t"]
    assert {"c0", "v0", "c9", "v9"} <= set(texts)



def test_a_header_taller_than_a_page_is_cut_and_the_layout_ends() -> None:
    cols = [f"c{i}" for i in range(9)]
    first = " ".join(["کلمه"] * 1500)  # a wide table's first cell heads its record
    body = "| " + " | ".join(cols) + " |\n|" + "---|" * 9 + "\n| " + first + " | "
    body += " | ".join(f"v{i}" for i in range(1, 9)) + " |"
    pages = pdf.pages_of("t", body)  # it used to start page after page without end
    assert len(pages) == 1
    texts = [op[3] for op in pages[0] if op[0] == "t"]
    assert {"c1", "v1", "c8", "v8"} <= set(texts) and any(t.endswith(" …") for t in texts)

# ------------------------------------------------------------- end to end --
async def _answer(
    client: httpx.AsyncClient, rn: dict[str, Any], job: dict[str, Any], text: str
) -> None:
    r = await client.post(f"/api/v1/runners/jobs/{job['id']}/result", headers=rn["h"],
                          json={"exit_code": 0, "data": {"result_fa": text}})  # fmt: skip
    assert r.status_code == 200, r.text


async def test_a_broken_answer_is_asked_once_more_then_kept_as_prose(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "ty-1")
    assert (
        await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    ).status_code == 202
    jobs = {
        j["args"]["title"].split(": ", 1)[1]: j
        for j in [await take(client, rn) for _ in CAT.SECTIONS]
    }
    assert all("ONE fenced JSON block" in j["args"]["brief"] for j in jobs.values())
    risks, data = jobs.pop(CAT.SECTION_FA["risks"]), jobs.pop(CAT.SECTION_FA["data"])
    for j in jobs.values():
        await _answer(client, rn, j, fenced(GOOD))
    await _answer(client, rn, risks, MESSY)  # no JSON at all
    bad = {**GOOD, "tables": [{"title_fa": "t", "columns": ["a", "b"], "rows": [["1", "2", "3"]]}]}
    await _answer(client, rn, data, fenced(bad))  # a row wider than its columns
    again = [await take(client, rn) for _ in range(2)]
    briefs = {j["args"]["title"]: j["args"]["brief"] for j in again}
    risky = next(b for t, b in briefs.items() if CAT.SECTION_FA["risks"] in t)
    assert "COULD NOT BE READ" in risky and "holds no JSON object" in risky
    datab = next(b for t, b in briefs.items() if CAT.SECTION_FA["data"] in t)
    assert "do not have exactly 2 cells" in datab
    got = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert got["state"] == "running"  # it waits for the second answers
    by_title = {j["args"]["title"]: j for j in again}
    for title, j in by_title.items():
        if CAT.SECTION_FA["risks"] in title:
            await _answer(client, rn, j, MESSY)  # broken again: the prose is kept
        else:
            await _answer(client, rn, j, fenced(GOOD))  # mended
    r = await poll(client, rn)
    assert r.status_code == 204  # asked once more, never twice
    got = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert got["state"] == "done", got
    for s in got["sections"]:
        assert set(s) == SHAPE
        assert not RAW_JSON.search(prose_of(s)), s
        for t in s["tables"]:
            assert all(isinstance(v, str) for r in t["rows"] for v in r)
            assert all(len(r) == len(t["columns"]) for r in t["rows"])
    risks_sec = next(s for s in got["sections"] if s["key"] == "risks")
    assert risks_sec["tables"] == [] and risks_sec["notes_fa"][0] == CAT.NOT_STRUCTURED_FA
    assert any("پشتیبان دیروز هم سالم است" in n for n in risks_sec["notes_fa"])
    data_sec = next(s for s in got["sections"] if s["key"] == "data")
    assert data_sec["tables"][0]["columns"] == ["نام", "ردیف‌ها", "اندازه"]  # the second answer
    body = await su.fetchval(
        "SELECT body FROM cartable.deliverables WHERE ref = $1", got["deliverable"]
    )
    assert "backup_verification" not in body and "```" not in body and '"rows"' not in body


async def test_stored_catalogues_are_rerendered_from_their_answers(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    h = owner_session["headers"]
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "old-1")
    await client.post(f"/api/v1/companies/{co['code']}/catalogue", headers=h)
    for _ in CAT.SECTIONS:
        await _answer(client, rn, await take(client, rn), fenced(GOOD))
    before = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert before["state"] == "done" and before["record"]
    # as a catalogue from before 19.2 was stored: the whole answer as the summary
    legacy = [{"key": k, "title_fa": t, "summary_md": fenced(GOOD), "tables": [],
               "notes_md": None, "count": None} for k, t, _ in CAT.SECTIONS]  # fmt: skip
    await su.execute(
        """UPDATE infra.catalogues SET sections = $1::jsonb
           WHERE company_id = $2 AND state = 'done'""",
        json.dumps(legacy, ensure_ascii=False),
        co["id"],
    )
    served = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert all(set(s) == SHAPE and not RAW_JSON.search(prose_of(s)) for s in served["sections"])
    out = [x for x in await CAT.rerender_all(hub) if x.get("company") == co["code"]]
    assert len(out) == 1 and "error" not in out[0], out
    assert out[0]["tables"] == len(CAT.SECTIONS) and out[0]["rows"] == 2 * len(CAT.SECTIONS)
    after = (await client.get(f"/api/v1/companies/{co['code']}/catalogue", headers=h)).json()
    assert after["deliverable"] != before["deliverable"] and after["record"] != before["record"]
    assert after["record"].startswith("AR-")
    data = next(s for s in after["sections"] if s["key"] == "data")
    assert data["summary_fa"] == GOOD["summary_fa"] and data["tables"][0]["rows"][0] == [
        "users",
        "1520",
        "12 MB",
    ]
    # the old deliverable and record stay (the archive never forgets)
    assert (
        await su.fetchval(
            "SELECT count(*) FROM cartable.deliverables WHERE ref = $1", before["deliverable"]
        )
        == 1
    )
    rec = await su.fetchrow(
        """SELECT f.mime, f.pages FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
           WHERE r.ref = $1""",
        after["record"],
    )
    assert rec["mime"] == "application/pdf" and rec["pages"] >= 1
    # again: idempotent in shape, a fresh deliverable each time it is asked
    again = [x for x in await CAT.rerender_all(hub) if x.get("company") == co["code"]]
    assert again[0]["rows"] == out[0]["rows"]
