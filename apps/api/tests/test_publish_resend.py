"""⟨2026-11-27⟩ A publication's job the runner never ran is sent again by itself.

The owner: automation heals itself and never loses a day's post. On 2026-11-27 IG-Hub's runner
restarted (06:18:54Z) while its long poll was still open on the hub; the hub never saw the hang-up
(Starlette's BaseHTTPMiddleware hid it), handed the bjtech reel's publish job to that dead poll at
06:19:04Z, and the job timed out at 06:36Z with no event: the reel was lost (2026-11-20 a story
the same way). Now the hang-up is seen (app.RequestContext) and a job that still never ran goes
again under the same IG-Hub key, up to RESEND_MAX times, never at night, then fails and is told.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from hq_api.app import RequestContext
from hq_api.domain import quiet_hours as QH
from hq_api.domain import session_publish as SPB
from hq_api.hub import Hub

from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w17_session_publish import an_output, tap
from .test_w19_publish_time import answer, connected


def a_job(state: str = "failed", code: str | None = "timed_out", **meta: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": uuid4(), "state": state, "error_code": code, "summary_fa": "کار در زمانش تمام نشد",
        "args": {"kind": "reel", "account": "a", "session": {"output": "O-1", "file_id": "f"},
                 "meta": {"key": "k", **meta}},
        "result": None, "created_at": now - timedelta(minutes=20), "finished_at": now,
    }  # fmt: skip


def test_a_job_that_never_ran_stands_till_its_tries_are_used_up() -> None:
    assert SPB._state(a_job()) == "publishing"
    later = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    assert SPB._state(a_job(scheduled_at=later)) == "scheduled"
    assert SPB._state(a_job(resend=SPB.RESEND_MAX - 1)) == "publishing"
    assert SPB._state(a_job(resend=SPB.RESEND_MAX)) == "failed"
    assert SPB._state(a_job(code="not_started")) == "publishing"
    # a real refusal, an old failure, a Trial Reel copy, a rule: failed as before
    assert SPB._state(a_job(code="exit_nonzero")) == "failed"
    old = a_job()
    old["finished_at"] = datetime.now(UTC) - SPB.RESEND_WITHIN - timedelta(minutes=1)
    assert SPB._state(old) == "failed"
    trial = a_job()
    trial["args"]["trial"] = {"n": 1}
    assert SPB._state(trial) == "failed"
    rule = a_job()
    rule["args"]["rule_for"] = {"job": "x"}
    assert SPB._state(rule) == "failed"
    # a question the runner never answered is asked again (its own path, unchanged)
    assert SPB._state(a_job(check="pub:1")) == "publishing"
    assert SPB._chained({"resend": 1}) and not SPB._chained({"key": "k"})


async def test_the_request_layer_passes_a_hang_up_on() -> None:
    """A runner's long poll whose runner went away is seen as gone (it is never handed a job)."""
    seen: list[bool] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(await Request(scope, receive).is_disconnected())
        await Response(status_code=204)(scope, receive, send)

    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    settings = SimpleNamespace(max_file_bytes=1 << 20, max_body_bytes=1 << 20)
    app = SimpleNamespace(state=SimpleNamespace(hub=SimpleNamespace(settings=settings)))
    scope = {"type": "http", "method": "GET", "path": "/api/v1/runners/jobs/next",
             "query_string": b"", "headers": [], "app": app}  # fmt: skip
    await RequestContext(inner)(scope, receive, send)
    assert seen == [True]
    headers = dict(sent[0]["headers"])
    assert sent[0]["status"] == 204 and headers[b"x-request-id"] and headers[b"cache-control"]


