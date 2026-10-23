"""Prompt 13 §4 (contract §22.3, §22.7): one voice registry for the media
items and the spoken briefings; every candidate with its licence and its
measured numbers; a non-commercial voice is never active without the owner;
the bake-off's audio goes through §17.1; the owner's own reference; the
bake-off schedule and the TTS job do nothing while the holding is locked."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from hq_api.domain import voices as V
from hq_api.hub import Hub
from hq_api.speech import assert_spoken

from .conftest import TTS_TOKEN, agent_headers, idem, step_up
from .p10_support import holding_switch
from .test_files_media import audio, upload

TTS = {"Authorization": f"Bearer {TTS_TOKEN}"}


@pytest.fixture(autouse=True)
async def _seeded(hub: Hub) -> None:
    """The registry's rows (the seed's; a migration test may have run the
    migrations down and up again, which empties media.voices)."""
    holding = await hub.companies.holding()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await V.seed(tx, holding.id)


@pytest.fixture(autouse=True)
async def _end_test_runs(su: Any) -> AsyncIterator[None]:
    """The holding's agents these tests gave a running run (agent tokens)
    end it afterwards, and the runs their work queued for them end too:
    other modules claim runs of the same agents."""
    yield
    await su.execute(
        """UPDATE agents.runs r SET state = 'done', finished_at = now()
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'running'
             AND r.reason = 'test' AND e.code IN ('HQ-ADV', 'HQ-PA', 'HQ-LGL', 'HQ-LEGAL-77')"""
    )
    await su.execute(
        """UPDATE agents.runs r SET state = 'refused', finished_at = now(), error_code = 'test_cleanup'
           FROM core.employees e WHERE e.id = r.employee_id AND r.state = 'queued'
             AND e.code IN ('HQ-LGL', 'HQ-LEGAL-77')"""
    )


@pytest.fixture
async def quiet_queue(su: Any) -> AsyncIterator[None]:
    """Only this test's jobs wait (the test database outlives a run), and
    the registry's choice is restored afterwards."""
    await su.execute(
        "UPDATE media.speech_jobs SET state = 'cancelled' WHERE state IN ('queued', 'claimed')"
    )
    active = await su.fetchval("SELECT id FROM media.voices WHERE status = 'active'")
    yield
    await su.execute(
        "UPDATE media.speech_jobs SET state = 'cancelled' WHERE state IN ('queued', 'claimed')"
    )
    await su.execute("UPDATE media.voices SET status = 'candidate' WHERE status = 'active'")
    await su.execute("UPDATE media.voices SET status = 'active' WHERE id = $1", active)


NC = "test-nc-piper"  # an installed, measured, non-commercial voice (test data)


async def _nc_voice(su: Any) -> None:
    await su.execute(
        """INSERT INTO media.voices (id, company_id, engine, name_fa, licence, licence_commercial, speaker,
               runtime, rtf, mem_mb, measured_at, measured_on, status, sort)
           SELECT $1, id, 'piper', 'صدای آزمون غیرتجاری', 'CC BY-NC 4.0 (test)', false, 'model',
                  '{"piper_voice": "fa_IR-amir-medium"}', 0.2, 260, now(), 'test', 'candidate', 999
           FROM core.companies WHERE kind = 'holding' ON CONFLICT (id) DO NOTHING""",
        NC,
    )


async def _measured(su: Any, voice_id: str) -> None:
    await su.execute(
        """UPDATE media.voices SET rtf = 0.2, mem_mb = 260, measured_at = now(), measured_on = 'test'
           WHERE id = $1 AND measured_at IS NULL""",
        voice_id,
    )


async def _sample_job(su: Any, voice_id: str) -> None:
    """A fresh bake-off round for one voice and script (the test database
    keeps every earlier round)."""
    await su.execute(
        """INSERT INTO media.speech_jobs (company_id, kind, voice_id, script_key, round, script,
               created_by_kind, created_by_code)
           SELECT company_id, 'sample', id, 'numbers',
                  (SELECT COALESCE(max(round), 1) + 1 FROM media.speech_jobs WHERE voice_id = $1),
                  $2, 'service', 'test'
           FROM media.voices WHERE id = $1""",
        voice_id,
        V.spoken("numbers"),
    )


async def _done(
    client: httpx.AsyncClient, job: dict[str, Any], body: bytes, **params: Any
) -> httpx.Response:
    return await client.post(
        f"/internal/v1/voices/jobs/{job['id']}/done",
        params=params,
        content=body,
        headers={**TTS, "Content-Type": "audio/ogg"},
    )


