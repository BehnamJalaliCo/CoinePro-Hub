"""Prompt 22 (contract §30, §31.1): the production lines' engine.

Every external adapter is faked here (gpt_text, tts, council_pick,
opus_build, render, publish, n8n); dedupe, quality and seal are the real
ones. A reel-like line runs end to end in draft (it waits at publish, the
owner's seal publishes), in auto mode, dry, again from a step; a step is
tested alone; caps and the kill switch skip a run with a Persian reason;
versions and revert; a copy to a second company runs with only its settings
changed (§30.7); dedupe makes the script again; n8n's callback is signed;
the routes are the owner's; the learning loop ranks published runs.
"""

from __future__ import annotations

import json
import random
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.hub import Hub
from hq_api.lines import adapters, engine, learning, signing, store
from hq_api.lines import templates as T
from hq_api.lines.adapters import core
from hq_api.lines.base import REGISTRY, StepContext, StepFailed, StepOutput

from .conftest import agent_headers, idem, step_up
from .p10_fakes import holding_switch

FIXTURES = Path(__file__).parent / "lines_fixture"
API = "/api/v1"
WORDS = [
    "بازار",
    "طلا",
    "دلار",
    "سهام",
    "رشد",
    "افت",
    "امروز",
    "فردا",
    "خبر",
    "تحلیل",
    "روند",
    "قیمت",
    "سرمایه",
    "فرصت",
    "خطر",
    "آموزش",
    "نکته",
    "ارز",
    "صرافی",
    "پس\u200cانداز",
    "بورس",
    "شاخص",
    "معامله",
    "سود",
    "زیان",
    "هدف",
    "برنامه",
    "حساب",
    "خرید",
    "فروش",
    "نمودار",
    "حمایت",
    "مقاومت",
    "کندل",
    "حجم",
    "نقدینگی",
    "تورم",
    "بانک",
    "وام",
    "مسکن",
    "خودرو",
]


def persian_text(n: int = 40) -> str:
    rnd = random.Random(uuid.uuid4().int)
    first = " ".join(rnd.choice(WORDS) for _ in range(6))
    return first + "\n" + " ".join(rnd.choice(WORDS) for _ in range(n))


class Fake:
    def __init__(self, kind: str, fn: Callable[[StepContext], Any]) -> None:
        self.kind = kind
        self._fn = fn

    async def run(self, ctx: StepContext) -> StepOutput:
        out: StepOutput = await self._fn(ctx)
        return out


class FakePublish:
    kind = "publish"

    def __init__(self, seen: dict[str, list[Any]], views: dict[str, float]) -> None:
        self.seen = seen
        self.views = views

    async def run(self, ctx: StepContext) -> StepOutput:
        self.seen["publish"].append(ctx)
        return StepOutput(
            data={"external_id": None if ctx.dry else f"ig-{ctx.run_ref}", "kind": "reel",
                  "url": None if ctx.dry else f"https://instagram.test/{ctx.run_ref}"},
            via="ig-hub",
        )  # fmt: skip

    async def insights(self, ctx: StepContext, published: list[dict[str, Any]]) -> dict[str, Any]:
        return {"views": self.views.get(ctx.run_ref, 100)}


class Fakes:
    def __init__(self) -> None:
        self.seen: dict[str, list[Any]] = defaultdict(list)
        self.scripts: list[str] = []
        self.views: dict[str, float] = {}
        self.build_tokens = 1000

    def all(self) -> list[Any]:
        async def script(ctx: StepContext) -> StepOutput:
            self.seen["script"].append(ctx)
            text = self.scripts.pop(0) if self.scripts else persian_text()
            return StepOutput(text=text, via="chatgpt-web")

        async def tts(ctx: StepContext) -> StepOutput:
            self.seen["tts"].append(ctx)
            voice = ctx.step["settings"].get("voice")
            return StepOutput(file_id=str(uuid.uuid4()), data={"duration_s": 28, "voice": voice},
                              via="aistudio-web")  # fmt: skip

        async def pick(ctx: StepContext) -> StepOutput:
            return StepOutput(
                text="الگوی شماره یک", data={"pattern": "pinterest:کارت"}, via="council"
            )

        async def build(ctx: StepContext) -> StepOutput:
            self.seen["build"].append(ctx)
            return StepOutput(
                text=persian_text(30), data={"caption": "کپشن کوتاه فارسی برای ریل"},
                via="router:opus", tokens=self.build_tokens, usd_equiv=Decimal("0.05"),
            )  # fmt: skip

        async def render(ctx: StepContext) -> StepOutput:
            return StepOutput(file_id=str(uuid.uuid4()), via="media-studio")

        async def flow(ctx: StepContext) -> StepOutput:
            self.seen["n8n"].append(ctx)
            token = f"{ctx.run_ref}:{ctx.step['key']}"
            return StepOutput(data={"waiting": True, "token": token, "execution": "e-1"}, via="n8n")

        return [
            Fake("gpt_text", script), Fake("tts", tts), Fake("council_pick", pick),
            Fake("opus_build", build), Fake("render", render), Fake("n8n", flow),
            FakePublish(self.seen, self.views),
        ]  # fmt: skip