async def test_a_publish_job_that_never_ran_goes_again_with_its_key_then_fails_and_is_told(
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
    r = await tap(client, owner, order,
                  {"output": output, "file_id": reel, "cover_file_id": cover, "caption": "طلا"})  # fmt: skip
    assert r.status_code == 202, r.text
    first = await take(client, rn)
    key = first["args"]["meta"]["key"]

    async def never_ran(job_id: str, at: datetime) -> None:
        """What the sweep makes of a job handed to a poll nobody read."""
        await su.execute(
            "UPDATE infra.server_jobs SET state = 'failed', error_code = 'timed_out', "
            "summary_fa = 'کار در زمانش تمام نشد', finished_at = $2 WHERE id = $1",
            UUID(job_id), at,
        )  # fmt: skip
        await SPB.after_job(hub, UUID(job_id))

    async def sent_again(now: datetime) -> list[Any]:
        await SPB.follow_up(hub, now=now)
        return list(
            await su.fetch(
                "SELECT id, args FROM infra.server_jobs WHERE kind = 'publish' "
                "AND args -> 'session' ->> 'output' = $1 AND args -> 'meta' ? 'resend' "
                "ORDER BY created_at",
                output,
            )
        )

    async def row() -> Any:
        return await su.fetchrow(
            "SELECT state, cardinality(chain) AS n FROM media.publications WHERE chain[1] = $1",
            UUID(first["id"]),
        )

    t = datetime.now(UTC)
    await never_ran(first["id"], t)
    # it stands as publishing: the session, the panel and the publication's row
    assert (await row())["state"] == "publishing"
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert panel["publishes"][0]["state"] == "publishing"
    # a tap meanwhile sends nothing new (the publication is on its way)
    again = await tap(client, owner, order, {"output": output, "file_id": reel, "caption": "طلا"})
    assert again.status_code == 202 and again.json()["job"] == first["id"], again.text

    assert await sent_again(t + timedelta(minutes=1)) == []  # its wait is not over
    tries = await sent_again(t + timedelta(minutes=3))
    assert len(tries) == 1
    job = await take(client, rn)
    assert job["id"] == str(tries[0]["id"])
    meta = job["args"]["meta"]
    assert meta["key"] == key and meta["resend"] == 1  # the same IG-Hub key: never a twin

    def files(x: dict[str, Any]) -> list[tuple[str, str]]:
        return [(f["file_id"], f["name"]) for f in x["args"]["files"]]

    assert files(job) == files(first) and len(files(job)) == 2  # the reel and its cover
    assert job["args"]["caption"] == first["args"]["caption"]
    assert await sent_again(t + timedelta(minutes=30)) == tries  # one at a time
    assert (await row())["n"] == 2 and (await row())["state"] == "publishing"
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    assert any("دوباره فرستاده شد (1 از 3)" in s["what_fa"] for s in rep["steps"])

    # the second try never ran either, the third neither: each goes again after its wait
    for n in (2, 3):
        t = datetime.now(UTC)
        await never_ran(job["id"], t)
        assert (await row())["state"] == "publishing"
        wait = SPB.RESEND_AFTER[n - 1]
        assert len(await sent_again(t + wait - timedelta(seconds=30))) == n - 1
        assert len(await sent_again(t + wait + timedelta(seconds=30))) == n
        job = await take(client, rn)
        assert job["args"]["meta"]["resend"] == n and job["args"]["meta"]["key"] == key

    # the last one fails too: the publication is failed and the owner is told
    t = datetime.now(UTC)
    await never_ran(job["id"], t)
    assert len(await sent_again(t + timedelta(hours=1))) == SPB.RESEND_MAX
    assert (await row())["state"] == "failed"
    told = await su.fetch(
        "SELECT title_fa, link_kind FROM notify.notifications WHERE link_ref = $1 "
        "AND source_code = 'publish'",
        order,
    )
    assert [(x["title_fa"], x["link_kind"]) for x in told] == [
        ("انتشار خودکار ریلز پس از 4 بار فرستادن انجام نشد", "order")
    ]
    panel = (await client.get(f"/api/v1/deliverables/{output}/publish", headers=owner)).json()
    assert panel["publishes"][0]["state"] == "failed"


async def test_a_job_that_never_ran_is_sent_again_at_night_for_the_morning_and_heard_once_out(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the owner's night itself (conftest leaves it out for every other test)
    monkeypatch.setattr(
        QH, "is_quiet", lambda at: QH.QUIET_FROM <= at.astimezone(QH.TEHRAN).time() < QH.OPEN_AT
    )
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    r = await tap(client, owner, order,
                  {"output": output, "file_id": reel, "cover_file_id": cover, "caption": "طلا"})  # fmt: skip
    assert r.status_code == 202, r.text
    first = await take(client, rn)
    # it failed at 01:00 Tehran (its runner gone): the resend is set for the morning, not now
    night = datetime.now(UTC).astimezone(QH.TEHRAN).replace(hour=1, minute=0, second=0,
                                                           microsecond=0).astimezone(UTC)  # fmt: skip
    if night < datetime.now(UTC) - timedelta(hours=2):
        night += timedelta(days=1)
    await su.execute(
        "UPDATE infra.server_jobs SET state = 'failed', error_code = 'timed_out', "
        "finished_at = $2 WHERE id = $1",
        UUID(first["id"]), night,
    )  # fmt: skip
    await SPB.after_job(hub, UUID(first["id"]))
    await SPB.follow_up(hub, now=night + timedelta(minutes=3))
    job = await take(client, rn)
    assert job["args"]["session"]["output"] == output and job["args"]["meta"]["resend"] == 1
    at = datetime.fromisoformat(job["args"]["meta"]["scheduled_at"])
    assert at == QH.out_of_night(night + timedelta(minutes=3)) and not QH.is_quiet(at)
    # IG-Hub took it this time (the same key): out, said once, the row published
    await answer(client, rn, job["id"],
                 {"external_id": "1790", "url": "https://www.instagram.com/reel/Cy1/"})  # fmt: skip
    rep = (await client.get(f"/api/v1/orders/{order}/report", headers=owner)).json()
    said = [s["what_fa"] for s in rep["steps"]]
    assert sum(1 for x in said if x.startswith("منتشر شد: ریلز در @pro.chart")) == 1, said
    [p] = rep["publishes"]
    assert p["state"] == "published" and p["url"] == "https://www.instagram.com/reel/Cy1/"
    state = await su.fetchval(
        "SELECT state FROM media.publications WHERE chain[1] = $1", UUID(first["id"])
    )
    assert state == "published"
    await SPB.follow_up(hub, now=night + timedelta(hours=1))
    assert not await su.fetchval(
        "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish' AND state = 'queued' "
        "AND args -> 'session' ->> 'output' = $1",
        output,
    )
