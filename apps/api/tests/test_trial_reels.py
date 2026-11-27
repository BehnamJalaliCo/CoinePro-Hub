"""⟨2026-11-26⟩ Trial Reels (domain/trial_reels.py): every Instagram reel goes out once more as a
Trial Reel, the same reel very slightly changed (never made again), at another hour of its day
(never in the night), once, tracked as its own row that no flow, topic gate or day rule reads."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest

from hq_api import trial_copy as TC
from hq_api.domain import flows as FL
from hq_api.domain import quiet_hours as QH
from hq_api.domain import trial_reels as TR
from hq_api.hub import Hub

from .test_p13a_media import FFMPEG
from .test_p17_runners import take
from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_w17_session_publish import an_output, tap
from .test_w19_publish_time import answer, connected

pytestmark = pytest.mark.usefixtures("hiring_open")


@pytest.fixture
def inline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The copy made by the worker itself (live, the hub host makes it: hq_api.trial_copy)."""
    monkeypatch.setattr(TR, "INLINE", True)


TEHRAN = ZoneInfo("Asia/Tehran")


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def at(day: Any, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=TEHRAN).astimezone(UTC)


def local(t: datetime) -> datetime:
    return t.astimezone(TEHRAN)


def clip(seconds: int = 4) -> bytes:
    """A short reel with picture and sound (25 frames a second)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.mp4"
        subprocess.run(  # the test image's own ffmpeg, fixed arguments
            [FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s=270x480:d={seconds}:r=25",
             "-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-c:v", "libx264", "-pix_fmt",
             "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(out)],
            check=True, timeout=120,
        )  # fmt: skip
        return out.read_bytes()


async def real_video(hub: Hub, su: Any, file_id: str) -> None:
    """The session's video is 2 s at one frame a second: a real reel in its place."""
    key = await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1", UUID(file_id))
    await asyncio.to_thread(Path(hub.storage.local_path(key)).write_bytes, clip())


async def trial_of(hub: Hub, su: Any, ref: str) -> Any:
    """Ticks until this reel's trial is there (another test's reel may come first)."""
    for _ in range(8):
        await TR.tick(hub)
        row = await su.fetchrow(
            "SELECT * FROM media.publications WHERE source ->> 'trial_of' = $1", ref
        )
        if row is not None:
            return row
    raise AssertionError(f"no trial of {ref}")


async def trials(su: Any, ref: str) -> int:
    return int(
        await su.fetchval(
            "SELECT count(*) FROM media.publications WHERE source ->> 'trial_of' = $1", ref
        )
    )


def test_the_trials_hour_is_its_days_far_from_the_rest_and_never_in_the_night() -> None:
    day = datetime(2026, 12, 1, tzinfo=TEHRAN).date()
    now = at(day, 7)
    # a noon reel, the page's other reel at 18:00 and stories through the day
    own, other = at(day, 12), at(day, 18)
    stories = [at(day, h, 30) for h in range(9, 23)]
    for seed in ("P-1", "P-2", "P-3", "P-4", "P-5"):
        t = TR.pick_slot(own_at=own, feed=[own, other], stories=stories, now=now, seed=seed)
        assert t is not None and local(t).date() == day
        assert t - own >= TR.GAP_OWN and abs(t - other) >= TR.GAP_FEED
        assert all(abs(t - s) >= TR.GAP_STORY for s in stories)
        assert time(8, 10) <= local(t).time() <= time(23, 40) and not QH.is_quiet(t)
    # seeded: the same reel, the same hour; another reel may get another one
    one = TR.pick_slot(own_at=own, feed=[own], stories=[], now=now, seed="P-9")
    assert one == TR.pick_slot(own_at=own, feed=[own], stories=[], now=now, seed="P-9")
    hours = {TR.pick_slot(own_at=own, feed=[own], stories=[], now=now, seed=f"P-{i}")
             for i in range(12)}  # fmt: skip
    assert len(hours) > 3
    # out at 22:10: no room that day, the next morning on (never 00:00-08:10)
    late = at(day, 22, 10)
    t = TR.pick_slot(own_at=late, feed=[late], stories=[], now=late, seed="P-7")
    assert t is not None and local(t).date() == day + timedelta(days=1)
    assert local(t).time() >= time(8, 10)
    # a full day: the widest gap of at least two hours, still the same day
    full = [at(day, h) for h in (9, 12, 15, 18, 21)]
    t = TR.pick_slot(own_at=at(day, 9), feed=full, stories=[], now=now, seed="P-8")
    assert t is not None and local(t).date() == day
    assert min(abs(t - x) for x in full) >= TR.GAP_FEED_MIN
    # a reel of two days ago: too late for a trial
    old = at(day - timedelta(days=2), 12)
    assert TR.pick_slot(own_at=old, feed=[old], stories=[], now=now, seed="P-6") is None
    # ⟨2026-11-28⟩ a day with a reel or post every two hours: a page's trial goes the next
    # morning; a PER_DAY page's (tight) stays its day, its widest gap of at least an hour
    packed = [at(day, h) for h in (9, 11, 13, 15, 17, 19, 21, 23)]
    t = TR.pick_slot(own_at=at(day, 9), feed=packed, stories=[], now=now, seed="P-10")
    assert t is not None and local(t).date() == day + timedelta(days=1)
    t = TR.pick_slot(own_at=at(day, 9), feed=packed, stories=[], now=now, seed="P-10", tight=True)
    assert t is not None and local(t).date() == day
    assert min(abs(t - x) for x in packed) >= TR.GAP_FEED_TIGHT and t - at(day, 9) >= TR.GAP_OWN


