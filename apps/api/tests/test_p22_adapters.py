"""Prompt 22: the production lines' step adapters (contract §30.2) and the seeded templates (§30.6).

Every adapter runs against fakes: a hub with an in-memory database stand-in, the egress profile
browser, the LLM router, the connections' egress HTTP and the studio's publisher. No network, no
real model, no database row. The templates are loaded and validated by a minimal local validator
(the engine owns `lines/templates.py`).
"""

from __future__ import annotations

import base64
import importlib
import json
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
import yaml

from hq_api.agents.clients import ModelCall
from hq_api.domain import connections as CN
from hq_api.domain import notify
from hq_api.domain import studio as ST
from hq_api.domain import studio_publish as SP
from hq_api.lines import base as B
from hq_api.lines import signing
from hq_api.lines.adapters import _common as C
from hq_api.lines.adapters import council_pick, n8n, opus_build, publish, tts
from hq_api.lines.base import REGISTRY, StepContext, StepFailed, StepOutput

# The engine's loader imports every module of the package; here the ten of this prompt.
for _kind in ("gpt_text", "tts", "pattern_search", "council_pick", "opus_build", "render", "cover",
              "publish", "deliver", "n8n"):  # fmt: skip
    importlib.import_module(f"hq_api.lines.adapters.{_kind}")

SEED = Path(__file__).resolve().parents[1] / "seed" / "lines"
CO = SimpleNamespace(id=uuid4(), code="AB")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ------------------------------------------------------------------- fakes --
class FakeTx:
    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows = rows

    def _hit(self, sql: str) -> Any:
        for needle, value in self.rows.items():
            if needle in sql:
                return value() if callable(value) else value
        return None

    async def first(self, sql: str, **_: Any) -> Any:
        return self._hit(sql)

    async def one(self, sql: str, **_: Any) -> Any:
        return self._hit(sql)

    async def scalar(self, sql: str, **_: Any) -> Any:
        return self._hit(sql)

    async def all(self, sql: str, **_: Any) -> Any:
        return self._hit(sql) or []

    async def exec(self, sql: str, **_: Any) -> int:
        self.rows.setdefault("_exec", []).append(sql)
        return 1


class FakeHub:
    def __init__(self, **rows: Any) -> None:
        self.rows = rows
        self.settings = SimpleNamespace(
            support_egress_url="http://egress:8090",
            media=True,
            public_origin="https://hq.example",
            llm_router_url="http://router",
        )
        self.secrets = SimpleNamespace(
            llm_router_token="t" * 8,
            agent_token_key=b"k" * 32,
            telegram_bot_token="",
        )
        self.bao_data: dict[str, dict[str, Any]] = {}
        self.stored: dict[str, bytes] = {}
        self.channels = None
        hub = self

        class Companies:
            async def by_code(self, code: str) -> Any:
                return CO

            async def ids(self) -> list[UUID]:
                return [CO.id]

            async def holding(self) -> Any:
                return CO

        class Db:
            @asynccontextmanager
            async def tx(self, _ids: Any) -> Any:
                yield FakeTx(hub.rows)

        class Bao:
            async def read_kv(self, path: str) -> dict[str, Any]:
                if path not in hub.bao_data:
                    raise KeyError(path)
                return hub.bao_data[path]

        class Storage:
            async def put(self, data: bytes) -> tuple[str, str]:
                key = f"k{len(hub.stored)}"
                hub.stored[key] = data
                return key, "0" * 64

            async def get(self, key: str) -> bytes:
                return hub.stored[key]

        self.companies, self.db, self.bao, self.storage = Companies(), Db(), Bao(), Storage()


def out(text: str | None = None, **kw: Any) -> StepOutput:
    return StepOutput(text=text, **kw)


def ctx(
    hub: FakeHub,
    kind: str,
    *,
    settings: dict[str, Any] | None = None,
    prompt: str | None = "p",
    inputs: dict[str, StepOutput] | None = None,
    library: tuple[dict[str, Any], ...] = (),
    dry: bool = False,
    platform: str = "instagram_reel",
    key: str | None = None,
    timeout_s: int = 30,
) -> StepContext:
    return StepContext(
        run_ref="LR-000001",
        line_ref="LN-0001",
        company="AB",
        platform=platform,
        channel={"kind": "page", "subject": "page_a"},
        step={
            "key": key or kind,
            "kind": kind,
            "settings": settings or {},
            "timeout_s": timeout_s,
            "title_fa": "عنوان",
        },
        prompt=prompt,
        inputs=inputs or {},
        library=library,
        dry=dry,
        hub=hub,
    )


class FakeWeb:
    """The egress profile-browser client (POST /v1/substitutes/web)."""

    def __init__(self, *answers: dict[str, Any]) -> None:
        self.answers = list(answers)
        self.sent: list[dict[str, Any]] = []

    async def job(self, hub: Any, body: dict[str, Any], limit_s: float) -> dict[str, Any]:
        self.sent.append(body)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


@pytest.fixture(autouse=True)
def quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def instant(_s: float) -> None:
        return None

    async def unlocked(_tx: Any) -> None:
        return None

    monkeypatch.setattr(C, "sleep", instant)
    monkeypatch.setattr(C.gate, "holding_lock", unlocked)
    monkeypatch.setattr(C, "WEB_OVERRIDE", None)
    monkeypatch.setattr(C, "ROUTER_OVERRIDE", None)
    monkeypatch.setattr(CN, "OVERRIDE", None)
    monkeypatch.setattr(SP, "OVERRIDE", None)
    monkeypatch.setattr(n8n, "SEND_OVERRIDE", None)


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Files an adapter stores (the database insert is the engine's and the studio's concern)."""
    got: list[dict[str, Any]] = []

    async def store(
        hub: Any, company_id: UUID, data: bytes, *, name: str, mime: str, **kw: Any
    ) -> UUID:
        got.append({"name": name, "mime": mime, "data": data})
        return uuid4()

    monkeypatch.setattr(C, "store_file", store)
    return got


# ---------------------------------------------------------------- registry --
def test_every_step_kind_with_an_adapter_here_is_registered() -> None:
    mine = {"gpt_text", "tts", "pattern_search", "council_pick", "opus_build", "render", "cover",
            "publish", "deliver", "n8n"}  # fmt: skip
    assert mine <= set(REGISTRY)
    for kind in mine:
        assert REGISTRY[kind].kind == kind


# ---------------------------------------------------------------- gpt_text --
async def test_gpt_text_returns_the_answer_with_its_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def ask(
        c: StepContext, text: str, *, player: str = "gpt", timeout_s: int | None = None
    ) -> Any:
        seen.update(text=text, player=player)
        return {"text": " سلام \n", "tokens": 120, "usd_equiv": "0.0123", "model": "gpt-5.5"}

    monkeypatch.setattr(C, "ask_seat", ask)
    res = await REGISTRY["gpt_text"].run(ctx(FakeHub(), "gpt_text", prompt="بنویس"))
    assert (res.text, res.via, res.tokens, str(res.usd_equiv)) == (
        "سلام",
        "chatgpt-web",
        120,
        "0.0123",
    )
    assert seen == {"text": "بنویس", "player": "gpt"}


async def test_gpt_text_fails_plainly_on_an_empty_prompt_or_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(StepFailed) as e:
        await REGISTRY["gpt_text"].run(ctx(FakeHub(), "gpt_text", prompt="  "))
    assert "خالی" in e.value.reason_fa

    async def empty(*a: Any, **k: Any) -> Any:
        return {"text": " ", "tokens": 0, "usd_equiv": 0, "model": None}

    monkeypatch.setattr(C, "ask_seat", empty)
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["gpt_text"].run(ctx(FakeHub(), "gpt_text"))
    assert e2.value.retry and "خالی" in e2.value.reason_fa


class Calls:
    """The substitute call's life: queued, then the rows the poll sees."""

    def __init__(self, *states: dict[str, Any]) -> None:
        self.states = list(states)


