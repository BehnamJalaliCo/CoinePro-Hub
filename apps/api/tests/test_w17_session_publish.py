"""⟨2026-11-10⟩ «تأیید و انتشار» (contract §44.5): the owner's tap on a file of his own session
publishes it through IG-Hub's own runner.

The owner: «این برو بیا و هی مهر بکن و اینو مجوز بده … آزار و اذیت میده منو». What goes out and
can be taken back needs his word once, in the session, on the file itself: no card, no passkey.
A company whose publish command is not registered yet is the holding's technical work, made by
code, and never his step.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import httpx
from PIL import Image

from hq_api.domain import decisions as D
from hq_api.hub import Hub

from .conftest import idem
from .test_p13a_media import mp4
from .test_p17_runners import pair, take
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_w11_connections import set_connection
from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop


def a_png(i: int) -> bytes:
    """A picture of its own (the same bytes twice for one job are one file)."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), (12 + 60 * i, 80, 160)).save(buf, format="PNG")
    return buf.getvalue()


async def an_output(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    su: Any,
    co: str,
    names: tuple[str, ...] = ("cover.png",),
) -> dict[str, Any]:
    """A session of `co` whose workshop turn delivered one output with these files."""
    rn = await workshop(client, hub, owner_session, su)
    out = await post_order(
        client, owner, f"برای {co} {words()} وضع کامل شرکت را بررسی کن و گزارش بده"
    )
    [route] = out["routes"]
    holder, work_ref = route["to"], route["work_ref"]
    wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", work_ref)
    r = await run_ask(client, holder, {"work": work_ref, "brief": "یک کاور بساز"})
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    files = []
    for i, name in enumerate(names):
        if name.endswith(".mp4"):
            r = await send_file(client, rn, job["id"], name, "video/mp4", mp4(2))
        else:
            r = await send_file(client, rn, job["id"], name, "image/png", a_png(i))
        assert r.status_code == 201, r.text
        files.append(r.json()["id"])
    await refuse_queued(su, str(wid))
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "تمام شد.",
              "data": {"session_id": "cs-pub-1", "result_fa": "ساخته شد.", "files": files}},
        headers=rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    rep = (await client.get(f"/api/v1/orders/{out['ref']}/report", headers=owner)).json()
    return {"order": out["ref"], "output": rep["outputs"][-1]["ref"], "files": files,
            "work_ref": work_ref, "work_id": wid}  # fmt: skip


async def tap(
    client: httpx.AsyncClient, owner: dict[str, str], order: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/api/v1/orders/{order}/publish", headers={**owner, **idem()}, json=body
    )


def test_what_goes_out_and_can_be_taken_back_is_a_tap() -> None:
    assert D.needs_step_up({"kind": "media_publish", "action_class": "A3"}) is False
    # the passkey stays for money, deleting for good, keys and access, a destructive command
    for kind, cls in (("hire", "A2"), ("budget_change", "A2"), ("erase", "A2"),
                      ("server_destructive", "A3"), ("tool_enable", "A2"), ("a3_action", "A3"),
                      ("line_publish", "A3"), ("media_series", "A2")):  # fmt: skip
        assert D.needs_step_up({"kind": kind, "action_class": cls}) is True, kind


