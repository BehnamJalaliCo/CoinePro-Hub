"""Prompt 26, W8 (contract §36): files in a session. The owner, 2026-11-06: «میخوام اینجا فایل
بفرستم برای سشن نمیتونم» · «تایتل بذاره با فونتی که ما میدیم».

- §36.1 upload: fonts (TrueType, OpenType, WOFF, WOFF2 by their first bytes -> `kind: font`, its
  family read in the untrusted child into `meta.family`), plain text / Markdown and ZIP
  (`document`; a ZIP is stored, never unpacked); every earlier kind keeps its behaviour;
- §36.2 a talk turn with files: stored on the owner's turn, rendered as `files`, and the
  persona's model sees each one (an image as an image, a document's first pages as text, a
  font's family, a video's poster and transcript, an audio's transcript);
- §36.3 files go with the order: in a session every file of the owner's turns belongs to the
  order (a step, `OrderReport.files`, the brief of every run of the order's works), and
  `files.read` reads it for a run of the order's works whatever its company, never for another;
- a font of the order is used by the creative overlay (`overlay.font_file_id`) and the media
  studio (`media.item` style `font_file_id`); IRANYekanX stays the default.
"""

from __future__ import annotations

import io
import json
import os
import struct
import uuid
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import media
from hq_api.domain import files as F
from hq_api.domain import order_turns as OT
from hq_api.hub import Hub
from hq_api.security import agent_tokens

from .conftest import AGENT_KEY, agent_headers, idem
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p23_talk import answer, open_cv, say, talk  # noqa: F401 - the fixture

FONTS = Path(os.environ.get("HQ_FONTS_DIR", "/fonts"))
OTHER_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


# ------------------------------------------------------------------ helpers --
def ttf() -> bytes:
    path = FONTS / "IRANYekanX-Regular.ttf"
    if not path.exists():
        pytest.skip("the IRANYekanX fonts are not mounted")
    return path.read_bytes()


def other_ttf() -> bytes:
    if not OTHER_FONT.exists():
        pytest.skip("no second font in this image")
    return OTHER_FONT.read_bytes()


def woff_of(sfnt: bytes) -> bytes:
    """The WOFF 1.0 of an sfnt font (each table zlib-compressed when that is smaller)."""
    flavor, n = struct.unpack(">IH", sfnt[:6])
    entries = [struct.unpack(">4sIII", sfnt[12 + 16 * i : 28 + 16 * i]) for i in range(n)]
    head = 44 + 20 * n
    offset, dirs, blobs = head, [], []
    for tag, checksum, off, length in entries:
        raw = sfnt[off : off + length]
        comp = zlib.compress(raw)
        data = comp if len(comp) < len(raw) else raw
        dirs.append(struct.pack(">4sIIII", tag, offset, len(data), length, checksum))
        pad = (-len(data)) % 4
        blobs.append(data + b"\0" * pad)
        offset += len(data) + pad
    total_sfnt = 12 + 16 * n + sum((length + 3) & ~3 for *_, length in entries)
    header = struct.pack(">4sIIHHIHHIIIII", b"wOFF", flavor, offset, n, 0, total_sfnt, 1, 0,
                         0, 0, 0, 0, 0)  # fmt: skip
    return header + b"".join(dirs) + b"".join(blobs)


def a_zip() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("cover/title.txt", "پروچارت")
        z.writestr("../escape.txt", "never unpacked")
    return out.getvalue()


async def upload(
    client: httpx.AsyncClient, owner: dict[str, str], data: bytes, mime: str, name: str = "x"
) -> httpx.Response:
    return await client.post(
        "/api/v1/files",
        content=data,
        headers={**owner, **idem(), "Content-Type": mime, "X-File-Name": name},
    )


async def uploaded(
    client: httpx.AsyncClient, owner: dict[str, str], data: bytes, mime: str, name: str = "x"
) -> dict[str, Any]:
    r = await upload(client, owner, data, mime, name)
    assert r.status_code == 201, r.text
    return dict(r.json())