def seat_world(monkeypatch: pytest.MonkeyPatch, *, call_state: str = "queued", reason: str | None = None,
                guard: str | None = None, found: bool = True) -> list[Any]:  # fmt: skip
    abandoned: list[Any] = []

    async def abandon(tx: Any, hub: Any, call_id: Any) -> bool:
        abandoned.append(call_id)
        return True

    async def text_seat(tx: Any, player: str) -> Any:
        return ({"player": player}, {"seat": "assistant_errand"}) if found else None

    async def guard_(tx: Any, hub: Any, seat: str, text: str) -> str | None:
        return guard

    async def seat_call(tx: Any, hub: Any, who: Any, **kw: Any) -> dict[str, Any]:
        assert kw["seat"] == "assistant_errand" and kw["purpose"] == ("lines", "LR-000001")
        return {"id": uuid4(), "state": call_state, "state_reason": reason}

    async def full_text(tx: Any, hub: Any, result: Any) -> str:
        return str((result or {}).get("text_md") or "")

    monkeypatch.setattr(C.players, "text_seat", text_seat)
    monkeypatch.setattr(C.S, "guard", guard_)
    monkeypatch.setattr(C.S, "seat_call", seat_call)
    monkeypatch.setattr(C.S, "full_text", full_text)
    monkeypatch.setattr(C.S, "abandon", abandon)
    return abandoned


async def test_the_seat_call_waits_for_the_answer_and_reads_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seat_world(monkeypatch)
    rows = iter([{"state": "queued"}, {"state": "running"},
                 {"state": "done", "result": {"text_md": "جواب"}, "input_tokens": 5,
                  "output_tokens": 7, "equiv_usd": 0.5, "model": "gpt-5.3"}])  # fmt: skip
    hub = FakeHub(**{"FROM substitutes.calls": lambda: next(rows)})
    got = await C.ask_seat(ctx(hub, "gpt_text"), "سؤال")
    assert got["text"] == "جواب" and got["tokens"] == 12 and got["model"] == "gpt-5.3"


@pytest.mark.parametrize(
    ("state", "reason", "guard", "found", "word"),
    [
        ("skipped", "signed_out", None, True, "وارد نشده"),
        ("skipped", "expired", None, True, "منقضی"),
        ("skipped", "per_day", None, True, "سقف روزانه"),
        ("skipped", "holding_locked", None, True, "قفل"),
        ("queued", None, "personal_or_secret_data", True, "محرمانه"),
        ("queued", None, None, False, "خاموش"),
    ],
)
async def test_a_signed_out_or_limited_chatgpt_is_a_plain_failure_never_another_model(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    reason: str | None,
    guard: str | None,
    found: bool,
    word: str,
) -> None:
    seat_world(monkeypatch, call_state=state, reason=reason, guard=guard, found=found)
    with pytest.raises(StepFailed) as e:
        await C.ask_seat(ctx(FakeHub(), "gpt_text"), "x")
    assert word in e.value.reason_fa and e.value.reason_fa.startswith("ChatGPT")


async def test_a_call_that_never_answers_times_out_plainly(monkeypatch: pytest.MonkeyPatch) -> None:
    abandoned = seat_world(monkeypatch)
    hub = FakeHub(**{"FROM substitutes.calls": {"state": "running"}})
    with pytest.raises(StepFailed) as e:
        await C.ask_seat(ctx(hub, "gpt_text", timeout_s=10), "x")
    assert e.value.code == "timeout" and "به موقع" in e.value.reason_fa
    # ⟨2026-11-11⟩ its call ends with it (no orphan in the player's queue, no daily cap eaten)
    assert len(abandoned) == 1


# --------------------------------------------------------------------- tts --
async def test_tts_asks_aistudio_for_the_voice_and_style_and_stores_the_audio(
    stored: list[dict[str, Any]],
) -> None:
    web = FakeWeb({"ok": True, "file": {"name": "a.wav", "mime": "audio/wav", "b64": b64(WAV)}})
    C.WEB_OVERRIDE = web
    script = out("سلام دنیا")
    res = await REGISTRY["tts"].run(
        ctx(
            FakeHub(),
            "tts",
            settings={"voice": "Puck", "style": "گرم", "text_from": "script"},
            inputs={"script": script},
            key="voice",
        )
    )
    sent = web.sent[0]
    assert (sent["account"], sent["task"], sent["prompt"]) == ("aistudio-web", "tts", "سلام دنیا")
    assert (sent["voice"], sent["style"]) == ("Puck", "گرم")
    assert res.via == "aistudio-web" and res.file_id and res.data["voice"] == "Puck"
    assert stored[0]["mime"] == "audio/wav" and stored[0]["name"].endswith("-voice.wav")


@pytest.mark.parametrize(
    ("answer", "word"),
    [
        ({"ok": False, "error": "expired"}, "make aistudio-web-login"),
        ({"ok": False, "error": "recipe_failed", "step": "3:select"}, "3:select"),
        ({"ok": False, "error": "timeout"}, "به موقع"),
        ({"ok": False, "error": "off"}, "خاموش"),
        ({"ok": True, "file": {"name": "x.png", "mime": "image/png", "b64": b64(PNG)}}, "صدا نبود"),
        ({"ok": True, "file": None}, "فایلی"),
    ],
)
async def test_tts_failures_are_plain_persian(
    answer: dict[str, Any], word: str, stored: list[Any]
) -> None:
    C.WEB_OVERRIDE = FakeWeb(answer)
    with pytest.raises(StepFailed) as e:
        await REGISTRY["tts"].run(ctx(FakeHub(), "tts", prompt="متن"))
    assert word in e.value.reason_fa


