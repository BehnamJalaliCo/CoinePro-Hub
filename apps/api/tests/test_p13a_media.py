"""Prompt 13 §2 (contract §22.2, §22.7): the media studio.

- An unsealed series publishes nothing (409 series_not_sealed); editing a
  sealed series takes its seal away.
- One item goes from its script (a fake-model run through the gateway) to the
  render (the one-shot's api), the checks and the review, and is published
  with a fake Telegram and a fake Instagram.
- A failed check (no risk warning) makes a card, not a publish.
- A composition with fetch() or <script src=https://…> is refused.
- A signed URL is one file for 15 minutes; any other URL is 404.
- The company's kill switch holds scheduled publishing; nothing at all runs
  while the holding is locked.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from hq_api.audit import SYSTEM
from hq_api.domain import decisions as D
from hq_api.domain import egress as G
from hq_api.domain import studio as S
from hq_api.domain import studio_publish as P
from hq_api.hub import Hub
from hq_api.worker.activities import _ScopedTx
from hq_api.worker.studio_activities import StudioActivities

from .conftest import MEDIA_TOKEN, TTS_TOKEN, agent_headers, idem, step_up
from .p10_support import holding_switch

MEDIA = {"Authorization": f"Bearer {MEDIA_TOKEN}"}
TTS = {"Authorization": f"Bearer {TTS_TOKEN}"}
INK, ACCENT = "#0E1116", "#F2B705"
FFMPEG = "/usr/bin/ffmpeg"

SCRIPT = (
    "«قلاب»\nبیت‌کوین (BTC) این هفته کجا ایستاده؟\n"
    "«بدنه»\nحمایت مهم در 64,000 دلار است و مقاومت در 71,500 دلار.\n"
    "«هشدار ریسک»\nترید پرریسک است و ممکن است سرمایه از دست برود.\n"
    "«کپشن»\nسطح‌های این هفته‌ی بیت‌کوین. ترید پرریسک است و ممکن است سرمایه از دست برود."
)
SOURCES = [
    {
        "kind": "url",
        "url": "https://example.org/levels",
        "note": "حمایت 64,000 و مقاومت 71,500، خوانده‌شده 1405-08-01",
    },
]
SHOTS = [
    {"n": 1, "duration_s": 10, "visual_fa": "نمودار ساده", "text_on_screen_fa": "BTC کجاست؟", "voice_fa": "بیت‌کوین این هفته کجا ایستاده؟"},
    {"n": 2, "duration_s": 12, "visual_fa": "دو سطح", "text_on_screen_fa": "64,000 · 71,500", "voice_fa": "حمایت در شصت و چهار هزار و مقاومت در هفتاد و یک و نیم هزار دلار."},
    {"n": 3, "duration_s": 8, "visual_fa": "هشدار", "text_on_screen_fa": "ترید پرریسک است", "voice_fa": "ترید پرریسک است و ممکن است سرمایه از دست برود."},
]  # fmt: skip
COMPOSITION = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>body{{margin:0;background:{INK};font-family:IRANYekanX}}
.t{{color:{ACCENT};font:700 72px/1.3 IRANYekanX;animation:in 1s ease-out both}}
@keyframes in{{from{{opacity:0}}to{{opacity:1}}}}</style>
<script src="/lib/anime.min.js"></script></head>
<body><div class="t">بیت‌کوین <bdi>BTC</bdi> کجاست؟</div>
<script>anime({{targets: '.t', translateY: [40, 0], duration: 1000}});</script></body></html>"""


