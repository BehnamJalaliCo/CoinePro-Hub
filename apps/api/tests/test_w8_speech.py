"""`speech.make` (A1), the owner, 2026-11-06: the voices for content came from Google AI Studio and
the hub was not connected to it (domain/speech_make.py, routes/speech.py).

- The media roles get a voice from AI Studio outside any line: the lines' own egress call (the
  `aistudio-web` profile, its voice and style), the audio as the company's file with its §17.1
  processing row; audited (the request A1, the outcome, the account's state on the holding).
- With the worker (Temporal) the first answer is `running` with the job; the answer is read by
  the job id, only by the job's own company; the same Idempotency-Key is the same job.
- Signed out: a failure in plain Persian naming the owner's `make aistudio-web-login`; new jobs
  are held back for a while, then try again.
- Refusals: a voice AI Studio does not have, personal or secret data, another role, no key.
- speech_state(): the last answer AI Studio gave (a speech.make or a line's `tts` step).
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api import audit
from hq_api.domain import speech_make as SM
from hq_api.hub import Hub
from hq_api.lines.adapters import _common as C

from .conftest import agent_headers, idem
from .test_p13a_media import hire

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
OK = {
    "ok": True,
    "file": {"name": "a.wav", "mime": "audio/wav", "b64": base64.b64encode(WAV).decode()},
}
EXPIRED = {"ok": False, "error": "expired"}


class FakeWeb:
    """The egress profile-browser client (POST /v1/substitutes/web), as the lines' tests use it."""

    def __init__(self, *answers: dict[str, Any]) -> None:
        self.answers = list(answers)
        self.sent: list[dict[str, Any]] = []

    async def job(self, hub: Any, body: dict[str, Any], limit_s: float) -> dict[str, Any]:
        self.sent.append(body)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


@pytest.fixture
def web(monkeypatch: pytest.MonkeyPatch) -> FakeWeb:
    fake = FakeWeb(OK)
    monkeypatch.setattr(C, "WEB_OVERRIDE", fake)
    return fake


async def signed_in_again(hub: Hub) -> None:
    """The account's state back to signed in (as a voice made would leave it)."""
    holding = await hub.companies.holding()
    async with hub.db.tx([holding.id]) as tx:
        await audit.record(
            tx, SM.SERVICE, company_id=holding.id, action="speech.account", action_class="A0",
            target_kind="account", target_ref=SM.ACCOUNT, summary="signed_in",
        )  # fmt: skip


@pytest.fixture
async def clean(hub: Hub) -> AsyncIterator[None]:
    await signed_in_again(hub)
    yield
    await signed_in_again(hub)


async def state(hub: Hub) -> str:
    async with hub.db.tx(await hub.companies.ids()) as tx:
        return (await SM.speech_state(tx))["aistudio"]


async def make(
    client: httpx.AsyncClient, who: str, body: dict[str, Any], key: dict[str, str] | None = None
) -> httpx.Response:
    return await client.post(
        "/internal/v1/speech/make",
        headers={**await agent_headers(who), **(key if key is not None else idem())},
        json=body,
    )


# ------------------------------------------------------------- inline --
async def test_a_voice_producer_gets_an_aistudio_voice_as_its_companys_file(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    web: FakeWeb,
    clean: None,
) -> None:
    co = await new_company()
    producer = await hire(su, co, "voice_producer")
    r = await make(
        client, producer, {"text_fa": "سلام؛ این صدای تازه است.", "voice": "Puck", "style": "گرم"}
    )
    assert r.status_code == 202, r.text
    got = r.json()
    assert (got["state"], got["engine"], got["voice"], got["style"]) == (
        "done", "aistudio", "Puck", "گرم",
    )  # fmt: skip
    assert got["mime"] == "audio/wav" and got["bytes"] == len(WAV) and got["code"] is None
    sent = web.sent[-1]
    assert (sent["account"], sent["task"], sent["prompt"]) == (
        "aistudio-web", "tts", "سلام؛ این صدای تازه است.",
    )  # fmt: skip
    assert (sent["voice"], sent["style"]) == ("Puck", "گرم")
    f = await su.fetchrow("SELECT * FROM files.files WHERE id = $1::uuid", got["file_id"])
    assert f["company_id"] == co["id"] and f["kind"] == "audio" and f["mime"] == "audio/wav"
    assert (f["created_by_kind"], f["created_by_code"]) == ("agent", producer)
    assert f["name"] == f"speech-{got['job'][:8]}.wav"
    assert await su.fetchval(
        "SELECT count(*) FROM files.processing WHERE file_id = $1::uuid", got["file_id"]
    ) == 1  # fmt: skip
    rows = await su.fetch(
        """SELECT action, action_class, actor_code, target_ref, summary FROM audit.entries
           WHERE company_id = $1 AND action LIKE 'speech.%' ORDER BY seq""",
        co["id"],
    )
    assert [(x["action"], x["action_class"]) for x in rows] == [
        ("speech.make", "A1"), ("speech.made", "A1"),
    ]  # fmt: skip
    assert rows[0]["actor_code"] == producer and rows[0]["target_ref"] == got["job"]
    assert rows[1]["target_ref"] == got["file_id"] and rows[1]["summary"].startswith(producer)
    assert await state(hub) == "signed_in"
    # the default speaker is Kore; the director and the other media roles have it too
    director = await hire(su, co, "media_director")
    r = await make(client, director, {"text_fa": "یک صدای آزمایشی"})
    assert r.status_code == 202 and r.json()["voice"] == "Kore", r.text
    assert web.sent[-1]["voice"] == "Kore" and "style" not in web.sent[-1]