class _Tx:
    """scalar/one of a transaction, answered in order."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)

    async def scalar(self, *_a: Any, **_k: Any) -> Any:
        return self.answers.pop(0)

    async def one(self, *_a: Any, **_k: Any) -> Any:
        return self.answers.pop(0)


def test_a_capped_page_gets_its_days_number_of_trials_spread_through_the_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⟨2026-11-28⟩ @oneoxxo 5 reels → 3 trials, @fxbyfx 4 → 2; other pages one per reel."""
    assert TR.PER_DAY == {"oneoxxo": 3, "fxbyfx": 2}
    assert TR.spread(5, 3) == {0, 1, 3} and TR.spread(4, 2) == {0, 2}
    assert TR.spread(2, 3) == {0, 1} and TR.spread(0, 3) == set()
    day = datetime(2026, 12, 1, tzinfo=TEHRAN).date()
    reels = [(at(day, h), f"P-{h}") for h in (9, 12, 15, 18)] + [(at(day, 21), "")]  # one planned

    async def day_reels(*_a: Any) -> list[tuple[datetime, str]]:
        return reels

    monkeypatch.setattr(TR, "_day_reels", day_reels)

    def row(account: str, h: int) -> dict[str, Any]:
        return {"account": account, "ref": f"P-{h}", "published_at": None,
                "scheduled_at": at(day, h), "at": at(day, h)}  # fmt: skip

    def cap_ok(account: str, h: int, used: int) -> bool:
        return asyncio.run(TR._cap_ok(_Tx(used), row(account, h)))  # type: ignore[arg-type]

    # 5 reels, 3 a day: the 1st, 2nd and 4th (each looked at once the ones before have theirs)
    got = [cap_ok("oneoxxo", 9, 0), cap_ok("oneoxxo", 12, 1), cap_ok("oneoxxo", 15, 2),
           cap_ok("oneoxxo", 18, 2)]  # fmt: skip
    assert got == [True, True, False, True]
    assert not cap_ok("oneoxxo", 18, 3)  # the day has its three
    # the 2nd got none (its hour, its video): the 3rd takes its place when it is needed
    assert cap_ok("oneoxxo", 15, 1) is False  # two picks still ahead (the 4th, and the 5th)
    assert cap_ok("oneoxxo", 18, 1) is True
    # any other page: every reel
    assert all(asyncio.run(TR._cap_ok(_Tx(), row("theprochart", h))) for h in (9, 15))  # type: ignore[arg-type]


