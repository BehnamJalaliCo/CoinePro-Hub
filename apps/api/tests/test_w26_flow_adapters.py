"""Prompt 38 (contract §59.2): the flow's six new step adapters (topic, voice_check, inspire,
workshop, package, report), the publish step's standing path, and the checks of tts, gpt_text and
cover against the prompt. Every outside call is a fake (the router, the browser profile, the
speech to text, the workshop); no database row (the fake transaction of test_p22_adapters)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from hq_api.domain import hands as HANDS
from hq_api.domain import servers as SV
from hq_api.domain import session_publish as SPB
from hq_api.domain import topics as T
from hq_api.domain import work as W
from hq_api.domain import workspace as WS
from hq_api.errors import ApiError
from hq_api.lines import adapters
from hq_api.lines.adapters import _common as C
from hq_api.lines.adapters import _flow as FW
from hq_api.lines.adapters import tts, voice_check, workshop
from hq_api.lines.base import REGISTRY, StepFailed, StepOutput

from .test_p22_adapters import (  # noqa: F401 - the fixtures
    MP4,
    PNG,
    FakeHub,
    FakeRouter,
    FakeWeb,
    b64,
    ctx,
    mc,
    out,
    quiet,
    stored,
)

adapters.load()
RUN_ID = uuid4()
SOON = datetime.now(UTC) + timedelta(hours=3)
POLICY = {
    "comment": {"match": "any"}, "story": True, "dm": True,
    "public_pool": ["اول مال من 🌱", "دوم مال من 🙌"],
    "dm_template": {"text_fa": "سلام! درباره‌ی «{topic}» 👇",
                    "buttons": [{"title_fa": "نمودار", "section": "next"}]},
    "per_video_dm": False, "repeat": {"mode": "once_a_year"},
}  # fmt: skip
LINKS = {"site": {"url": "https://pro-chart.com", "title_fa": "پرو چارت"},
         "sections": [{"key": "next", "title_fa": "بعدی", "url": "https://pro-chart.com/next/?a=1"}],
         "utm": {}, "updated_at": None, "by_fa": ""}  # fmt: skip


def flow_row(**over: Any) -> dict[str, Any]:
    return {"ref": "AT-0042", "company_id": uuid4(), "sentence_fa": "ریلز", "playbook": "PB-0001",
            "playbook_version": 1, "line": "LN-0001", "schedule": {}, "budget": {},
            "replies": POLICY, "mode": "auto", "account": "pro.chart", "story": True,
            "state": "on", "group_id": None, "playbook_fa": "ریلز روزانه", **over}  # fmt: skip


def run_row(**over: Any) -> dict[str, Any]:
    return {"id": RUN_ID, "ref": "LR-000001", "occurrence_at": SOON, "at": datetime.now(UTC),
            "dry": False, **over}  # fmt: skip


def test_the_six_new_kinds_have_their_adapters() -> None:
    for kind in ("topic", "voice_check", "inspire", "workshop", "package", "report"):
        assert kind in REGISTRY, kind
    assert getattr(REGISTRY["voice_check"], "reruns_input", False) is True


def test_a_labelled_script_is_read_by_code() -> None:
    text = (
        "voice: سلام، امروز درباره‌ی بازپخش میگوییم.\nبازپخش را کامنت کن.\n"
        "caption: کپشن امروز #ترید\nkeyword: بازپخش\nreply: سلام 👋\nخط دوم\n"
        "public: یک 🌱\npublic: دو 🙌\nسه ✨"
    )
    p = FW.script_parts(text)
    assert p["voice"].endswith("بازپخش را کامنت کن.") and p["caption"] == "کپشن امروز #ترید"
    assert p["keyword"] == "بازپخش" and p["reply"] == "سلام 👋\nخط دوم"
    assert p["public"] == ["یک 🌱", "دو 🙌", "سه ✨"]
    assert FW.script_parts('{"voice": "v", "keyword": "k", "public": ["a"]}')["public"] == ["a"]
    assert FW.script_parts("just a text") == {}


# ------------------------------------------------------------------ topic --
async def test_topic_claims_the_first_candidate_the_ledger_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = FakeRouter(mc('{"candidates": ["سطح حمایت", "کندل چکش", "واگرایی"]}'))
    C.ROUTER_OVERRIDE = router
    claimed: list[tuple[str, Any]] = []

    async def claim(tx: Any, scope: dict[str, Any], **kw: Any) -> tuple[dict[str, Any], bool]:
        if kw["title"] == "سطح حمایت":
            raise ApiError(409, "topic_taken", "said")
        claimed.append((kw["title"], scope["run_id"]))
        return {"title_fa": kw["title"]}, True

    monkeypatch.setattr(T, "claim", claim)
    hub = FakeHub(**{"FROM growth.automations a": None, "FROM lines.runs WHERE ref": run_row()})
    res = await REGISTRY["topic"].run(ctx(hub, "topic", prompt="آموزش ترید"))
    assert res.text == "کندل چکش" and res.data["refused"] == ["سطح حمایت"]
    assert claimed == [("کندل چکش", RUN_ID)]  # the line run is the ledger's run (freed on skip)
    body = router.bodies[0]
    assert body["task_class"] == "flow_topic" and body["model"] == "claude-sonnet-5-5"
    assert res.tokens == 150 and res.usd_equiv == Decimal("0.4")


async def test_topic_asks_again_once_then_fails_and_a_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    C.ROUTER_OVERRIDE = FakeRouter(
        mc('{"candidates": ["سطح حمایت"]}'), mc('{"candidates": ["خط روند"]}')
    )

    async def taken(*_a: Any, **_k: Any) -> Any:
        raise ApiError(409, "topic_taken", "said")

    monkeypatch.setattr(T, "claim", taken)
    hub = FakeHub(**{"FROM lines.runs WHERE ref": run_row()})
    with pytest.raises(StepFailed) as e:
        await REGISTRY["topic"].run(ctx(hub, "topic"))
    assert e.value.code == "topic_taken" and e.value.retry
    C.ROUTER_OVERRIDE = FakeRouter(mc('{"candidates": ["کندل دوجی"]}'))

    async def free(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(T, "taken_by", free)
    res = await REGISTRY["topic"].run(ctx(hub, "topic", dry=True))
    assert res.text == "کندل دوجی" and res.data["claimed"] is False


# ------------------------------------------------------------ voice_check --
SCRIPT = "سلام دوستان امروز درباره‌ی سطح حمایت حرف میزنیم و بازپخش را کامنت کنید"


def heard(text: str, duration: float, gaps: tuple[float, ...] = ()) -> Any:
    async def fake(_hub: Any, _fid: str) -> dict[str, Any]:
        segs: list[dict[str, Any]] = []
        at, left = 0.2, list(gaps)
        while at < duration - 0.5:
            end = min(at + 1.5, duration - 0.2)
            segs.append({"start_s": at, "end_s": end, "text": "x"})
            at = end + (left.pop(0) if left else 0.1)
        return {"text": text, "duration_s": duration, "segments": segs}

    return fake


async def test_voice_check_passes_a_voice_that_says_the_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # «می زنیم» heard apart, «درباره ی» with a space: still the same words
    said = "سلام دوستان امروز درباره ی سطح حمایت حرف می زنیم و بازپخش را کامنت کنید"
    monkeypatch.setattr(voice_check, "TRANSCRIBE_OVERRIDE", heard(said, 5.6))
    inputs = {"voice": out(None, file_id="F1"), "script": out(SCRIPT)}
    res = await REGISTRY["voice_check"].run(
        ctx(FakeHub(), "voice_check", inputs=inputs,
            settings={"of": "voice", "script_from": "script"})
    )  # fmt: skip
    assert res.data["match"] >= 0.85 and res.file_id == "F1"


@pytest.mark.parametrize(
    ("said", "duration", "gaps", "word"),
    [
        ("سلام دوستان امروز", 5.6, (), "کلمه"),  # words missing
        (SCRIPT, 12.0, (), "طول"),  # far longer than the script's estimate
        (SCRIPT, 5.6, (2.5,), "سکوت"),  # a silence over two seconds
    ],
)
async def test_voice_check_fails_with_a_retry_so_the_voice_is_made_again(
    monkeypatch: pytest.MonkeyPatch, said: str, duration: float, gaps: tuple[float, ...], word: str
) -> None:
    monkeypatch.setattr(voice_check, "TRANSCRIBE_OVERRIDE", heard(said, duration, gaps))
    inputs = {"voice": out(None, file_id="F1"), "script": out(SCRIPT)}
    with pytest.raises(StepFailed) as e:
        await REGISTRY["voice_check"].run(
            ctx(FakeHub(), "voice_check", inputs=inputs, settings={"of": "voice"})
        )
    assert e.value.retry and e.value.code == "voice_mismatch" and word in e.value.reason_fa


# ---------------------------------------------------------------- inspire --
async def test_inspire_takes_the_first_pin_the_ledger_has_not_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pins = ('[{"image": "https://i.pinimg.com/1.jpg", "link": "https://www.pinterest.com/pin/111/",'
            ' "title": "یک"}, {"image": "https://i.pinimg.com/2.jpg",'
            ' "link": "https://www.pinterest.com/pin/222/", "title": "دو"}]')  # fmt: skip
    web = FakeWeb({"ok": True, "text_md": pins})
    C.WEB_OVERRIDE = web

    async def claim(tx: Any, scope: dict[str, Any], **kw: Any) -> tuple[dict[str, Any], bool]:
        if "111" in kw["url"]:
            raise ApiError(409, "topic_taken", "used")
        return {"url": kw["url"]}, True

    monkeypatch.setattr(T, "claim", claim)
    hub = FakeHub(**{"FROM lines.runs WHERE ref": run_row()})
    res = await REGISTRY["inspire"].run(
        ctx(hub, "inspire", inputs={"topic": out("کندل چکش")}, settings={"topic_from": "topic"})
    )
    assert web.sent[0]["prompt"] == "کندل چکش" and web.sent[0]["task"] == "search"
    assert res.data["reference"]["link"].endswith("/222/") and res.data["taken"] == 1


# --------------------------------------------------------------- workshop --
def test_the_workshop_turn_carries_a_short_tool_list_and_the_steps_effort() -> None:
    c = ctx(FakeHub(), "workshop", settings={"tools": ["Bash", "Read", "Nope", "Bash"],
                                             "effort": "max"})  # fmt: skip
    assert workshop.tools_of(c) == ["Bash", "Read"] and workshop.effort_of(c) == "max"
    many = ctx(FakeHub(), "workshop", settings={"tools": list(HANDS.ALLOWED_TOOLS)})
    assert len(workshop.tools_of(many)) == 10
    assert len(workshop.tools_of(ctx(FakeHub(), "workshop"))) <= 10
    assert workshop.effort_of(ctx(FakeHub(), "workshop", settings={"effort": "ultra"})) == "high"


async def test_the_workshop_step_starts_one_turn_and_waits_for_its_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: dict[str, Any] = {}

    async def server(_tx: Any) -> dict[str, Any]:
        return {"id": uuid4(), "name": "studio", "company_id": uuid4()}

    async def create(tx: Any, who: Any, **kw: Any) -> dict[str, Any]:
        started["work"] = kw
        return {"id": uuid4(), "ref": "W-000123"}

    async def start(tx: Any, who: Any, srv: Any, w: Any, **kw: Any) -> Any:
        started.update(kw, who=who)
        return HANDS.WorkshopRun(job="J1", work_ref=w["ref"], state="starting", turn=1,
                                 path="~/hq-workspace/W-000123", server="studio")  # fmt: skip

    monkeypatch.setattr(HANDS, "workshop_server", server)
    monkeypatch.setattr(W, "create", create)
    monkeypatch.setattr(HANDS, "start", start)
    hub = FakeHub(**{"FROM core.employees": {"id": uuid4(), "code": "AB-CEO", "kind": "ceo",
                                             "role": "ceo"}})  # fmt: skip
    inputs = {"script": out("متن گوینده"), "voice": out(None, file_id=str(uuid4())),
              "cover": out(None, file_id=str(uuid4()), files=())}  # fmt: skip
    res = await REGISTRY["workshop"].run(
        ctx(hub, "workshop", prompt="ریلز را بساز", inputs=inputs,
            settings={"effort": "max", "tools": ["Bash", "Read", "Write"]})
    )  # fmt: skip
    assert res.data["wait"] == "callback" and res.data["work"] == "W-000123"
    assert started["effort"] == "max" and started["tools"] == ["Bash", "Read", "Write"]
    assert started["extra_args"] == {"line_step": {"run": "LR-000001", "key": "workshop"}}
    assert len(started["files"]) == 2 and started["who"].code == "AB-CEO"
    assert started["work"]["mode"] == "on_server"
    assert "حداکثر ۲ پردازش" in started["brief"] and "متن گوینده" in started["brief"]


async def test_the_turns_end_completes_the_step_with_its_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video, cover = uuid4(), uuid4()
    job = {"id": uuid4(), "kind": "claude", "state": "done", "usage": {}, "summary_fa": "",
           "args": {"workspace": "W-000123", "line_step": {"run": "LR-000001", "key": "build"}}}  # fmt: skip
    called: list[dict[str, Any]] = []

    async def load_job(_tx: Any, _id: Any) -> dict[str, Any]:
        return job

    async def load(_tx: Any, _id: Any, lock: bool = False) -> dict[str, Any]:
        return {"id": uuid4(), "ref": "W-000123", "company_id": uuid4(), "status": "in_progress"}

    async def of_work(_tx: Any, _id: Any, lock: bool = False) -> dict[str, Any]:
        return {"id": uuid4(), "state": "working"}

    async def made(_tx: Any, _j: Any, _co: Any) -> list[str]:
        return [str(video), str(cover)]

    async def answer(_tx: Any, _hub: Any, _j: Any) -> str:
        return "ساختم: video.mp4 و cover.jpg"

    async def on_callback(_hub: Any, body: dict[str, Any]) -> dict[str, Any]:
        called.append(body)
        return {}

    from hq_api.lines import engine as LE

    monkeypatch.setattr(SV, "load_job", load_job)
    monkeypatch.setattr(W, "load", load)
    monkeypatch.setattr(WS, "of_work", of_work)
    monkeypatch.setattr(WS, "made_files", made)
    monkeypatch.setattr(SV, "full_answer", answer)
    monkeypatch.setattr(LE, "on_callback", on_callback)
    rows = [{"id": video, "name": "video.mp4", "mime": "video/mp4"},
            {"id": cover, "name": "cover.jpg", "mime": "image/jpeg"}]  # fmt: skip
    hub = FakeHub(**{"FROM work.work WHERE ref": uuid4(), "FROM llm.calls": Decimal("1.25"),
                     "FROM files.files": rows})  # fmt: skip
    assert await workshop.after_turn(hub, job["id"]) is True
    [body] = called
    assert body["ok"] and body["run"] == "LR-000001" and body["step"] == "build"
    assert body["files"] == [str(video), str(cover)] and body["file_id"] == str(video)
    assert body["via"] == "workshop" and body["usd_equiv"] == "1.25"
    assert any("status = :s" in s for s in hub.rows["_exec"])  # its own work is closed
    # a turn that left nothing fails the step with one plain line
    monkeypatch.setattr(WS, "made_files", lambda *_a: _none())
    called.clear()
    await workshop.after_turn(hub, job["id"])
    assert called[0]["ok"] is False and called[0]["error_fa"] == workshop.NO_FILES_FA
    # a workshop turn that is no line step's is left to the workspace
    job["args"] = {"workspace": "W-000123"}
    assert await workshop.after_turn(hub, job["id"]) is False


async def _none() -> list[str]:
    return []


# ---------------------------------------------------------------- package --
def package_hub(files: list[dict[str, Any]], **over: Any) -> FakeHub:
    return FakeHub(**{"FROM files.files": files, "FROM growth.automations a": flow_row(**over),
                      "FROM lines.runs WHERE ref": run_row(), "FROM growth.site_links": LINKS})  # fmt: skip


async def test_package_writes_the_three_texts_and_the_three_rules_by_code(
    stored: list[dict[str, Any]],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def zone(_tx: Any) -> str:
        return "Asia/Tehran"

    monkeypatch.setattr(FW, "zone_of", zone)
    v, s, c = uuid4(), uuid4(), uuid4()
    files = [{"id": v, "name": "video.mp4", "mime": "video/mp4", "size": 9},
             {"id": s, "name": "story.mp4", "mime": "video/mp4", "size": 9},
             {"id": c, "name": "cover.jpg", "mime": "image/jpeg", "size": 9}]  # fmt: skip
    parts = {"voice": "متن", "caption": "کپشن #ترید", "keyword": "بازپخش", "public": []}
    inputs = {"script": out("متن", data={"parts": parts}),
              "topic": out("کندل چکش", data={"topic": "کندل چکش"}),
              "build": out(None, file_id=str(v), files=(str(v), str(s), str(c)))}  # fmt: skip
    res = await REGISTRY["package"].run(ctx(package_hub(files), "package", inputs=inputs))
    d = res.data
    assert (d["video"], d["story"], d["cover"]) == (str(v), str(s), str(c))
    assert d["caption"] == "کپشن #ترید" and d["topic"] == "کندل چکش" and d["match_any"]
    texts = {f["name"]: f["data"].decode() for f in stored}
    assert set(texts) == {"caption.txt", "comment.txt", "topic.txt"}
    comment = texts["comment.txt"]
    assert "keyword: بازپخش" in comment and "match: any" in comment
    assert "reply: سلام! درباره‌ی «کندل چکش» 👇" in comment  # the policy's DM, the topic filled
    publics = [x[len("public: ") :] for x in comment.splitlines() if x.startswith("public: ")]
    assert publics[:2] == POLICY["public_pool"] and len(publics) == 10
    assert publics == d["public"]
    day = FW.day_of(run_row(), "Asia/Tehran").strftime("%Y%m%d")
    rules = d["rules"]
    assert set(rules) == {"comment", "story_reply", "dm"}
    for trigger, medium in (("comment", "comment"), ("story_reply", "story"), ("dm", "dm")):
        url = rules[trigger]["buttons"][0]["url"]
        assert url.startswith("https://pro-chart.com/next/?a=1&utm_source=instagram"), url
        assert f"utm_medium={medium}" in url and f"utm_content={day}" in url
        assert "utm_campaign=at_0042" in url and rules[trigger]["cooldown_days"] == 365
    assert rules["comment"]["match"] == "any" and rules["dm"]["match"] == "contains"
    assert f"link: {rules['comment']['buttons'][0]['url']}" in comment
    assert len(res.files) == 6 and res.file_id == str(v)


async def test_package_without_a_video_or_a_caption_fails_plainly(
    stored: list[dict[str, Any]],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def zone(_tx: Any) -> str:
        return "Asia/Tehran"

    monkeypatch.setattr(FW, "zone_of", zone)
    with pytest.raises(StepFailed) as e:
        await REGISTRY["package"].run(ctx(package_hub([]), "package", inputs={"s": out("x")}))
    assert e.value.code == "no_video"
    v = uuid4()
    files = [{"id": v, "name": "video.mp4", "mime": "video/mp4", "size": 9}]
    with pytest.raises(StepFailed) as e2:
        await REGISTRY["package"].run(
            ctx(package_hub(files), "package", inputs={"b": out(None, file_id=str(v))})
        )
    assert e2.value.code == "no_caption"


# ---------------------------------------------------------------- publish --
PKG = {"video": str(uuid4()), "story": str(uuid4()), "cover": str(uuid4()), "caption": "کپشن",
       "topic": "کندل", "rules": {"comment": {"keywords": ["x"]}, "story_reply": {"keywords": ["x"]},
                                  "dm": {"keywords": ["x"]}}}  # fmt: skip
ROUTE = {"accounts": ["pro.chart"], "command": "python3 hq_publish.py", "ready": True,
         "server_co": "IG", "server_name": "IG-Hub"}  # fmt: skip


async def test_a_flows_publish_takes_the_standing_path_and_a_dry_run_leaves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def route(_tx: Any, _co: Any) -> dict[str, Any]:
        return ROUTE

    sent: list[dict[str, Any]] = []

    async def send(tx: Any, who: Any, d: Any, f: Any, cover: Any, **kw: Any) -> dict[str, Any]:
        sent.append({"d": d, "f": f, "cover": cover, **kw})
        return {"id": uuid4()}

    async def nothing(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(SPB, "_route", route)
    monkeypatch.setattr(SPB, "_send", send)
    monkeypatch.setattr(SPB, "lock_publication", nothing)
    monkeypatch.setattr(SPB, "last_of", nothing)
    rows = [{"id": UUID(PKG[k]), "name": f"{k}.x", "mime": "video/mp4", "size": 1, "storage_key": k}
            for k in ("video", "story", "cover")]  # fmt: skip
    hub = FakeHub(**{"FROM growth.automations a": flow_row(), "FROM lines.runs WHERE ref": run_row(),
                     "FROM files.files": rows})  # fmt: skip
    settings = {"route": "standing"}
    dry = await REGISTRY["publish"].run(
        ctx(hub, "publish", settings=settings, inputs={"package": out(None, data=PKG)}, dry=True)
    )
    assert dry.via == "dry" and dry.data["would_publish"]["account"] == "pro.chart" and not sent
    assert dry.data["would_publish"]["rules"] == ["comment", "dm", "story_reply"]
    res = await REGISTRY["publish"].run(
        ctx(hub, "publish", settings=settings, inputs={"package": out(None, data=PKG)})
    )
    assert res.data["wait"] == "callback" and len(res.data["jobs"]) == 2
    reel, story = sent
    assert (reel["what"], story["what"]) == ("reel", "story")
    assert reel["caption"] == "کپشن" and story["caption"] == ""
    assert reel["scheduled_at"] == SOON and reel["account"] == "pro.chart"
    assert reel["flow"]["rules"] == PKG["rules"] and reel["flow"]["run"] == "LR-000001"
    assert reel["d"]["ref"] == "LR-000001" and reel["d"]["work_ref"] is None
    # no story: no story rule either
    sent.clear()
    hub.rows["FROM growth.automations a"] = flow_row(story=False)
    await REGISTRY["publish"].run(
        ctx(hub, "publish", settings=settings, inputs={"package": out(None, data=PKG)})
    )
    assert [x["what"] for x in sent] == ["reel"] and "story_reply" not in sent[0]["flow"]["rules"]


# ----------------------------------------------------------------- report --
async def test_report_writes_the_days_line() -> None:
    hub = FakeHub(**{"FROM lines.runs WHERE ref": {"usd_equiv": Decimal("1.5"), "tokens": 9}})
    pub = out("x", data={"published": [{"kind": "reel", "url": "https://instagram.com/reel/1"},
                                       {"kind": "story", "url": None}]})  # fmt: skip
    res = await REGISTRY["report"].run(
        ctx(hub, "report", inputs={"topic": out("کندل", data={"topic": "کندل"}), "publish": pub})
    )
    assert res.text == "امروز: ریلز و استوری «کندل» منتشر شد." and res.data["cost_usd"] == 1.5
    dry = await REGISTRY["report"].run(ctx(hub, "report", inputs={"publish": pub}, dry=True))
    assert dry.text.startswith("اجرای آزمایشی")
    none = await REGISTRY["report"].run(ctx(hub, "report", inputs={"publish": out("نشد")}))
    assert none.text == "امروز چیزی منتشر نشد: نشد"


# ------------------------------------------------- tts, gpt_text, cover --
async def test_tts_asks_the_api_first_with_the_companys_narrator(
    stored: list[dict[str, Any]],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs: list[dict[str, Any]] = []

    async def api(_hub: Any, job: dict[str, Any]) -> tuple[bytes, str]:
        jobs.append(job)
        return b"OggS", "audio/ogg"

    monkeypatch.setattr(tts, "API_OVERRIDE", api)
    web = FakeWeb({"ok": False, "error": "off"})
    C.WEB_OVERRIDE = web
    hub = FakeHub(**{"FROM media.narrators": {"voice": "Cruz", "style_fa": ""}})
    res = await REGISTRY["tts"].run(
        ctx(hub, "tts", settings={"voice": "Puck"}, inputs={"script": out("سلام")})
    )
    assert jobs[0]["voice"] == "Cruz" and jobs[0]["text"] == "سلام" and not web.sent
    assert res.via == "gemini-api" and res.data["engine"] == "gemini_api"
    assert "lite" not in res.data["model"]

    async def none(_hub: Any, _job: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(tts, "API_OVERRIDE", none)
    C.WEB_OVERRIDE = FakeWeb(
        {"ok": True, "file": {"name": "a.wav", "mime": "audio/wav", "b64": b64(b"RIFF")}}
    )
    res = await REGISTRY["tts"].run(ctx(hub, "tts", inputs={"script": out("سلام")}))
    assert res.via == "aistudio-web" and res.data["voice"] == "Cruz"  # the page second


async def test_gpt_text_parts_give_the_narrator_its_part_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    async def seat(_ctx: Any, text: str, **_k: Any) -> dict[str, Any]:
        asked.append(text)
        return {"text": "voice: بخوان این را\ncaption: کپشن\nkeyword: بازپخش\npublic: یک",
                "tokens": 10, "usd_equiv": 0, "model": "gpt"}  # fmt: skip

    monkeypatch.setattr(C, "ask_seat", seat)
    res = await REGISTRY["gpt_text"].run(ctx(FakeHub(), "gpt_text", settings={"parts": True}))
    assert "keyword:" in asked[0] and res.text == "بخوان این را"
    assert res.data["parts"]["keyword"] == "بازپخش" and res.data["parts"]["public"] == ["یک"]


async def test_cover_without_a_folder_makes_the_image_in_a_new_regular_chat(
    stored: list[dict[str, Any]],  # noqa: F811
) -> None:
    web = FakeWeb({"ok": True, "file": {"name": "c.png", "mime": "image/png", "b64": b64(PNG)}})
    C.WEB_OVERRIDE = web
    res = await REGISTRY["cover"].run(
        ctx(FakeHub(), "cover", prompt="کاور امروز", settings={"folder": "optional"})
    )
    assert web.sent[0]["task"] == "image" and "files" not in web.sent[0]
    assert res.file_id and res.data["from_files"] == 0


def test_the_fakes_are_the_shared_ones() -> None:
    assert isinstance(out("x"), StepOutput) and MP4 and SimpleNamespace