async def test_tts_refuses_an_empty_or_too_long_text_and_waits_out_a_busy_profile(
    stored: list[Any],
) -> None:
    with pytest.raises(StepFailed):
        await REGISTRY["tts"].run(ctx(FakeHub(), "tts", prompt=None))
    with pytest.raises(StepFailed) as e:
        await REGISTRY["tts"].run(ctx(FakeHub(), "tts", prompt="ا" * 5001))
    assert "بلند" in e.value.reason_fa
    web = FakeWeb(
        {"ok": False, "error": "busy"},
        {"ok": True, "file": {"name": "a.wav", "mime": "audio/wav", "b64": b64(WAV)}},
    )
    C.WEB_OVERRIDE = web
    res = await REGISTRY["tts"].run(ctx(FakeHub(), "tts", prompt="متن"))
    assert res.file_id and len(web.sent) == 2  # tried again after the profile was busy


async def test_the_voices_list_is_documented_cached_and_labelled() -> None:
    rows = await tts.voices(now=1000.0)
    assert len(rows) == 30 and {r["source"] for r in rows} == {"documented"}
    assert {"name", "title_fa", "gender", "sample_file"} <= set(rows[0])
    assert {"Kore", "Puck", "Charon"} <= {r["name"] for r in rows}
    rows[0]["name"] = "changed"
    assert (await tts.voices(now=1500.0))[0]["name"] != "changed"  # a copy of the day's cache


# ---------------------------------------------------------- pattern_search --
PINS = [{"image": "https://i.pinimg.com/a.jpg", "link": "https://www.pinterest.com/pin/1/", "title": "الف"},
        {"image": "https://i.pinimg.com/b.jpg", "link": "https://www.pinterest.com/pin/2/", "title": "ب"},
        {"image": "http://insecure/c.jpg", "link": "", "title": "ج"}]  # fmt: skip


async def test_pattern_search_returns_the_top_pins_read_only() -> None:
    web = FakeWeb({"ok": True, "text_md": json.dumps(PINS)})
    C.WEB_OVERRIDE = web
    res = await REGISTRY["pattern_search"].run(
        ctx(FakeHub(), "pattern_search", prompt="موشن گرافیک", settings={"limit": 2})
    )
    assert web.sent[0]["account"] == "pinterest-web" and web.sent[0]["task"] == "search"
    assert (web.sent[0]["prompt"], web.sent[0]["limit"]) == ("موشن گرافیک", 2)
    assert [p["title"] for p in res.data["items"]] == ["الف", "ب"]  # the insecure pin is dropped
    assert res.via == "pinterest-web" and "pin/1" in str(res.text)


async def test_pattern_search_fails_plainly_with_no_query_no_pins_or_a_signed_out_profile() -> None:
    with pytest.raises(StepFailed):
        await REGISTRY["pattern_search"].run(ctx(FakeHub(), "pattern_search", prompt=""))
    C.WEB_OVERRIDE = FakeWeb({"ok": True, "text_md": "[]"})
    with pytest.raises(StepFailed) as e:
        await REGISTRY["pattern_search"].run(ctx(FakeHub(), "pattern_search", prompt="x"))
    assert "پیدا نشد" in e.value.reason_fa
    C.WEB_OVERRIDE = FakeWeb({"ok": False, "error": "expired"})
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["pattern_search"].run(ctx(FakeHub(), "pattern_search", prompt="x"))
    assert "پینترست" in e2.value.reason_fa