# ------------------------------------------------------------ the registry --
async def test_the_registry_has_every_candidate_with_its_licence_and_numbers(
    client: httpx.AsyncClient, owner: dict[str, str]
) -> None:
    r = await client.get("/api/v1/media/voices", headers=owner)
    assert r.status_code == 200
    by = {v["id"]: v for v in r.json()}
    assert {"piper-amir", "piper-ganji", "piper-reza-ibrahim", "manatts-piper", "parsvoice-xtts",
            "parsvoice-xtts-owner", "chatterbox-fa", "chatterbox-fa-owner"} <= set(by)  # fmt: skip
    assert [v["id"] for v in by.values() if v["status"] == "active"] == ["piper-amir"]
    amir = by["piper-amir"]
    assert amir["licence_commercial"] and amir["installed"] and amir["rtf"] and amir["mem_mb"]
    assert "MIT" in amir["licence"] and amir["measured_at"] is not None
    xtts = by["parsvoice-xtts"]
    assert xtts["licence_commercial"] is False and "Coqui Public Model License" in xtts["licence"]
    assert xtts["installed"] is False and xtts["rtf"] is None and xtts["note_fa"]
    assert by["parsvoice-xtts-owner"]["speaker"] == "owner" and by["parsvoice-xtts-owner"]["clones"]
    assert (
        by["chatterbox-fa"]["licence"].startswith("CC BY-NC")
        and not by["chatterbox-fa"]["licence_commercial"]
    )
    assert by["manatts-piper"]["installed"] is False and "GPU" in by["manatts-piper"]["note_fa"]
    assert by["piper-gyro"]["licence_commercial"] is False  # its dataset licence is unstated
    assert by["piper-gyro"]["installed"] is False  # ... so it is not shipped


@pytest.mark.usefixtures("quiet_queue")
async def test_a_non_commercial_voice_is_never_active_without_the_owner(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], su: Any
) -> None:
    h = owner_session["headers"]

    async def activate(vid: str, body: dict[str, Any], seal: bool = True) -> httpx.Response:
        extra = (
            await step_up(hub, owner_session["session_id"], "voice.activate", vid) if seal else {}
        )
        return await client.post(
            f"/api/v1/media/voices/{vid}/activate", headers={**h, **extra}, json=body
        )

    # Not installed on the hub (gated, over the memory budget): never, whatever is accepted.
    r = await activate("parsvoice-xtts", {"accept_non_commercial": True})
    assert r.status_code == 409 and r.json()["code"] == "not_ready"
    # Its dataset licence unstated: not shipped, so never active either.
    r = await activate("piper-gyro", {"accept_non_commercial": True})
    assert r.status_code == 409 and r.json()["code"] == "not_ready"
    await _nc_voice(su)
    r = await activate(NC, {})
    assert r.status_code == 422 and "accept_non_commercial" in r.json()["fields"]
    r = await activate(NC, {"accept_non_commercial": True}, seal=False)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    r = await activate(NC, {"accept_non_commercial": True})
    assert (
        r.status_code == 200
        and r.json()["status"] == "active"
        and r.json()["licence_commercial"] is False
    )
    listed = (await client.get("/api/v1/media/voices", headers=h)).json()
    assert [v["id"] for v in listed if v["status"] == "active"] == [NC]
    # A commercial one needs no acceptance, only the seal; one voice is active.
    await _measured(su, "piper-ganji")
    r = await activate("piper-ganji", {})
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert await su.fetchval("SELECT status FROM media.voices WHERE id = $1", NC) == "candidate"
    n = await su.fetchval(
        "SELECT count(*) FROM audit.entries WHERE action = 'voice.activate' AND step_up"
    )
    assert n >= 2
    # The owner's blind score.
    s = await client.post("/api/v1/media/voices/piper-ganji/score", headers=h, json={"score": 8})
    assert s.status_code == 200 and s.json()["owner_score"] == 8
    bad = await client.post("/api/v1/media/voices/piper-ganji/score", headers=h, json={"score": 11})
    assert bad.status_code == 422


async def test_the_briefings_speak_with_the_registrys_active_voice(hub: Hub) -> None:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        v = await V.briefing_voice(tx, hub.settings)
        active = await V.active(tx)
    assert active is not None and v["engine"] == "piper"
    assert v["voice"] == active["runtime"]["piper_voice"] and v["license"] == active["licence"]