# ---------------------------------------------------------------- setup --
async def hire(su: Any, co: dict[str, Any], role: str) -> str:
    dept = await su.fetchval(
        "SELECT id FROM core.departments WHERE company_id = $1 AND code = 'MEDIA'", co["id"]
    )
    code = await su.fetchval("SELECT core.issue_employee_code($1, $2)", co["id"], dept)
    if role == "media_director":
        return f"{co['code']}-MEDIA-MGR"
    mgr = await su.fetchval(
        "SELECT id FROM core.employees WHERE code = $1", f"{co['code']}-MEDIA-MGR"
    )
    await su.execute(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en, reports_to, role)
           VALUES ($1, $2, $3, 'employee', $4, $4, $5, $4)""",
        co["id"], dept, code, role, mgr,
    )  # fmt: skip
    await su.execute(
        """INSERT INTO msg.threads (code, kind, company_id, employee_id, title_fa)
           SELECT code, 'employee', company_id, id, title_fa FROM core.employees WHERE code = $1""",
        code,
    )
    return str(code)


async def team(su: Any, co: dict[str, Any]) -> dict[str, str]:
    roles = (
        "scriptwriter",
        "video_director",
        "motion_designer",
        "voice_producer",
        "media_director",
    )
    return {r: await hire(su, co, r) for r in roles}


async def brand(su: Any, co: dict[str, Any]) -> None:
    mark = {"vb": "0 0 10 10", "layers": [{"role": "ink", "color": INK, "d": "M0 0h10v10H0z"}]}
    await su.execute(
        """INSERT INTO org.company_brands (company_id, version, state, part, source, mark, ink, accent, palette,
               digest, created_by_kind, created_by_code, activated_at)
           VALUES ($1, 1, 'active', 'mark', '{"kind": "seed", "sha256": "x"}', $2::jsonb, $3, $4, $5::jsonb,
                   repeat('c', 64), 'service', 'seed', now())""",
        co["id"], json.dumps(mark), INK, ACCENT,
        json.dumps([{"hex": INK, "share": 0.6}, {"hex": ACCENT, "share": 0.4}]),
    )  # fmt: skip


async def accounts(su: Any, co: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    low = co["code"].lower()
    for key, site in (
        (f"telegram-{low}", f"https://t.me/coine_{low}"),
        (f"instagram-{low}", f"https://www.instagram.com/coine_{low}/"),
    ):
        await su.execute(
            """INSERT INTO tools.accounts (key, site, title_fa, companies, policy)
               VALUES ($1, $2, 'انتشار', ARRAY[$3]::text[], '{}'::jsonb) ON CONFLICT (key) DO NOTHING""",
            key, site, co["code"],
        )  # fmt: skip

    async def secret(bao: Any, key: str) -> str | None:
        return "bot-or-page-token-for-tests" if key.endswith(f"-{low}") else None

    async def has(bao: Any, key: str) -> bool:
        return bool(await secret(bao, key))

    monkeypatch.setattr(G, "read_secret", secret)
    monkeypatch.setattr(G, "has_secret", has)


def series_body(co: str, **over: Any) -> dict[str, Any]:
    low = co.lower()
    return {
        "company": co,
        "title_fa": "سطح‌های هفته",
        "kind": "reel",
        "targets": [
            {"channel": "instagram", "account": f"instagram-{low}", "placement": "instagram_reel"},
            {"channel": "telegram", "account": f"telegram-{low}", "placement": "telegram_post"},
        ],
        "schedule": "FREQ=DAILY;BYHOUR=9;BYMINUTE=0",
        "topics": {"pool": ["بیت‌کوین", "اتریوم"], "rule_fa": None},
        "format": {"aspect": "9:16", "duration_s": 30, "voice": {"voice_id": "default"}, "captions": True,
                   "music": "none", "overlay": {"cta_fa": "کانال را دنبال کنید", "mark": True}},
        "auto_publish": True,
        "max_per_day": 2,
        **over,
    }  # fmt: skip


async def make_series(
    client: httpx.AsyncClient, owner: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    r = await client.post("/api/v1/media/series", headers={**owner, **idem()}, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def seal(
    client: httpx.AsyncClient, hub: Hub, session: dict[str, Any], s: dict[str, Any]
) -> httpx.Response:
    su_ = await step_up(hub, session["session_id"], "media.series", s["digest"])
    return await client.post(
        f"/api/v1/media/series/{s['ref']}/seal",
        headers={**session["headers"], **su_},
        json={"digest": s["digest"]},
    )


async def tick_one(hub: Hub, su: Any, s: dict[str, Any]) -> str:
    """Make the series' next item now: an hourly occurrence ten minutes ago."""
    m = (datetime.now(UTC) - timedelta(minutes=10)).minute
    await su.execute(
        "UPDATE media.series SET schedule = $2, ticked_at = now() - interval '20 minutes' WHERE ref = $1",
        s["ref"], f"FREQ=HOURLY;BYMINUTE={m}",
    )  # fmt: skip
    async with _ScopedTx(hub)() as tx:
        out = await S.tick_series(tx, hub)
    made = list(out["made"])
    assert len(made) == 1, out
    return made[0]


async def item(client: httpx.AsyncClient, owner: dict[str, str], ref: str) -> dict[str, Any]:
    r = await client.get(f"/api/v1/media/items/{ref}", headers=owner)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def tool(
    client: httpx.AsyncClient, code: str, path: str, body: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"/internal/v1/media/{path}", headers={**await agent_headers(code), **idem()}, json=body
    )


def mp4(seconds: int, w: int = 1080, h: int = 1920) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "o.mp4"
        subprocess.run(  # the test image's own ffmpeg, fixed arguments
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"color=c=0x0E1116:s={w}x{h}:d={seconds}:r=1",
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(seconds), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(out)],
            check=True, timeout=120,
        )  # fmt: skip
        return out.read_bytes()


def jpeg() -> bytes:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "p.jpg"
        subprocess.run(
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=0x0E1116:s=108x192", "-frames:v", "1", str(out)],
            check=True, timeout=60,
        )  # fmt: skip
        return out.read_bytes()


async def render(client: httpx.AsyncClient, ref: str, seconds: int = 30) -> dict[str, Any]:
    """The render one-shot's api: claim, the outputs, done."""
    r = await client.post("/internal/v1/media/render/claim", headers=MEDIA)
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["item"] == ref and job["composition"]["format"] == "html"
    assert job["overlay"]["mark"] is True and job["brand"]["mark"]
    main = job["outputs"][0]
    base = f"/internal/v1/media/render/{job['id']}/output"
    up = await client.post(base, params={"name": main["name"], "kind": "video", "width": 1080, "height": 1920},
                           content=mp4(seconds), headers={**MEDIA, "Content-Type": "video/mp4"})  # fmt: skip
    assert up.status_code == 201, up.text
    up = await client.post(base, params={"name": main["name"], "kind": "poster"}, content=jpeg(),
                           headers={**MEDIA, "Content-Type": "image/jpeg"})  # fmt: skip
    assert up.status_code == 201, up.text
    vtt = "WEBVTT\n\n00:00.000 --> 00:03.000\nبیت‌کوین کجاست؟\n".encode()
    up = await client.post(base, params={"name": main["name"], "kind": "captions"}, content=vtt,
                           headers={**MEDIA, "Content-Type": "text/vtt"})  # fmt: skip
    assert up.status_code == 201, up.text
    done = await client.post(f"/internal/v1/media/render/{job['id']}/done", headers=MEDIA,
                             json={"metrics": {"peak_rss_mb": 600, "seconds": 90, "frames": 900}})  # fmt: skip
    assert done.status_code == 204, done.text
    return dict(job)