async def test_refusals_come_before_anything_leaves(
    client: httpx.AsyncClient,
    su: Any,
    new_company: Callable[..., Any],
    web: FakeWeb,
    clean: None,
) -> None:
    co = await new_company()
    writer = await hire(su, co, "scriptwriter")
    r = await make(client, writer, {"text_fa": "متن", "voice": "Nobody"})
    assert r.status_code == 422 and "Kore" in r.json()["message_fa"], r.text
    r = await make(client, writer, {"text_fa": "با من تماس بگیر: ali.rezaei@example.com"})
    assert r.status_code == 403 and r.json()["message_fa"], r.text
    r = await make(client, writer, {"text_fa": "متن", "style": "sk-ant-api03-" + "Q" * 40})
    assert r.status_code == 403
    r = await make(client, writer, {"text_fa": "ا" * 5001})
    assert r.status_code == 422
    r = await make(client, writer, {"text_fa": "متن"}, key={})
    assert r.status_code == 422  # Idempotency-Key is required
    publisher = await hire(su, co, "publisher")
    r = await make(client, publisher, {"text_fa": "متن"})
    assert r.status_code == 403
    # ⟨2026-11-12⟩ the CEO may (a media order without a media director is his: ROLES, media.rego);
    # a role with no voice work may not
    r = await make(client, f"{co['code']}-TECH-MGR", {"text_fa": "متن"})
    assert r.status_code == 403
    assert web.sent == []  # nothing left the hub
    # the same key is the same answer (stored once the voice is made)
    key = idem()
    first = await make(client, writer, {"text_fa": "یک بار"}, key=key)
    again = await make(client, writer, {"text_fa": "یک بار"}, key=key)
    assert first.status_code == again.status_code == 202 and first.json() == again.json()
    assert again.headers.get("Idempotent-Replay") == "true" and len(web.sent) == 1


async def test_signed_out_names_the_owners_step_and_holds_new_jobs_back(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    web: FakeWeb,
    clean: None,
) -> None:
    co = await new_company()
    producer = await hire(su, co, "voice_producer")
    web.answers = [EXPIRED]
    r = await make(client, producer, {"text_fa": "متن"})
    assert r.status_code == 202, r.text
    got = r.json()
    assert (got["state"], got["code"], got["file_id"]) == ("failed", "signed_out", None)
    assert "make aistudio-web-login" in got["hint_fa"]
    assert await state(hub) == "signed_out"
    # a new job is refused at once, in Persian, without asking AI Studio again
    sent = len(web.sent)
    r = await make(client, producer, {"text_fa": "متن دوم"})
    assert r.status_code == 503 and r.json()["code"] == "channel_not_configured", r.text
    assert "make aistudio-web-login" in r.json()["message_fa"] and len(web.sent) == sent
    async with hub.db.tx(await hub.companies.ids()) as tx:
        assert await SM.held_back(tx)
        later = datetime.now(UTC) + SM.SIGNED_OUT_HOLD + timedelta(minutes=1)
        assert not await SM.held_back(tx, now=later)  # then it tries again
    # other failures in plain Persian, and they say nothing about the sign-in
    await signed_in_again(hub)
    for answer, code in (
        ({"ok": False, "error": "off"}, "channel_not_configured"),
        ({"ok": False, "error": "timeout"}, "timeout"),
        ({"ok": False, "error": "recipe_failed", "step": "3:select"}, "recipe_failed"),
    ):
        web.answers = [answer]
        r = await make(client, producer, {"text_fa": "متن"})
        assert (r.json()["state"], r.json()["code"]) == ("failed", code), r.text
        assert r.json()["hint_fa"]
    assert await state(hub) == "signed_in"