@pytest.fixture(autouse=True)
def fixture_templates() -> Any:
    T.use_dirs(FIXTURES)
    T._load.cache_clear()
    yield
    T.use_dirs()
    T._load.cache_clear()


@pytest.fixture
def fakes() -> Any:
    adapters.load()
    saved = dict(REGISTRY)
    f = Fakes()
    for a in f.all():
        REGISTRY[a.kind] = a
    yield f
    REGISTRY.clear()
    REGISTRY.update(saved)


# ----------------------------------------------------------------- helpers --
async def make_line(
    client: httpx.AsyncClient, h: dict[str, str], code: str, template: str = "reel_test"
) -> dict[str, Any]:
    r = await client.post(
        f"{API}/companies/{code}/lines",
        json={"template": template, "title_fa": "ریل روزانه",
              "channel": {"kind": "instagram", "subject": "@page"}},
        headers={**h, **idem()},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    line: dict[str, Any] = r.json()
    return line


async def start(
    client: httpx.AsyncClient, h: dict[str, str], ref: str, **body: Any
) -> dict[str, Any]:
    r = await client.post(f"{API}/lines/{ref}/runs", json=body, headers={**h, **idem()})
    assert r.status_code == 201, r.text
    run: dict[str, Any] = r.json()
    return run


async def get_run(client: httpx.AsyncClient, h: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.get(f"{API}/line-runs/{ref}", headers=h)
    assert r.status_code == 200, r.text
    run: dict[str, Any] = r.json()
    return run


async def seal(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, Any],
    run: dict[str, Any],
    approve: bool = True,
) -> dict[str, Any]:
    h = owner["headers"]
    su = (
        await step_up(hub, owner["session_id"], "decision.approve", run["decision"])
        if approve
        else {}
    )
    r = await client.post(
        f"{API}/line-runs/{run['ref']}/seal", json={"approve": approve, "note_fa": "خوب است"},
        headers={**h, **su},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def steps_of(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["key"]: s for s in run["steps"]}


# ------------------------------------------------------------------ units --
def test_templates_load_and_a_bad_file_is_refused_with_its_name(tmp_path: Path) -> None:
    good = (FIXTURES / "reel_test.yaml").read_text(encoding="utf-8")
    (tmp_path / "good.yaml").write_text(good, encoding="utf-8")
    (tmp_path / "bad_kind.yaml").write_text(
        good.replace("key: reel_test", "key: bad_one").replace("kind: render", "kind: paint"),
        encoding="utf-8",
    )
    (tmp_path / "bad_input.yaml").write_text(
        good.replace("key: reel_test", "key: bad_two").replace("inputs: [render, build]", "inputs: [later]"),
        encoding="utf-8",
    )  # fmt: skip
    (tmp_path / "rules.yaml").write_text("all: {links: none}\n", encoding="utf-8")
    found, refused = T.load_dir(tmp_path)
    assert set(found) == {"reel_test"}
    assert found["reel_test"].defaults.insights.metric == "views"
    assert found["reel_test"].outputs_fa == ["یک ریل", "یک استوری"]
    assert any(r.startswith("bad_kind.yaml:") and "paint" in r for r in refused), refused
    assert any(r.startswith("bad_input.yaml:") and "later" in r for r in refused), refused
    assert not any(r.startswith("rules.yaml") for r in refused)
    assert T.get("flow_test").outputs_fa == ["یک پست"]  # a string becomes one item


def test_prompts_are_filled_by_plain_dotted_lookup() -> None:
    env = {
        "company": {"name_fa": "تریدیار", "code": "TY"},
        "steps": {"script": {"text": "سلام", "data": {"n": 3, "deep": {"x": "y"}}}},
        "settings": {"tone": "ساده"},
        "library": {"voice": "گوینده‌ی یک"},
        "insights": {},
    }
    text, missing = engine.render_prompt(
        "{{company.name_fa}}/{{ company.code }} {{steps.script.text}} {{steps.script.data.n}} "
        "{{steps.script.data.deep.x}} {{settings.tone}} {{library.voice}} {{insights.lessons}} "
        "{{__class__.__init__}} {{steps.nope.text}}",
        env,
    )
    assert text == "تریدیار/TY سلام 3 y ساده گوینده‌ی یک   "
    assert missing == ["insights.lessons", "__class__.__init__", "steps.nope.text"]
    assert engine.render_prompt(None, env) == (None, [])


def test_gates_follow_the_mode() -> None:
    publish = {"kind": "publish", "gate": "auto"}
    seal = {"kind": "seal", "gate": "auto"}
    assert engine.effective_gate(publish, "draft", False) == "owner"
    assert engine.effective_gate(publish, "auto", False) is None
    assert engine.effective_gate(seal, "draft", False) == "owner"
    assert engine.effective_gate(seal, "auto", False) is None
    assert engine.effective_gate({"kind": "render", "gate": "ceo"}, "auto", False) == "ceo"
    assert engine.effective_gate({"kind": "render", "gate": "ceo"}, "auto", True) is None  # dry


def test_shingles_see_a_rewrite() -> None:
    a = persian_text(60)
    assert core.similarity(a, a) == 1.0
    assert core.similarity(a, a.replace("ي", "ی")) == 1.0
    assert core.similarity(a, persian_text(60)) < 0.3


async def test_quality_applies_the_platforms_rules() -> None:
    def ctx(platform: str, text: str, **settings: Any) -> StepContext:
        return StepContext(
            run_ref="RN-000001", line_ref="LN-0001", company="TY", platform=platform, channel={},
            step={"key": "quality", "kind": "quality", "settings": {
                "repeat": False, "sources_required": False, **settings}},
            prompt=None, inputs={"build": StepOutput(text=text)}, library=(), dry=False, hub=None,
        )  # fmt: skip

    q = core.Quality()
    ok = await q.run(ctx("instagram_reel", "امروز درباره‌ی پس‌انداز ساده حرف میزنیم."))
    assert {c["key"] for c in ok.data["checks"]} >= {"links", "financial_claims", "persian"}
    with pytest.raises(StepFailed) as e:
        await q.run(ctx("instagram_reel", "برای خرید به www.example.com بروید."))
    assert "بیو" in e.value.reason_fa and e.value.retry
    await q.run(ctx("telegram_post", "برای خرید به https://example.com بروید."))  # links allowed
    with pytest.raises(StepFailed) as e:
        await q.run(ctx("telegram_post", "این روش سود تضمینی دارد."))
    assert "ادعای مالی" in e.value.reason_fa
    with pytest.raises(StepFailed) as e:
        await q.run(ctx("telegram_post", "متن کوتاه", min_chars=50, banned_words=["کوتاه"]))
    assert "نویسه" in e.value.reason_fa and "کوتاه" in e.value.reason_fa
    with pytest.raises(StepFailed) as e:
        await q.run(ctx("telegram_post", "طلا ۲۵٪ رشد کرد.", sources_required=True))
    assert "بی‌منبع" in e.value.reason_fa
    assert learning.platform_rules("instagram_reel")["links"] == "none"


# ------------------------------------------------------------- end to end --
async def test_a_reel_line_runs_end_to_end_in_draft(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    assert line["state"] == "draft" and line["mode"] == "draft" and line["version"] == 1
    assert [s["key"] for s in line["steps"]][:3] == ["script", "dedupe", "voice"]
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert run["state"] == "queued" and run["line_version"] == 1
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"
        run = await get_run(client, h, run["ref"])
        s = steps_of(run)
        assert run["state"] == "waiting" and run["decision"]
        assert s["publish"]["state"] == "waiting" and s["publish"]["gate"] == "owner"
        assert all(
            s[k]["state"] == "done"
            for k in ("script", "dedupe", "voice", "pick", "build", "render", "quality")
        )
        assert s["script"]["via"] == "chatgpt-web" and s["script"]["output"]["text"]
        assert s["build"]["tokens"] == 1000 and run["cost"]["tokens"] == 1000
        assert s["script"]["missing"] == ["insights.lessons"]  # no insights yet: noted
        prompt = fakes.seen["script"][0].prompt
        assert co["code"] in prompt and "instagram_reel" in prompt and "ریل روزانه" in prompt
        assert "28" in fakes.seen["build"][0].prompt and "ساده" in fakes.seen["build"][0].prompt
        card = await client.get(f"{API}/decisions/{run['decision']}", headers=h)
        assert card.json()["kind"] == "line_publish" and card.json()["action_class"] == "A3"
        assert card.json()["payload"]["preview"]["text"]
        # approving without the step-up is refused
        bad = await client.post(
            f"{API}/line-runs/{run['ref']}/seal", json={"approve": True}, headers=h
        )
        assert bad.status_code == 403
        await seal(client, hub, owner_session, run)
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
    run = await get_run(client, h, run["ref"])
    assert run["state"] == "done" and steps_of(run)["publish"]["sealed_by"] == "owner"
    assert run["published"][0]["external_id"] == f"ig-{run['ref']}"
    assert run["published"][0]["kind"] == "reel" and not fakes.seen["publish"][0].dry
    line = (await client.get(f"{API}/lines/{line['ref']}", headers=h)).json()
    assert (
        line["good_runs"] == 1 and not line["offer_auto"] and line["last_run"]["ref"] == run["ref"]
    )
    features = await su.fetchrow(
        "SELECT * FROM lines.run_features f JOIN lines.runs r ON r.id = f.run_id WHERE r.ref = $1",
        run["ref"],
    )
    assert features["voice"] == "Kore" and features["pattern"] == "pinterest:کارت"
    assert features["hook"] and features["length_s"] == 28 and features["caption_len"] > 0
    assert (
        await su.fetchval(
            "SELECT count(*) FROM audit.entries WHERE action = 'line.step' AND target_ref LIKE $1",
            f"{run['ref']}:%",
        )
        == 8
    )
    # a second run the owner rejects ends cancelled with the note
    async with holding_switch(su, "released"):
        run2 = await start(client, h, line["ref"])
        await engine.drive(hub, run2["ref"])
        run2 = await seal(
            client, hub, owner_session, await get_run(client, h, run2["ref"]), approve=False
        )
    assert run2["state"] == "cancelled" and "خوب است" in run2["note_fa"]
    assert steps_of(run2)["publish"]["state"] == "failed"


async def test_auto_mode_publishes_without_a_seal(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    r = await client.post(f"{API}/lines/{line['ref']}/mode", json={"mode": "auto"}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_h = await step_up(hub, owner_session["session_id"], "line.auto", line["ref"])
    r = await client.post(
        f"{API}/lines/{line['ref']}/mode", json={"mode": "auto"}, headers={**h, **su_h}
    )
    assert r.status_code == 200 and r.json()["mode"] == "auto"
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
    run = await get_run(client, h, run["ref"])
    assert run["decision"] is None and run["published"]
    assert (await client.get(f"{API}/lines/{line['ref']}", headers=h)).json()["good_runs"] == 0
    back = await client.post(f"{API}/lines/{line['ref']}/mode", json={"mode": "draft"}, headers=h)
    assert back.json()["mode"] == "draft"  # back to draft: no step-up


async def test_a_dry_run_leaves_nothing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"], dry=True)
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
    run = await get_run(client, h, run["ref"])
    assert run["dry"] and run["published"] == [] and run["decision"] is None
    assert "منتشر نشد" in run["note_fa"]
    assert fakes.seen["publish"][-1].dry and all(c.dry for c in fakes.seen["script"])
    assert not await su.fetchval(
        "SELECT 1 FROM lines.run_features f JOIN lines.runs r ON r.id = f.run_id WHERE r.ref = $1",
        run["ref"],
    )


async def test_a_rerun_from_a_step_reuses_the_steps_before_it(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    async with holding_switch(su, "released"):
        first = await start(client, h, line["ref"], dry=True)
        await engine.drive(hub, first["ref"])
        first = await get_run(client, h, first["ref"])
        r = await client.post(
            f"{API}/line-runs/{first['ref']}/rerun",
            json={"from_step": "build"},
            headers={**h, **idem()},
        )
        assert r.status_code == 201, r.text
        again = r.json()
        assert again["rerun_of"] == first["ref"] and again["from_step"] == "build" and again["dry"]
        scripts = len(fakes.seen["script"])
        assert (await engine.drive(hub, again["ref"]))["state"] == "done"
    again = await get_run(client, h, again["ref"])
    s, f = steps_of(again), steps_of(first)
    assert len(fakes.seen["script"]) == scripts  # the script was not written again
    for k in ("script", "dedupe", "voice", "pick"):
        assert s[k]["reused"] and s[k]["output"] == f[k]["output"]
    assert not s["build"]["reused"] and s["build"]["output"] != f["build"]["output"]
    bad = await client.post(
        f"{API}/line-runs/{first['ref']}/rerun", json={"from_step": "nope"}, headers={**h, **idem()}
    )
    assert bad.status_code == 422


async def test_one_step_alone_keeps_nothing(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any, su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    r = await client.post(
        f"{API}/lines/{line['ref']}/steps/build/test",
        json={
            "inputs": {"script": {"text": "سناریوی آزمایشی"}, "voice": {"data": {"duration_s": 12}}}
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["state"] == "done" and out["output"]["text"] and out["tokens"] == 1000
    assert "سناریوی آزمایشی" in out["prompt"] and "12" in out["prompt"]
    pub = await client.post(f"{API}/lines/{line['ref']}/steps/publish/test", json={}, headers=h)
    assert pub.json()["state"] == "done" and fakes.seen["publish"][-1].dry
    assert not await su.fetchval(
        "SELECT count(*) FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id WHERE l.ref = $1",
        line["ref"],
    )
    missing = await client.post(f"{API}/lines/{line['ref']}/steps/nope/test", json={}, headers=h)
    assert missing.status_code == 409


async def test_caps_and_the_kill_switch_skip_a_run_with_the_reason(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    caps = {"runs_per_day": 1, "tokens_per_run": 500, "opus_per_day": 5}
    r = await client.put(
        f"{API}/lines/{line['ref']}", json={"caps": caps}, headers=h
    )  # lower: free
    assert r.status_code == 200 and r.json()["version"] == 2
    async with holding_switch(su, "engaged"):
        locked = await start(client, h, line["ref"])
    assert locked["state"] == "skipped" and "قفل" in locked["note_fa"]
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "skipped"  # build spent 1000 > 500
        run = await get_run(client, h, run["ref"])
        assert (
            "سقف توکن این اجرا" in run["note_fa"] and steps_of(run)["render"]["state"] == "skipped"
        )
        second = await start(client, h, line["ref"])
        assert second["state"] == "skipped" and "سقف اجرای روزانه" in second["note_fa"]
        dry = await start(client, h, line["ref"], dry=True)  # a dry run is not counted
        assert dry["state"] == "queued"
        # the company's daily token cap
        await su.execute("UPDATE core.companies SET daily_token_cap = 1 WHERE id = $1", co["id"])
        await su.execute(
            """INSERT INTO llm.calls (id, started_at, company_id, actor_ref, task_class, priority,
                   caller, status, input_tokens, output_tokens)
               VALUES (gen_random_uuid(), now(), $1, 'lines', 'general', 3, 'lines', 'ok', 10, 10)""",
            co["id"],
        )
        out = await engine.drive(hub, dry["ref"])
    assert out["state"] == "skipped"
    assert "سقف توکن امروز این شرکت" in (await get_run(client, h, dry["ref"]))["note_fa"]


async def test_versions_and_revert(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    ref = line["ref"]
    steps = line["steps"]
    steps[0]["prompt_fa"] = "متن تازه برای {{company.name_fa}}"
    r = await client.put(
        f"{API}/lines/{ref}",
        json={"title_fa": "ریل تازه", "steps": steps, "note_fa": "دستور تازه"},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["title_fa"] == "ریل تازه"
    same = await client.put(f"{API}/lines/{ref}", json={"title_fa": "ریل تازه"}, headers=h)
    assert same.json()["version"] == 2  # nothing changed: no version
    higher = {**line["caps"], "runs_per_day": 9}
    r = await client.put(f"{API}/lines/{ref}", json={"caps": higher}, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    su_h = await step_up(hub, owner_session["session_id"], "line.caps", ref)
    r = await client.put(f"{API}/lines/{ref}", json={"caps": higher}, headers={**h, **su_h})
    assert (
        r.status_code == 200 and r.json()["version"] == 3 and r.json()["caps"]["runs_per_day"] == 9
    )
    bad = await client.put(f"{API}/lines/{ref}", json={"schedule": "FREQ=SECONDLY"}, headers=h)
    assert bad.status_code == 422
    dup = await client.put(f"{API}/lines/{ref}", json={"steps": [steps[0], steps[0]]}, headers=h)
    assert dup.status_code == 422
    versions = (await client.get(f"{API}/lines/{ref}/versions", headers=h)).json()
    assert [v["version"] for v in versions] == [3, 2, 1] and versions[1]["note_fa"] == "دستور تازه"
    assert versions[2]["body"]["title_fa"] == "ریل روزانه" and versions[0]["by"]["kind"] == "owner"
    r = await client.post(
        f"{API}/lines/{ref}/revert", json={"version": 1}, headers=h
    )  # caps fall: free
    assert r.status_code == 200, r.text
    out = r.json()
    assert (
        out["version"] == 4 and out["title_fa"] == "ریل روزانه" and out["caps"]["runs_per_day"] == 5
    )
    assert (
        out["steps"][0]["prompt_fa"].startswith("برای ")
        and "متن تازه" not in out["steps"][0]["prompt_fa"]
    )
    r = await client.post(f"{API}/lines/{ref}/revert", json={"version": 3}, headers=h)  # caps rise
    assert r.status_code == 403
    on = await client.post(f"{API}/lines/{ref}/state", json={"state": "on"}, headers=h)
    assert on.json()["state"] == "on" and on.json()["next_at"]


async def test_a_copy_runs_for_a_second_company_with_only_its_settings_changed(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    a, b = await new_company(), await new_company()
    line = await make_line(client, h, a["code"])
    holding_asset = await client.post(
        f"{API}/library", json={"kind": "prompt", "title_fa": "لحن هلدینگ", "config": {"text": "ساده بنویس"}},
        headers={**h, **idem()},
    )  # fmt: skip
    own = await client.post(
        f"{API}/library", json={"company": a["code"], "kind": "voice", "title_fa": "صدای الف"},
        headers={**h, **idem()},
    )  # fmt: skip
    assert holding_asset.status_code == 201 and holding_asset.json()["company"] is None
    lib = [holding_asset.json()["id"], own.json()["id"]]
    assert (
        await client.put(f"{API}/lines/{line['ref']}", json={"library": lib}, headers=h)
    ).status_code == 200
    r = await client.post(
        f"{API}/lines/{line['ref']}/copy", json={"company": b["code"]}, headers={**h, **idem()}
    )
    assert r.status_code == 201, r.text
    copy = r.json()
    assert (
        copy["company"] == b["code"]
        and copy["state"] == "draft"
        and copy["copied_from"] == line["ref"]
    )
    assert copy["library"] == [holding_asset.json()["id"]] and copy["channel"]["subject"] == ""
    steps = copy["steps"]
    next(s for s in steps if s["key"] == "voice")["settings"]["voice"] = "Puck"
    r = await client.put(
        f"{API}/lines/{copy['ref']}",
        json={"steps": steps, "channel": {"kind": "instagram", "subject": "@b_page"}},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["version"] == 2
    lib_b = (await client.get(f"{API}/library", params={"company": b["code"]}, headers=h)).json()
    assert holding_asset.json()["id"] in {x["id"] for x in lib_b} and own.json()["id"] not in {
        x["id"] for x in lib_b
    }
    async with holding_switch(su, "released"):
        run = await start(client, h, copy["ref"])
        await engine.drive(hub, run["ref"])
        await seal(client, hub, owner_session, await get_run(client, h, run["ref"]))
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
    run = await get_run(client, h, run["ref"])
    assert run["company"] == b["code"] and run["published"]
    assert fakes.seen["tts"][-1].step["settings"]["voice"] == "Puck"
    assert fakes.seen["tts"][-1].channel["subject"] == "@b_page"
    assert b["code"] in fakes.seen["script"][-1].prompt
    assert [x["title_fa"] for x in fakes.seen["script"][-1].library] == ["لحن هلدینگ"]
    # the library: an asset changed and retired
    aid = own.json()["id"]
    up = await client.put(f"{API}/library/{aid}", json={"title_fa": "صدای تازه"}, headers=h)
    assert up.json()["version"] == 2
    assert (await client.delete(f"{API}/library/{aid}", headers=h)).status_code == 204
    assert (
        await client.put(f"{API}/library/{aid}", json={"title_fa": "x"}, headers=h)
    ).status_code == 404


async def test_dedupe_makes_the_script_again(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    old, fresh = persian_text(50), persian_text(50)
    fakes.scripts = [old]
    async with holding_switch(su, "released"):
        first = await start(client, h, line["ref"])
        assert (await engine.drive(hub, first["ref"]))["state"] == "waiting"
        fakes.scripts = [old, fresh]
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"
    run = await get_run(client, h, run["ref"])
    s = steps_of(run)
    assert s["script"]["output"]["text"] == fresh and s["dedupe"]["attempt"] == 2
    assert s["dedupe"]["state"] == "done" and s["dedupe"]["output"]["data"]["similarity"] < 0.6
    assert (
        "بار قبل" in fakes.seen["script"][-1].prompt and "شبیه" in fakes.seen["script"][-1].prompt
    )
    # always the same text: the dedupe step gives up after its attempts
    fakes.scripts = [old] * 5
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "failed"
    run = await get_run(client, h, run["ref"])
    assert steps_of(run)["dedupe"]["state"] == "failed" and "شبیه" in run["note_fa"]
    # a cancelled run withdraws its card
    async with holding_switch(su, "released"):
        w = await start(client, h, line["ref"])
        await engine.drive(hub, w["ref"])
    w = await get_run(client, h, w["ref"])
    r = await client.post(f"{API}/line-runs/{w['ref']}/cancel", headers=h)
    assert r.json()["state"] == "cancelled"
    assert (await client.get(f"{API}/decisions/{w['decision']}", headers=h)).json()[
        "status"
    ] == "withdrawn"


async def test_n8n_callback_is_signed_and_a_ceo_gate_is_the_ceos(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    secret = "test-n8n-secret-" + uuid.uuid4().hex
    monkeypatch.setattr(hub, "secrets", replace(hub.secrets, n8n_secret=secret))
    line = await make_line(client, h, co["code"], template="flow_test")
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"])
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"
        assert steps_of(await get_run(client, h, run["ref"]))["flow"]["state"] == "waiting"
        token = fakes.seen["n8n"][-1].run_ref + ":flow"
        body = json.dumps(
            {"token": token, "ok": True, "text": "متن از n8n", "data": {"post": 7}}
        ).encode()
        url = "/internal/v1/lines/callback"
        ct = {"Content-Type": "application/json"}
        assert (await client.post(url, content=body, headers=ct)).status_code == 401
        bad = {signing.HEADER: signing.sign("wrong", body), **ct}
        assert (await client.post(url, content=body, headers=bad)).status_code == 401
        old = {
            signing.HEADER: signing.sign(
                secret, body, now=int(datetime.now(UTC).timestamp()) - 3600
            ),
            **ct,
        }
        assert (await client.post(url, content=body, headers=old)).status_code == 401
        good = {signing.HEADER: signing.sign(secret, body), **ct}
        r = await client.post(url, content=body, headers=good)
        assert r.status_code == 200, r.text
        assert r.json() == {"run": run["ref"], "step": "flow", "state": "running"}
        again = await client.post(
            url, content=body, headers={signing.HEADER: signing.sign(secret, body), **ct}
        )
        assert again.status_code == 409  # answered once
        assert (await engine.drive(hub, run["ref"]))["state"] == "waiting"  # the CEO's seal
        cur = await get_run(client, h, run["ref"])
        flow = steps_of(cur)["flow"]
        assert flow["state"] == "done" and flow["output"]["text"] == "متن از n8n"
        assert flow["output"]["data"]["post"] == 7 and flow["output"]["data"]["execution"] == "e-1"
        card = (await client.get(f"{API}/decisions/{cur['decision']}", headers=h)).json()
        assert card["approver"]["code"] == f"{co['code']}-CEO" and card["payload"]["gate"] == "ceo"
        ceo = await agent_headers(f"{co['code']}-CEO")
        r = await client.post(
            f"/internal/v1/cards/{cur['decision']}/decide", json={"verdict": "approve", "note": "باشد"},
            headers={**ceo, **idem()},
        )  # fmt: skip
        assert r.status_code == 200, r.text
        assert (await engine.drive(hub, run["ref"]))[
            "state"
        ] == "waiting"  # draft: the owner's publish seal
        cur = await get_run(client, h, run["ref"])
        assert steps_of(cur)["approve"]["sealed_by"] == f"{co['code']}-CEO"
        assert steps_of(cur)["approve"]["output"]["data"]["sealed"] is True
        await seal(client, hub, owner_session, cur)
        assert (await engine.drive(hub, run["ref"]))["state"] == "done"
        # a callback that never comes: the step fails after its timeout_s
        late = await start(client, h, line["ref"])
        assert (await engine.drive(hub, late["ref"]))["state"] == "waiting"
        await su.execute(
            """UPDATE lines.step_runs s SET started_at = now() - interval '1 hour' FROM lines.runs r
               WHERE r.id = s.run_id AND r.ref = $1 AND s.key = 'flow'""",
            late["ref"],
        )
        assert (await engine.drive(hub, late["ref"]))["state"] == "failed"
    late = await get_run(client, h, late["ref"])
    assert steps_of(late)["flow"]["state"] == "failed" and "نرسید" in late["note_fa"]


async def test_the_routes_are_the_owners(
    client: httpx.AsyncClient, owner_session: dict[str, Any], new_company: Any,
) -> None:  # fmt: skip
    co = await new_company()
    ceo = await agent_headers(f"{co['code']}-CEO")
    for path in (
        f"/companies/{co['code']}/lines",
        "/line-templates",
        "/library",
        "/calendar/lines",
    ):
        r = await client.get(API + path, headers=ceo)
        assert r.status_code == 403, path
    r = await client.post(f"{API}/companies/{co['code']}/lines", json={"template": "reel_test", "title_fa": "x"},
                          headers={**ceo, **idem()})  # fmt: skip
    assert r.status_code == 403
    assert (await client.get(API + "/line-templates")).status_code == 401
    h = owner_session["headers"]
    tpl = (await client.get(API + "/line-templates", headers=h)).json()
    assert {"reel_test", "flow_test"} <= {t["key"] for t in tpl}
    assert (await client.get(API + "/line-templates/nope", headers=h)).status_code == 404
    assert (await client.get(API + "/tts/voices", headers=h)).status_code == 200


async def test_the_kits_create_line_and_the_calendar(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any, su: Any,
) -> None:  # fmt: skip
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        row = await store.create_line(
            tx, company_id=co["id"], template_key="reel_test", platform="instagram_reel",
            title_fa="ریل کیت",
        )  # fmt: skip
        assert row["ref"].startswith("LN-") and row["state"] == "draft"
        v = await tx.one(
            "SELECT by_kind, by_code FROM lines.line_versions WHERE line_id = :id", id=row["id"]
        )
        assert (v["by_kind"], v["by_code"]) == ("service", "kit")
    h = owner_session["headers"]
    await client.post(f"{API}/lines/{row['ref']}/state", json={"state": "on"}, headers=h)
    cal = await client.get(f"{API}/calendar/lines", params={"company": co["code"]}, headers=h)
    assert cal.status_code == 200
    items = [i for d in cal.json()["days"] for i in d["items"]]
    assert items and all(i["line"] == row["ref"] and i["state"] == "planned" for i in items)


async def test_the_tick_makes_one_run_per_occurrence_and_waits_for_the_switch(
    hub: Hub, new_company: Any, su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    from hq_api.domain.gov_common import zone
    from hq_api.worker.lines_activities import LinesActivities

    real = hub.settings
    acts = LinesActivities(hub, lambda: hub.db.tx([]))
    try:
        hub.settings = replace(real, lines=False)
        assert await acts.lines_tick() == {"skipped": "lines_off"}
    finally:
        hub.settings = real
    co = await new_company()
    async with hub.db.tx(await hub.companies.ids()) as tx:
        row = await store.create_line(
            tx, company_id=co["id"], template_key="reel_test", platform="instagram_reel", title_fa="ریل",
            by="owner",
        )  # fmt: skip
        await tx.exec("UPDATE lines.lines SET state = 'on' WHERE id = :id", id=row["id"])
        tz = await engine.owner_tz(tx)
    local = (
        datetime.now(UTC).astimezone(zone(tz)).replace(hour=9, minute=3, second=0, microsecond=0)
    )
    now = local.astimezone(UTC)
    async with holding_switch(su, "released"):
        first = await engine.tick(hub, now)
        second = await engine.tick(hub, now + timedelta(minutes=5))
    assert first["made"] >= 1
    runs = await su.fetch(
        "SELECT trigger, occurrence_at, state FROM lines.runs WHERE line_id = $1", row["id"]
    )
    assert len(runs) == 1 and runs[0]["trigger"] == "schedule"
    assert runs[0]["occurrence_at"] == local.replace(minute=0).astimezone(UTC)
    assert second["made"] == 0 or len(runs) == 1
    async with holding_switch(su, "engaged"):
        assert (await engine.tick(hub, now))["skipped"] is True


async def test_the_learning_loop_ranks_published_runs(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Any,
    su: Any, fakes: Fakes,
) -> None:  # fmt: skip
    h = owner_session["headers"]
    co = await new_company()
    line = await make_line(client, h, co["code"])
    lid = await su.fetchval("SELECT id FROM lines.lines WHERE ref = $1", line["ref"])
    shape = [(19, "Kore", 1000, "قلاب برنده"), (19, "Kore", 1300, "قلاب بهترین"),
             (8, "Puck", 300, "قلاب ضعیف"), (8, "Puck", 400, "قلاب معمولی")]  # fmt: skip
    for hour, voice, views, hook in shape:
        run = await su.fetchval(
            """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, published,
                   metrics, ended_at)
               VALUES ($1, $2, 1, 'owner', 'done', '[{"platform": "instagram_reel"}]',
                       jsonb_build_object('d7', jsonb_build_object('views', $3::int)), now())
               RETURNING id""",
            co["id"], lid, views,
        )  # fmt: skip
        await su.execute(
            """INSERT INTO lines.run_features (run_id, company_id, line_id, platform, hook, words,
                   voice, pattern, publish_hour) VALUES ($1, $2, $3, 'instagram_reel', $4, 80, $5, 'x', $6)""",
            run, co["id"], lid, hook, voice, hour,
        )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        ins = await learning.compute(tx, lid)
    assert ins.metric == "views" and ins.window_runs == 4
    assert ins.best.hour == 19 and ins.best.voice == "Kore" and ins.best.length_bucket is None
    assert ins.top_hooks[:2] == ["قلاب بهترین", "قلاب برنده"]
    assert any("ساعت 19" in x for x in ins.lessons_fa)
    keys = {
        r["key"]
        for r in await su.fetch("SELECT key FROM owner.suggestions WHERE company_id = $1", co["id"])
    }
    assert f"line:{line['ref']}:hour:19" in keys and f"line:{line['ref']}:voice:Kore" in keys
    got = (await client.get(f"{API}/lines/{line['ref']}/insights", headers=h)).json()
    assert got["best"]["hour"] == 19 and got["top_hooks"][0] == "قلاب بهترین"
    # the next script reads the lessons
    async with holding_switch(su, "released"):
        run = await start(client, h, line["ref"], dry=True)
        await engine.drive(hub, run["ref"])
    assert "بهترین ساعت" in fakes.seen["script"][-1].prompt
    # the 24h read: the publish adapter's insights into Run.metrics, then the insights again
    async with holding_switch(su, "released"):
        real = await start(client, h, line["ref"])
        await engine.drive(hub, real["ref"])
        await seal(client, hub, owner_session, await get_run(client, h, real["ref"]))
        await engine.drive(hub, real["ref"])
        fakes.views[real["ref"]] = 5000
        await su.execute(
            "UPDATE lines.runs SET ended_at = now() - interval '25 hours' WHERE ref = $1",
            real["ref"],
        )
        out = await learning.read_metrics(hub)
    assert out["read"] >= 1
    assert (await get_run(client, h, real["ref"]))["metrics"]["h24"] == {"views": 5000}
    got = (await client.get(f"{API}/lines/{line['ref']}/insights", headers=h)).json()
    assert got["window_runs"] == 5 and got["top_hooks"][0] != "قلاب بهترین"


async def _unused(_: AsyncIterator[None]) -> None:  # keeps the AsyncIterator import honest
    return None


async def test_a_cancelled_line_advance_stops_its_step(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit 2026-11-11: a cancelled line_advance (heartbeat timeout, backstop) left
    engine.advance running beside the retry's attempt of the same step."""
    import asyncio

    from hq_api.worker import lines_activities as LA

    started, stopped = asyncio.Event(), asyncio.Event()

    async def advance(_hub: Any, _ref: str) -> dict[str, Any]:
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            stopped.set()
        return {}

    monkeypatch.setattr(LA.engine, "advance", advance)
    acts = LA.LinesActivities(hub, lambda: hub.db.tx([]))
    outer = asyncio.create_task(acts.line_advance("LR-000001"))
    await asyncio.wait_for(started.wait(), 5)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    assert stopped.is_set()