async def test_the_owners_tap_publishes_a_session_file_through_ig_hub(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    igc, co = ig["code"], pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("cover.png", "two.png"))
    order, output, (one, two) = made["order"], made["output"], made["files"]

    # 1. nothing registered yet: never the owner's step. The technical work is made by code,
    #    once, under the order, and the session says so.
    r = await tap(client, owner, order, {"output": output, "file_id": one})
    assert r.status_code == 202, r.text
    assert r.json()["state"] == "waiting_setup" and r.json()["job"] is None
    assert (
        "تیم فنی هلدینگ" in r.json()["note_fa"] and "کاری از شما لازم نیست" in r.json()["note_fa"]
    )
    r = await tap(client, owner, order, {"output": output, "file_id": one})
    assert r.json()["state"] == "waiting_setup"
    works = await su.fetch(
        "SELECT ref, brief, requested_by_work_id FROM work.work WHERE run_meta ->> 'ig_publish' = $1",
        co,
    )
    assert len(works) == 1 and works[0]["requested_by_work_id"] == made["work_id"]
    assert "HQ_PUBLISH_FILE_1" in works[0]["brief"] and "publish_command" in works[0]["brief"]
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    assert any("مسیر انتشار اینستاگرام" in s["what_fa"] for s in rep["steps"])
    assert rep["publishes"] == []

    # 2. the technical team registers it (connection.set): never a secret, never destructive
    base = {"company": co, "kind": "instagram", "accounts": ["@pro.chart", "@pro.chart.edu"],
            "via": "ig_hub", "server": {"company": igc, "name": "IG-Hub"},
            "read_command": "cat /srv/ig/daily.json"}  # fmt: skip
    cto = f"{igc}-TECH-MGR"
    r = await set_connection(
        client, cto, {**base, "publish_command": "dropdb prod && /srv/ig/bin/hq-publish"}
    )
    assert r.status_code == 422 and "publish_command" in r.json()["fields"], r.text
    r = await set_connection(
        client, cto, {**base, "publish_command": "ig publish --token abcdefabcdefabcdefabcdef"}
    )
    assert r.status_code == 422, r.text
    command = "/srv/ig/bin/hq-publish"
    r = await set_connection(client, cto, {**base, "publish_command": command})
    assert r.status_code == 200 and r.json()["config"]["publish_command"] == command, r.text
    ig_rn = await pair(client, hub, owner_session, ig, "IG-Hub")

    # 3. the tap: his word in the session is the seal (the owner's bearer, no step-up, no card)
    r = await tap(client, owner, order, {"output": output, "file_id": one})
    assert r.status_code == 422 and "pro.chart.edu" in r.json()["fields"]["account"], r.text
    body = {"output": output, "file_id": one, "account": "@pro.chart", "caption": "هفته‌ی طلا #طلا"}
    r = await tap(client, owner, order, {**body, "kind": "reel"})
    assert r.status_code == 422 and "kind" in r.json()["fields"], r.text  # a reel is a video
    cards = await su.fetchval("SELECT count(*) FROM cartable.decisions WHERE status = 'pending'")
    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    pub = r.json()
    assert pub["state"] == "publishing" and pub["kind"] == "post" and pub["account"] == "pro.chart"
    assert pub["file_name"] == "cover.png" and pub["output"] == output
    assert cards == await su.fetchval(
        "SELECT count(*) FROM cartable.decisions WHERE status = 'pending'"
    )
    # one tap, one post: the same file to the same account is not sent twice
    again = await tap(client, owner, order, body)
    assert again.status_code == 202 and again.json()["job"] == pub["job"]

    job = await take(client, ig_rn)
    assert job["id"] == pub["job"] and job["kind"] == "publish"
    a = job["args"]
    assert a["command"] == command and a["caption"] == "هفته‌ی طلا #طلا"
    assert a["meta"] == {"channel": "instagram", "kind": "post", "account": "pro.chart",
                         "company": co, "cover": False}  # fmt: skip
    [f] = a["files"]
    assert f["url"] == f"/api/v1/runners/jobs/{job['id']}/inputs/{one}" and f["name"] == "cover.png"
    got = await client.get(f["url"], headers=ig_rn["h"])
    assert got.status_code == 200 and got.content[:8] == b"\x89PNG\r\n\x1a\n"
    # only the file the tap named, only for that job's runner
    assert (
        await client.get(f"/api/v1/runners/jobs/{job['id']}/inputs/{two}", headers=ig_rn["h"])
    ).status_code == 404
    assert (await client.get(f["url"])).status_code in (401, 403)

    # 4. IG-Hub published it: the session says so, with the link
    r = await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result",
        json={"exit_code": 0, "summary_fa": "منتشر شد.",
              "data": {"external_id": "ig-17", "url": "https://www.instagram.com/p/abc/"}},
        headers=ig_rn["h"],
    )  # fmt: skip
    assert r.status_code == 200, r.text
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    [p] = rep["publishes"]
    assert p["state"] == "published" and p["url"] == "https://www.instagram.com/p/abc/"
    assert p["published_at"] and p["job"] == pub["job"]
    said = [s["what_fa"] for s in rep["steps"]]
    assert any("«تأیید و انتشار»" in x and "cover.png" in x for x in said), said
    assert any(x.startswith("منتشر شد: پست در @pro.chart") and "instagram.com" in x for x in said)
    acts = [
        r["action"]
        for r in await su.fetch(
            # (of this run's two companies: a test database that outlives a run sees the same
            # order ref again after a fresh start, and the audit trail is never deleted)
            "SELECT action FROM audit.entries WHERE target_ref = $1 AND action LIKE 'publish.%' "
            "AND company_id = ANY($2::uuid[])",
            order,
            [ig["id"], pc["id"]],
        )
    ]
    assert acts.count("publish.session") == 2 and "publish.session_done" in acts
    # a published file is not published again by a second tap
    again = await tap(client, owner, order, body)
    assert again.json()["state"] == "published" and again.json()["job"] == pub["job"]

    # the output's own page reads the same: its session, the accounts, its publishes
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert panel["order"] == order and panel["ready"] is True
    assert panel["accounts"] == ["pro.chart", "pro.chart.edu"]
    assert [x["job"] for x in panel["publishes"]] == [pub["job"]]

    # 5. a publish IG-Hub refused is said plainly, and the tap can be made again
    body2 = {"output": output, "file_id": two, "account": "pro.chart.edu", "kind": "story"}
    # (this one from the output's own page: the same tap)
    r = await client.post(
        f"/api/v1/deliverables/{output}/publish",
        headers={**owner, **idem()},
        json={k: v for k, v in body2.items() if k != "output"},
    )
    assert r.status_code == 202 and r.json()["state"] == "publishing", r.text
    job2 = await take(client, ig_rn)
    r = await client.post(
        f"/api/v1/runners/jobs/{job2['id']}/result",
        json={"exit_code": 1, "summary_fa": "حساب امروز به سقف انتشار رسیده است."},
        headers=ig_rn["h"],
    )
    assert r.status_code == 200, r.text
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    failed = next(p for p in rep["publishes"] if p["job"] == job2["id"])
    assert failed["state"] == "failed" and "سقف انتشار" in failed["note_fa"]
    assert any("انجام نشد" in s["what_fa"] and "سقف انتشار" in s["what_fa"] for s in rep["steps"])
    r = await tap(client, owner, order, body2)
    assert r.status_code == 202 and r.json()["job"] != job2["id"]  # a new try