async def test_speech_state_also_reads_a_lines_tts_step(
    hub: Hub, su: Any, new_company: Callable[..., Any], clean: None
) -> None:
    co = await new_company()
    line = await su.fetchval(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa, caps, steps)
           VALUES ($1, 'cal_line', 1, 'telegram_post', 'صدا', '{}', '[]') RETURNING id""",
        co["id"],
    )
    run = await su.fetchval(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, at)
           VALUES ($1, $2, 1, 'owner', 'failed', now()) RETURNING id""",
        co["id"],
        line,
    )
    await su.execute(
        """INSERT INTO lines.step_runs (company_id, run_id, pos, key, kind, state, ended_at, error_fa)
           VALUES ($1, $2, 0, 'voice', 'tts', 'failed', now() + interval '1 second',
                   'ورود حساب منقضی شده؛ مالک باید وارد شود (make aistudio-web-login).')""",
        co["id"],
        run,
    )
    assert await state(hub) == "signed_out"
    await su.execute(
        """INSERT INTO lines.step_runs (company_id, run_id, pos, key, kind, state, ended_at)
           VALUES ($1, $2, 1, 'voice2', 'tts', 'done', now() + interval '2 seconds')""",
        co["id"],
        run,
    )
    assert await state(hub) == "signed_in"
    await su.execute(  # a failure that says nothing of the sign-in changes nothing
        """INSERT INTO lines.step_runs (company_id, run_id, pos, key, kind, state, ended_at, error_fa)
           VALUES ($1, $2, 2, 'voice3', 'tts', 'failed', now() + interval '3 seconds', 'به موقع')""",
        co["id"],
        run,
    )
    assert await state(hub) == "signed_in"
    await asyncio.sleep(3.1)  # the rows above are dated ahead; the fixture's own row comes after


# ------------------------------------------------------- with the worker --
async def test_with_the_worker_the_answer_is_read_by_the_job_of_ones_own_company(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    wk: dict[str, Any],
    new_company: Callable[..., Any],
    web: FakeWeb,
    clean: None,
) -> None:
    co, other = await new_company(), await new_company()
    producer = await hire(su, co, "voice_producer")
    stranger = await hire(su, other, "voice_producer")
    saved = (hub.temporal, hub.settings)
    hub.temporal = wk["client"]
    hub.settings = dataclasses.replace(hub.settings, task_queue=wk["tq"])
    try:
        key = idem()
        r = await make(client, producer, {"text_fa": "صدای کارگر", "voice": "Charon"}, key=key)
        assert r.status_code == 202, r.text
        started = r.json()
        assert started["state"] == "running" and started["hint_fa"] and started["file_id"] is None
        job = started["job"]
        again = await make(client, producer, {"text_fa": "صدای کارگر", "voice": "Charon"}, key=key)
        assert again.json()["job"] == job  # the same key, the same job
        got: dict[str, Any] = {}
        for _ in range(60):
            r = await client.get(
                f"/internal/v1/speech/make/{job}", headers=await agent_headers(producer)
            )
            assert r.status_code == 200, r.text
            got = r.json()
            if got["state"] != "running":
                break
            await asyncio.sleep(0.5)
        assert got["state"] == "done" and got["voice"] == "Charon" and got["file_id"], got
        assert await su.fetchval(
            "SELECT company_id FROM files.files WHERE id = $1::uuid", got["file_id"]
        ) == co["id"]  # fmt: skip
        assert len([s for s in web.sent if s["prompt"] == "صدای کارگر"]) == 1  # spoken once
        # another company's agent never finds it; an unknown job neither
        r = await client.get(
            f"/internal/v1/speech/make/{job}", headers=await agent_headers(stranger)
        )
        assert r.status_code == 404
        r = await client.get(
            "/internal/v1/speech/make/00000000-0000-0000-0000-000000000001",
            headers=await agent_headers(producer),
        )
        assert r.status_code == 404
    finally:
        hub.temporal, hub.settings = saved
    # without a worker there is nothing to ask for
    r = await client.get(f"/internal/v1/speech/make/{job}", headers=await agent_headers(producer))
    assert r.status_code == 404