# ------------------------------------------------------------- the bake-off --
@pytest.mark.usefixtures("quiet_queue")
async def test_the_bakeoff_queues_once_and_its_audio_goes_through_17_1(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    wk: dict[str, Any],
    tmp_path: Path,
) -> None:
    async with holding_switch(su, "released"):
        first = await wk["acts"].legal_voice.voice_bakeoff()
        again = await wk["acts"].legal_voice.voice_bakeoff()
        assert again["queued"] == 0 and first["voices"] >= 4
        runnable = await su.fetchval(
            "SELECT count(*) FROM media.voices WHERE runtime IS NOT NULL AND status <> 'retired' AND speaker = 'model'"
        )
        jobs = await su.fetch(
            "SELECT voice_id, script_key, script FROM media.speech_jobs WHERE kind = 'sample' AND round = $1",
            V.ROUND,
        )
        assert len(jobs) == runnable * len(V.SCRIPTS)
        assert not {j["voice_id"] for j in jobs} & {
            "parsvoice-xtts", "chatterbox-fa", "manatts-piper", "piper-gyro"
        }  # fmt: skip
        for j in jobs:
            assert_spoken(j["script"])  # the hub's own spoken form: no digit left
        await su.execute("UPDATE media.speech_jobs SET state = 'cancelled' WHERE state = 'queued'")
        await _sample_job(su, "piper-reza-ibrahim")
        r = await client.post("/internal/v1/voices/jobs/claim", headers=TTS)
        assert r.status_code == 200, r.text
        job = r.json()
        assert (job["kind"], job["engine"], job["voice"]) == (
            "sample",
            "piper",
            "fa_IR-reza_ibrahim-medium",
        )
        # §17.1: the type is read from the bytes and the length from the file.
        assert (await _done(client, job, b"not audio at all, really")).status_code == 422
        wrong = await client.post(
            f"/internal/v1/voices/jobs/{job['id']}/done",
            content=b"x",
            headers={**TTS, "Content-Type": "audio/mpeg"},
        )
        assert wrong.status_code == 415
        ok = await _done(client, job, audio(tmp_path, "ogg", 3), synth_s=0.6, peak_mb=251.5)
        assert ok.status_code == 200, ok.text
        fid = UUID(ok.json()["file"])
        row = await su.fetchrow(
            """SELECT f.kind, f.mime, f.duration_s, f.created_by_code, f.name, p.status
               FROM files.files f JOIN files.processing p ON p.file_id = f.id WHERE f.id = $1""",
            fid,
        )
        assert (
            row["kind"] == "audio"
            and row["mime"] == "audio/ogg"
            and row["created_by_code"] == "tts"
        )
        assert row["status"] == "processing" and 2.5 < float(row["duration_s"]) < 3.5
        assert "reza" not in row["name"]  # a neutral name: the listening is blind
        v = await su.fetchrow(
            "SELECT rtf, mem_mb, measured_at FROM media.voices WHERE id = 'piper-reza-ibrahim'"
        )
        assert (
            v["measured_at"] is not None
            and 0.1 < float(v["rtf"]) < 0.3
            and float(v["mem_mb"]) >= 251.5
        )
        listed = {
            x["id"]: x for x in (await client.get("/api/v1/media/voices", headers=owner)).json()
        }
        (sample,) = [s for s in listed["piper-reza-ibrahim"]["samples"] if s["script"] == "numbers"]
        assert sample["title_fa"] == "عدد و درصد" and sample["file"]["id"] == str(fid)
        assert (await client.post("/internal/v1/voices/jobs/claim", headers=TTS)).status_code == 204


@pytest.mark.usefixtures("quiet_queue")
async def test_the_bakeoff_and_the_tts_job_do_nothing_while_the_holding_is_locked(
    client: httpx.AsyncClient, su: Any, wk: dict[str, Any]
) -> None:
    async with holding_switch(su, "released"):
        await wk["acts"].legal_voice.voice_bakeoff()
        await _sample_job(su, "piper-amir")
    before = await su.fetch(
        "SELECT id, state, attempts FROM media.speech_jobs WHERE state = 'queued'"
    )
    assert before
    async with holding_switch(su, "engaged"):
        out = await wk["acts"].legal_voice.voice_bakeoff()
        assert out == {"skipped": True, "reason": "holding_locked"}
        assert (await client.post("/internal/v1/voices/jobs/claim", headers=TTS)).status_code == 204
        assert (await client.post("/internal/v1/tts/claim", headers=TTS)).status_code == 204
    after = await su.fetch(
        "SELECT id, state, attempts FROM media.speech_jobs WHERE state = 'queued'"
    )
    assert sorted(map(tuple, before)) == sorted(map(tuple, after))  # nothing claimed, nothing new
    # Only the TTS service takes jobs.
    assert (
        await client.post("/internal/v1/voices/jobs/claim", headers=await agent_headers("HQ-ADV"))
    ).status_code == 403