# ================================================================ §36.1 upload ==
def test_fonts_text_and_zip_are_known_by_their_first_bytes() -> None:
    font = ttf()
    assert media.font_type(font[:64]) == "font/ttf"
    assert media.font_type(b"OTTO\x00\x0a\x00\x80\x00\x03\x00\x20CFF " + b"\0" * 48) == "font/otf"
    assert media.font_type(woff_of(font)[:64]) == "font/woff"
    assert media.font_type(b"wOF2" + b"\0" * 60) == "font/woff2"
    # 00 01 00 00 alone is not a font: its table directory must make sense
    assert media.font_type(b"\x00\x01\x00\x00" + b"\0" * 60) is None
    assert media.check_type("font/ttf", font[:64]) == ("font/ttf", media.FONT)
    assert media.check_type("application/x-font-ttf", font[:64]) == ("font/ttf", media.FONT)
    assert media.check_type("application/octet-stream", font[:64]) == ("font/ttf", media.FONT)
    assert media.check_type("application/octet-stream", a_zip()[:64]) == (
        "application/zip",
        media.PACKAGE,
    )
    assert isinstance(
        media.check_type("application/octet-stream", b"\x89PNG\r\n\x1a\n" + b"\0" * 56), str
    )
    assert media.check_type("text/markdown", "# سلام\nمتن".encode()) == (
        "text/markdown",
        media.PACKAGE,
    )
    assert isinstance(media.check_type("text/plain", font[:64]), str)  # a font is not text
    assert isinstance(media.check_type("text/plain", b"%PDF-1.4 hidden"), str)
    assert isinstance(media.check_type("text/plain", b"abc\x00def"), str)
    assert isinstance(media.check_type("font/ttf", b"just some words, not a font at all....."), str)
    # a Persian letter cut at the end of the first chunk is still text
    assert media.looks_text("سلام".encode()[:-1])
    assert media.clean_family('Pro"Chart, <b>Sans</b>;\n') == "ProChart bSans/b"