# ---------------------------------------------- ⟨2026-11-13⟩ the API first --
async def test_the_api_speaks_first_and_the_web_page_only_when_it_cannot(
    client: httpx.AsyncClient,
    hub: Hub,
    su: Any,
    new_company: Callable[..., Any],
    web: FakeWeb,
    clean: None,
) -> None:
    """The owner, 2026-11-13: «اول API، و اگر نشد نسخه‌ی وب». Gemini's API (the voice layer's
    engine, with its key) is asked first, with the style as a reading instruction; no key, or a
    refusal, and it is AI Studio's web page as before."""
    from hq_api.voice import audio
    from hq_api.voice import engines as voice_engines
    from hq_api.voice.base import EngineAudio, EngineFailed

    class FakeApi:
        key = SM.API_ENGINE

        def __init__(self) -> None:
            self.spoken: list[tuple[str, str]] = []
            self.fail = False

        async def speak(self, hub_: Any, text: str, voice: str, rate: float) -> EngineAudio:
            if self.fail:
                raise EngineFailed("نه", state="failing", code="bad_request")
            self.spoken.append((text, voice))
            holding = await hub_.companies.holding()
            fid = await audio.store(
                hub_, holding.id, b"OggS-api", name="api.ogg", mime="audio/ogg", seconds=2
            )
            return EngineAudio(str(fid), "audio/ogg", 2.0, 50, 10)

        async def check(self, hub_: Any) -> tuple[str, str | None]:
            return "ok", None

    async def key_state(state_: str) -> None:
        holding = await hub.companies.holding()
        async with hub.db.tx([holding.id]) as tx:
            from hq_api.voice import store as VS

            await VS.states(tx, holding.id)  # the rows exist
        await su.execute(
            "UPDATE talk.engine_state SET state = $2 WHERE engine = $1", SM.API_ENGINE, state_
        )

    co = await new_company()
    producer = await hire(su, co, "voice_producer")
    api = FakeApi()
    voice_engines.OVERRIDE[SM.API_ENGINE] = api  # type: ignore[assignment]
    try:
        # no key given: the web page, as before
        await key_state("missing")
        r = await make(client, producer, {"text_fa": "سلام", "voice": "Cruz", "style": "Narration"})
        assert r.status_code == 202 and r.json()["engine"] == "aistudio", r.text
        assert api.spoken == [] and web.sent[-1]["voice"] == "Cruz"

        # with the key: the API speaks, the web page is not asked
        await key_state("ok")
        n = len(web.sent)
        r = await make(
            client, producer, {"text_fa": "با پروچارت", "voice": "Cruz", "style": "Narration"}
        )
        got = r.json()
        assert r.status_code == 202 and got["engine"] == "gemini_api", r.text
        assert (got["voice"], got["style"], got["mime"]) == ("Cruz", "Narration", "audio/ogg")
        assert len(web.sent) == n
        text, voice = api.spoken[-1]
        assert voice == "Cruz" and text.endswith("با پروچارت")
        assert "dramatic pauses" in text  # the preset, as a reading instruction
        f = await su.fetchrow("SELECT * FROM files.files WHERE id = $1::uuid", got["file_id"])
        assert f["company_id"] == co["id"] and f["size"] == len(b"OggS-api")
        made = await su.fetchval(
            "SELECT summary FROM audit.entries WHERE company_id = $1 AND action = 'speech.made' "
            "ORDER BY seq DESC LIMIT 1",
            co["id"],
        )
        assert "Gemini API Cruz" in made
        assert await su.fetchval(
            "SELECT count(*) FROM talk.voice_usage WHERE engine = $1 AND persona = $2",
            SM.API_ENGINE, f"speech.make {producer}",
        ) == 1  # fmt: skip

        # the API refuses: the web page, in the same job
        api.fail = True
        r = await make(client, producer, {"text_fa": "دوباره", "voice": "Cruz"})
        assert r.status_code == 202 and r.json()["engine"] == "aistudio", r.text
        assert web.sent[-1]["prompt"] == "دوباره"
    finally:
        voice_engines.OVERRIDE.pop(SM.API_ENGINE, None)
        await su.execute(
            "UPDATE talk.engine_state SET state = 'missing' WHERE engine = $1", SM.API_ENGINE
        )


def test_a_style_is_a_reading_instruction_for_the_api() -> None:
    assert SM.api_text("متن", "") == "متن"
    assert "dramatic pauses" in SM.api_text("متن", "narration")
    assert SM.api_text("متن", "آرام و گرم").startswith(
        "Read the following Persian text aloud, in this manner: آرام و گرم."
    )


async def test_a_passing_api_refusal_is_tried_again_before_the_web_page(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⟨2026-11-13⟩ F-0018: one upstream_error between two good voices sent a job to the signed-out
    web page. A refusal that may pass is tried once more; a lasting one (a bad key) is not."""
    from hq_api.voice import speaker as SP
    from hq_api.voice.base import EngineFailed

    tries: list[str] = []

    async def ready(hub_: Any, tx: Any) -> bool:
        return True

    async def flaky(*a: Any, **k: Any) -> Any:
        tries.append("x")
        raise EngineFailed("نه", state="failing", code=codes.pop(0))

    monkeypatch.setattr(SM, "api_ready", ready)
    monkeypatch.setattr(SP, "speak_one", flaky)
    monkeypatch.setattr(SM, "API_RETRY_S", 0.0)
    job = {"job": "j1", "by": "X", "text": "سلام", "voice": "Cruz", "style": ""}
    codes = ["upstream_error", "upstream_error"]
    assert await SM.api_speak(hub, job) is None and len(tries) == SM.API_TRIES
    tries.clear()
    codes = ["bad_key"]
    assert await SM.api_speak(hub, job) is None and len(tries) == 1
