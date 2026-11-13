"""W24 (2026-11-13): what stays after a publication, and what goes (contract §58.4).

The owner: «میز انتشار … حجمش زیاد میشه … کاور اصلی و ریلز اصلی و متن کپشن بایگانی بشه و بقیه … پاک
بشه دیسک رو سنگین نکنه».

A. IG-Hub's confirmed publication keeps its package (the reel, its cover, caption.txt) and files it
   to the archive as the publication's record; the desk's `published` card says so;
B. 72 hours after, the daily sweep deletes every other file of that output and of the earlier
   versions of its revision chain (rows, variants and their stored objects queued for
   destruction), except what the owner opened since, what another output or a session uses; one
   audit row per output with the count and the bytes; a second pass does nothing; an output with
   no confirmed publication loses nothing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from hq_api.domain import players as PL
from hq_api.domain import publish_keep as PK
from hq_api.domain import work as W
from hq_api.hub import Hub

from .test_p17_runners import pair, take
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w7_sessions import WORK_TEXT
from .test_w11_connections import set_connection
from .test_w17_session_publish import an_output, tap


async def a_file(
    su: Any,
    hub: Hub,
    company_id: Any,
    name: str,
    mime: str,
    data: bytes,
    *,
    parent: Any = None,
    variant: str = "original",
) -> UUID:
    key, _ = await hub.storage.put(data)
    fid: UUID = await su.fetchval(
        """INSERT INTO files.files (company_id, name, mime, size, sha256, storage_key,
               created_by_kind, created_by_code, parent_id, variant)
           VALUES ($1, $2, $3, $4, $5, $6, 'service', 'test', $7, $8) RETURNING id""",
        company_id, name, mime, len(data), hashlib.sha256(data).hexdigest(), key, parent,
        variant,
    )  # fmt: skip
    return fid


async def exists(su: Any, fid: Any) -> bool:
    return bool(await su.fetchval("SELECT 1 FROM files.files WHERE id = $1", fid))


# ======================================================= A. the package is kept ==
async def test_a_confirmed_publication_keeps_its_package_in_the_archive(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    made = await an_output(client, hub, owner, owner_session, su, pc["code"],
                           ("reel.mp4", "cover.png", "other.png"))  # fmt: skip
    reel, cover, other = made["files"]
    r = await set_connection(
        client, f"{ig['code']}-TECH-MGR",
        {"company": pc["code"], "kind": "instagram", "accounts": ["@pro.chart"], "via": "ig_hub",
         "server": {"company": ig["code"], "name": "IG-Hub"}, "read_command": "cat /srv/ig/d.json",
         "publish_command": "/srv/ig/bin/hq-publish"},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    ig_rn = await pair(client, hub, owner_session, ig, "IG-Hub")
    r = await tap(client, owner, made["order"], {"output": made["output"], "file_id": reel,
                                                 "cover_file_id": cover, "caption": "سه سطح طلا"})  # fmt: skip
    assert r.status_code == 202, r.text
    job = await take(client, ig_rn)

    # a failed publication keeps nothing and so deletes nothing
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 1, "summary_fa": "حساب امروز به سقف انتشار رسیده است."},
        headers=ig_rn["h"],
    )
    assert r.status_code == 200, r.text
    assert not await su.fetchval(
        "SELECT 1 FROM files.publish_keep WHERE output = $1", made["output"]
    )
    r = await tap(client, owner, made["order"], {"output": made["output"], "file_id": reel,
                                                 "cover_file_id": cover, "caption": "سه سطح طلا"})  # fmt: skip
    assert r.status_code == 202, r.text
    job = await take(client, ig_rn)
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "منتشر شد.",
              "data": {"external_id": "ig-58", "url": "https://www.instagram.com/p/k58/"}},
        headers=ig_rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    row = await su.fetchrow("SELECT * FROM files.publish_keep WHERE output = $1", made["output"])
    assert row is not None and row["job_id"] == UUID(job["id"])
    assert {str(x) for x in row["kept"]} == {reel, cover}  # the reel and the cover it carried
    assert row["record_ref"] and row["swept_at"] is None
    rec = await su.fetchrow(
        "SELECT id, state, source_kind, source_ref FROM archive.records WHERE ref = $1",
        row["record_ref"],
    )
    assert rec["state"] == "filed" and rec["source_ref"] == f"publication:{made['output']}"
    names = {
        r["name"]
        for r in await su.fetch(
            "SELECT name FROM archive.record_files WHERE record_id = $1", rec["id"]
        )
    }
    assert names == {"reel.mp4", "cover.png"}
    # the desk's `published` card: archived, nothing freed yet
    desk = (await client.get("/api/v1/publish-desk", headers=owner)).json()
    card = next(c for c in desk["done"] if c["output"] == made["output"])
    assert card["state"] == "published" and card["archived"] is True
    assert card["freed_bytes"] is None
    # 72 hours later the sweep runs: the other picture goes, the package stays, the card says it
    ids = await hub.companies.ids()
    got = await PK.sweep(hub, lambda: hub.db.tx(ids), now=datetime.now(UTC) + timedelta(hours=73))
    assert got["outputs"] >= 1
    assert not await exists(su, other)
    assert await exists(su, reel) and await exists(su, cover)
    desk = (await client.get("/api/v1/publish-desk", headers=owner)).json()
    card = next(c for c in desk["done"] if c["output"] == made["output"])
    assert card["archived"] is True and card["freed_bytes"] and card["freed_bytes"] > 0


# ============================================================ B. the sweep ==
async def test_the_sweep_takes_the_rest_of_the_chain_and_keeps_what_is_used(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    new_company: Callable[..., Any],
) -> None:
    company = await new_company()
    co = company["code"]
    out = await post_order(client, owner, WORK_TEXT.format(co=co, w=words()))
    root_ref = out["routes"][0]["work_ref"]
    cid = company["id"]

    async def f(name: str, mime: str = "text/plain", size: int = 40) -> UUID:
        return await a_file(su, hub, cid, name, mime, (name * 40).encode()[:size] + b"\n")

    # the earlier version: its notes and a draft render (with a poster)
    notes_v1 = await f("notes-v1.md", "text/markdown")
    draft = await f("draft.mp4", "video/mp4", 300)
    poster = await a_file(su, hub, cid, "draft.jpg", "image/jpeg", b"\xff\xd8\xff poster",
                          parent=draft, variant="poster")  # fmt: skip
    # the published one: the package, its notes, the topic file once used, a file another output
    # uses too, one the owner opens, one a session's talk holds
    reel = await f("reel.mp4", "video/mp4", 500)
    cover = await f("cover.png", "image/png", 200)
    caption = await f("caption.txt")
    notes_v2 = await f("notes-v2.md", "text/markdown")
    topic = await f("topic.txt")
    shared = await f("logo.png", "image/png")
    opened = await f("script.md", "text/markdown")
    # an output never published (its publication failed): nothing of it goes
    lone = await f("idea.md", "text/markdown")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        w = await W.load_ref(tx, root_ref)
        first = await PL.deliver(tx, w, title="notes", body="یادداشت", close=False,
                                 produced_with={"direct": True},
                                 attachments=[str(notes_v1), str(draft)])  # fmt: skip
        second = await PL.deliver(
            tx, w, title="نسخه‌ی تازه‌ی notes", body="ریلز", close=False,
            produced_with={"direct": True, "revision_of": first["ref"]},
            attachments=[str(x) for x in (reel, cover, caption, notes_v2, topic, shared, opened)],
        )  # fmt: skip
        await PL.deliver(tx, w, title="لوگو", body="لوگو", close=False,
                         produced_with={"direct": True}, attachments=[str(shared)])  # fmt: skip
        await PL.deliver(tx, w, title="ایده", body="ایده", close=False,
                         produced_with={"direct": True}, attachments=[str(lone)])  # fmt: skip
        # IG-Hub confirmed the second (as session_publish.after_job reads its job)
        job = {
            "id": UUID(int=int(datetime.now(UTC).timestamp() * 1e6)),
            "finished_at": datetime.now(UTC),
            "args": {"session": {"output": second["ref"], "file_id": str(reel),
                                 "cover_name": "cover.png"},
                     "files": [{"file_id": str(reel)}]},
        }  # fmt: skip
        assert await PK.on_published(tx, job) == second["ref"]
        assert await PK.on_published(tx, job) is None  # once per output
        assert await PK.chain_of(tx, second["ref"]) == [second["ref"], first["ref"]]
    # the owner opens one of its files (the app's GET /files/{id})
    r = await client.get(f"/api/v1/files/{opened}", headers=owner)
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT 1 FROM files.opened WHERE file_id = $1", opened)
    row = await su.fetchrow("SELECT * FROM files.publish_keep WHERE output = $1", second["ref"])
    assert {str(x) for x in row["kept"]} == {str(reel), str(cover), str(caption)}

    ids = await hub.companies.ids()

    def txf() -> Any:
        return hub.db.tx(ids)

    # within the 72 hours nothing goes
    got = await PK.sweep(hub, txf, now=datetime.now(UTC) + timedelta(hours=70))
    assert await exists(su, notes_v2) and await exists(su, draft)
    assert await su.fetchval(
        "SELECT swept_at FROM files.publish_keep WHERE output = $1", second["ref"]
    ) is None  # fmt: skip
    # the package is filed to the archive by the same pass (nothing filed it before)
    assert got["filed"] >= 1
    assert await su.fetchval(
        "SELECT record_ref FROM files.publish_keep WHERE output = $1", second["ref"]
    )
    gone_bytes = sum(
        int(await su.fetchval("SELECT size FROM files.files WHERE id = $1", x))
        for x in (notes_v2, topic, notes_v1, draft, poster)
    )
    keys = [
        str(await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1", x))
        for x in (notes_v2, draft, poster)
    ]
    got = await PK.sweep(hub, txf, now=datetime.now(UTC) + timedelta(hours=73))
    assert got["outputs"] >= 1
    for x in (notes_v2, topic, notes_v1, draft, poster):
        assert not await exists(su, x), x
    for x in (reel, cover, caption, shared, opened, lone):
        assert await exists(su, x), x
    row = await su.fetchrow("SELECT * FROM files.publish_keep WHERE output = $1", second["ref"])
    assert row["swept_at"] is not None and row["swept_files"] == 5
    assert row["freed_bytes"] == gone_bytes
    queued = {
        r["storage_key"]
        for r in await su.fetch(
            "SELECT storage_key FROM archive.destroy_queue WHERE why = 'publish_sweep' AND ref = $1",
            second["ref"],
        )
    }
    assert set(keys) <= queued
    entry = await su.fetchrow(
        """SELECT summary FROM audit.entries WHERE action = 'files.publish_sweep'
             AND target_ref = $1 AND company_id = $2""",
        second["ref"],
        cid,
    )
    assert entry is not None and entry["summary"].startswith(f"5 files, {gone_bytes} bytes")
    # once: a second pass does nothing more
    again = await su.fetchval("SELECT count(*) FROM audit.entries WHERE action = 'files.publish_sweep' "
                              "AND target_ref = $1", second["ref"])  # fmt: skip
    await PK.sweep(hub, txf, now=datetime.now(UTC) + timedelta(hours=100))
    assert again == await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'files.publish_sweep' AND target_ref = $1",
        second["ref"],
    )