async def test_a_font_is_uploaded_with_its_family(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    ref = await uploaded(client, owner, ttf(), "font/ttf", "IRANYekanX-Regular.ttf")
    assert ref["kind"] == "font" and ref["mime"] == "font/ttf" and ref["status"] == "ready"
    assert ref["meta"] == {"family": "IRANYekanX", "style": "Regular"}
    meta = (await client.get(f"/api/v1/files/{ref['id']}/meta", headers=owner)).json()
    assert meta["meta"]["family"] == "IRANYekanX"
    row = await su.fetchrow(
        "SELECT kind, meta, company_id, created_by_kind FROM files.files WHERE id = $1",
        uuid.UUID(ref["id"]),
    )
    assert row["kind"] == "font" and row["created_by_kind"] == "owner"
    # a phone's plain bytes: the bytes name it; WOFF and WOFF2 too
    w = await uploaded(client, owner, woff_of(ttf()), "application/octet-stream", "f.woff")
    assert (w["kind"], w["mime"], w["meta"]["family"]) == ("font", "font/woff", "IRANYekanX")
    w2_path = FONTS / "IRANYekanX-Bold.woff2"
    w2 = await uploaded(client, owner, w2_path.read_bytes(), "font/woff2", "b.woff2")
    assert (w2["kind"], w2["mime"], w2["meta"]["family"]) == ("font", "font/woff2", "IRANYekanX")
    # a font is never served inline
    r = await client.get(f"/api/v1/files/{ref['id']}", headers=owner)
    assert r.status_code == 200 and r.headers["content-disposition"].startswith("attachment")
    assert r.content == ttf()


async def test_a_broken_or_oversized_font_is_refused(
    client: httpx.AsyncClient, owner: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    font = ttf()
    broken = font[:300] + b"\xff" * 2000
    r = await upload(client, owner, broken, "font/ttf")
    assert r.status_code == 415 and "font" in r.text
    monkeypatch.setattr(media, "FONT", media.Kind("font", 10_000))
    r = await upload(client, owner, font, "application/octet-stream")
    assert r.status_code == 413
    # a type not taken, and a font declared as text
    assert (await upload(client, owner, font, "application/x-shockwave-flash")).status_code == 415
    assert (await upload(client, owner, font, "text/plain")).status_code == 415


async def test_text_markdown_and_zip_are_documents(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any
) -> None:
    md = "# جلد پروچارت\n\nعنوان با فونت شرکت.\n".encode()
    ref = await uploaded(client, owner, md, "text/markdown; charset=utf-8", "brief.md")
    assert (ref["kind"], ref["mime"], ref["status"]) == ("document", "text/markdown", "ready")
    text = await su.fetchval(
        "SELECT text FROM files.processing WHERE file_id = $1", uuid.UUID(ref["id"])
    )
    assert text.startswith("# جلد پروچارت")
    z = await uploaded(client, owner, a_zip(), "application/zip", "pack.zip")
    assert (z["kind"], z["mime"], z["status"]) == ("document", "application/zip", "ready")
    # stored as it is: one row, no processing, nothing unpacked
    rows = await su.fetchval(
        "SELECT count(*) FROM files.files WHERE id = $1 OR parent_id = $1", uuid.UUID(z["id"])
    )
    assert rows == 1
    assert (
        await su.fetchval(
            "SELECT count(*) FROM files.processing WHERE file_id = $1", uuid.UUID(z["id"])
        )
        == 0
    )
    z2 = await uploaded(client, owner, a_zip(), "application/octet-stream", "pack2.zip")
    assert z2["mime"] == "application/zip"
    r = await client.get(f"/api/v1/files/{z['id']}", headers=owner)
    assert r.headers["content-disposition"].startswith("attachment")
    # binary bytes declared as text are refused
    assert (await upload(client, owner, b"\x00\x01\x02binary", "text/plain")).status_code == 415


async def test_the_earlier_kinds_keep_their_behaviour(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    pdf = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
    ref = await uploaded(client, owner, pdf, "application/pdf")
    assert (ref["kind"], ref["mime"], ref["meta"]) == ("document", "application/pdf", None)
    # a PDF sent as plain bytes is still refused (only a font or a ZIP is taken by its bytes)
    assert (await upload(client, owner, pdf, "application/octet-stream")).status_code == 415


# ======================================================= §36.2 a turn with files ==
def png() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(out, format="PNG")
    return out.getvalue()


async def some_files(client: httpx.AsyncClient, owner: dict[str, str]) -> list[dict[str, Any]]:
    """A font, a Markdown brief, a ZIP and a picture, uploaded by the owner."""
    return [
        await uploaded(client, owner, ttf(), "font/ttf", "ProChart-Title.ttf"),
        await uploaded(
            client, owner, "# بریف جلد\nعنوان درشت و سفید.".encode(), "text/markdown", "brief.md"
        ),
        await uploaded(client, owner, a_zip(), "application/zip", "pack.zip"),
        await uploaded(client, owner, png(), "image/png", "cover.png"),
    ]


async def turn(
    client: httpx.AsyncClient, owner: dict[str, str], ref: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/talk/conversations/{ref}/turns", json={"source": "typed", **body},
        headers={**owner, **idem()},
    )  # fmt: skip


async def test_a_turn_with_files_is_kept_and_seen_by_the_persona(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    talk: dict[str, Any],  # noqa: F811
) -> None:
    cv = await open_cv(client, owner)
    files = await some_files(client, owner)
    ids = [f["id"] for f in files]
    out = await say(client, owner, cv["ref"], "این فایل‌ها را ببین", file_ids=ids)
    assert [f["id"] for f in out["owner_turn"]["files"]] == ids
    assert out["owner_turn"]["files"][0]["meta"]["family"] == "IRANYekanX"
    assert out["answer"]["files"] == []
    last = talk["router"].bodies[-1]["messages"][-1]["content"]
    assert isinstance(last, list) and last[0]["type"] == "text"
    text = last[0]["text"]
    assert "این فایل‌ها را ببین\n\n## The owner's files with these words" in text
    assert "family «IRANYekanX»" in text and "عنوان درشت و سفید" in text
    assert "UNTRUSTED DATA" in text and "ZIP archive «pack.zip»" in text and "not unpacked" in text
    assert "escape.txt" not in text  # a ZIP is never opened
    assert [b["type"] for b in last[1:]] == ["image"] and last[1]["media_type"] == "image/jpeg"
    # the conversation's page shows them on the owner's turn
    page = (await client.get(f"/api/v1/talk/conversations/{cv['ref']}", headers=owner)).json()
    mine = [t for t in page["turns_page"]["items"] if t["by"] == "owner"]
    assert [f["id"] for f in mine[-1]["files"]] == ids
    # files without words; the earlier turn's files are named in one line
    await say(client, owner, cv["ref"], "", file_ids=[files[1]["id"]])
    msgs = talk["router"].bodies[-1]["messages"]
    assert isinstance(msgs[-1]["content"], str)  # no picture this time
    assert "(the owner sent these files without words)" in msgs[-1]["content"]
    assert "[the owner sent with this: font «ProChart-Title.ttf»" in json.dumps(
        msgs, ensure_ascii=False
    )


async def test_a_turns_files_must_be_the_owners_own_uploads(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    talk: dict[str, Any],  # noqa: F811
    su: Any,
) -> None:
    cv = await open_cv(client, owner)
    img = await uploaded(client, owner, png(), "image/png", "cover.png")
    r = await turn(client, owner, cv["ref"], {"text": "این", "file_ids": [str(uuid.uuid4())]})
    assert r.status_code == 422 and r.json()["message_fa"] == F.UNKNOWN_FA
    thumb = img["variants"]["thumb"]  # a variant is not an upload
    r = await turn(client, owner, cv["ref"], {"text": "این", "file_ids": [thumb]})
    assert r.status_code == 422 and r.json()["message_fa"] == F.UNKNOWN_FA
    # a file the hub made (not the owner's)
    made = await su.fetchval(
        "SELECT id FROM files.files WHERE created_by_kind <> 'owner' AND variant = 'original' LIMIT 1"
    )
    if made is not None:
        r = await turn(client, owner, cv["ref"], {"text": "این", "file_ids": [str(made)]})
        assert r.status_code == 422
    r = await turn(client, owner, cv["ref"], {"text": "", "file_ids": []})
    assert r.status_code == 422
    r = await turn(client, owner, cv["ref"], {"text": "x", "file_ids": [img["id"]] * 11})
    assert r.status_code == 422
    # the same file twice is one file
    r = await turn(client, owner, cv["ref"], {"text": "دوباره", "file_ids": [img["id"]] * 2})
    assert r.status_code == 202 and [f["id"] for f in r.json()["owner_turn"]["files"]] == [
        img["id"]
    ]


# =================================================== §36.3 files go with the order ==
async def run_on(su: Any, code: str, work_ref: str) -> dict[str, str]:
    """An agent token for `code`, bound to a running run on the work `work_ref`."""
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now()
           FROM core.employees e WHERE e.id = r.employee_id AND e.code = $1
             AND r.state = 'running' AND r.trigger <> 'talk'""",
        code,
    )
    rid = await su.fetchval(
        """INSERT INTO agents.runs (company_id, employee_id, work_id, trigger, reason, state,
               started_at, token_expires_at)
           SELECT e.company_id, e.id, w.id, 'work', 'test', 'running', now(), now() + interval '1 hour'
           FROM core.employees e, work.work w WHERE e.code = $1 AND w.ref = $2 RETURNING id""",
        code,
        work_ref,
    )
    return {"Authorization": f"Bearer {agent_tokens.mint(AGENT_KEY, code, str(rid))}"}


async def test_files_in_a_session_go_with_the_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    other = (await new_company())["code"]
    out = await post_order(client, owner, f"برای {co} جلد اینستاگرام با عنوان بساز {words()}")
    ref, conv = out["ref"], out["talk_ref"]
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    files = await some_files(client, owner)
    font, md, _, img = files
    talk["router"].answers = [answer("فونت را گرفتم؛ عنوان جلد با همین فونت میشود.")]
    said = await say(client, owner, conv, "این فونت شرکت است؛ عنوان جلد با این باشد",
                     file_ids=[f["id"] for f in files])  # fmt: skip
    assert len(said["owner_turn"]["files"]) == 4
    # a step per file, the report's files newest first
    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    steps = [s["what_fa"] for s in rep["steps"]]
    assert "فایل از مدیر کل: ProChart-Title.ttf" in steps and "فایل از مدیر کل: brief.md" in steps
    assert [f["id"] for f in rep["files"]] == [f["id"] for f in reversed(files)]
    assert rep["files"][-1]["meta"]["family"] == "IRANYekanX"
    # the same file again is not a second file of the order
    await say(client, owner, conv, "همان فونت", file_ids=[font["id"]])
    rep = (await client.get(f"/api/v1/orders/{ref}/report", headers=owner)).json()
    assert len(rep["files"]) == 4
    assert sum(s["what_fa"].startswith("فایل از مدیر کل") for s in rep["steps"]) == 4
    # the persona of the session reads them under «## The order you hold»
    assert "ProChart-Title.ttf" in talk["router"].text_sent()
    # the holder's run sees them in its brief
    async with hub.db.tx(await hub.companies.ids()) as tx:
        wid = await tx.scalar("SELECT id FROM work.work WHERE ref = :r", r=work_ref)
        d = await OT.dialogue(tx, wid)
    assert d is not None
    by_id = {f["id"]: f for f in d["files"]}
    assert by_id[font["id"]] == {"id": font["id"], "name": "ProChart-Title.ttf", "kind": "font",
                                 "family": "IRANYekanX"}  # fmt: skip
    assert by_id[md["id"]]["kind"] == "document" and by_id[img["id"]]["kind"] == "image"
    # files.read: a run of the order's works reads them (the holding's rows, whatever its company)
    mine = await run_on(su, holder, work_ref)
    r = await client.get(f"/internal/v1/files/{font['id']}/meta", headers=mine)
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["family"] == "IRANYekanX" and r.json()["kind"] == "font"
    r = await client.get(f"/internal/v1/files/{md['id']}/meta", headers=mine)
    assert r.status_code == 200 and "عنوان درشت" in r.json()["text"]
    r = await client.get(f"/internal/v1/files/{img['id']}/meta", headers=mine)
    assert r.status_code == 200 and r.json()["agent"]
    agent_copy = uuid.UUID(r.json()["agent"])
    run_id = await su.fetchval(
        """SELECT r.id FROM agents.runs r JOIN core.employees e ON e.id = r.employee_id
           WHERE e.code = $1 AND r.state = 'running' AND r.trigger = 'work'""",
        holder,
    )
    async with hub.db.tx(await hub.companies.ids()) as tx:
        # the runner shows the picture's copy for a model (a variant of the order's file)
        assert await F.order_grant(tx, str(run_id), [agent_copy, uuid.uuid4()]) == {agent_copy}
    # an employee of another company, on no work of the order: refused, as a missing file is
    stranger = await agent_headers(f"{other}-TECH-MGR")
    r = await client.get(f"/internal/v1/files/{font['id']}/meta", headers=stranger)
    assert r.status_code == 403
    # a run on another order's work is refused too
    out2 = await post_order(client, owner, f"برای {other} گزارش هفته را آماده کن {words()}")
    [route2] = out2["routes"]
    theirs = await run_on(su, route2["to"], route2["work_ref"])
    r = await client.get(f"/internal/v1/files/{font['id']}/meta", headers=theirs)
    assert r.status_code == 403
    # a talk with no order keeps its files to itself
    cv = await open_cv(client, owner)
    lone = await uploaded(client, owner, png(), "image/png", "lone.png")
    await say(client, owner, cv["ref"], "این یکی", file_ids=[lone["id"]])
    r = await client.get(f"/internal/v1/files/{lone['id']}/meta", headers=mine)
    assert r.status_code == 403


# ============================================== §36.3 a font of the order is used ==
def _render(tmp: Path, family: str | None, font: Path | None, mime: str | None) -> bytes:
    from hq_api.domain import creative_overlay as O

    overlay = {"title_fa": "ProChart Weekly", "body_fa": "تحلیل هفته", "mark": False}
    svg = O.svg("instagram_post", overlay, None, {"ink": "#111216"}, None, title_family=family)
    out, sfnt = tmp / f"o-{uuid.uuid4().hex}.png", tmp / f"s-{uuid.uuid4().hex}.ttf"
    O.compose_job(svg, str(out), str(FONTS), str(font) if font else None, mime, str(sfnt))
    return out.read_bytes()


def test_the_title_is_set_in_the_owners_font(tmp_path: Path) -> None:
    from PIL import ImageFont

    from hq_api.domain import creative_overlay as O

    other_ttf()
    svg = O.svg("instagram_post", {"title_fa": "عنوان"}, None, {}, None, title_family="DejaVu Sans")
    assert 'font-family="&#x27;DejaVu Sans&#x27;, IRANYekanX"' in svg
    # a family is never a way into the SVG
    bad = O.svg("instagram_post", {"title_fa": "x"}, None, {}, None, title_family='A"/><script>')
    assert "<script>" not in bad and 'A"' not in bad
    plain = _render(tmp_path, None, None, None)
    dejavu = _render(tmp_path, "DejaVu Sans", OTHER_FONT, "font/ttf")
    assert plain != dejavu  # the title is drawn in the owner's font
    # a WOFF is unpacked to its sfnt in the child, and draws the same
    woff = tmp_path / "d.woff"
    woff.write_bytes(woff_of(OTHER_FONT.read_bytes()))
    assert _render(tmp_path, "DejaVu Sans", woff, "font/woff") == dejavu
    sfnt = tmp_path / "back.ttf"
    sfnt.write_bytes(O.woff_to_sfnt(woff.read_bytes()))
    assert ImageFont.truetype(str(sfnt), 20).getname()[0] == "DejaVu Sans"
    with pytest.raises(ValueError):
        O.woff_to_sfnt(b"wOFF" + b"\xff" * 60)
    with pytest.raises(ValueError):  # a WOFF2 is never handed to the renderer
        _render(tmp_path, "IRANYekanX", FONTS / "IRANYekanX-Bold.woff2", "font/woff2")


async def test_a_creative_names_a_font_of_its_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    from hq_api.domain import creative_overlay as O
    from hq_api.domain import substitutes as S

    from .test_p12a_substitutes import FakeEgress, bench, per_day
    from .test_p12a_substitutes import png as png_b64

    co = (await new_company())["code"]
    font = await uploaded(client, owner, other_ttf(), "font/ttf", "brand.ttf")
    woff2 = await uploaded(client, owner, (FONTS / "IRANYekanX-Bold.woff2").read_bytes(),
                           "font/woff2", "brand.woff2")  # fmt: skip
    overlay = {"title_fa": "ProChart Weekly", "mark": False}
    body = {
        "company": co,
        "kind": "image",
        "brief_md": "جلد پست هفتگی",
        "placement": "instagram_post",
    }
    async with bench(su, hub, web=("gpt",)):
        await per_day(su, "gpt", "creative", 10)
        # the owner: any of the owner's own fonts; a WOFF2 is refused with the reason
        r = await client.post("/api/v1/creatives", headers={**owner, **idem()},
                              json={**body, "overlay": {**overlay, "font_file_id": woff2["id"]}})  # fmt: skip
        assert r.status_code == 422 and r.json()["message_fa"] == O.FONT_WOFF2_FA
        r = await client.post("/api/v1/creatives", headers={**owner, **idem()},
                              json={**body, "overlay": {**overlay, "font_file_id": str(uuid.uuid4())}})  # fmt: skip
        assert r.status_code == 422 and r.json()["message_fa"] == O.FONT_UNKNOWN_FA
        r = await client.post("/api/v1/creatives", headers={**owner, **idem()},
                              json={**body, "overlay": {**overlay, "font_file_id": font["id"]}})  # fmt: skip
        assert r.status_code == 201, r.text
        mine = r.json()
        r = await client.post("/api/v1/creatives", headers={**owner, **idem()},
                              json={**body, "overlay": overlay})  # fmt: skip
        plain = r.json()
        fake = FakeEgress(*[{"ok": True, "file": {"name": "i.png", "mime": "image/png",
                                                  "b64": png_b64(1080, 1350)}} for _ in range(2)])  # fmt: skip
        for _ in range(2):  # one web job at a time, with the player's pause between them
            await su.execute(
                "UPDATE substitutes.players SET web_last_job_at = NULL WHERE player = 'gpt'"
            )
            await S.web_jobs(hub, fake)
        got = {}
        for c in (mine, plain):
            x = (await client.get(f"/api/v1/creatives/{c['ref']}", headers=owner)).json()
            assert x["state"] == "review", x
            got[c["ref"]] = (await client.get(f"/api/v1/files/{x['composed']['id']}",
                                              headers=owner)).content  # fmt: skip
        assert got[mine["ref"]] != got[plain["ref"]]  # the title in the owner's font
        stored = await su.fetchval(
            "SELECT overlay->>'font_file_id' FROM substitutes.creatives WHERE ref = $1", mine["ref"]
        )
        assert stored == font["id"]
        # an agent: a font of the order its run works on; another order's run is refused
        out = await post_order(client, owner, f"برای {co} جلد اینستاگرام بساز {words()}")
        [route] = out["routes"]
        await say(client, owner, out["talk_ref"], "با این فونت", file_ids=[font["id"]])
        call = {"seat": "creative", "input_md": "a weekly cover, blue", "kind": "image",
                "placement": "instagram_post", "overlay": {**overlay, "font_file_id": font["id"]}}  # fmt: skip
        holder = await run_on(su, route["to"], route["work_ref"])
        r = await client.post("/internal/v1/substitutes/call", headers=holder, json=call)
        assert r.status_code == 200, r.text
        other = (await new_company())["code"]
        out2 = await post_order(client, owner, f"برای {other} جلد بساز {words()}")
        [route2] = out2["routes"]
        theirs = await run_on(su, route2["to"], route2["work_ref"])
        r = await client.post("/internal/v1/substitutes/call", headers=theirs, json=call)
        assert r.status_code == 422 and r.json()["message_fa"] == O.FONT_UNKNOWN_FA


async def test_a_media_item_names_a_font_of_its_order(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    from hq_api.domain import creative_overlay as O

    from .conftest import MEDIA_TOKEN
    from .test_p13a_media import COMPOSITION, hire, item, only_this_job

    media_svc = {"Authorization": f"Bearer {MEDIA_TOKEN}"}
    co = await new_company()
    ui = await hire(su, co, "ui_designer")
    font_bytes = other_ttf()
    font = await uploaded(client, owner, font_bytes, "font/ttf", "brand.ttf")
    out = await post_order(client, owner, f"برای {co['code']} صفحه‌ی فرود بساز {words()}")
    [route] = out["routes"]
    await say(client, owner, out["talk_ref"], "فونت شرکت", file_ids=[font["id"]])
    r = await client.post("/api/v1/media/items", headers={**owner, **idem()},
                          json={"company": co["code"], "kind": "design", "brief_md": "صفحه‌ی فرود"})  # fmt: skip
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    named = COMPOSITION.replace(
        "font:700 72px/1.3 IRANYekanX", "font:700 72px/1.3 'DejaVu Sans', IRANYekanX"
    )
    assert named != COMPOSITION
    # a run on another order (of the same company) may not name this font
    out2 = await post_order(client, owner, f"برای {co['code']} گزارش فروش بساز {words()}")
    [route2] = out2["routes"]
    theirs = await run_on(su, ui, route2["work_ref"])
    brief = {"ref": ref, "step": "brief", "brief_md": "بریف: یک اقدام، فارسی درست"}
    r = await client.post("/internal/v1/media/item", headers={**theirs, **idem()},
                          json={**brief, "style": {"font_file_id": font["id"]}})  # fmt: skip
    assert r.status_code == 422 and r.json()["message_fa"] == O.FONT_UNKNOWN_FA
    # the designer's run on this order's work names it with the brief
    mine = await run_on(su, ui, route["work_ref"])
    r = await client.post("/internal/v1/media/item", headers={**mine, **idem()},
                          json={**brief, "style": {"font_file_id": font["id"]}})  # fmt: skip
    assert r.status_code == 200, r.text
    x = await item(client, owner, ref)
    assert x["style"] == {"font_file_id": font["id"], "family": "DejaVu Sans"}
    # the composition may name its family beside IRANYekanX (another family is still refused)
    bad = named.replace("DejaVu Sans", "Comic Sans MS")
    r = await client.post("/internal/v1/media/item", headers={**mine, **idem()},
                          json={"ref": ref, "step": "composition",
                                "composition": {"format": "html", "source": bad}})  # fmt: skip
    assert r.status_code == 422 and "font" in r.json()["fields"]["composition"]
    r = await client.post("/internal/v1/media/item", headers={**mine, **idem()},
                          json={"ref": ref, "step": "composition",
                                "composition": {"format": "html", "source": named}})  # fmt: skip
    assert r.status_code == 200, r.text
    # the render job carries the font as one of its assets, and the page declares it
    await only_this_job(ref)
    job = (await client.post("/internal/v1/media/render/claim", headers=media_svc)).json()
    assert job["item"] == ref
    assert job["fonts"] == [{"id": font["id"], "family": "DejaVu Sans", "mime": "font/ttf"}]
    assert font["id"] in {a["id"] for a in job["assets"]}
    r = await client.get(f"/internal/v1/media/render/{job['id']}/files/{font['id']}",
                         headers=media_svc)  # fmt: skip
    assert r.status_code == 200 and r.content == font_bytes