# -------------------------------------------------------------- narration --
async def _to_voicing(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, co: dict[str, Any]
) -> tuple[str, dict[str, str]]:
    """A one-off reel of `co` brought to its voice step by its team's tools
    (prompt 13 §2's pipeline): script, direction, composition."""
    from .test_p13a_media import COMPOSITION, SCRIPT, SHOTS, SOURCES, brand, team, tool

    staff = await team(su, co)
    await brand(su, co)
    r = await client.post(
        "/api/v1/media/items",
        headers={**owner, **idem()},
        json={"company": co["code"], "kind": "reel", "brief_md": "یک ریلز"},
    )
    assert r.status_code == 201, r.text
    ref = str(r.json()["ref"])
    for code, step in (
        (staff["scriptwriter"], {"step": "script", "script": {"text_fa": SCRIPT, "sources": SOURCES}}),
        (staff["video_director"], {"step": "direction", "direction": {"shots": SHOTS}}),
        (staff["motion_designer"],
         {"step": "composition", "composition": {"format": "html", "source": COMPOSITION}}),
    ):  # fmt: skip
        assert (await tool(client, code, "item", {"ref": ref, **step})).status_code == 200
    assert await su.fetchval("SELECT state FROM media.items WHERE ref = $1", ref) == "voicing"
    return ref, staff