async def test_only_a_file_of_the_session_and_never_past_the_kill_switch(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    pc, other = await new_company(), await new_company()
    made = await an_output(client, hub, owner, owner_session, su, pc["code"])
    theirs = await an_output(client, hub, owner, owner_session, su, other["code"])
    # another session's output, or a file that is not this output's
    r = await tap(client, owner, made["order"],
                  {"output": theirs["output"], "file_id": theirs["files"][0]})  # fmt: skip
    assert r.status_code == 404, r.text
    r = await tap(client, owner, made["order"],
                  {"output": made["output"], "file_id": theirs["files"][0]})  # fmt: skip
    assert r.status_code == 422 and "file_id" in r.json()["fields"], r.text
    # an agent's token is not the owner's word
    from .conftest import agent_headers

    r = await client.post(
        f"/api/v1/orders/{made['order']}/publish",
        headers={**(await agent_headers(f"{pc['code']}-CEO")), **idem()},
        json={"output": made["output"], "file_id": made["files"][0]},
    )
    assert r.status_code in (401, 403), r.text
    # the company's kill switch holds
    from hq_api.domain import control
    from hq_api.principal import Principal

    boss = Principal(kind="owner", code="owner", role="owner")
    async with hub.db.tx(await hub.companies.ids()) as tx:
        scope = await control.resolve_scope(tx, f"company:{pc['code']}")
        await control.set_kill_switch(tx, boss, scope, "engaged", "test")
    try:
        r = await tap(client, owner, made["order"],
                      {"output": made["output"], "file_id": made["files"][0]})  # fmt: skip
        assert r.status_code == 423, r.text
    finally:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            scope = await control.resolve_scope(tx, f"company:{pc['code']}")
            await control.set_kill_switch(tx, boss, scope, "released", "test")


async def test_a_reel_goes_out_with_its_cover_and_caption(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    """The owner's own order: «ویدیو و کاور و کپشن رو میبریم به شرکت IG». The reel is the job's
    first file and the cover he chose its second; a cover is an image of the same output and
    belongs to a reel only."""
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
    base = {"output": made["output"]}
    # a cover belongs to a reel, and is an image of this very output
    r = await tap(client, owner, made["order"], {**base, "file_id": other, "cover_file_id": cover})
    assert r.status_code == 422 and "cover_file_id" in r.json()["fields"], r.text
    r = await tap(client, owner, made["order"], {**base, "file_id": reel, "cover_file_id": reel})
    assert r.status_code == 422 and "cover_file_id" in r.json()["fields"], r.text
    r = await tap(
        client, owner, made["order"],
        {**base, "file_id": reel, "cover_file_id": cover, "caption": "سه سطح طلا. کامنت کن «۳»"},
    )  # fmt: skip
    assert r.status_code == 202, r.text
    pub = r.json()
    assert pub["kind"] == "reel" and pub["file_name"] == "reel.mp4"
    assert pub["cover_name"] == "cover.png" and pub["account"] == "pro.chart"
    job = await take(client, ig_rn)
    a = job["args"]
    assert [f["name"] for f in a["files"]] == ["reel.mp4", "cover.png"]
    assert a["files"][1]["role"] == "cover" and a["meta"]["cover"] is True
    assert a["meta"]["kind"] == "reel" and a["caption"].endswith("کامنت کن «۳»")
    for f in a["files"]:  # both come from the job's own route, with the runner's token
        got = await client.get(f["url"], headers=ig_rn["h"])
        assert got.status_code == 200, got.text