class FakePlatforms:
    """Telegram's Bot API and Instagram's Graph API as egress answers them."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.files: list[list[tuple[str, int, str]]] = []

    async def call(
        self, hub: Any, call: dict[str, Any], files: list[tuple[str, bytes, str]]
    ) -> dict[str, Any]:
        self.calls.append(call)
        self.files.append([(n, len(b), m) for n, b, m in files])
        m = call["method"]
        data: dict[str, Any] = {
            "sendVideo": {"message_id": 41, "chat_id": call["payload"].get("chat_id")},
            "sendPhoto": {"message_id": 42},
            "sendMediaGroup": {"message_ids": [43, 44]},
            "deleteMessage": {},
            "me": {"user_id": "1789", "username": "coine_" + call.get("_low", "")},
            "limit": {"quota_usage": 0},
            "create": {"id": "c-1"},
            "status": {"status_code": "FINISHED"},
            "publish": {"id": "m-1"},
            "permalink": {"permalink": "https://www.instagram.com/reel/abc/"},
        }.get(m, {})
        return {"outcome": "ok", "code": None, "data": data, "entries": []}


@asynccontextmanager
async def platforms(low: str) -> AsyncIterator[FakePlatforms]:
    fake = FakePlatforms()
    orig = fake.call

    async def call(
        hub: Any, c: dict[str, Any], files: list[tuple[str, bytes, str]]
    ) -> dict[str, Any]:
        return await orig(hub, {**c, "_low": low}, files)

    fake.call = call  # type: ignore[method-assign]
    P.OVERRIDE = fake
    try:
        yield fake
    finally:
        P.OVERRIDE = None


# ---------------------------------------------------------------- tests --
async def test_an_unsealed_series_publishes_nothing_and_an_edit_takes_the_seal_away(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    s = await make_series(client, h, series_body(co["code"]))
    assert s["status"] == "draft" and s["next_at"] == [] and s["checks"] == list(S.CHECK_KEYS)
    # A draft makes no item and nothing it holds is published.
    async with _ScopedTx(hub)() as tx:
        out = await S.tick_series(tx, hub)
    assert not [r for r in out["made"] if r.startswith("MI-")] or all(
        (await item(client, h, r))["series"] != s["ref"] for r in out["made"]
    )
    one = await client.post("/api/v1/media/items", headers={**h, **idem()},
                            json={"company": co["code"], "kind": "reel", "brief_md": "یک ریلز", "series": s["ref"]})  # fmt: skip
    assert one.status_code == 201, one.text
    r = await client.post(
        f"/api/v1/media/items/{one.json()['ref']}/publish", headers={**h, **idem()}
    )
    assert r.status_code == 409 and r.json()["code"] == "series_not_sealed"
    # The seal is a step-up on the digest; another digest is a conflict.
    r = await client.post(
        f"/api/v1/media/series/{s['ref']}/seal", headers=h, json={"digest": s["digest"]}
    )
    assert r.status_code == 403 and r.json()["code"] == "step_up_required"
    other = {**s, "digest": "f" * 64}
    r = await seal(client, hub, owner_session, other)
    assert r.status_code == 409 and r.json()["code"] == "version_conflict"
    r = await seal(client, hub, owner_session, s)
    assert r.status_code == 200, r.text
    sealed = r.json()
    assert sealed["status"] == "sealed" and sealed["sealed_at"] and len(sealed["next_at"]) == 5
    # Editing it takes the seal away: back to `proposed`, nothing runs.
    body = series_body(co["code"], max_per_day=1)
    r = await client.put(
        f"/api/v1/media/series/{s['ref']}",
        headers={**h, "If-Match": str(sealed["version"])},
        json=body,
    )
    assert r.status_code == 200, r.text
    edited = r.json()
    assert (
        edited["status"] == "proposed"
        and edited["sealed_at"] is None
        and edited["digest"] != s["digest"]
    )
    assert "مُهر قبلی" in edited["status_note_fa"]
    await su.execute(
        "UPDATE media.series SET ticked_at = now() - interval '2 hours', schedule = 'FREQ=HOURLY;BYMINUTE=0' WHERE ref = $1",
        s["ref"],
    )
    async with _ScopedTx(hub)() as tx:
        out = await S.tick_series(tx, hub)
    assert not await su.fetchval(
        "SELECT count(*) FROM media.items i JOIN media.series s ON s.id = i.series_id WHERE s.ref = $1 AND i.slot_at IS NOT NULL",
        s["ref"],
    )


async def test_one_item_from_its_script_to_its_publishing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, agents: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    from .test_agents import run, runs_of, step

    co = await new_company()
    h = owner_session["headers"]
    staff = await team(su, co)
    await brand(su, co)
    await accounts(su, co, monkeypatch)
    s = await make_series(client, h, series_body(co["code"]))
    assert (await seal(client, hub, owner_session, s)).status_code == 200
    ref = await tick_one(hub, su, s)
    x = await item(client, h, ref)
    assert x["state"] == "scripting" and x["topic_fa"] == "بیت‌کوین" and x["series"] == s["ref"]
    # The script, by a fake-model run of the scriptwriter, through the gateway.
    queued = [r for r in await runs_of(su, staff["scriptwriter"]) if r["state"] == "queued"]
    assert queued, "the step's work item woke the scriptwriter"
    agents.fake.enqueue(
        staff["scriptwriter"],
        step(
            "سناریو را نوشتم.",
            (
                "media.item",
                {"ref": ref, "step": "script", "script": {"text_fa": SCRIPT, "sources": SOURCES}},
            ),
        ),
    )
    out = await run(agents, queued[-1]["id"])
    assert out["state"] == "done", out
    x = await item(client, h, ref)
    assert x["state"] == "directing" and x["script"]["text_fa"] == SCRIPT
    # Direction and composition (the tools' api), the voice off (no tts profile).
    r = await tool(
        client,
        staff["video_director"],
        "item",
        {"ref": ref, "step": "direction", "direction": {"shots": SHOTS}},
    )
    assert r.status_code == 200, r.text
    r = await tool(
        client,
        staff["scriptwriter"],
        "item",
        {
            "ref": ref,
            "step": "composition",
            "composition": {"format": "html", "source": COMPOSITION},
        },
    )
    assert r.status_code == 403  # not the step's role
    r = await tool(
        client,
        staff["motion_designer"],
        "item",
        {
            "ref": ref,
            "step": "composition",
            "composition": {"format": "html", "source": COMPOSITION},
        },
    )
    assert r.status_code == 200, r.text
    x = await item(client, h, ref)
    assert x["state"] == "rendering" and x["composition"]["version"] == 1
    assert "صدای هاب خاموش" in (x["state_note_fa"] or "") or x["voice"] is None
    job = await render(client, ref)
    assert job["voice"] is None and job["captions"], "captions from the shots' voice lines"
    x = await item(client, h, ref)
    assert x["state"] == "review", x
    checks = {c["key"]: c for c in x["checks"]}
    assert [checks[k]["result"] for k in S.CHECK_KEYS[:-1]] == ["pass"] * 6, x["checks"]
    assert x["render"]["mime"] == "video/mp4" and x["captions"]["mime"] == "text/vtt"
    assert x["render"]["variants"]["poster"]
    # The director's review: only the media director reviews.
    r = await tool(
        client,
        staff["motion_designer"],
        "review",
        {"ref": ref, "verdict": "pass", "note_md": "خوب"},
    )
    assert r.status_code == 403
    r = await tool(
        client,
        staff["media_director"],
        "review",
        {"ref": ref, "verdict": "pass", "note_md": "قبول"},
    )
    assert r.status_code == 200, r.text
    x = await item(client, h, ref)
    assert x["state"] == "scheduled" and x["publish_at"], x
    await su.execute(
        "UPDATE media.items SET publish_at = now() - interval '1 minute' WHERE ref = $1", ref
    )
    async with platforms(co["code"].lower()) as fake:
        out = await P.publish_due(hub, only=ref)
    assert out["published"] == [ref], out
    x = await item(client, h, ref)
    assert x["state"] == "published"
    rows = {p["placement"]: p for p in x["publish"]}
    assert rows["telegram_post"]["external_id"] == "41" and rows["telegram_post"]["url"].endswith(
        "/41"
    )
    assert (
        rows["instagram_reel"]["external_id"] == "m-1"
        and "instagram.com" in rows["instagram_reel"]["url"]
    )
    tg = next(c for c in fake.calls if c["method"] == "sendVideo")
    assert P.AI_LABEL in tg["payload"]["caption"] and "سرمایه" in tg["payload"]["caption"]
    create = next(c for c in fake.calls if c["method"] == "create")
    assert create["payload"]["media_type"] == "REELS"
    url = create["payload"]["video_url"]
    assert url.startswith("https://hq.test/public/v1/media/")
    assert P.verify(hub, url.rsplit("/", 1)[1]) == uuid.UUID(x["render"]["id"])
    assert all(
        "bot-or-page" not in json.dumps(c, ensure_ascii=False) or c.get("token") for c in fake.calls
    )
    log = await su.fetch(
        "SELECT placement, outcome, external_id FROM media.publish_log WHERE item_id = $1",
        uuid.UUID(x["id"]),
    )
    assert {(r["placement"], r["outcome"]) for r in log} == {
        ("telegram_post", "ok"),
        ("instagram_reel", "ok"),
    }
    limits = (await client.get("/api/v1/media/limits", headers=h)).json()
    ig = next(lim for lim in limits if lim["account"] == f"instagram-{co['code'].lower()}")
    assert ig["per_24h"] == 50 and ig["used_24h"] == 1


async def _to_review(client: httpx.AsyncClient, su: Any, hub: Hub, h: dict[str, str], co: dict[str, Any],
                     staff: dict[str, str], ref: str, script: str) -> dict[str, Any]:  # fmt: skip
    for code, body in (
        (
            staff["scriptwriter"],
            {"ref": ref, "step": "script", "script": {"text_fa": script, "sources": SOURCES}},
        ),
        (staff["video_director"], {"ref": ref, "step": "direction", "direction": {"shots": SHOTS}}),
        (
            staff["motion_designer"],
            {
                "ref": ref,
                "step": "composition",
                "composition": {"format": "html", "source": COMPOSITION},
            },
        ),
    ):
        r = await tool(client, code, "item", body)
        assert r.status_code == 200, r.text
    await render(client, ref)
    return await item(client, h, ref)


async def test_a_failed_check_makes_a_card_not_a_publish(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    staff = await team(su, co)
    await brand(su, co)
    await accounts(su, co, monkeypatch)
    s = await make_series(client, h, series_body(co["code"]))
    assert (await seal(client, hub, owner_session, s)).status_code == 200
    ref = await tick_one(hub, su, s)
    no_warning = "«قلاب»\nبیت‌کوین این هفته کجاست؟\n«کپشن»\nسطح‌های بیت‌کوین."
    shots = [dict(x, voice_fa="بیت‌کوین کجاست؟", text_on_screen_fa="BTC") for x in SHOTS]
    monkeypatch.setattr(__import__(__name__), "SHOTS", shots, raising=False)
    x = await _to_review(client, su, hub, h, co, staff, ref, no_warning)
    checks = {c["key"]: c for c in x["checks"]}
    assert (
        checks["risk_warning"]["result"] == "fail"
        and "هشدار ریسک" in checks["risk_warning"]["note_fa"]
    )
    r = await tool(
        client,
        staff["media_director"],
        "review",
        {"ref": ref, "verdict": "pass", "note_md": "بازبینی شد"},
    )
    assert r.status_code == 200, r.text
    x = await item(client, h, ref)
    assert x["state"] == "waiting_owner" and x["decision_ref"], x
    card = await su.fetchrow(
        "SELECT kind, action_class, payload, status FROM cartable.decisions WHERE ref = $1",
        x["decision_ref"],
    )
    payload = json.loads(card["payload"])
    assert (card["kind"], card["action_class"], card["status"]) == (
        "media_publish",
        "A3",
        "pending",
    )
    assert payload["item"] == ref and payload["why"] == "check_failed"
    assert {p["placement"]: p["via"] for p in payload["placements"]} == {
        "instagram_reel": "api",
        "telegram_post": "api",
    }
    async with platforms(co["code"].lower()) as fake:
        out = await P.publish_due(hub)
        assert ref not in out.get("published", []) and not fake.calls
        # The owner's seal on the card (🔏 decision.approve) publishes it now.
        r = await client.post(f"/api/v1/media/items/{ref}/publish", headers={**h, **idem()})
        assert r.status_code == 403 and r.json()["code"] == "step_up_required"
        su_ = await step_up(hub, owner_session["session_id"], "decision.approve", x["decision_ref"])
        r = await client.post(f"/api/v1/media/items/{ref}/publish", headers={**h, **su_, **idem()})
        assert r.status_code == 200, r.text
        async with hub.db.tx(await hub.companies.ids()) as tx:
            eff = await D.apply_effect(tx, x["decision_ref"], SYSTEM)
        assert eff["state"] == "scheduled", eff
        out = await P.publish_due(hub, only=ref)
        assert out["published"] == [ref]
    assert (await item(client, h, ref))["state"] == "published"


async def test_a_composition_that_reaches_for_the_network_is_refused(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    staff = await team(su, co)
    r = await client.post("/api/v1/media/items", headers={**owner, **idem()},
                          json={"company": co["code"], "kind": "reel", "brief_md": "یک ریلز"})  # fmt: skip
    ref = r.json()["ref"]
    for code, body in (
        (
            staff["scriptwriter"],
            {"ref": ref, "step": "script", "script": {"text_fa": SCRIPT, "sources": SOURCES}},
        ),
        (staff["video_director"], {"ref": ref, "step": "direction", "direction": {"shots": SHOTS}}),
    ):
        assert (await tool(client, code, "item", body)).status_code == 200
    for bad, rule in (
        (COMPOSITION.replace("</body>", "<script>fetch('/x')</script></body>"), "fetch"),
        (
            COMPOSITION.replace(
                'src="/lib/anime.min.js"', 'src="https://cdn.example.com/anime.js"'
            ),
            "network",
        ),
        (
            COMPOSITION.replace("IRANYekanX}}", "Vazirmatn}}", 1).replace(
                "font-family:IRANYekanX", "font-family:Vazirmatn"
            ),
            "font",
        ),
        (COMPOSITION.replace("</body>", "<p>owner@example.com</p></body>"), "secret"),
    ):
        r = await tool(
            client,
            staff["motion_designer"],
            "item",
            {"ref": ref, "step": "composition", "composition": {"format": "html", "source": bad}},
        )
        assert r.status_code == 422, r.text
        assert rule in r.json()["fields"]["composition"], r.json()
    assert (await item(client, owner, ref))["state"] == "composing"
    assert not await su.fetchval(
        "SELECT count(*) FROM media.compositions c JOIN media.items i ON i.id = c.item_id WHERE i.ref = $1",
        ref,
    )


async def test_a_signed_url_is_one_file_for_fifteen_minutes(
    client: httpx.AsyncClient, hub: Hub, su: Any, new_company: Callable[..., Any]
) -> None:
    co = await new_company()
    key, sha = await hub.storage.put(b"\xff\xd8\xff" + b"0" * 64)
    async with hub.db.tx([co["id"]]) as tx:
        from hq_api.domain import files as F

        fid = await F.insert(tx, company_id=co["id"], name="r.jpg", mime="image/jpeg", size=67, sha256=sha,
                             storage_key=key, kind="image", by_kind="service", by_code="media")  # fmt: skip
        owners = await F.insert(tx, company_id=co["id"], name="o.jpg", mime="image/jpeg", size=67, sha256=sha,
                                storage_key=key, kind="image", by_kind="owner", by_code="owner")  # fmt: skip
    token = P.sign(hub, fid)
    r = await client.get(f"/public/v1/media/{token}")
    assert (
        r.status_code == 200
        and r.content.startswith(b"\xff\xd8\xff")
        and r.headers["cache-control"] == "no-store"
    )
    assert (await client.head(f"/public/v1/media/{token}")).status_code == 200
    expired = P.sign(hub, fid, now=time.time() - 16 * 60)
    assert (await client.get(f"/public/v1/media/{expired}")).status_code == 404
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert (await client.get(f"/public/v1/media/{forged}")).status_code == 404
    assert (
        await client.get(f"/public/v1/media/{P.sign(hub, owners)}")
    ).status_code == 404  # not a render
    assert (await client.get(f"/public/v1/media/{P.sign(hub, uuid.uuid4())}")).status_code == 404
    assert (await client.get("/public/v1/media/x")).status_code == 404
    assert P.verify(hub, token, now=time.time() + 15 * 60 + 1) is None
    assert (
        P.sign(hub, fid, ttl_s=3600)
        and P.verify(hub, P.sign(hub, fid, ttl_s=3600), now=time.time() + 16 * 60) is None
    )


async def test_the_company_kill_switch_holds_scheduled_publishing(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    staff = await team(su, co)
    await brand(su, co)
    await accounts(su, co, monkeypatch)
    s = await make_series(client, h, series_body(co["code"]))
    assert (await seal(client, hub, owner_session, s)).status_code == 200
    ref = await tick_one(hub, su, s)
    await _to_review(client, su, hub, h, co, staff, ref, SCRIPT)
    assert (
        await tool(
            client,
            staff["media_director"],
            "review",
            {"ref": ref, "verdict": "pass", "note_md": "قبول"},
        )
    ).status_code == 200
    await su.execute(
        "UPDATE media.items SET publish_at = now() - interval '1 minute' WHERE ref = $1", ref
    )
    await su.execute(
        "UPDATE control.kill_switches SET state = 'engaged' WHERE company_id = $1", co["id"]
    )
    try:
        async with platforms(co["code"].lower()) as fake:
            out = await P.publish_due(hub, only=ref)
            assert out["waiting"].get(ref) == "company_locked" and not fake.calls
        assert (await item(client, h, ref))["state"] == "scheduled"
    finally:
        await su.execute(
            "UPDATE control.kill_switches SET state = 'released' WHERE company_id = $1", co["id"]
        )
    async with platforms(co["code"].lower()):
        assert (await P.publish_due(hub, only=ref))["published"] == [ref]


async def test_nothing_runs_while_the_holding_is_locked(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    staff = await team(su, co)
    await brand(su, co)
    await accounts(su, co, monkeypatch)
    s = await make_series(client, h, series_body(co["code"]))
    assert (await seal(client, hub, owner_session, s)).status_code == 200
    ref = await tick_one(hub, su, s)
    for code, body in (
        (
            staff["scriptwriter"],
            {"ref": ref, "step": "script", "script": {"text_fa": SCRIPT, "sources": SOURCES}},
        ),
        (staff["video_director"], {"ref": ref, "step": "direction", "direction": {"shots": SHOTS}}),
        (
            staff["motion_designer"],
            {
                "ref": ref,
                "step": "composition",
                "composition": {"format": "html", "source": COMPOSITION},
            },
        ),
    ):
        assert (await tool(client, code, "item", body)).status_code == 200
    m = (datetime.now(UTC) - timedelta(minutes=10)).minute
    await su.execute(
        "UPDATE media.series SET schedule = $2, ticked_at = now() - interval '20 minutes' WHERE ref = $1",
        s["ref"],
        f"FREQ=HOURLY;BYMINUTE={m}",
    )
    acts = StudioActivities(hub, _ScopedTx(hub))
    async with holding_switch(su, "engaged"), platforms(co["code"].lower()) as fake:
        out = await acts.media_sweep()
        assert out == {"skipped": True, "reason": "holding_locked"}
        assert (
            await client.post("/internal/v1/media/render/claim", headers=MEDIA)
        ).status_code == 204
        assert (await client.post("/internal/v1/tts/media/claim", headers=TTS)).status_code == 204
        assert (await P.publish_due(hub)) == {"skipped": True, "reason": "holding_locked"}
        assert await acts.recheck() == {"skipped": True, "reason": "holding_locked"}
        assert not fake.calls
    assert (
        await su.fetchval(
            "SELECT count(*) FROM media.items WHERE series_id = (SELECT id FROM media.series WHERE ref = $1)",
            s["ref"],
        )
        == 1
    )
    assert (
        await su.fetchval(
            "SELECT state FROM media.render_jobs WHERE item_id = (SELECT id FROM media.items WHERE ref = $1)",
            ref,
        )
        == "queued"
    )
    # Released, the sweep makes the due item and the one-shot gets its job.
    out = await acts.media_sweep()
    assert len(out["made"]) == 1, out
    assert (await client.post("/internal/v1/media/render/claim", headers=MEDIA)).status_code == 200


async def test_review_changes_go_back_to_the_named_role_and_a_reject_ends_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    staff = await team(su, co)
    await brand(su, co)
    r = await client.post("/api/v1/media/items", headers={**owner, **idem()},
                          json={"company": co["code"], "kind": "reel", "brief_md": "یک ریلز"})  # fmt: skip
    ref = r.json()["ref"]
    await _to_review(client, su, hub, owner, co, staff, ref, SCRIPT)
    r = await tool(client, staff["media_director"], "review",
                   {"ref": ref, "verdict": "changes", "note_md": "شات ۲: عدد را بزرگ‌تر کن (video_director)"})  # fmt: skip
    assert r.status_code == 200, r.text
    x = await item(client, owner, ref)
    assert x["state"] == "directing" and x["qc"]["verdict"] == "changes"
    w = await su.fetchrow(
        """SELECT w.brief, e.code FROM media.items i JOIN work.work w ON w.id = i.step_work_id
           JOIN core.employees e ON e.id = w.assignee_id WHERE i.ref = $1""",
        ref,
    )
    assert w["code"] == staff["video_director"] and "عدد را بزرگ‌تر کن" in w["brief"]
    # Back through direction, composition (a new version), render and review: reject.
    assert (
        await tool(
            client,
            staff["video_director"],
            "item",
            {"ref": ref, "step": "direction", "direction": {"shots": SHOTS}},
        )
    ).status_code == 200
    assert (
        await tool(
            client,
            staff["motion_designer"],
            "item",
            {
                "ref": ref,
                "step": "composition",
                "composition": {"format": "html", "source": COMPOSITION + " "},
            },
        )
    ).status_code == 200
    assert (await item(client, owner, ref))["composition"]["version"] == 2
    await render(client, ref)
    r = await tool(
        client,
        staff["media_director"],
        "review",
        {"ref": ref, "verdict": "reject", "note_md": "نه"},
    )
    assert r.status_code == 200
    assert (await item(client, owner, ref))["state"] == "rejected"


async def test_a_one_off_ends_as_a_card_and_unpublishing_removes_what_it_can(
    client: httpx.AsyncClient, hub: Hub, owner_session: dict[str, Any], new_company: Callable[..., Any],
    su: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    co = await new_company()
    h = owner_session["headers"]
    staff = await team(su, co)
    await brand(su, co)
    await accounts(su, co, monkeypatch)
    r = await client.post("/api/v1/media/items", headers={**h, **idem()},
                          json={"company": co["code"], "kind": "reel", "brief_md": "یک ریلز یک‌باره"})  # fmt: skip
    ref = r.json()["ref"]
    await _to_review(client, su, hub, h, co, staff, ref, SCRIPT)
    assert (
        await tool(
            client,
            staff["media_director"],
            "review",
            {"ref": ref, "verdict": "pass", "note_md": "قبول"},
        )
    ).status_code == 200
    x = await item(client, h, ref)
    assert x["state"] == "waiting_owner"
    payload = json.loads(
        await su.fetchval(
            "SELECT payload FROM cartable.decisions WHERE ref = $1", x["decision_ref"]
        )
    )
    assert payload["why"] == "one_off" and payload["series"] is None
    # The cartable's approve publishes it (A3, step-up); a media_series card is never approved there.
    su_ = await step_up(hub, owner_session["session_id"], "decision.approve", x["decision_ref"])
    r = await client.post(
        f"/api/v1/decisions/{x['decision_ref']}/approve", headers={**h, **su_, **idem()}, json={}
    )
    assert r.status_code == 200, r.text
    async with hub.db.tx(await hub.companies.ids()) as tx:
        await D.apply_effect(tx, x["decision_ref"], SYSTEM)
    async with platforms(co["code"].lower()) as fake:
        assert (await P.publish_due(hub, only=ref))["published"] == [ref]
        r = await client.post(f"/api/v1/media/items/{ref}/unpublish", headers=h)
        assert r.status_code == 403
        su_ = await step_up(hub, owner_session["session_id"], "media.unpublish", ref)
        r = await client.post(f"/api/v1/media/items/{ref}/unpublish", headers={**h, **su_})
        assert r.status_code == 200, r.text
        out = await P.unpublish_due(hub)
        assert out["unpublished"] == [ref]
        assert any(
            c["method"] == "deleteMessage" and c["payload"]["message_id"] == 41 for c in fake.calls
        )
    x = await item(client, h, ref)
    rows = {p["placement"]: p["error"] for p in x["publish"]}
    assert x["state"] == "rejected" and rows == {
        "telegram_post": "removed",
        "instagram_reel": "remove_by_hand",
    }


async def test_a_series_card_is_sealed_on_its_page_and_the_limit_answers_429(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    h = owner_session["headers"]
    director = f"{co['code']}-MEDIA-MGR"
    body = {**series_body(co["code"]), "why_fa": "سه آیتم آزمایشی قبول شد"}
    r = await tool(client, director, "series/propose", body)
    assert r.status_code == 200, r.text
    card = r.json()["detail"]["card"]
    sref = r.json()["ref"]
    d = await su.fetchrow(
        "SELECT kind, action_class, payload FROM cartable.decisions WHERE ref = $1", card
    )
    assert d["kind"] == "media_series" and json.loads(d["payload"])["series"] == sref
    su_ = await step_up(hub, owner_session["session_id"], "decision.approve", card)
    r = await client.post(
        f"/api/v1/decisions/{card}/approve", headers={**h, **su_, **idem()}, json={}
    )
    assert r.status_code == 409 and r.json()["code"] == "validation_failed"
    s = (await client.get(f"/api/v1/media/series/{sref}", headers=h)).json()
    assert (
        s["status"] == "proposed"
        and s["decision_ref"] == card
        and s["proposed_by"]["code"] == director
    )
    assert (await seal(client, hub, owner_session, s)).status_code == 200
    assert (
        await su.fetchval("SELECT status FROM cartable.decisions WHERE ref = $1", card)
        == "approved"
    )
    # A non-director cannot propose; the platform's own limit is a 429 with Retry-After.
    other = await hire(su, co, "scriptwriter")
    assert (await tool(client, other, "series/propose", body)).status_code == 403
    low = co["code"].lower()
    item_id = await su.fetchval(
        """INSERT INTO media.items (company_id, kind, title_fa, state, created_by_kind, created_by_code)
           VALUES ($1, 'reel', 'x', 'published', 'owner', 'owner') RETURNING id""",
        co["id"],
    )
    for _ in range(50):
        await su.execute(
            """INSERT INTO media.publish_log (company_id, item_id, action, channel, placement, account, via,
                   outcome, by_kind, by_code) VALUES ($1, $2, 'publish', 'instagram', 'instagram_reel', $3, 'api',
                   'ok', 'service', 'media')""",
            co["id"], item_id, f"instagram-{low}",
        )  # fmt: skip
    async with hub.db.tx(await hub.companies.ids()) as tx:
        with pytest.raises(Exception) as err:
            await P.check_limit_now(tx, f"instagram-{low}", "instagram")
    assert (
        getattr(err.value, "status", None) == 429
        and getattr(err.value, "code", None) == "platform_limit"
    )
    assert int(err.value.headers["Retry-After"]) > 0  # type: ignore[attr-defined]
    ig = next(
        x
        for x in (await client.get("/api/v1/media/limits", headers=h)).json()
        if x["account"] == f"instagram-{low}"
    )
    assert ig["used_24h"] == 50 and ig["resets_at"] and "سقف" in ig["note_fa"]


async def test_a_design_is_rendered_to_pages_and_never_published(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    ui = await hire(su, co, "ui_designer")
    director = f"{co['code']}-MEDIA-MGR"
    r = await client.post("/api/v1/media/items", headers={**owner, **idem()},
                          json={"company": co["code"], "kind": "design", "brief_md": "صفحه‌ی اول را ساده کن"})  # fmt: skip
    assert r.status_code == 201, r.text
    ref = r.json()["ref"]
    assert (
        await tool(
            client,
            ui,
            "item",
            {"ref": ref, "step": "brief", "brief_md": "بریف: یک اقدام، فارسی درست"},
        )
    ).status_code == 200
    page = COMPOSITION.replace("anime.min.js", "anime.min.js")
    r = await tool(
        client,
        ui,
        "item",
        {"ref": ref, "step": "composition", "composition": {"format": "html", "source": page}},
    )
    assert r.status_code == 200, r.text
    claim = await client.post("/internal/v1/media/render/claim", headers=MEDIA)
    job = claim.json()
    assert [o["name"] for o in job["outputs"]] == ["phone", "desktop"] and job["overlay"][
        "mark"
    ] is False
    for o in job["outputs"]:
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
        up = await client.post(f"/internal/v1/media/render/{job['id']}/output", params={"name": o["name"], "kind": "image", "width": o["width"], "height": o["height"]},
                               content=png, headers={**MEDIA, "Content-Type": "image/png"})  # fmt: skip
        assert up.status_code == 201, up.text
    assert (
        await client.post(f"/internal/v1/media/render/{job['id']}/done", headers=MEDIA, json={})
    ).status_code == 204
    x = await item(client, owner, ref)
    assert x["state"] == "review" and len(x["pages"]) == 2 and x["checks"] == []
    assert (
        await tool(
            client, director, "review", {"ref": ref, "verdict": "pass", "note_md": "تحویل به CTO"}
        )
    ).status_code == 200
    x = await item(client, owner, ref)
    assert x["state"] == "review" and x["publish"] == [] and x["decision_ref"] is None


async def test_a_runtime_violation_sends_the_item_back_to_its_composer(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    new_company: Callable[..., Any],
    su: Any,
) -> None:
    co = await new_company()
    staff = await team(su, co)
    r = await client.post("/api/v1/media/items", headers={**owner, **idem()},
                          json={"company": co["code"], "kind": "reel", "brief_md": "یک ریلز"})  # fmt: skip
    ref = r.json()["ref"]
    for code, body in (
        (
            staff["scriptwriter"],
            {"ref": ref, "step": "script", "script": {"text_fa": SCRIPT, "sources": SOURCES}},
        ),
        (staff["video_director"], {"ref": ref, "step": "direction", "direction": {"shots": SHOTS}}),
        (
            staff["motion_designer"],
            {
                "ref": ref,
                "step": "composition",
                "composition": {"format": "html", "source": COMPOSITION},
            },
        ),
    ):
        assert (await tool(client, code, "item", body)).status_code == 200
    job = (await client.post("/internal/v1/media/render/claim", headers=MEDIA)).json()
    done = await client.post(f"/internal/v1/media/render/{job['id']}/done", headers=MEDIA,
                             json={"violations": [{"rule": "network_request", "detail": "http://10.10.1.3/"}]})  # fmt: skip
    assert done.status_code == 204
    x = await item(client, owner, ref)
    assert x["state"] == "composing"
    assert (
        await su.fetchval("SELECT state FROM media.render_jobs WHERE id = $1", uuid.UUID(job["id"]))
        == "failed"
    )
    brief = await su.fetchval(
        "SELECT w.brief FROM media.items i JOIN work.work w ON w.id = i.step_work_id WHERE i.ref = $1",
        ref,
    )
    assert "runtime_violation" in brief
    # Another service, or an agent, never reaches the queue.
    assert (await client.post("/internal/v1/media/render/claim", headers=TTS)).status_code == 403
    assert (
        await client.post(
            "/internal/v1/media/render/claim", headers=await agent_headers(staff["motion_designer"])
        )
    ).status_code == 403


def test_captions_follow_the_shots_or_the_narration() -> None:
    by_shot = S.captions(SHOTS, None)
    assert by_shot[0]["start_s"] == 0 and by_shot[-1]["end_s"] == 30
    spread = S.captions(SHOTS, 24.0)
    assert spread[-1]["end_s"] == pytest.approx(24.0, abs=0.05)
    assert all(len(c["text_fa"]) <= 60 for c in spread)


def test_a_series_must_fit_its_kind() -> None:
    from hq_api.errors import ApiError

    good = series_body("TY")
    assert S.check_series("TY", dict(good))["schedule"] == "FREQ=DAILY;BYHOUR=9;BYMINUTE=0"
    for over, field in (
        ({"format": {**good["format"], "aspect": "4:5"}}, "format.aspect"),
        ({"format": {**good["format"], "music": "library"}}, "format.music"),
        (
            {
                "targets": [
                    {
                        "channel": "instagram",
                        "account": "instagram-fx",
                        "placement": "instagram_reel",
                    }
                ]
            },
            "targets.0.account",
        ),
        (
            {
                "targets": [
                    {"channel": "telegram", "account": "telegram-ty", "placement": "instagram_post"}
                ]
            },
            "targets.0.placement",
        ),
        ({"checks": ["brand"]}, "checks"),
    ):
        with pytest.raises(ApiError) as e:
            S.check_series("TY", {**good, **over})
        assert field in (e.value.fields or {}), (field, e.value.fields)
    with pytest.raises(ApiError):
        S.check_series("TY", {**good, "schedule": "FREQ=SECONDLY"})
