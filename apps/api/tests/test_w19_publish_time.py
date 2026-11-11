"""⟨2026-11-10⟩ The time, the comment rule and the carousel of a publish (contract §46).

The owner: «هر بار شاید یک کامنت باشد. … ساعت را باید هاب تنظیم بکند … باز هم از داخل خود سرور
IG-Hub نگاه کنی تنظیم پست با ساعت دارد.» The hub sets the time and IG-Hub holds the post till
then; the word viewers comment (it differs with every reel) goes with the post and becomes its
own rule there; a publication IG-Hub still holds is asked about again until it is out.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest

from hq_api.domain import session_publish as SPB
from hq_api.hub import Hub

from .conftest import idem
from .test_p17_runners import pair, take
from .test_p21_groups import TEHRAN
from .test_p21_routing_orders import auto_hiring  # noqa: F401 - the fixture
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_p23_talk import talk  # noqa: F401 - the fixture
from .test_w11_connections import set_connection
from .test_w17_session_publish import an_output, tap
from .test_w18_standing_publish import a_day, a_group, args_of, jobs_of

COMMAND = "python3 /srv/ig-hub/deploy/hq_publish.py"


async def connected(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], ig: Any, co: str
) -> dict[str, Any]:
    r = await set_connection(
        client,
        f"{ig['code']}-TECH-MGR",
        {"company": co, "kind": "instagram", "accounts": ["@pro.chart"], "via": "ig_hub",
         "server": {"company": ig["code"], "name": "IG-Hub"},
         "read_command": "cat /srv/ig/daily.json", "publish_command": COMMAND},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    return await pair(client, hub, owner_session, ig, "IG-Hub")


async def answer(
    client: httpx.AsyncClient, rn: dict[str, Any], job: str, data: dict[str, Any] | None,
    exit_code: int = 0, why: str = "تمام شد.",
) -> None:  # fmt: skip
    r = await client.post(
        f"/api/v1/runners/jobs/{job}/result",
        json={"exit_code": exit_code, "summary_fa": why, **({"data": data} if data else {})},
        headers=rn["h"],
    )
    assert r.status_code == 200, r.text


async def asked(hub: Hub, su: Any, output: str, now: datetime | None = None) -> int:
    """Runs the follow-up (the hub's, for every company) and counts the questions it has made
    about this output so far."""
    await SPB.follow_up(hub, now=now)
    return int(
        await su.fetchval(
            "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish' "
            "AND args -> 'meta' ? 'check' AND args -> 'session' ->> 'output' = $1",
            output,
        )
    )


def test_the_packages_comment_and_the_hour_are_read_by_code() -> None:
    text = "کلمه: ۷، هفت\nreply: این هم لینک آموزش\nلینک: https://pro-chart.com/learn\npublic: دایرکت را ببین"
    assert SPB.parse_comment(text) == {
        "keywords": ["۷", "هفت"],
        "reply": "این هم لینک آموزش",
        "link": "https://pro-chart.com/learn",
        "public_replies": ["دایرکت را ببین"],
    }
    assert SPB.parse_comment("keyword: code\nreply: hi\nlink: http://plain.test") == {
        "keywords": ["code"],
        "reply": "hi",
    }
    # a word without its reply (or a reply without its word) is no rule
    assert SPB.parse_comment("keyword: code") is None and SPB.parse_comment("reply: hi") is None
    assert SPB.parse_comment(None) is None and SPB.clean_comment("x") is None
    assert SPB.clean_comment({"keyword": " کد ", "reply_text": "سلام"}) == {
        "keywords": ["کد"],
        "reply": "سلام",
    }
    # today's hour while it is ahead, in the owner's zone; past it: now
    noon = datetime(2026, 11, 10, 8, 30, tzinfo=UTC)  # 12:00 in Tehran
    assert SPB.at_today("18:30", "Asia/Tehran", noon) == datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
    assert SPB.at_today("09:00", "Asia/Tehran", noon) is None
    assert SPB.at_today("12:01", "Asia/Tehran", noon) is None  # that near is now
    assert SPB.at_today("25:00", "Asia/Tehran", noon) is None and SPB.at_today(None, "UTC") is None
    assert SPB.rule_of({"mode": "auto", "at": "18:30"})["at"] == "18:30"
    assert SPB.rule_of({"mode": "auto", "at": "soon"})["at"] is None
    told = SPB.brief_block({"mode": "auto", "account": "pro.chart", "at": "18:30"})
    assert "at 18:30 (the owner's time)" in told and "comment.txt" in told
    assert "keyword: <that word>" in told and "cover.jpg" in told


async def test_a_reel_is_set_for_a_time_with_its_own_comment_rule_and_followed_to_the_end(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    later = datetime.now(UTC) + timedelta(hours=5)
    body = {
        "output": output, "file_id": reel, "cover_file_id": cover, "caption": "سه سطح طلا",
        "scheduled_at": later.isoformat(),
        "comment": {"keywords": ["۷"], "reply": "این هم لینک:", "link": "https://pro-chart.com/x"},
        "first_comment": "#طلا",
    }  # fmt: skip
    # a rule needs its word and its reply; a time needs its zone
    bad = await tap(client, owner, order, {**body, "comment": {"keywords": [], "reply": "x"}})
    assert bad.status_code == 422 and "comment" in bad.json()["fields"], bad.text
    bad = await tap(client, owner, order, {**body, "scheduled_at": "2027-01-01T10:00:00"})
    assert bad.status_code == 422 and "scheduled_at" in bad.json()["fields"], bad.text
    bad = await tap(client, owner, order, {**body, "file_ids": [cover]})
    assert bad.status_code == 422 and "file_ids" in bad.json()["fields"], bad.text

    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    pub = r.json()
    assert pub["state"] == "publishing" and pub["comment"] == "۷"
    assert pub["scheduled_at"] and pub["cover_name"] == "cover.png"
    job = await take(client, rn)
    meta = job["args"]["meta"]
    assert meta["scheduled_at"] == later.isoformat() and meta["first_comment"] == "#طلا"
    assert meta["comment"] == {
        "keywords": ["۷"], "reply": "این هم لینک:", "link": "https://pro-chart.com/x"}  # fmt: skip
    assert [f.get("role") for f in job["args"]["files"]] == [None, "cover"]

    # IG-Hub holds it for its time: the session says «زمان‌بندی شد», nothing says «منتشر شد»
    await answer(client, rn, job["id"], {"external_id": "pub:41", "url": None})
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    [p] = rep["publishes"]
    assert p["state"] == "scheduled" and p["url"] is None and p["published_at"] is None
    said = [s["what_fa"] for s in rep["steps"]]
    assert any(x.startswith("زمان‌بندی شد: ریلز در @pro.chart، ساعت ") for x in said), said
    assert not any(x.startswith("منتشر شد") for x in said)
    # a second tap is the same publication, never a second post
    again = await tap(client, owner, order, body)
    assert again.status_code == 202 and again.json()["state"] == "scheduled"
    assert again.json()["job"] == pub["job"]

    # nothing is asked before its time; 90 seconds after it, IG-Hub is asked once
    assert await asked(hub, su, output) == 0
    after = later + timedelta(seconds=100)
    assert await asked(hub, su, output, after) == 1
    assert await asked(hub, su, output, after) == 1  # the question is on its way
    check = await take(client, rn)
    assert check["args"]["files"] == [] and check["args"]["meta"]["check"] == "pub:41"
    assert check["args"]["command"] == COMMAND and check["args"]["caption"] == ""

    # the runner never answered that question: it is asked again, and nothing is called failed
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'failed', error_code = 'timed_out', "
        "finished_at = $2 WHERE id = $1",
        UUID(check["id"]),
        after,
    )
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert panel["publishes"][0]["state"] in ("scheduled", "publishing")
    assert panel["publishes"][0]["file_name"] == "reel.mp4"
    assert await asked(hub, su, output, after + timedelta(minutes=4)) == 2
    check = await take(client, rn)

    # Meta is still preparing it, then it is out: only now the session says «منتشر شد»
    await answer(client, rn, check["id"], {"external_id": "pub:41", "url": None})
    done_at = later + timedelta(minutes=10)
    assert await asked(hub, su, output, done_at) == 3
    check = await take(client, rn)
    await answer(
        client, rn, check["id"],
        {"external_id": "1789", "url": "https://www.instagram.com/reel/Cx9/"},
    )  # fmt: skip
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    p = rep["publishes"][0]
    assert p["state"] == "published" and p["url"] == "https://www.instagram.com/reel/Cx9/"
    assert p["cover_name"] == "cover.png" and p["comment"] == "۷"
    said = [s["what_fa"] for s in rep["steps"]]
    assert sum(1 for x in said if x.startswith("زمان‌بندی شد")) == 1
    assert sum(1 for x in said if x.startswith("منتشر شد: ریلز در @pro.chart")) == 1
    assert await asked(hub, su, output, done_at + timedelta(hours=1)) == 3


async def test_a_carousel_goes_out_whole_and_a_refusal_at_its_time_can_be_tried_again(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(
        client, hub, owner, owner_session, su, co, ("one.png", "two.png", "three.png")
    )
    output, (one, two, three) = made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)

    async def press(body: dict[str, Any]) -> httpx.Response:
        return await client.post(
            f"/api/v1/deliverables/{output}/publish", headers={**owner, **idem()}, json=body
        )

    # a carousel is this file and at least one more of the same output
    bad = await press({"file_id": one, "kind": "carousel"})
    assert bad.status_code == 422 and "file_ids" in bad.json()["fields"], bad.text
    stranger = "00000000-0000-4000-8000-000000000001"
    bad = await press({"file_id": one, "kind": "carousel", "file_ids": [stranger]})
    assert bad.status_code == 422, bad.text
    later = datetime.now(UTC) + timedelta(hours=2)
    r = await press({"file_id": one, "kind": "carousel", "file_ids": [three, two],
                     "caption": "سه نما", "scheduled_at": later.isoformat()})  # fmt: skip
    assert r.status_code == 202 and r.json()["kind"] == "carousel", r.text
    assert r.json()["files"] == 3
    job = await take(client, rn)
    # ⟨§52⟩ each picture goes out as a JPEG, in the order he gave
    assert [f["name"] for f in job["args"]["files"]] == ["one.jpg", "three.jpg", "two.jpg"]
    assert job["args"]["meta"]["kind"] == "carousel" and job["args"]["meta"]["cover"] is False
    await answer(client, rn, job["id"], {"external_id": "pub:8", "url": None})

    # at its time Instagram refuses it: said plainly, and a tap is a new try
    assert await asked(hub, su, output, later + timedelta(minutes=2)) == 1
    check = await take(client, rn)
    await answer(client, rn, check["id"], None, exit_code=1, why="اینستاگرام نپذیرفت: نسبت تصویر")
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert panel["publishes"][0]["state"] == "failed" and panel["publishes"][0]["files"] == 3
    assert await asked(hub, su, output, later + timedelta(minutes=30)) == 1
    r = await press({"file_id": one, "kind": "carousel", "file_ids": [two, three]})
    assert r.status_code == 202 and r.json()["state"] == "publishing", r.text
    assert r.json()["scheduled_at"] is None
    retry = await take(client, rn)
    assert retry["id"] == r.json()["job"] and "scheduled_at" not in retry["args"]["meta"]
    # a time that near is now
    soon = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    r = await press({"file_id": two, "scheduled_at": soon})
    assert r.status_code == 202 and r.json()["scheduled_at"] is None, r.text


async def test_a_working_groups_package_goes_out_at_its_hour_with_the_days_own_comment_rule(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    auto_hiring: None,  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = owner_session["headers"]
    g = await a_group(client, hub, owner_session, su, new_company, monkeypatch,
                      {"publish": {"mode": "auto", "at": "23:58"}})  # fmt: skip
    co, key = g["co"], g["key"]
    assert g["sealed"]["members"][0]["publish"]["at"] == "23:58"
    r = await client.put(f"/api/v1/groups/{key}/members/{co}/publish", headers=owner,
                         json={"mode": "auto", "at": "soon"})  # fmt: skip
    assert r.status_code == 422 and "at" in r.json()["fields"], r.text
    # today's word and link, as the routine's work wrote them beside the video
    words = "keyword: ۱۲\nreply: این هم لینک امروز\nlink: https://pro-chart.com/today"
    day = datetime.now(TEHRAN).date() + timedelta(days=1)
    made = await a_day(
        client, hub, su, g, day, ("reel.mp4", "cover.png", "caption.txt", "comment.txt"),
        texts={"comment.txt": words},
    )  # fmt: skip
    assert "at 23:58 (the owner's time)" in made["brief"] and "comment.txt" in made["brief"]
    [job] = await jobs_of(su, made["run"])
    meta = args_of(job)["meta"]
    assert meta["comment"] == {
        "keywords": ["۱۲"], "reply": "این هم لینک امروز", "link": "https://pro-chart.com/today"}  # fmt: skip
    # its hour today while that is still ahead (IG-Hub holds it till then); past it: now
    tz = await su.fetchval("SELECT timezone FROM owner.settings WHERE id = 1") or "Asia/Tehran"
    hour = SPB.at_today("23:58", tz)
    if hour is not None:
        assert abs((datetime.fromisoformat(meta["scheduled_at"]) - hour).total_seconds()) < 90
    else:
        assert "scheduled_at" not in meta
    panel = (
        await client.get(f"/api/v1/deliverables/{made['output']}/publish", headers=owner)
    ).json()
    assert panel["comment"]["keywords"] == ["۱۲"] and panel["comment"]["link"].endswith("/today")
    assert panel["publishes"][0]["comment"] == "۱۲" and panel["publishes"][0]["auto"] is True
    # IG-Hub holds it: the run says when, and nobody is told anything
    await answer(client, g["ig_rn"], str(job["id"]), {"external_id": "pub:3", "url": None})
    note = await su.fetchval("SELECT note_fa FROM growth.routine_runs WHERE id = $1", made["run"])
    if hour is not None:
        assert note.startswith("زمان‌بندی شد: ریلز در @pro.chart، ساعت ")
    assert await su.fetchval(
        "SELECT count(*) FROM notify.notifications WHERE link_ref = $1 AND source_code = 'publish'",
        made["output"],
    ) == 0  # fmt: skip


async def test_a_publication_sent_for_now_is_followed_for_six_hours_from_its_first_answer(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    body = {"output": output, "file_id": reel, "cover_file_id": cover, "caption": "سه سطح طلا"}
    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    job = await take(client, rn)
    # Meta is still preparing it, and it never gets a link
    await answer(client, rn, job["id"], {"external_id": "pub:77", "url": None})
    t0 = datetime.now(UTC)
    assert await asked(hub, su, output, t0 + timedelta(minutes=2)) == 1
    check = await take(client, rn)
    first = check["args"]["meta"]["first_at"]
    await answer(client, rn, check["id"], {"external_id": "pub:77", "url": None})

    async def answered_at(job_id: str, at: datetime) -> None:
        await su.execute(
            "UPDATE infra.server_jobs SET finished_at = $2 WHERE id = $1", UUID(job_id), at
        )

    # five hours on, it is still asked about, every 3 minutes
    await answered_at(check["id"], t0 + timedelta(hours=5))
    assert await asked(hub, su, output, t0 + timedelta(hours=5, minutes=4)) == 2
    check = await take(client, rn)
    assert check["args"]["meta"]["first_at"] == first  # the window never moves
    await answer(client, rn, check["id"], {"external_id": "pub:77", "url": None})
    # six hours after its first answer it is no longer asked about, however recent the last one
    await answered_at(check["id"], t0 + timedelta(hours=6, minutes=1))
    assert await asked(hub, su, output, t0 + timedelta(hours=6, minutes=5)) == 2


async def test_a_post_set_far_ahead_is_followed_at_its_time_and_a_held_question_is_asked_again(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    later = datetime.now(UTC) + timedelta(hours=1)
    body = {"output": output, "file_id": reel, "cover_file_id": cover, "caption": "سه سطح طلا",
            "scheduled_at": later.isoformat()}  # fmt: skip
    r = await tap(client, owner, order, body)
    assert r.status_code == 202, r.text
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:88", "url": None})
    # it was sent nine days before its time: it is still asked about when that comes
    await su.execute(
        "UPDATE infra.server_jobs SET created_at = now() - interval '9 days' WHERE id = $1",
        UUID(job["id"]),
    )
    after = later + timedelta(seconds=100)
    assert await asked(hub, su, output, after) == 1
    check = await take(client, rn)
    # a kill switch took the question back before it was answered: the publication IG-Hub holds
    # still stands, and it is asked about again
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'cancelled', error_code = 'company_locked', "
        "finished_at = $2 WHERE id = $1",
        UUID(check["id"]),
        after,
    )
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert panel["publishes"][0]["state"] in ("scheduled", "publishing"), panel["publishes"]
    assert await asked(hub, su, output, after + timedelta(minutes=4)) == 2