@pytest.mark.usefixtures("quiet_queue")
async def test_media_voice_queues_the_narration_with_the_active_voice(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, new_company: Any,
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """The media pipeline's voice step is the registry's: media.voice queues a
    narration job with the active voice, the TTS one-shot speaks it, its Ogg
    goes through §17.1, and voices.ON_NARRATION brings the file to the item,
    which moves on to its render."""
    monkeypatch.setattr(hub, "settings", replace(hub.settings, tts=True))  # profile tts on
    co = await new_company()
    seen: list[tuple[str, UUID]] = []

    async def hook(tx: Any, hub_: Any, job: dict[str, Any], file_id: UUID) -> None:
        seen.append((job["subject_ref"], file_id))

    V.ON_NARRATION.append(hook)
    try:
        async with holding_switch(su, "released"):
            ref, staff = await _to_voicing(client, owner, su, co)
            producer = staff["voice_producer"]
            h = await agent_headers(producer)
            # A non-commercial voice the owner did not choose is refused.
            await _nc_voice(su)
            no = await client.post(
                "/internal/v1/media/voice",
                headers={**h, **idem()},
                json={"ref": ref, "text_fa": "سلام", "voice_id": NC},
            )
            assert no.status_code == 409 and no.json()["fields"]["voice_id"] == "licence_not_chosen"
            # Another employee has no media.voice.
            other = await client.post(
                "/internal/v1/media/voice",
                headers={**await agent_headers(f"{co['code']}-CEO"), **idem()},
                json={"ref": ref, "text_fa": "سلام"},
            )
            assert other.status_code == 403
            r = await client.post(
                "/internal/v1/media/voice",
                headers={**h, **idem()},
                json={"ref": ref, "text_fa": "قیمت 2.35% بالا رفت؛ این توصیه‌ی مالی نیست."},
            )
            assert r.status_code == 202, r.text
            out = r.json()
            assert out["voice"]["licence_commercial"] is True and out["state"] == "queued"
            script = await su.fetchval(
                "SELECT script FROM media.speech_jobs WHERE id = $1", UUID(out["job"])
            )
            assert_spoken(script)
            assert "درصد" in script
            job = (await client.post("/internal/v1/voices/jobs/claim", headers=TTS)).json()
            assert job["kind"] == "narration" and job["ref"] == ref
            done = await _done(client, job, audio(tmp_path, "ogg", 2), synth_s=0.3, peak_mb=240)
            assert done.status_code == 200, done.text
            file_id = UUID(done.json()["file"])
            assert seen == [(ref, file_id)]
            owner_of = await su.fetchval("SELECT company_id FROM files.files WHERE id = $1", file_id)
            assert owner_of == co["id"]
            # The pipeline's hook: the narration is on the item, and the render follows.
            x = await su.fetchrow(
                "SELECT id, state, voice_file_id, narration FROM media.items WHERE ref = $1", ref
            )
            assert x["state"] == "rendering" and x["voice_file_id"] == file_id
            assert json.loads(x["narration"])["state"] == "ready"
            spec = await su.fetchval(
                "SELECT spec FROM media.render_jobs WHERE item_id = $1 AND state = 'queued'",
                x["id"],
            )
            assert json.loads(spec)["voice"]["id"] == str(file_id)
        async with holding_switch(su, "engaged"):
            locked = await client.post(
                "/internal/v1/media/voice",
                headers={**await agent_headers(producer), **idem()},
                json={"ref": ref, "text_fa": "سلام"},
            )
            assert locked.status_code == 423
    finally:
        V.ON_NARRATION.remove(hook)


@pytest.mark.usefixtures("quiet_queue")
async def test_a_narration_given_up_lets_the_item_go_on_silent(
    client: httpx.AsyncClient, hub: Hub, owner: dict[str, str], su: Any, new_company: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    """Three failed tries of a narration (voices.ON_NARRATION_FAILED): the item
    goes on to its render without a voice, with captions. A company that is
    locked itself does not get its narration spoken meanwhile (204)."""
    monkeypatch.setattr(hub, "settings", replace(hub.settings, tts=True))
    co = await new_company()
    async with holding_switch(su, "released"):
        ref, staff = await _to_voicing(client, owner, su, co)
        r = await client.post(
            "/internal/v1/media/voice",
            headers={**await agent_headers(staff["voice_producer"]), **idem()},
            json={"ref": ref, "text_fa": "بیت‌کوین کجاست؟"},
        )
        assert r.status_code == 202, r.text
        await su.execute(
            "UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1", co["id"]
        )
        try:
            claimed = await client.post("/internal/v1/voices/jobs/claim", headers=TTS)
            assert claimed.status_code == 204
        finally:
            await su.execute(
                "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1",
                co["id"],
            )
        for _ in range(V.MAX_ATTEMPTS):
            job = (await client.post("/internal/v1/voices/jobs/claim", headers=TTS)).json()
            assert job["ref"] == ref
            fail = await client.post(
                f"/internal/v1/voices/jobs/{job['id']}/fail", headers=TTS, json={"error": "engine"}
            )
            assert fail.status_code == 204
    x = await su.fetchrow("SELECT state, voice_file_id, narration FROM media.items WHERE ref = $1", ref)
    assert x["state"] == "rendering" and x["voice_file_id"] is None
    assert json.loads(x["narration"])["state"] == "failed"


# -------------------------------------------------------------- reference --
async def test_the_owners_reference_is_the_owners_and_never_an_agents(
    client: httpx.AsyncClient, owner: dict[str, str], su: Any, tmp_path: Path
) -> None:
    await su.execute(
        "UPDATE media.voice_references SET state = 'superseded' WHERE state <> 'superseded'"
    )
    assert (await client.get("/api/v1/media/voices/reference", headers=owner)).status_code == 404
    short = (
        await upload(client, owner, audio(tmp_path, "ogg", 20), "audio/ogg", "short.ogg")
    ).json()
    r = await client.post(
        "/api/v1/media/voices/reference", headers={**owner, **idem()}, json={"file_id": short["id"]}
    )
    assert r.status_code == 422 and "duration_s" in r.json()["fields"]
    good = (await upload(client, owner, audio(tmp_path, "ogg", 75), "audio/ogg", "me.ogg")).json()
    r = await client.post(
        "/api/v1/media/voices/reference", headers={**owner, **idem()}, json={"file_id": good["id"]}
    )
    assert r.status_code == 201, r.text
    got = (await client.get("/api/v1/media/voices/reference", headers=owner)).json()
    assert got["file"]["id"] == good["id"] and 70 < got["duration_s"] < 80
    assert got["state"] in ("processing", "ready")
    # Never an agent's: the holding's own agents do not see it either.
    # (the counsel has files.read in the holding; the reference is not a
    # file it may open: a missing and a forbidden file answer the same 403)
    seen = await client.get(
        f"/internal/v1/files/{good['id']}/meta", headers=await agent_headers("HQ-LGL")
    )
    assert seen.status_code == 403 and seen.json()["code"] == "policy_denied"
    # Only the owner sets it.
    agent = await client.post(
        "/api/v1/media/voices/reference",
        headers={**await agent_headers("HQ-ADV"), **idem()},
        json={"file_id": good["id"]},
    )
    assert agent.status_code in (401, 403)


def test_the_tts_images_scripts_are_the_hubs_spoken_scripts() -> None:
    """services/tts/bakeoff_scripts.json (the operator's bake-off, make
    tts-bakeoff) is exactly what the hub's queue gives every voice."""
    import json

    shipped = json.loads(Path("/w/tts/bakeoff_scripts.json").read_text(encoding="utf-8"))
    assert shipped == [{"key": s["key"], "spoken": V.spoken(s["key"])} for s in V.SCRIPTS]
    assert {s["key"] for s in V.SCRIPTS} == {"numbers", "latin", "crypto", "long", "reel60"}
    for s in shipped:
        assert_spoken(s["spoken"])