def test_a_page_meta_refused_is_probed_once_a_day() -> None:
    """⟨2026-11-28⟩ «ریلز آزمایشی هر روز تست شود»: none the day of the refusal, then one a day
    (none while one is on its way) until Meta lets one through."""
    now = at(datetime(2026, 12, 2, tzinfo=TEHRAN).date(), 10)
    today = at(datetime(2026, 12, 2, tzinfo=TEHRAN).date(), 0)

    def probe(*answers: Any) -> tuple[bool, bool]:
        return asyncio.run(TR._probe_ok(_Tx(*answers), "dotcoinme", now))  # type: ignore[arg-type]

    assert probe(None) == (True, False)  # never refused
    assert probe(today + timedelta(hours=3)) == (False, True)  # refused today
    yesterday = today - timedelta(hours=5)
    assert probe(yesterday, {"through": False, "on_way": False}) == (True, True)  # today's probe
    assert probe(yesterday, {"through": False, "on_way": True}) == (False, True)  # one on its way
    assert probe(yesterday, {"through": True, "on_way": True}) == (True, False)  # let through


def test_the_caption_keeps_its_words_and_moves_its_hashtags() -> None:
    caption = "پول از کجا آمد؟\n\nیک قصه‌ی واقعی\nکامنت بذار «پول»\n#پول #قصه #تاریخ #اقتصاد"
    got = TR.vary_caption(caption, "P-1:1")
    assert got != caption and got == TR.vary_caption(caption, "P-1:1")

    def words(t: str) -> list[str]:
        return sorted(re.sub("[" + "".join(TR.MARKS) + "]", "", t).split())

    assert words(got) == words(caption)
    assert got.split("\n")[1:4] == caption.split("\n")[1:4]  # the Persian lines as they were
    tags = TR.HASHTAG.findall(got)
    assert sorted(tags) == sorted(TR.HASHTAG.findall(caption))
    assert tags != TR.HASHTAG.findall(caption)
    first = got.split("\n")[0]
    assert first.startswith("پول از کجا آمد؟") and first != "پول از کجا آمد؟"
    # a first line that ends with a mark loses it
    assert TR.vary_caption("سلام 👀\nدوم", "x").split("\n")[0] == "سلام"


def test_the_copy_differs_a_little_at_the_reels_own_top_quality() -> None:
    r = TC.recipe_of("P-1:1")
    assert r == TC.recipe_of("P-1:1") and r != TC.recipe_of("P-1:2")
    assert TC.checked(r) == {**r, "trim_frames": r["trim_frames"]}
    for bad in ({**r, "zoom": 0.5}, {**r, "brightness": "1;rm"}, {**r, "contrast": True}, None):
        with pytest.raises(ValueError):
            TC.checked(bad)
    assert 0.012 <= r["zoom"] <= 0.02 and abs(r["brightness"]) <= 0.012
    assert abs(r["contrast"] - 1) <= 0.012 and abs(r["saturation"] - 1) <= 0.014
    info = {"width": 1080, "height": 1920, "rate": "60/1", "fps": 60.0, "audio": True,
            "duration_s": 88.0}  # fmt: skip
    line = " ".join(TC.ffmpeg_args(Path("/in.mp4"), Path("/out.part"), info, r, 14))
    assert "-crf 14" in line and "aq-mode=3" in line and "scale=1080:1920" in line
    assert "-maxrate 16000k" in line and "-r 60/1" in line and "-map_metadata -1" in line
    assert "-b:a 256k" in line and "-colorspace bt709" in line
    assert f"trim=start_frame={TC.trim_of(r, 60.0)}" in line and TC.trim_of(r, 60.0) >= 2
    assert TC.trim_of(r, 1.0) == 0  # never more than 0.15 s of a reel
    assert TC.vbv_k(200.0) < 16000  # a long reel stays under ~180 MB
    assert TC.fps_of("60/1") == ("60/1", 60.0) and TC.fps_of("1;x") == ("30", 30.0)


