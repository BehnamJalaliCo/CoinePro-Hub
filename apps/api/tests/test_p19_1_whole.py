"""Prompt 19.1: nothing a runner or a substitute player returns is cut. A long
Claude answer and the output past a job's live stream are kept whole in the
file store; a long CLI answer, a long deliverable and a long council brief go
whole into files; a model the CLI lists joins the player's list."""

from __future__ import annotations

import base64
import gzip
import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.domain import catalogue as CAT
from hq_api.domain import players as PL
from hq_api.domain import servers as SV
from hq_api.domain import substitutes as S
from hq_api.hub import Hub

from .conftest import agent_headers, idem
from .test_p12a_advisor import _end_test_runs  # noqa: F401 - an autouse fixture here too
from .test_p12a_substitutes import bench, claim, done, per_day
from .test_p17_runners import pair, take

pytestmark = pytest.mark.usefixtures("relay")


async def _blob(hub: Hub, su: Any, file_id: str) -> bytes:
    key = await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1::uuid", file_id)
    return bytes(await hub.storage.get(key))


async def test_a_jobs_output_past_the_stream_and_a_long_answer_are_kept_whole(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "big-1")
    # a catalogue section whose answer is far past the old 4 000 characters
    r = await client.post(
        f"/api/v1/companies/{co['code']}/catalogue", headers=owner_session["headers"]
    )
    assert r.status_code == 202
    rows = [[f"svc-{i}", "سرویس پشتیبان برای گزارش روزانه " * 4] for i in range(2200)]  # ~330 KB
    answer = json.dumps({"summary_md": "همه", "count": 2200,
                         "tables": [{"title_fa": "سرویس‌ها", "columns": ["نام", "شرح"], "rows": rows}]},
                        ensure_ascii=False)  # fmt: skip
    jobs = [await take(client, rn) for _ in CAT.SECTIONS]
    small = json.dumps({"summary_md": "کم", "count": 1,
                        "tables": [{"title_fa": "یک", "columns": ["نام"], "rows": [["تنها"]]}]},
                       ensure_ascii=False)  # fmt: skip
    for n, j in enumerate(jobs):
        text = answer if n < 2 else small  # two long sections: past the body's column
        rest = ("خط خروجی بعد از ۱۰ مگابایت\n" * 20_000).encode()
        body = {"exit_code": 0, "data": {
            "result_fa": text, "answer_chars": len(text), "answer_truncated": False,
            "output_overflow": {"encoding": "gzip+base64", "b64": base64.b64encode(gzip.compress(rest)).decode(),
                                "bytes": len(rest), "kept_from_byte": 0, "dropped_bytes": 0},
        }}  # fmt: skip
        res = await client.post(
            f"/api/v1/runners/jobs/{j['id']}/result", headers=rn["h"], json=body
        )
        assert res.status_code == 200, res.text
    row = await su.fetchrow(
        "SELECT result FROM infra.server_jobs WHERE id = $1::uuid", jobs[0]["id"]
    )
    result = json.loads(row["result"])
    assert len(result["result_fa"]) == SV.INLINE_ANSWER and result["result_file"]
    assert (await _blob(hub, su, result["result_file"])).decode() == answer
    assert result["output_overflow"]["stored"] is True and result["output_overflow"][
        "bytes"
    ] == len(rest)
    assert (await _blob(hub, su, result["output_file"])) == rest
    got = (await client.get(f"/api/v1/companies/{co['code']}/catalogue",
                            headers=owner_session["headers"])).json()  # fmt: skip
    assert got["state"] == "done" and got["record"]
    rec = await su.fetchrow(
        """SELECT f.mime, f.size_bytes FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
           WHERE r.ref = $1""",
        got["record"],
    )
    assert rec["mime"] == "application/pdf"  # the whole catalogue, not only the body's head
    pages = await su.fetchval(
        """SELECT f.pages FROM archive.record_files f JOIN archive.records r ON r.id = f.record_id
           WHERE r.ref = $1""",
        got["record"],
    )
    assert pages > 100
    products = next(s for s in got["sections"] if s["key"] == "products")
    assert (
        len(products["tables"][0]["rows"]) == 2200
        and products["tables"][0]["rows"][-1][1] == "سرویس پشتیبان برای گزارش روزانه " * 4
    )
    # the deliverable's body is past its column: whole in its attachment
    dl = await su.fetchrow(
        "SELECT body, attachments FROM cartable.deliverables WHERE ref = $1", got["deliverable"]
    )
    assert len(dl["body"]) <= PL.BODY_LIMIT + 200 and len(dl["attachments"]) == 1
    full = (await _blob(hub, su, str(dl["attachments"][0]))).decode()
    assert "svc-2199" in full and full.count("svc-") >= 2 * 2200