# ------------------------------------------------------------ council_pick --
def council_world(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> list[str]:
    asked: list[str] = []

    async def roles(tx: Any) -> dict[str, str]:
        return {"claude": "captain", "gemini": "researcher", "deepseek": "numbers", "gpt": "devil"}

    async def ask(
        c: StepContext, text: str, *, player: str = "gpt", timeout_s: int | None = None
    ) -> Any:
        asked.append(player)
        a = answers[player]
        if isinstance(a, StepFailed):
            raise a
        return {"text": a, "tokens": 10, "usd_equiv": 0, "model": "m"}

    monkeypatch.setattr(council_pick.CV, "roles", roles)
    monkeypatch.setattr(C, "ask_seat", ask)
    return asked


PICK_INPUT = {
    "patterns": out(
        "1. الف\n2. ب\n3. ج", data={"items": [{"title": "الف"}, {"title": "ب"}, {"title": "ج"}]}
    )
}


async def test_the_council_picks_the_most_voted_candidate_with_reasons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    council_world(monkeypatch, {
        "gemini": '{"pick": 2, "reason_fa": "خواناتر است"}',
        "deepseek": '```json\n{"pick": 2, "reason_fa": "ساده‌تر است"}\n```',
        "gpt": '{"pick": 3, "reason_fa": "متفاوت است"}',
    })  # fmt: skip
    res = await REGISTRY["council_pick"].run(
        ctx(FakeHub(), "council_pick", inputs=PICK_INPUT, settings={"candidates_from": "patterns"})
    )
    assert res.data["pick"] == 2 and res.data["chosen"]["title"] == "ب" and res.tokens == 30
    assert "خواناتر است" in str(res.text) and "گزینه‌ی برگزیده: ب" in str(res.text)


async def test_a_tie_goes_to_the_researcher_and_a_silent_member_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    council_world(monkeypatch, {
        "gemini": '{"pick": 3, "reason_fa": "الف"}',
        "deepseek": '{"pick": 1, "reason_fa": "ب"}',
        "gpt": StepFailed("ChatGPT: ورود حساب منقضی شده؛ مالک باید دوباره وارد شود."),
    })  # fmt: skip
    res = await REGISTRY["council_pick"].run(ctx(FakeHub(), "council_pick", inputs=PICK_INPUT))
    assert res.data["pick"] == 3 and len(res.data["votes"]) == 2
    assert "منقضی" in str(res.text)  # the member left out is told, not hidden


async def test_with_no_answer_at_all_the_pick_fails_and_one_candidate_needs_no_council(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    down = StepFailed("x")
    asked = council_world(monkeypatch, {"gemini": down, "deepseek": down, "gpt": "هیچ عددی نیست"})
    with pytest.raises(StepFailed) as e:
        await REGISTRY["council_pick"].run(ctx(FakeHub(), "council_pick", inputs=PICK_INPUT))
    assert "شورا جواب نداد" in e.value.reason_fa and len(asked) == 3
    asked.clear()
    one = {"p": out("فقط یکی", data={"items": [{"title": "یکی"}]})}
    res = await REGISTRY["council_pick"].run(ctx(FakeHub(), "council_pick", inputs=one))
    assert res.data["pick"] == 1 and not asked
    with pytest.raises(StepFailed):
        await REGISTRY["council_pick"].run(ctx(FakeHub(), "council_pick"))


# -------------------------------------------------------------- opus_build --
HTML = (
    '<html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>'
    "html,body{margin:0;width:1080px;height:1920px;background:#ffffff}"
    ".t{font-family:IRANYekanX;font-size:64px;color:#000000;animation:in 1s both}"
    "@keyframes in{from{opacity:0}to{opacity:1}}</style></head>"
    '<body><div class="t">سلام</div></body></html>'
)
GOOD = {"composition": {"format": "html", "source": HTML},
        "direction": {"shots": [{"duration_s": 3, "text_fa": "سلام", "visual_fa": "متن"}]},
        "duration_s": 3, "caption_fa": "کپشن تست", "hashtags": ["#آموزش", "ترید", "#آموزش"],
        "title_fa": "عنوان", "description_fa": "توضیح"}  # fmt: skip


class FakeRouter:
    def __init__(self, *calls: ModelCall) -> None:
        self.calls = list(calls)
        self.bodies: list[dict[str, Any]] = []

    async def run(self, body: dict[str, Any], timeout_s: int) -> ModelCall:
        self.bodies.append(body)
        return self.calls.pop(0)


def mc(text: str | None, *, ok: bool = True, code: str | None = None) -> ModelCall:
    return ModelCall(ok, "ok" if ok else "error", code, "c1", "claude-opus-5-5", "high", "claude",
                     None, text, input_tokens=100, output_tokens=50, equiv_cost_usd="0.4")  # fmt: skip


async def test_opus_build_calls_the_router_at_effort_high_and_validates_the_spec() -> None:
    router = FakeRouter(mc(json.dumps(GOOD, ensure_ascii=False)))
    C.ROUTER_OVERRIDE = router
    res = await REGISTRY["opus_build"].run(ctx(FakeHub(), "opus_build", prompt="بساز", key="build"))
    body = router.bodies[0]
    assert (body["task_class"], body["effort"], body["model"]) == (
        "line_build",
        "high",
        "claude-opus-5-5",
    )
    assert body["company_code"] == "AB" and body["meta"] == {"purpose": "line_build"}
    spec = res.data["spec"]
    assert spec["composition"]["format"] == "html" and spec["direction"]["shots"]
    assert res.data["hashtags"] == ["#آموزش", "#ترید"] and res.data["caption"] == "کپشن تست"
    assert (
        res.text == "کپشن تست\n\n#آموزش #ترید" and res.tokens == 150 and str(res.usd_equiv) == "0.4"
    )
    assert res.via == "router:claude-opus-5-5"


async def test_a_bad_spec_is_told_once_then_the_step_fails_plainly() -> None:
    bad = {**GOOD, "composition": {"format": "html", "source": "<html>fetch('x')</html>"}}
    router = FakeRouter(mc(json.dumps(bad)), mc(json.dumps(GOOD, ensure_ascii=False)))
    C.ROUTER_OVERRIDE = router
    res = await REGISTRY["opus_build"].run(ctx(FakeHub(), "opus_build"))
    assert res.data["attempt"] == 2 and "پذیرفته نشد" in router.bodies[1]["prompt"]
    assert res.tokens == 300
    C.ROUTER_OVERRIDE = FakeRouter(mc("نه JSON"), mc("{}"))
    with pytest.raises(StepFailed) as e:
        await REGISTRY["opus_build"].run(ctx(FakeHub(), "opus_build"))
    assert e.value.code == "bad_spec" and e.value.retry


async def test_a_router_refusal_is_never_hidden_behind_another_model() -> None:
    router = FakeRouter(mc(None, ok=False, code="quota"))
    C.ROUTER_OVERRIDE = router
    with pytest.raises(StepFailed) as e:
        await REGISTRY["opus_build"].run(ctx(FakeHub(), "opus_build"))
    assert "جایگزین بی‌صدا" in e.value.reason_fa and len(router.bodies) == 1


def test_validate_names_what_is_wrong() -> None:
    for bad, word in [
        ({**GOOD, "composition": {"format": "pdf", "source": "x"}}, "format"),
        ({**GOOD, "direction": {"shots": []}}, "shot"),
        ({**GOOD, "direction": {"shots": [{"text_fa": "x"}]}}, "duration_s"),
        ({**GOOD, "caption_fa": " "}, "caption_fa"),
    ]:
        with pytest.raises(ValueError, match=word):
            opus_build.validate(bad)


# ------------------------------------------------------------------ render --
def build_out() -> StepOutput:
    return out("cap", data={"spec": opus_build.validate(GOOD), "title": "عنوان"})


async def test_render_fails_plainly_when_the_media_profile_is_off_or_the_spec_is_missing() -> None:
    hub = FakeHub()
    hub.settings.media = False
    with pytest.raises(StepFailed) as e:
        await REGISTRY["render"].run(ctx(hub, "render", inputs={"build": build_out()}))
    assert "media" in e.value.reason_fa and e.value.code == "media_off"
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["render"].run(ctx(FakeHub(), "render", inputs={"build": out("x")}))
    assert e2.value.code == "no_spec"
    with pytest.raises(StepFailed) as e3:
        await REGISTRY["render"].run(
            ctx(FakeHub(), "render", inputs={"build": build_out()}, settings={"where": "mars"})
        )
    assert e3.value.code == "bad_where"


async def test_render_hands_the_spec_to_the_studio_and_waits_for_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fid, job = uuid4(), uuid4()
    item = {"id": uuid4(), "ref": "MI-0001", "render_file_id": fid,
            "outputs": [{"file_id": str(fid), "width": 1080, "height": 1920, "duration_s": 3.0}]}  # fmt: skip
    queued: dict[str, Any] = {}
    polls = iter([{"state": "queued"}, {"state": "claimed"}, {"state": "done"}])

    async def load_item(tx: Any, ref: str, lock: bool = False) -> dict[str, Any]:
        return item

    async def check(tx: Any, it: Any, fmt: str, source: str) -> Any:
        return SimpleNamespace(sha256="a" * 64, assets=[], as_dict=dict)

    async def queue_render(tx: Any, hub: Any, it: Any, *, purpose: str, by: str) -> dict[str, Any]:
        queued.update(purpose=purpose, by=by)
        return {"job": job, "purpose": purpose}

    monkeypatch.setattr(ST, "load_item", load_item)
    monkeypatch.setattr(ST, "check_composition", check)
    monkeypatch.setattr(ST, "queue_render", queue_render)
    hub = FakeHub(**{"INSERT INTO media.items": {"id": item["id"], "ref": "MI-0001"},
                     "INSERT INTO media.compositions": uuid4(),
                     "FROM media.render_jobs": lambda: next(polls)})  # fmt: skip
    voice = out(file_id=str(uuid4()), data={"mime": "audio/wav"})
    res = await REGISTRY["render"].run(
        ctx(hub, "render", inputs={"build": build_out(), "voice": voice}, platform="instagram_reel")
    )
    assert queued == {"purpose": "final", "by": "lines"}
    assert res.file_id == str(fid) and res.via == "media-studio" and res.data["item"] == "MI-0001"
    assert any(
        "line_run_ref = :run" in s for s in hub.rows["_exec"]
    )  # marked as the line's: the studio's review and publishing skip it


async def test_a_failed_render_is_a_plain_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    job = uuid4()

    async def load_item(tx: Any, ref: str, lock: bool = False) -> dict[str, Any]:
        return {"id": uuid4(), "ref": "MI-0002"}

    async def check(tx: Any, it: Any, fmt: str, source: str) -> Any:
        return SimpleNamespace(sha256="a" * 64, assets=[], as_dict=dict)

    async def queue_render(tx: Any, hub: Any, it: Any, *, purpose: str, by: str) -> dict[str, Any]:
        return {"job": job}

    monkeypatch.setattr(ST, "load_item", load_item)
    monkeypatch.setattr(ST, "check_composition", check)
    monkeypatch.setattr(ST, "queue_render", queue_render)
    hub = FakeHub(**{"INSERT INTO media.items": {"id": uuid4(), "ref": "MI-0002"},
                     "INSERT INTO media.compositions": uuid4(),
                     "FROM media.render_jobs": {"state": "failed", "error": "schema: x"}})  # fmt: skip
    with pytest.raises(StepFailed) as e:
        await REGISTRY["render"].run(ctx(hub, "render", inputs={"build": build_out()}))
    assert "قواعد رندر" in e.value.reason_fa and not e.value.retry


async def test_the_company_render_needs_its_server_and_command() -> None:
    with pytest.raises(StepFailed) as e:
        await REGISTRY["render"].run(
            ctx(FakeHub(), "render", inputs={"build": build_out()}, settings={"where": "company"})
        )
    assert e.value.code == "not_set"


# ------------------------------------------------------------------- cover --
def folder(*files: UUID) -> dict[str, Any]:
    return {"id": "A1", "kind": "cover_folder", "files": [str(f) for f in files]}


async def test_cover_sends_the_folders_images_to_chatgpt_and_stores_the_image(
    stored: list[dict[str, Any]],
) -> None:
    f1, f2 = uuid4(), uuid4()
    hub = FakeHub(**{"FROM files.files": lambda: {"id": f1, "name": "a.png", "mime": "image/png",
                                                  "storage_key": "k0", "kind": "image"}})  # fmt: skip
    hub.stored["k0"] = PNG
    web = FakeWeb({"ok": True, "file": {"name": "cover.png", "mime": "image/png", "b64": b64(PNG)}})
    C.WEB_OVERRIDE = web
    res = await REGISTRY["cover"].run(
        ctx(
            hub, "cover", prompt="کاور بساز", library=(folder(f1, f2), {"kind": "voice", "id": "V"})
        )
    )
    sent = web.sent[0]
    assert (sent["account"], sent["task"], sent["prompt"]) == ("chatgpt-web", "cover", "کاور بساز")
    assert len(sent["files"]) == 2 and sent["files"][0]["name"] == "a.png"
    assert res.file_id and res.data["from_files"] == 2 and stored[0]["mime"] == "image/png"


async def test_cover_fails_plainly_without_a_folder_or_images_or_an_image_back(
    stored: list[Any],
) -> None:
    with pytest.raises(StepFailed) as e:
        await REGISTRY["cover"].run(ctx(FakeHub(), "cover"))
    assert e.value.code == "no_cover_folder"
    hub = FakeHub(**{"FROM files.files": {"id": uuid4(), "name": "n.txt", "mime": "text/plain",
                                          "storage_key": "k0", "kind": "document"}})  # fmt: skip
    hub.stored["k0"] = b"x"
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["cover"].run(ctx(hub, "cover", library=(folder(uuid4()),)))
    assert e2.value.code == "empty_folder"
    hub.rows["FROM files.files"] = {
        "id": uuid4(),
        "name": "a.png",
        "mime": "image/png",
        "storage_key": "k0",
        "kind": "image",
    }
    hub.stored["k0"] = PNG
    C.WEB_OVERRIDE = FakeWeb(
        {"ok": True, "file": {"name": "x.mp4", "mime": "video/mp4", "b64": b64(MP4)}}
    )
    with pytest.raises(StepFailed) as e3:
        await REGISTRY["cover"].run(ctx(hub, "cover", library=(folder(uuid4()),)))
    assert e3.value.code == "not_image"


# ----------------------------------------------------------------- publish --
class FakeHttp:
    def __init__(self, *answers: CN.Answer) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kw: Any) -> CN.Answer:
        self.calls.append({"method": method, "url": url, **kw})
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


def ok(doc: dict[str, Any], status: int = 200) -> CN.Answer:
    return CN.Answer("ok", status=status, body=json.dumps(doc))


def reel_hub() -> FakeHub:
    hub = FakeHub(**{"FROM growth.connections": {"config": {"base_url": "https://ighub.example", "account": "page_a"}},
                     "FROM files.files": {"id": uuid4(), "name": "r.mp4", "mime": "video/mp4",
                                          "storage_key": "k0", "kind": "video"}})  # fmt: skip
    hub.bao_data["hq/growth/AB/instagram"] = {"secret": "TOKEN-INSTAGRAM-123456"}
    hub.stored["k0"] = MP4
    return hub


def pub_inputs() -> dict[str, StepOutput]:
    return {
        "render": out(file_id=str(uuid4()), data={"duration_s": 30}),
        "cover": out(file_id=str(uuid4())),
        "build": out("cap", data={"caption": "کپشن", "hashtags": ["#الف", "#ب"], "title": "عنوان",
                                  "description": "توضیح"}),
    }  # fmt: skip


async def test_a_dry_publish_answers_without_leaving(monkeypatch: pytest.MonkeyPatch) -> None:
    CN.OVERRIDE = FakeHttp(ok({}))
    res = await REGISTRY["publish"].run(ctx(FakeHub(), "publish", inputs=pub_inputs(), dry=True))
    assert res.data["dry"] is True and res.data["would_publish"]["has_cover"] is True
    assert res.data["would_publish"]["platform"] == "instagram_reel" and not CN.OVERRIDE.calls  # type: ignore[union-attr]
    for platform in ("youtube_short", "telegram_post", "site_article"):
        got = await REGISTRY["publish"].run(
            ctx(FakeHub(), "publish", platform=platform, inputs=pub_inputs(), dry=True)
        )
        assert got.data["dry"] is True


async def test_an_instagram_reel_goes_to_ighub_with_signed_urls_and_the_cover() -> None:
    http = FakeHttp(
        ok({"id": "ighub-1", "state": "scheduled", "url": None, "cover_set": True}, 202)
    )
    CN.OVERRIDE = http
    res = await REGISTRY["publish"].run(
        ctx(
            reel_hub(),
            "publish",
            inputs=pub_inputs(),
            settings={"kind": "reel", "in_min": 60},
            key="publish",
        )
    )
    call = http.calls[0]
    assert call["method"] == "POST" and call["url"] == "https://ighub.example/v1/publish/reel"
    assert (
        call["account"]["inject"] == {"kind": "bearer"}
        and call["account"]["site"] == "ighub.example"
    )
    body = call["json_body"]
    assert body["media_url"].startswith("https://hq.example/public/v1/media/")
    assert body["cover_url"].startswith("https://hq.example/public/v1/media/")
    assert (
        body["caption"] == "کپشن\n\n#الف #ب" and body["publish_at"] and body["account"] == "page_a"
    )
    assert call["headers"]["Idempotency-Key"] == "LR-000001:publish"
    assert res.via == "ig-hub" and res.data["published"]["external_id"] == "ighub-1"
    assert res.data["published"]["platform"] == "instagram_reel" and res.data["cover_set"] is True


async def test_a_cover_the_platform_cannot_set_is_returned_for_the_deliver_step() -> None:
    CN.OVERRIDE = FakeHttp(ok({"id": "x", "state": "published", "cover_set": False}))
    res = await REGISTRY["publish"].run(
        ctx(reel_hub(), "publish", inputs=pub_inputs(), settings={"kind": "reel"})
    )
    assert res.data["cover_set"] is False


async def test_the_story_comes_the_same_day_after_the_reel_and_takes_no_caption_or_cover() -> None:
    http = FakeHttp(ok({"id": "st-1", "state": "scheduled"}, 202))
    CN.OVERRIDE = http
    first = out(data={"published": {"at": "2026-11-05T06:00:00+00:00"}})
    inputs = {**pub_inputs(), "publish": first}
    res = await REGISTRY["publish"].run(
        ctx(
            reel_hub(),
            "publish",
            inputs=inputs,
            key="story",
            settings={
                "kind": "story",
                "media_from": "render",
                "after": "publish",
                "delay_min": 180,
            },
        )
    )
    call = http.calls[0]
    assert call["url"].endswith("/v1/publish/story")
    assert "caption" not in call["json_body"] and "cover_url" not in call["json_body"]
    assert call["json_body"]["publish_at"] == "2026-11-05T09:00:00+00:00"
    assert res.data["published"]["kind"] == "story" and "cover_set" not in res.data


@pytest.mark.parametrize(
    ("hub_fix", "answer", "word"),
    [
        ("no_url", ok({}), "آدرس API"),
        ("no_token", ok({}), "توکن"),
        (None, CN.Answer("error", code="host_not_allowed"), "فهرست مجاز"),
        (None, ok({}, 401), "نپذیرفت"),
        (None, ok({}, 429), "سقف"),
        (None, ok({"error_fa": "کاور نامعتبر است"}, 400), "کاور نامعتبر است"),
    ],
)
async def test_instagram_failures_are_plain(
    hub_fix: str | None, answer: CN.Answer, word: str
) -> None:
    hub = reel_hub()
    if hub_fix == "no_url":
        hub.rows["FROM growth.connections"] = {"config": {}}
    if hub_fix == "no_token":
        hub.bao_data.clear()
    CN.OVERRIDE = FakeHttp(answer)
    with pytest.raises(StepFailed) as e:
        await REGISTRY["publish"].run(
            ctx(hub, "publish", inputs=pub_inputs(), settings={"kind": "reel"})
        )
    assert word in e.value.reason_fa


class FakePublisher:
    def __init__(self, *outs: dict[str, Any]) -> None:
        self.outs = list(outs)
        self.calls: list[tuple[dict[str, Any], list[tuple[str, bytes, str]]]] = []

    async def call(
        self, hub: Any, call: dict[str, Any], files: list[tuple[str, bytes, str]]
    ) -> dict[str, Any]:
        self.calls.append((call, files))
        return self.outs.pop(0) if len(self.outs) > 1 else self.outs[0]


async def test_a_youtube_short_uploads_through_egress_with_a_fresh_token() -> None:
    hub = reel_hub()
    hub.bao_data["hq/growth/AB/youtube"] = {
        "client_id": "cid",
        "client_secret": "csec",
        "refresh_token": "rtok",
    }
    http = FakeHttp(ok({"access_token": "ya29.ACCESS-TOKEN-0000000000"}))
    CN.OVERRIDE = http
    SP.OVERRIDE = pubr = FakePublisher({"outcome": "ok", "data": {"video_id": "VID1"}})
    res = await REGISTRY["publish"].run(
        ctx(
            hub,
            "publish",
            platform="youtube_short",
            inputs=pub_inputs(),
            settings={"kind": "short", "privacy": "public"},
        )
    )
    assert (
        http.calls[0]["url"] == publish.YT_TOKEN_URL
        and "grant_type=refresh_token" in http.calls[0]["body"]
    )
    call, files = pubr.calls[0]
    assert call["channel"] == "youtube" and call["method"] == "upload"
    assert call["payload"]["title"] == "عنوان" and "#Shorts" in call["payload"]["description"]
    assert (
        files[0][1] == MP4 and res.data["published"]["url"] == "https://www.youtube.com/shorts/VID1"
    )


async def test_youtube_fails_plainly_for_a_long_short_no_connection_or_a_limit() -> None:
    hub = reel_hub()
    long_in = {**pub_inputs(), "render": out(file_id=str(uuid4()), data={"duration_s": 75})}
    with pytest.raises(StepFailed) as e:
        await REGISTRY["publish"].run(
            ctx(
                hub, "publish", platform="youtube_short", inputs=long_in, settings={"kind": "short"}
            )
        )
    assert "۶۰ ثانیه" in e.value.reason_fa
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["publish"].run(
            ctx(
                hub,
                "publish",
                platform="youtube_long",
                inputs=pub_inputs(),
                settings={"kind": "video"},
            )
        )
    assert e2.value.code == "not_connected"
    hub.bao_data["hq/growth/AB/youtube"] = {
        "secret": json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r"})
    }
    CN.OVERRIDE = FakeHttp(ok({"access_token": "ya29.ACCESS-TOKEN-0000000000"}))
    SP.OVERRIDE = FakePublisher({"outcome": "error", "code": "platform_limit"})
    with pytest.raises(StepFailed) as e3:
        await REGISTRY["publish"].run(
            ctx(
                hub,
                "publish",
                platform="youtube_long",
                inputs=pub_inputs(),
                settings={"kind": "video"},
            )
        )
    assert e3.value.retry and "سقف" in e3.value.reason_fa


async def test_a_telegram_post_uses_the_studios_publisher_with_the_ai_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def account(hub: Any, key: str) -> Any:
        assert key == "telegram-ab"
        return {"key": key, "policy": {"inject": {"username": "@chan_ab"}}}, "123456789:" + "x" * 35

    monkeypatch.setattr(SP, "_account", account)
    SP.OVERRIDE = pubr = FakePublisher({"outcome": "ok", "data": {"message_id": 42}})
    hub = reel_hub()
    hub.rows["FROM files.files"] = {
        "id": uuid4(),
        "name": "c.png",
        "mime": "image/png",
        "storage_key": "k0",
        "kind": "image",
    }
    hub.stored["k0"] = PNG
    inputs = {"cover": out(file_id=str(uuid4())), "write": out("متن پست", data={})}
    res = await REGISTRY["publish"].run(
        ctx(
            hub,
            "publish",
            platform="telegram_post",
            inputs=inputs,
            settings={"kind": "message", "media_from": "cover", "text_from": "write"},
        )
    )
    call, files = pubr.calls[0]
    assert (call["method"], call["payload"]["chat_id"]) == ("sendPhoto", "@chan_ab")
    assert call["payload"]["caption"].endswith(SP.AI_LABEL) and files[0][2] == "image/png"
    assert res.data["published"]["url"] == "https://t.me/chan_ab/42"


async def test_the_site_is_not_connected_until_settings_say_wordpress() -> None:
    inputs = {"article": out("# عنوان\nمتن")}
    with pytest.raises(StepFailed) as e:
        await REGISTRY["publish"].run(
            ctx(
                FakeHub(),
                "publish",
                platform="site_article",
                inputs=inputs,
                settings={"kind": "article", "site": {}},
            )
        )
    assert e.value.reason_fa == "انتشار در سایت هنوز وصل نشده."
    hub = FakeHub()
    hub.bao_data["hq/growth/AB/site"] = {"secret": "app-password-xyz"}
    http = FakeHttp(ok({"id": 77, "link": "https://site.example/p/77"}, 201))
    CN.OVERRIDE = http
    res = await REGISTRY["publish"].run(
        ctx(
            hub,
            "publish",
            platform="site_article",
            inputs=inputs,
            settings={
                "kind": "article",
                "site": {"kind": "wordpress", "base_url": "https://site.example", "user": "bot"},
            },
        )
    )
    call = http.calls[0]
    assert call["url"] == "https://site.example/wp-json/wp/v2/posts"
    assert call["account"]["inject"] == {"kind": "basic", "username": "bot"}
    assert call["json_body"]["title"] == "عنوان" and res.data["published"]["external_id"] == "77"


async def test_insights_read_the_figures_for_instagram_and_youtube() -> None:
    hub = reel_hub()
    hub.rows["FROM growth.connections"] = {"config": {"base_url": "https://ighub.example"}}
    http = FakeHttp(ok({"views": 1200, "likes": 80, "note": "x"}))
    CN.OVERRIDE = http
    got = await publish.insights(
        SimpleNamespace(hub=hub, company="AB"),
        {"platform": "instagram_reel", "external_id": "ighub-1"},
    )
    assert (
        got == {"views": 1200, "likes": 80}
        and http.calls[0]["url"] == "https://ighub.example/v1/insights/ighub-1"
    )
    hub.bao_data["hq/growth/AB/youtube"] = {
        "client_id": "c",
        "client_secret": "s",
        "refresh_token": "r",
    }
    CN.OVERRIDE = FakeHttp(
        ok({"access_token": "ya29.ACCESS-TOKEN-0000000000"}),
        ok({"items": [{"statistics": {"viewCount": "9", "likeCount": "2"}}]}),
    )
    got2 = await publish.insights(
        SimpleNamespace(hub=hub, company="AB"), {"platform": "youtube_short", "external_id": "V"}
    )
    assert got2 == {"viewCount": 9, "likeCount": 2}
    assert (
        await publish.insights(
            SimpleNamespace(hub=hub, company="AB"), {"platform": "x", "external_id": ""}
        )
        == {}
    )


# ----------------------------------------------------------------- deliver --
async def test_deliver_does_nothing_unless_the_cover_could_not_be_set() -> None:
    settings = {"only_if": "cover_not_set", "check": "publish", "file_from": "cover"}
    done = {"publish": out(data={"cover_set": True}), "cover": out(file_id=str(uuid4()))}
    res = await REGISTRY["deliver"].run(
        ctx(FakeHub(), "deliver", prompt=None, settings=settings, inputs=done)
    )
    assert res.data == {"skipped": True}
    dry = {"publish": out(data={"cover_set": False}), "cover": out(file_id=str(uuid4()))}
    res2 = await REGISTRY["deliver"].run(
        ctx(FakeHub(), "deliver", prompt=None, settings=settings, inputs=dry, dry=True)
    )
    assert res2.data["dry"] is True and "کاور" in str(res2.text) and res2.data["file_id"]


async def test_deliver_raises_the_app_card_and_the_telegram_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raised: dict[str, Any] = {}

    async def raise_notification(tx: Any, **kw: Any) -> dict[str, Any]:
        raised.update(kw)
        return {"id": uuid4(), "push_now": False}

    pushed: list[Any] = []

    class Channels:
        telegram = SimpleNamespace(configured=True)

        async def push(self, msg: Any) -> dict[str, bool]:
            pushed.append(msg)
            return {"telegram": True}

    monkeypatch.setattr(notify, "raise_notification", raise_notification)
    hub = FakeHub()
    hub.channels = Channels()
    inputs = {"publish": out(data={"cover_set": False}), "cover": out(file_id=str(uuid4()))}
    res = await REGISTRY["deliver"].run(
        ctx(
            hub,
            "deliver",
            prompt=None,
            inputs=inputs,
            settings={"only_if": "cover_not_set", "check": "publish"},
        )
    )
    assert (
        raised["link_kind"] == "line_run"
        and raised["link_ref"] == "LR-000001"
        and raised["owner_action"] is True
    )
    assert res.data["telegram"] is True and pushed[0].link_ref == "LR-000001"


# -------------------------------------------------------------------- n8n --
async def test_n8n_posts_the_signed_summary_and_waits_for_the_callback() -> None:
    sent: dict[str, Any] = {}

    async def send(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        sent.update(url=url, body=body, headers=headers)
        return 200, "ok"

    n8n.SEND_OVERRIDE = send
    hub = FakeHub()
    hub.bao_data["hq/n8n"] = {"secret": "s" * 40}
    res = await REGISTRY["n8n"].run(
        ctx(
            hub,
            "n8n",
            settings={"workflow": "line-callback-demo"},
            inputs={"article": out("متن" * 2000)},
            key="feedback",
        )
    )
    assert res.data == {
        "waiting": True,
        "token": "LR-000001:feedback",
        "workflow": "line-callback-demo",
    }
    assert sent["url"].endswith("/webhook/line-callback-demo")
    assert signing.verify("s" * 40, sent["body"], sent["headers"][signing.HEADER])
    doc = json.loads(sent["body"])
    assert doc["token"] == "LR-000001:feedback" and len(doc["inputs"]["article"]["text"]) == 4000
    assert doc["callback"] == "http://api:8000/internal/v1/lines/callback"


async def test_n8n_failures_are_plain_and_a_dry_run_calls_nothing() -> None:
    hub = FakeHub()
    with pytest.raises(StepFailed) as e:
        await REGISTRY["n8n"].run(ctx(hub, "n8n", settings={"workflow": "../x"}))
    assert e.value.code == "no_workflow"
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["n8n"].run(ctx(hub, "n8n", settings={"workflow": "w"}))
    assert e2.value.code == "no_secret"
    hub.bao_data["hq/n8n"] = {"secret": "s" * 40}

    async def refuse(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        return 503, "down"

    n8n.SEND_OVERRIDE = refuse
    with pytest.raises(StepFailed) as e3:
        await REGISTRY["n8n"].run(ctx(hub, "n8n", settings={"workflow": "w"}))
    assert e3.value.retry and "503" in e3.value.reason_fa
    n8n.SEND_OVERRIDE = None
    res = await REGISTRY["n8n"].run(ctx(hub, "n8n", settings={"workflow": "w"}, dry=True))
    assert res.data["dry"] is True


def test_the_demo_workflow_signs_the_way_the_hub_checks() -> None:
    """The demo's HMAC is the same construction as lines.signing (`<t>.<body>`), by file."""
    up = Path(__file__).resolve().parents
    demo = up[min(3, len(up) - 1)] / "automations" / "n8n" / "line-callback-demo.json"
    if not demo.is_file():
        pytest.skip("automations/ is not mounted in this test image")
    wf = json.loads(demo.read_text())
    names = {n["name"]: n for n in wf["nodes"]}
    code = names["Verify and sign"]["parameters"]["jsCode"]
    assert "createHmac('sha256', secret).update(`${ts}.`).update(body)" in code
    assert "t=${ts},v1=${mac}" in code and "x-hq-signature" in code
    assert names["Hub webhook"]["parameters"]["options"] == {"rawBody": True}
    assert names["Call back the hub"]["parameters"]["url"] == "={{ $env.HQ_CALLBACK_URL }}"
    assert isinstance(wf["id"], str) and wf["connections"]["Hub webhook"]


# --------------------------------------------------------------- templates --
GATES = {"auto", "owner", "ceo"}
LIBRARY_KINDS = {"cover_folder", "voice", "prompt", "pattern", "music", "brand"}
VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")
FORBIDDEN = (
    "tradeyar",
    "coinepro",
    "coinefx",
    "pro-chart",
    "prochart",
    "تریدیار",
    "کوینه",
    "پروچارت",
    "dayan",
)


def templates() -> dict[str, dict[str, Any]]:
    out_: dict[str, dict[str, Any]] = {}
    for f in sorted(SEED.glob("*.yaml")):
        if f.name == "rules.yaml":  # §31.1 the platform rules live beside the templates
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert doc["key"] == f.stem, f.name
        out_[doc["key"]] = doc
    return out_


def check_template(t: dict[str, Any]) -> None:
    """A minimal local validator for contract §30.1/§30.6 (the engine's loader owns the real one)."""
    for k in ("key", "title_fa", "platform", "version", "outputs_fa", "defaults", "steps"):
        assert k in t, f"{t.get('key')}: no {k}"
    assert t["version"] == 1 and isinstance(t["title_fa"], str) and t["steps"]
    d = t["defaults"]
    assert set(d["caps"]) == {"runs_per_day", "tokens_per_run", "opus_per_day"}
    assert d["schedule"].startswith("FREQ=") and re.fullmatch(r"[A-Z0-9=;,]+", d["schedule"])
    seen: list[str] = []
    for s in t["steps"]:
        for k in ("key", "kind", "title_fa", "prompt_fa", "settings", "inputs", "gate", "optional", "enabled",
                  "max_attempts", "timeout_s"):  # fmt: skip
            assert k in s, f"{t['key']}.{s.get('key')}: no {k}"
        assert s["key"] not in seen and s["kind"] in B.KINDS and s["gate"] in GATES
        assert (
            1 <= s["max_attempts"] <= 3 and s["timeout_s"] > 0 and isinstance(s["settings"], dict)
        )
        assert all(i in seen for i in s["inputs"]), (
            f"{t['key']}.{s['key']}: an input that is not an earlier step"
        )
        for ref in VAR.findall(s["prompt_fa"] or ""):
            head, _, rest = ref.partition(".")
            if ref in ("company.name_fa", "line.title_fa"):
                continue
            if head == "steps":
                step_key, _, field = rest.partition(".")
                assert field == "text" and step_key in s["inputs"], f"{t['key']}.{s['key']}: {ref}"
            elif head == "settings":
                assert rest in s["settings"], (
                    f"{t['key']}.{s['key']}: {ref} is not a setting of the step"
                )
            elif head == "library":
                assert rest in LIBRARY_KINDS, f"{t['key']}.{s['key']}: {ref}"
            elif head == "insights":  # §31.1 the line's learning loop
                assert rest in ("lessons", "top_hooks"), f"{t['key']}.{s['key']}: {ref}"
            else:
                raise AssertionError(f"{t['key']}.{s['key']}: unknown variable {ref}")
        seen.append(s["key"])


def test_the_templates_load_and_validate_and_name_no_company() -> None:
    got = templates()
    assert set(got) == {"instagram_reel", "instagram_story", "youtube_short", "youtube_long",
                        "telegram_post", "site_article", "newsletter"}  # fmt: skip
    for key, t in got.items():
        check_template(t)
        text = (SEED / f"{key}.yaml").read_text(encoding="utf-8").lower()
        assert not [w for w in FORBIDDEN if w in text], key
    assert {t["platform"] for t in got.values()} == {
        "instagram_reel",
        "instagram_story",
        "youtube_short",
        "youtube_long",
        "telegram_post",
        "site_article",
        "newsletter",
    }


def test_the_reel_template_is_the_owners_chain() -> None:
    steps = templates()["instagram_reel"]["steps"]
    assert [(s["key"], s["kind"]) for s in steps] == [
        ("script", "gpt_text"), ("dedupe", "dedupe"), ("voice", "tts"), ("direction", "gpt_text"),
        ("patterns", "pattern_search"), ("pick", "council_pick"), ("build", "opus_build"),
        ("render", "render"), ("cover", "cover"), ("quality", "quality"), ("publish", "publish"),
        ("story", "publish"), ("deliver", "deliver"),
    ]  # fmt: skip
    by = {s["key"]: s for s in steps}
    assert by["voice"]["settings"]["voice"] and by["publish"]["settings"]["kind"] == "reel"
    assert by["publish"]["settings"]["in_min"] > 0  # scheduled
    assert (
        by["story"]["settings"]["kind"] == "story" and by["story"]["settings"]["after"] == "publish"
    )
    assert (
        by["deliver"]["settings"]["only_if"] == "cover_not_set"
        and by["deliver"]["optional"] is True
    )
    assert (
        by["render"]["settings"]["where"] == "media"
        and "{{library.prompt}}" in by["script"]["prompt_fa"]
    )
    # every adapter setting a template uses is one the adapter reads
    assert by["publish"]["inputs"] == ["render", "build", "cover", "quality"]


def test_the_adapters_templates_settings_meet_the_adapters_expectations() -> None:
    """Each step of each template can be run by its adapter: kinds with adapters here need their inputs."""
    for t in templates().values():
        for s in t["steps"]:
            if s["kind"] == "render":
                assert s["settings"]["spec_from"] in s["inputs"]
            if s["kind"] == "tts":
                assert s["settings"]["text_from"] in s["inputs"]
            if s["kind"] == "publish":
                for k in ("media_from", "cover_from", "text_from"):
                    if k in s["settings"]:
                        assert s["settings"][k] in s["inputs"], (t["key"], s["key"], k)
            if s["kind"] == "council_pick":
                assert s["settings"]["candidates_from"] in s["inputs"]


def test_the_time_helpers_use_utc_and_the_runs_clock() -> None:
    assert C.now().tzinfo is UTC and isinstance(C.now(), datetime)