async def test_a_reels_trial_is_made_once_for_its_hour_and_never_a_flows_day(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    inline: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    day = (datetime.now(TEHRAN) + timedelta(days=1)).date()
    caption = "سلام دنیا\nخط دوم\n#الف #ب #ج"
    r = await tap(client, owner, order, {
        "output": output, "file_id": reel, "cover_file_id": cover, "caption": caption,
        "scheduled_at": at(day, 12).isoformat(),
        "comment": {"keywords": ["پول"], "reply": "لینک", "link": "https://pro-chart.com/x"},
    })  # fmt: skip
    assert r.status_code == 202, r.text
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:91", "url": None})
    main = await su.fetchrow(
        "SELECT * FROM media.publications WHERE chain[1] = $1", UUID(job["id"])
    )
    await real_video(hub, su, reel)

    # (a PER_DAY page of one trial a day: its only reel is its pick)
    monkeypatch.setattr(TR, "PER_DAY", {main["account"]: 1})
    trial = await trial_of(hub, su, main["ref"])
    assert trial["kind"] == "reel" and trial["account"] == main["account"]
    assert trial["title_fa"].startswith("ریلز آزمایشی · ")
    src = _j(trial["source"])
    assert src["automation"] == "TRIAL" and src["flow_key"] is None and src["work"] is None
    t = trial["scheduled_at"]
    assert local(t).date() == day and t - at(day, 12) >= TR.GAP_OWN
    assert time(8, 10) <= local(t).time() <= time(23, 40)
    assert trial["caption"] != caption
    files = {f["role"]: f for f in _j(trial["files"])}
    assert files["video"]["file_id"] != reel and files["cover"]["file_id"] != cover
    assert files["video"]["name"] == "video_trial.mp4"
    copy = await su.fetchrow(
        "SELECT width, height, meta FROM files.files WHERE id = $1",
        UUID(files["video"]["file_id"]),
    )
    assert (copy["width"], copy["height"]) == (270, 480)
    assert _j(copy["meta"])["recipe"]["crf"] == 14
    # the job IG-Hub gets: a trial, of pub:91, under a key of its own, with the reel's comment rule
    tj = await take(client, rn)
    row = await su.fetchrow("SELECT args FROM infra.server_jobs WHERE id = $1", UUID(tj["id"]))
    meta = _j(row["args"])["meta"]
    assert meta["trial"] is True and meta["trial_of"] == "pub:91" and meta["kind"] == "reel"
    first = await su.fetchrow("SELECT args FROM infra.server_jobs WHERE id = $1", UUID(job["id"]))
    assert meta["key"] != _j(first["args"])["meta"]["key"]
    assert meta["comment"]["keywords"][0] == "پول"
    assert meta["scheduled_at"] == t.isoformat()
    await answer(client, rn, tj["id"], {"external_id": "pub:92", "url": None})
    # once: the next ticks send nothing more for it
    for _ in range(3):
        await TR.tick(hub)
    assert await trials(su, main["ref"]) == 1
    # no flow's day and no repeat gate reads the trial
    async with hub.db.tx([pc["id"]]) as tx:
        assert await tx.scalar(
            FL.PUBLISHED_SQL, k="x_reels", d=day.isoformat(), a=main["account"], kind="reel",
            lo=t - timedelta(hours=1), hi=t + timedelta(hours=1),
        ) is None  # fmt: skip

    # the reel cancelled: its trial is cancelled too (a cancel job to IG-Hub), asked once
    await su.execute("UPDATE media.publications SET state = 'cancelled' WHERE id = $1", main["id"])
    got = await TR.tick(hub)
    assert got["cancelled"] >= 1
    asked = await take(client, rn)
    row = await su.fetchrow("SELECT args FROM infra.server_jobs WHERE id = $1", UUID(asked["id"]))
    assert _j(row["args"])["meta"]["cancel"] == "pub:92"
    await TR.tick(hub)
    n = await su.fetchval(
        "SELECT count(*) FROM infra.server_jobs WHERE kind = 'publish'"
        " AND args -> 'meta' ->> 'cancel' = 'pub:92' AND args -> 'session' ->> 'output' = $1",
        output,
    )
    assert n == 1


async def test_a_page_meta_refuses_trials_is_left_alone_and_off_means_none(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    inline: None,
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    day = (datetime.now(TEHRAN) + timedelta(days=1)).date()
    await tap(client, owner, order, {
        "output": output, "file_id": reel, "cover_file_id": cover, "caption": "یک\n#a #b",
        "scheduled_at": at(day, 10).isoformat(),
    })  # fmt: skip
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:301", "url": None})
    main = await su.fetchrow(
        "SELECT * FROM media.publications WHERE chain[1] = $1", UUID(job["id"])
    )
    await real_video(hub, su, reel)

    # off: nothing
    await su.execute("UPDATE owner.settings SET flows_off = array_append(flows_off, 'trial_reels')")
    try:
        assert (await TR.tick(hub)) == {"off": True}
    finally:
        await su.execute(
            "UPDATE owner.settings SET flows_off = array_remove(flows_off, 'trial_reels')"
        )
    await trial_of(hub, su, main["ref"])
    tj = await take(client, rn)
    # IG-Hub: Meta does not let this page post trials (its command's stderr)
    await answer(client, rn, tj["id"], None, exit_code=1, why="انتشار با کد خروج 1 تمام شد.")
    no = "اینستاگرام نپذیرفت: trial_not_eligible: 10/2207081: Application does not have permission"
    await su.execute(
        """INSERT INTO infra.server_job_events (job_id, company_id, seq, type, data)
           SELECT id, company_id, 1, 'stderr', $2 FROM infra.server_jobs WHERE id = $1""",
        UUID(tj["id"]),
        json.dumps({"text": no}),
    )
    trial = await su.fetchrow(
        "SELECT * FROM media.publications WHERE source ->> 'trial_of' = $1", main["ref"]
    )
    assert trial["state"] == "failed"
    # refused: never tried again for this reel (nor the page's next reels today; one tomorrow)
    for _ in range(3):
        await TR.tick(hub)
    assert await trials(su, main["ref"]) == 1
    async with hub.db.tx([pc["id"]]) as tx:
        assert await TR._probe_ok(tx, main["account"], datetime.now(UTC)) == (False, True)
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        # tomorrow: on its daily probe (one trial, once none of the page's is on its way)
        assert (await TR._probe_ok(tx, main["account"], tomorrow))[1] is True
    # (every test's page is @pro.chart: the refusal goes to another page for the next tests)
    await su.execute(
        "UPDATE media.publications SET account = 'refused.page' WHERE id = $1", trial["id"]
    )


async def test_the_host_makes_the_copy_the_worker_asked_for_and_the_worker_takes_it(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ig, pc = await new_company(), await new_company()
    co = pc["code"]
    made = await an_output(client, hub, owner, owner_session, su, co, ("reel.mp4", "cover.png"))
    order, output, (reel, cover) = made["order"], made["output"], made["files"]
    rn = await connected(client, hub, owner_session, ig, co)
    day = (datetime.now(TEHRAN) + timedelta(days=1)).date()
    await tap(client, owner, order, {
        "output": output, "file_id": reel, "cover_file_id": cover, "caption": "دو\n#a #b",
        "scheduled_at": at(day, 9).isoformat(),
    })  # fmt: skip
    job = await take(client, rn)
    await answer(client, rn, job["id"], {"external_id": "pub:401", "url": None})
    main = await su.fetchrow(
        "SELECT * FROM media.publications WHERE chain[1] = $1", UUID(job["id"])
    )
    await real_video(hub, su, reel)
    volume = Path(hub.storage.local_path("0" * 32)).parent.parent
    ask = volume / TC.QUEUE / f"{main['ref']}-1.json"
    # the worker asks (another test's reel may be asked first)
    for _ in range(8):
        await TR.tick(hub)
        if await asyncio.to_thread(ask.exists):
            break
    asked = json.loads(await asyncio.to_thread(ask.read_text))
    key = await su.fetchval("SELECT storage_key FROM files.files WHERE id = $1", UUID(reel))
    assert asked["key"] == key and TC.checked(asked["recipe"])
    assert await trials(su, main["ref"]) == 0  # nothing sent while the copy is being made
    # the host's run: an ask of nothing but a key and numbers; a bad one is refused in its .err
    bad = volume / TC.QUEUE / "P-999999-1.json"
    await asyncio.to_thread(bad.write_text, json.dumps({"key": "../../etc/passwd", "recipe": {}}))
    for _ in range(4):
        await asyncio.to_thread(TC.run, volume)
    assert "bad key" in await asyncio.to_thread((volume / TC.QUEUE / "P-999999-1.err").read_text)
    assert await asyncio.to_thread((volume / TC.QUEUE / f"{main['ref']}-1.mp4").is_file)
    # the worker takes it into the store, sends it, and clears the queue
    trial = await trial_of(hub, su, main["ref"])
    files = {f["role"]: f for f in _j(trial["files"])}
    copy = await su.fetchrow(
        "SELECT width, height FROM files.files WHERE id = $1", UUID(files["video"]["file_id"])
    )
    assert (copy["width"], copy["height"]) == (270, 480)
    left = [p.name for p in await asyncio.to_thread(lambda: list((volume / TC.QUEUE).iterdir()))
            if p.name.startswith(f"{main['ref']}-")]  # fmt: skip
    assert left == []