async def test_an_agent_sees_where_the_whole_output_is(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
) -> None:
    co = await new_company()
    rn = await pair(client, hub, owner_session, co, "logs-1")
    me = await agent_headers(f"{co['code']}-CEO")
    r = await client.post("/internal/v1/servers/jobs", headers={**me, **idem()},
                          json={"wait_s": 0, "kind": "exec", "server": "logs-1", "args": {"cmd": "journalctl"}})  # fmt: skip
    assert r.status_code == 201, r.text
    job = await take(client, rn)
    lines = [{"seq": i + 1, "type": "stdout", "data": {"text": f"line {i} " + "y" * 200 + "\n"}}
             for i in range(200)]  # fmt: skip
    await client.post(
        f"/api/v1/runners/jobs/{job['id']}/events", headers=rn["h"], json={"events": lines}
    )
    await client.post(
        f"/api/v1/runners/jobs/{job['id']}/result", headers=rn["h"], json={"exit_code": 0}
    )
    got = (await client.get(f"/internal/v1/servers/jobs/{job['id']}", headers=me)).json()
    out = got["output"]
    assert len(out["stdout"]) == 12_000 and out["stdout_chars"] > 40_000
    assert out["full_output_file"]  # the job's whole (masked) record


async def test_a_long_cli_answer_is_kept_whole_and_reaches_its_reader(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    owner: dict[str, str],
    new_company: Callable[..., Any],
) -> None:
    co = (await new_company())["code"]
    long = "پاسخ بلند. " * 60_000  # ~660 000 characters
    async with bench(su, hub, cli=("gpt",)):
        await per_day(su, "gpt", "assistant_errand", 5)
        w = (await client.post("/api/v1/work", headers={**owner, **idem()},
                               json={"company": co, "title": "تحلیل بلند", "brief": "همه را بنویس",
                                     "player": "gpt"})).json()  # fmt: skip
        run = await su.fetchrow(
            "SELECT id FROM agents.runs WHERE work_id = $1 ORDER BY queued_at DESC LIMIT 1",
            uuid.UUID(w["id"]),
        )
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await PL.player_turn(tx, hub, {"work_id": uuid.UUID(w["id"]), "id": run["id"]})
        job = (await claim(client))["job"]
        r = await done(client, job["id"], ok=True, text_md=long,
                       usage={"input_tokens": 1, "output_tokens": 1, "estimated": False})  # fmt: skip
        assert r.status_code == 200, r.text
    res = json.loads(
        await su.fetchval("SELECT result FROM substitutes.calls WHERE id = $1::uuid", job["id"])
    )
    assert len(res["text_md"]) == S.INLINE_TEXT and res["text_chars"] == len(long)
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await S.full_text(tx, hub, res) == long
    dl = await su.fetchrow(
        "SELECT body, attachments FROM cartable.deliverables WHERE work_id = $1", uuid.UUID(w["id"])
    )
    assert len(dl["attachments"]) == 1 and len(dl["body"]) <= PL.BODY_LIMIT + 200
    assert (await _blob(hub, su, str(dl["attachments"][0]))).decode() == long


async def test_a_model_the_cli_lists_joins_the_players_models(hub: Hub, su: Any) -> None:
    before = await su.fetchval("SELECT models FROM substitutes.players WHERE player = 'gpt'")
    try:
        async with hub.db.tx(await hub.companies.ids()) as tx:
            await S.apply_models(tx, "gpt", ["gpt-6.1-sol", "gpt-6-luna"])
        models = {m["id"]: m for m in json.loads(
            await su.fetchval("SELECT models FROM substitutes.players WHERE player = 'gpt'"))}  # fmt: skip
        assert models["gpt-6.1-sol"]["tier"] == "strong" and models["gpt-6.1-sol"]["available"]
        assert models["gpt-6-luna"]["tier"] == "light"
        assert models["gpt-5.5"]["available"] is False
        seats = {r["seat"]: r["model"] for r in await su.fetch(
            "SELECT seat, model FROM substitutes.seats WHERE player = 'gpt'")}  # fmt: skip
        assert seats["assistant_errand"] == "gpt-6-luna" and seats["code_review"] == "gpt-6.1-sol"
    finally:
        await su.execute("UPDATE substitutes.players SET models = $1 WHERE player = 'gpt'", before)
        for seat in S.DEFAULT_SEATS["gpt"]:
            await su.execute("UPDATE substitutes.seats SET model = $3 WHERE player = $1 AND seat = $2",
                             "gpt", seat["seat"], seat["model"])  # fmt: skip
