"""Prompt 18 (contract §27 ⟨1.9⟩): the player of an order, the council of
models and the hub's speech to text. Substitutes answer through the fake
dispatcher body and a fake egress; the stt service is a fake; nothing reaches
ChatGPT, Gemini, DeepSeek or a real whisper."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api import workflows_client
from hq_api.domain import players as PL
from hq_api.domain import substitutes as S
from hq_api.domain import work as W
from hq_api.hub import Hub
from hq_api.schemas import FileRef
from hq_api.worker import media as M

from .conftest import agent_headers, idem
from .test_files_media import audio, media_acts, upload  # noqa: F401 - a fixture here too
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import FakeEgress, bench, claim, done, per_day, png

pytestmark = pytest.mark.usefixtures("relay")


async def order(
    client: httpx.AsyncClient, owner: dict[str, str], co: str, **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/work",
        headers={**owner, **idem()},
        json={"company": co, "title": extra.pop("title", "تحلیل بازار"),
              "brief": extra.pop("brief", "بازار آموزش آنلاین را در سه بند بررسی کن."), **extra},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return dict(r.json())


async def work_run(su: Any, work_id: str) -> Any:
    return await su.fetchrow(
        "SELECT * FROM agents.runs WHERE work_id = $1 ORDER BY queued_at DESC LIMIT 1",
        uuid.UUID(work_id),
    )


async def events_of(su: Any, work_id: str) -> list[str]:
    return [
        r["kind"]
        for r in await su.fetch(
            "SELECT kind FROM work.work_events WHERE work_id = $1 ORDER BY id", uuid.UUID(work_id)
        )
    ]


async def council(client: httpx.AsyncClient, owner: dict[str, str], work_id: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/work/{work_id}/council", headers=owner)
    assert r.status_code == 200, r.text
    return dict(r.json())


def by_player(c: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["player"]: m for m in c["members"]}


# ------------------------------------------------------------ voice orders --
@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("این گزارش را با جی‌پی‌تی بنویس", ("gpt", None)),
        ("با جی پی تی خلاصه کن", ("gpt", None)),
        ("با چت‌جی‌پی‌تی یک ایمیل بنویس", ("gpt", None)),
        ("متن تبلیغ را با جمنای آماده کن", ("gemini", None)),
        ("با دیپ‌سیک جستجو کن", ("deepseek", None)),
        ("با کلود بازبینی کن", ("claude", None)),
        ("این تصمیم را با شورا بررسی کن", (None, "council")),
        ("شورای مدل‌ها درباره‌ی قیمت نظر بدهد", (None, "council")),
        ("گزارش فروش هفته را آماده کن", (None, None)),
        ("", (None, None)),
    ],
)
def test_an_order_names_its_player_or_the_council_in_words(
    text: str, want: tuple[str | None, str | None]
) -> None:
    assert PL.from_voice(text) == want


def test_a_file_carries_its_transcript_by_its_contract_name() -> None:
    f = FileRef.model_validate(
        {"id": str(uuid.uuid4()), "kind": "audio", "mime": "audio/ogg", "size": 10,
         "sha256": "0" * 64, "name": "v.ogg", "transcript": "سلام"}
    )  # fmt: skip
    assert f.transcript_fa == "سلام"
    assert FileRef.model_validate(
        {"id": str(uuid.uuid4()), "kind": "image", "mime": "image/png", "size": 1, "sha256": "0" * 64,
         "name": "x"}
    ).transcript_fa is None  # fmt: skip


# ------------------------------------------------------------------ player --
async def test_a_named_player_does_the_work_and_its_answer_is_labelled_with_it(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        w = await order(client, owner, co, player="gpt")
        assert (w["player"], w["mode"], w["player_fallback"]) == ("gpt", "single", False)
        run = await work_run(su, w["id"])
        c = await agents.runner.claim(str(run["id"]))
        # The run hands the brief to the player's seat; no model call of its own.
        assert (c.state, c.final, c.code) == ("final", "done", "player_call")
        assert await su.fetchval("SELECT steps FROM agents.runs WHERE id = $1", run["id"]) == 0
        job = (await claim(client))["job"]
        assert job["model"] == "gpt-5.3" and "تحلیل بازار" in job["input_md"]
        call = await su.fetchrow("SELECT * FROM substitutes.calls WHERE id = $1::uuid", job["id"])
        assert (call["purpose_kind"], call["purpose_ref"], call["caller_code"]) == (
            "work", w["ref"], "players",
        )  # fmt: skip
        # A retried claim of a later run while the call is queued does not call twice.
        ok = await done(client, job["id"], ok=True, text_md="۱. رشد بالا\n۲. رقابت زیاد\n۳. فرصت",
                        usage={"input_tokens": 30, "output_tokens": 20, "estimated": False})  # fmt: skip
        assert ok.status_code == 200 and ok.json()["state"] == "done", ok.text
    got = (await client.get(f"/api/v1/work/{w['id']}", headers=owner)).json()
    assert got["status"] == "delivered"
    dl = await su.fetchrow(
        "SELECT produced_with, body, producer_id FROM cartable.deliverables WHERE work_id = $1",
        uuid.UUID(w["id"]),
    )
    pw = json.loads(dl["produced_with"])
    assert pw["player"] == "gpt" and pw["label_fa"] == "انجام‌شده با ChatGPT"
    assert pw["source"]["player"] == "gpt" and pw["substitute_call"] == job["id"]
    assert dl["body"].startswith("۱. رشد بالا")
    assert {"player_call", "delivered"} <= set(await events_of(su, w["id"]))


async def test_an_unavailable_player_waits_then_falls_back_to_auto_with_a_notice(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    agents: Any,
    wk: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    whub = wk["hub"]  # the worker's Maintenance sweeps (its role queues the runs)
    co = (await new_company())["code"]
    async with bench(su, hub):  # nobody signed in
        w = await order(client, owner, co, player="deepseek")
        run = await work_run(su, w["id"])
        c = await agents.runner.claim(str(run["id"]))
        assert (c.final, c.code) == ("refused", "player_waiting")
        row = await su.fetchrow(
            "SELECT player_wait_since, player_tried_at FROM work.work WHERE id = $1",
            uuid.UUID(w["id"]),
        )
        assert row["player_wait_since"] is not None and row["player_tried_at"] is not None
        # Within the 30 minutes: tried again every few minutes (a new run).
        async with whub.db.tx(await whub.companies.ids()) as tx:
            await PL.sweep(tx, whub, datetime.now(UTC) + timedelta(minutes=6))
        retry = await work_run(su, w["id"])
        assert retry["reason"] == "player_retry" and retry["state"] == "queued"
        c2 = await agents.runner.claim(str(retry["id"]))
        assert c2.code == "player_waiting"
        assert await su.fetchval(
            "SELECT player_fallback_at FROM work.work WHERE id = $1", uuid.UUID(w["id"])
        ) is None  # fmt: skip
        # After 30 minutes: auto, a notification and a work event say so.
        async with whub.db.tx(await whub.companies.ids()) as tx:
            await PL.sweep(tx, whub, datetime.now(UTC) + timedelta(minutes=31))
    got = (await client.get(f"/api/v1/work/{w['id']}", headers=owner)).json()
    assert got["player"] == "deepseek" and got["player_fallback"] is True
    assert "player_fallback" in await events_of(su, w["id"])
    note = await su.fetchrow(
        "SELECT title_fa, link_kind FROM notify.notifications WHERE link_ref = $1 AND source_code = 'players'",
        w["ref"],
    )
    assert note is not None and "DeepSeek" in note["title_fa"] and note["link_kind"] == "work"
    stream = await su.fetchval(
        """SELECT count(*) FROM core.outbox WHERE subject LIKE '%.work.updated' AND payload->>'ref' = $1
             AND payload->'data' ? 'player_fallback'""",
        w["ref"],
    )
    assert stream >= 1
    # The assignee's Claude run picks it up now.
    back = await work_run(su, w["id"])
    assert back["reason"] == "player_fallback"
    assert (await agents.runner.claim(str(back["id"]))).state == "running"
    await agents.runner.finish(str(back["id"]), "done", None)


async def test_children_inherit_the_player_but_oversight_stays_on_claude(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    holding = await hub.companies.holding()
    staff = {
        r["kind"]: r["code"]
        for r in await su.fetch(
            """SELECT DISTINCT ON (kind) kind, code FROM core.employees
               WHERE company_id = $1 AND kind IN ('manager', 'inspector') AND status = 'active'
               ORDER BY kind, code""",
            holding.id,
        )
    }
    made: list[Any] = []
    async with hub.db.tx(await hub.companies.ids()) as tx:

        async def make(**kw: Any) -> dict[str, Any]:
            row = await W.create(tx, PL.SERVICE, company_id=holding.id, company_code=holding.code,
                                 brief="", kind="one_off", priority="P3", **kw)  # fmt: skip
            made.append(row["id"])
            return await W.load(tx, row["id"])

        parent = await make(title="کار مادر", assignee_code=staff["manager"], player="gemini")
        child = await make(title="بخش اول", parent=parent, assignee_code=staff["manager"])
        assert (child["player"], child["mode"]) == ("gemini", "single")
        # An oversight role's judgement is never handed to a substitute.
        qc = await make(title="بازرسی", parent=parent, assignee_code=staff["inspector"])
        assert (qc["player"], qc["mode"]) == ("auto", "single")
        await tx.exec(
            "UPDATE work.work SET player_fallback_at = now() WHERE id = :id", id=parent["id"]
        )
        fell = await W.load(tx, parent["id"])
        later = await make(title="بخش دوم", parent=fell, assignee_code=staff["manager"])
        assert later["player"] == "auto"  # the parent already fell back
    await su.execute(
        """UPDATE agents.runs SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           WHERE work_id = ANY($1::uuid[]) AND state = 'queued'""",
        made,
    )
    await su.execute("UPDATE work.work SET status = 'cancelled' WHERE id = ANY($1::uuid[])", made)
    # The owner changes the player: the wait and the fallback start afresh.
    co = (await new_company())["code"]
    w2 = await order(client, owner, co, player="gpt")
    await su.execute(
        "UPDATE work.work SET player_fallback_at = now() WHERE id = $1", uuid.UUID(w2["id"])
    )
    fresh = (await client.get(f"/api/v1/work/{w2['id']}", headers=owner)).json()
    assert fresh["player_fallback"] is True
    r = await client.patch(
        f"/api/v1/work/{w2['id']}",
        headers={**owner, "If-Match": str(fresh["version"])},
        json={"player": "claude"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["player"], r.json()["player_fallback"]) == ("claude", False)
    assert (await client.get(f"/api/v1/work/{w2['id']}/council", headers=owner)).status_code == 404


# ----------------------------------------------------------------- council --
async def test_a_council_asks_every_ready_player_and_claude_writes_the_synthesis(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, cli=("gpt",), web=("deepseek",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        await per_day(su, "deepseek", "third_opinion", 0)  # its cap is spent
        w = await order(client, owner, co, mode="council", title="قیمت دوره")
        assert w["mode"] == "council"
        c = await council(client, owner, w["id"])
        m = by_player(c)
        assert c["state"] == "running" and c["synthesis_ref"] is None
        assert set(m) == {"claude", "gpt", "gemini", "deepseek"}
        assert m["gpt"]["state"] == "queued" and m["gpt"]["model"] == "gpt-5.3"
        assert (m["deepseek"]["state"], m["deepseek"]["reason_code"]) == ("skipped", "per_day")
        assert m["gemini"]["state"] == "skipped" and m["gemini"]["reason"]
        job = (await claim(client))["job"]
        assert "قیمت دوره" in job["input_md"]
        await done(client, job["id"], ok=True, text_md="پاسخ جی‌پی‌تی: قیمت ۲ میلیون")
    m = by_player(await council(client, owner, w["id"]))
    assert m["gpt"]["state"] == "done" and m["claude"]["state"] in ("queued", "working")
    # Claude's member: the assignee's own deliverable on the order.
    ceo = await agent_headers(f"{co}-CEO")
    r = await client.post(
        f"/internal/v1/work/{w['id']}/deliver",
        headers={**ceo, **idem()},
        json={"title": "نظر Claude", "summary": "قیمت ۳ میلیون", "body": "پاسخ Claude: قیمت ۳ میلیون",
              "produced_with": {"connection": "claude-max", "model": "claude-sonnet-5-5"}},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    c = await council(client, owner, w["id"])
    assert c["state"] == "synthesising" and by_player(c)["claude"]["deliverable_ref"]
    syn = await su.fetchrow(
        """SELECT w.id, w.brief, w.player, w.parent_id, e.code FROM work.councils k
           JOIN work.work w ON w.id = k.synthesis_work_id JOIN core.employees e ON e.id = w.assignee_id
           WHERE k.work_id = $1""",
        uuid.UUID(w["id"]),
    )
    assert syn["player"] == "claude" and syn["code"] == f"{co}-CEO"
    assert str(syn["parent_id"]) == w["id"]
    assert "پاسخ جی‌پی‌تی" in syn["brief"] and "پاسخ Claude" in syn["brief"]
    assert "سقف روزانه" in syn["brief"]  # a skipped member says why
    r = await client.post(
        f"/internal/v1/work/{syn['id']}/deliver",
        headers={**ceo, **idem()},
        json={"title": "جمع‌بندی شورا", "summary": "هم‌نظر نیستند", "body": "۱. ...\n۲. ...\n۳. پیشنهاد"},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    c = await council(client, owner, w["id"])
    assert c["state"] == "done" and c["synthesis_ref"] == r.json()["deliverable"]
    stream = await su.fetch(
        """SELECT payload->'data'->>'state' AS state FROM core.outbox
           WHERE subject LIKE '%.work.council' AND payload->>'ref' = $1 ORDER BY id""",
        w["ref"],
    )
    states = [s["state"] for s in stream]
    assert states[0] == "running" and states[-1] == "done" and "synthesising" in states


async def test_a_media_council_makes_a_version_per_player_the_owner_picks_and_animates(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    async with bench(su, hub, web=("gpt", "gemini")):
        await per_day(su, "gpt", "creative", 5)
        await per_day(su, "gemini", "creative", 5)
        await su.execute(
            "UPDATE substitutes.seats SET per_day_video = 100 WHERE player = 'gemini' AND seat = 'creative'"
        )
        try:
            w = await order(client, owner, co, mode="council", media="image",
                            title="پوستر دوره", brief="پوستر دوره‌ی رایگان")  # fmt: skip
            c = await council(client, owner, w["id"])
            m = by_player(c)
            assert c["media"] == "image" and set(m) == {"gpt", "gemini"}  # DeepSeek makes no image
            assert all(x["creative_ref"] and x["state"] == "queued" for x in m.values())
            for _ in range(2):
                await su.execute("UPDATE substitutes.players SET web_last_job_at = NULL")
                fake = FakeEgress(
                    *[{"ok": True, "file": {"name": "i.png", "mime": "image/png", "b64": png()},
                       "recipe_version": "2"}] * 2
                )  # fmt: skip
                await S.web_jobs(hub, fake)
            c = await council(client, owner, w["id"])
            assert c["state"] == "done", c
            assert all(x["state"] == "done" for x in c["members"])
            g, e = by_player(c)["gpt"]["creative_ref"], by_player(c)["gemini"]["creative_ref"]
            # The owner picks one; picking another unpicks the first.
            r = await client.post(f"/api/v1/creatives/{g}/pick", headers=owner)
            assert (
                r.status_code == 200 and r.json()["picked_at"] and r.json()["state"] == "accepted"
            )
            r = await client.post(f"/api/v1/creatives/{e}/pick", headers=owner)
            assert r.status_code == 200, r.text
            assert (await client.get(f"/api/v1/creatives/{g}", headers=owner)).json()[
                "picked_at"
            ] is None
            # An unpicked image is not animated; the picked one is, by the player that makes video.
            assert (
                await client.post(f"/api/v1/creatives/{g}/animate", headers=owner)
            ).status_code == 409
            r = await client.post(f"/api/v1/creatives/{e}/animate", headers=owner)
            assert r.status_code == 201, r.text
            v = r.json()
            assert v["kind"] == "video" and v["source_creative"] == e and v["player"] == "gemini"
            files = await su.fetchval(
                """SELECT x.file_ids FROM substitutes.calls x JOIN substitutes.creatives r ON r.call_id = x.id
                   WHERE r.ref = $1""",
                v["ref"],
            )
            assert files and len(files) == 1
            assert await su.fetchval(
                "SELECT count(*) FROM audit.entries WHERE action = 'creative.pick' AND target_ref = $1", e
            ) == 1  # fmt: skip
        finally:
            await su.execute(
                "UPDATE substitutes.seats SET per_day_video = 3 WHERE player = 'gemini' AND seat = 'creative'"
            )


# --------------------------------------------------------------- speech --
async def test_a_voice_order_without_text_is_transcribed_on_the_hub(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    hub: Hub,
    su: Any,
    media_acts: Any,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acts, stt = media_acts

    async def no_model(hub: Any, req: dict[str, Any], timeout_s: float = 60.0) -> None:
        return None

    monkeypatch.setattr(workflows_client, "route_order", no_model)
    stt.text = "به مدیر فنی FX بگو گزارش هفته را با جی‌پی‌تی آماده کند"
    ref = (await upload(client, owner, audio(tmp_path, "wav", 2), "audio/wav", "order.wav")).json()
    await acts.file_process(ref["id"])
    meta = (await client.get(f"/api/v1/files/{ref['id']}/meta", headers=owner)).json()
    assert meta["transcript"] and meta["transcript_fa"] == meta["transcript"]
    seen = await su.fetchrow(
        "SELECT payload FROM core.outbox WHERE subject LIKE '%.file.transcribed' AND payload->>'ref' = $1",
        ref["id"],
    )
    data = json.loads(seen["payload"])["data"]
    assert data["chars"] > 0 and data["kind"] == "audio" and "text" not in data
    # The phone had no recogniser: the order comes with its audio only.
    r = await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={"text": "", "source": "voice", "file_id": ref["id"]},
    )
    assert r.status_code == 201, r.text
    [route] = r.json()["routes"]
    work_ref = route["work_ref"]
    row = await su.fetchrow("SELECT player, brief FROM work.work WHERE ref = $1", work_ref)
    assert row["player"] == "gpt" and "گزارش هفته" in row["brief"]
    # No text, no audio: refused; audio the hub cannot hear while stt is off: 503.
    bad = await client.post(
        "/api/v1/orders", headers={**owner, **idem()}, json={"text": " ", "source": "text"}
    )
    assert bad.status_code == 422
    fresh = (await upload(client, owner, audio(tmp_path, "wav", 2), "audio/wav", "b.wav")).json()
    monkeypatch.setattr(hub, "settings", replace(hub.settings, stt_url=""))
    off = await client.post(
        "/api/v1/orders",
        headers={**owner, **idem()},
        json={"text": "", "source": "voice", "file_id": fresh["id"]},
    )
    assert off.status_code == 503, off.text


def _wav(seconds: float, rate: int = 16000, quiet: tuple[tuple[float, float], ...] = ()) -> bytes:
    """A 16-bit mono WAV: a tone, silent within the `quiet` spans (seconds)."""
    import array
    import io
    import math
    import wave

    samples = array.array("h")
    for i in range(int(seconds * rate)):
        t = i / rate
        silent = any(a <= t < b for a, b in quiet)
        samples.append(0 if silent else int(8000 * math.sin(2 * math.pi * 300 * t)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def _answer(n: int, request: httpx.Request) -> httpx.Response:
    secs = (len(request.content) - 44) / 32000
    return httpx.Response(200, json={
        "text_raw": f"بخش {n}", "text": f"بخش {n}", "language": "fa", "duration_s": secs,
        "confidence": 0.5 + n * 0.1, "segments": [{"start_s": 0.5, "end_s": 1.0, "text": f"بخش {n}"}],
        "engine": {"name": "faster-whisper", "model": "small", "version": "test"},
        "timing": {"load_s": 0.1, "transcribe_s": 1.0},
    })  # fmt: skip


async def test_every_recording_goes_to_stt_in_short_pieces_cut_where_it_is_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert M.CHUNK_S == 30  # small's limit is sized on its measured 30-second peak
    assert [at for at, _ in M.wav_chunks(_wav(1))] == [0.0]  # short: as it is
    assert M.wav_chunks(b"not a wav") == [(0.0, b"not a wav")]
    monkeypatch.setattr(M, "CHUNK_S", 2)
    seen: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.content[:4] == b"RIFF"
        seen.append((len(request.content) - 44) / 32000)
        return _answer(len(seen) - 1, request)

    f = tmp_path / "long.wav"
    f.write_bytes(_wav(5, quiet=((1.5, 1.7), (3.4, 3.6))))
    out = await M.transcribe("http://stt.test", f, transport=httpx.MockTransport(handle))
    assert out["pieces"] == len(seen) == 3 and all(s <= 2.0 for s in seen)
    assert abs(sum(seen) - 5.0) < 0.01 and out["duration_s"] == round(sum(seen), 2)
    # the cuts fall in the silences, not inside a word
    assert 1.5 <= seen[0] <= 1.7 and 3.4 <= seen[0] + seen[1] <= 3.6
    assert out["text"] == "بخش 0 بخش 1 بخش 2"
    assert out["segments"][1]["start_s"] == round(seen[0] + 0.5, 2)
    assert out["engine"]["model"] == "small" and out["timing"]["transcribe_s"] == 3.0


async def test_a_stopped_stt_is_asked_for_and_waited_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(M, "COLD_POLL_S", 0.01)
    calls = {"n": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 3:  # the container is still starting
            raise httpx.ConnectError("Name or service not known", request=request)
        return _answer(0, request)

    f = tmp_path / "order.wav"
    f.write_bytes(_wav(1))
    demand_dir = tmp_path / "stt"
    demand_dir.mkdir()
    out = await M.transcribe("http://stt.test", f, transport=httpx.MockTransport(handle),
                             demand_dir=str(demand_dir), cold_start_s=5)  # fmt: skip
    assert out["text"] == "بخش 0" and calls["n"] == 4
    assert (demand_dir / "want").read_text().strip().isdigit()
    # Without a demand directory (stt always up), or past the cold start: unavailable.
    calls["n"] = -100
    with pytest.raises(M.SttUnavailable):
        await M.transcribe("http://stt.test", f, transport=httpx.MockTransport(handle))
    with pytest.raises(M.SttUnavailable):
        await M.transcribe("http://stt.test", f, transport=httpx.MockTransport(handle),
                           demand_dir=str(demand_dir), cold_start_s=0.05)  # fmt: skip
