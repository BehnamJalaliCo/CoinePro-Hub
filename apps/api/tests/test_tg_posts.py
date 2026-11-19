"""⟨2026-11-19⟩ A page's own Telegram channel (domain/tg_posts.py): the day's package as Telegram takes it,
each post a publication at its hour, and the worker's minute that sends what is due only once the bot may
post in the channel, each post once.

- check(): Telegram's HTML subset, the visible lengths in UTF-16 units, link buttons only (never on an album
  or a poll, only on a post's last message), polls, the named files of their kind, the hours in order and
  after the flow's, never a topic the channel has had;
- calls(): one Bot API call per message (HTML, link buttons, a text's preview off, an album's caption on its
  first photo, an anonymous poll or quiz);
- a breaking item's Telegram post: its session's telegram.txt (its JSON: the runner delivers .txt) and picture become one publication due now;
- tick(): nothing while the bot is no admin (said on the post), once it is the post goes out once, a post
  far past its hour is cancelled, Telegram's own limit makes it wait.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest

from hq_api.domain import flow_events as EV
from hq_api.domain import flow_view as FV
from hq_api.domain import flows as FL
from hq_api.domain import studio_publish as SP
from hq_api.domain import tg_posts as TG
from hq_api.hub import Hub

from .test_p21_secretary import no_model  # noqa: F401 - the fixture
from .test_p39_flows import a_flow, all_off, fk, seed

DAY = date(2026, 11, 20)
FIRST = datetime(2026, 11, 20, 8, 30, tzinfo=TG.TEHRAN)
SIG = "\n\n🆔 @behnamjalali_tech"
JPG = b"\xff\xd8\xff\xe0" + bytes(200)
FILES = {
    "tg_02_card.jpg": {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "tg_02_card.jpg",
        "mime": "image/jpeg",
        "size": 2000,
    },
    "tg_05a.jpg": {
        "id": "22222222-2222-2222-2222-222222222222",
        "name": "tg_05a.jpg",
        "mime": "image/jpeg",
        "size": 2000,
    },
    "tg_05b.png": {
        "id": "33333333-3333-3333-3333-333333333333",
        "name": "tg_05b.png",
        "mime": "image/png",
        "size": 2000,
    },
    "tg_07.ogg": {
        "id": "44444444-4444-4444-4444-444444444444",
        "name": "tg_07.ogg",
        "mime": "audio/ogg",
        "size": 90000,
    },
    "big.mp4": {
        "id": "55555555-5555-5555-5555-555555555555",
        "name": "big.mp4",
        "mime": "video/mp4",
        "size": 60 * 1024 * 1024,
    },
}
LINKS = [
    [
        {"text": "اینستاگرام", "url": "https://www.instagram.com/behnamjalali.tech"},
        {"text": "یوتیوب", "url": "https://www.youtube.com/@behnamjalali-tech"},
    ]
]


def a_day() -> dict[str, Any]:
    return {
        "posts": [
            {
                "at": "08:30",
                "type": "brief",
                "topic": "صبحانه‌ی هوش مصنوعی ۲۹ آبان",
                "text": '☕️ <b>صبحانه</b>\n<b>۱) خبر</b> یعنی چه برای تو. <a href="https://openai.com/news/">منبع</a>'
                + SIG,
                "buttons": LINKS,
            },
            {
                "at": "10:30",
                "type": "tool",
                "topic": "Codex CLI در ترمینال",
                "parts": [
                    {"photo": "tg_02_card.jpg", "text": "🛠 <b>ابزار روز</b>"},
                    {
                        "text": '<pre><code class="language-bash">npm i -g @openai/codex</code></pre>'
                        + SIG,
                        "buttons": [[{"text": "GitHub", "url": "https://github.com/openai/codex"}]],
                    },
                ],
            },
            {
                "at": "14:30",
                "type": "poll",
                "topic": "نظرسنجی ایجنت کدنویسی",
                "poll": {
                    "question": "کدوم درسته؟",
                    "options": ["الف", "ب", "ج"],
                    "quiz": 1,
                    "explanation": "<b>چون</b> ب",
                },
            },
            {
                "at": "16:30",
                "type": "table",
                "topic": "مقایسه‌ی قیمت Astra و Sol",
                "photos": ["tg_05a.jpg", "tg_05b.png"],
                "text": "⚖️ <b>مقایسه</b>" + SIG,
            },
            {
                "at": "20:30",
                "type": "voice",
                "topic": "یک دقیقه: یک میلیون توکن",
                "voice": "tg_07.ogg",
                "text": "🎙 <b>یک دقیقه</b>" + SIG,
                "buttons": LINKS,
            },
            {
                "at": "22:00",
                "type": "tip",
                "topic": "نکته‌ی شب: کش پرامپت",
                "silent": True,
                "text": "💡 <b>نکته</b> a &amp; b" + SIG,
            },
        ]
    }


# ------------------------------------------------------------------ check --
def test_a_good_day_reads_as_its_posts_at_their_tehran_hours() -> None:
    posts, errors = TG.check(a_day(), FILES, day=DAY, first=FIRST, done=["موضوع دیروز"])
    assert errors == [], errors
    assert [p.type for p in posts] == ["brief", "tool", "poll", "table", "voice", "tip"]
    assert posts[0].at == FIRST and posts[-1].at == datetime(2026, 11, 20, 22, 0, tzinfo=TG.TEHRAN)
    assert [m["kind"] for m in posts[1].parts] == ["photo", "text"]
    assert posts[1].parts[0]["photo"] == {
        "name": "tg_02_card.jpg",
        "file_id": FILES["tg_02_card.jpg"]["id"],
        "mime": "image/jpeg",
    }
    assert posts[2].parts[0]["poll"] == {
        "question": "کدوم درسته؟",
        "options": ["الف", "ب", "ج"],
        "quiz": 1,
        "explanation": "<b>چون</b> ب",
    }
    assert "<b>" not in TG.visible_text(posts[0]) and "صبحانه" in TG.visible_text(posts[0])


@pytest.mark.parametrize(
    ("change", "fault"),
    [
        (lambda d: d["posts"][0].update(text="a<br>b" + SIG), "<br>"),
        (lambda d: d["posts"][0].update(text="<p>a</p>" + SIG), "تگ <p>"),
        (lambda d: d["posts"][0].update(text='<a href="http://x.test">x</a>' + SIG), "https"),
        (lambda d: d["posts"][0].update(text="<b>a<i>b</b></i>" + SIG), "بی‌جا بسته"),
        (lambda d: d["posts"][0].update(text="a & b" + SIG), "&amp;"),
        (lambda d: d["posts"][0].update(text="ب" * 4097), "حداکثر 4096"),
        (
            lambda d: d["posts"][4].update(text="😀" * 513),
            "حداکثر 1024",
        ),  # (an emoji is 2 UTF-16 units)
        (lambda d: d["posts"][3].update(buttons=LINKS), "آلبوم و نظرسنجی دکمه نمیگیرند"),
        (lambda d: d["posts"][1]["parts"][0].update(buttons=LINKS), "فقط روی آخرین پیام"),
        (
            lambda d: d["posts"][0].update(
                buttons=[[{"text": "x", "url": "https://x.test", "pay": True}]]
            ),
            "فقط text و url",
        ),
        (lambda d: d["posts"][2]["poll"].update(quiz=5), "quiz"),
        (lambda d: d["posts"][2]["poll"].update(options=["الف"]), "۲ تا ۱۰ گزینه"),
        (lambda d: d["posts"][4].update(voice="missing.ogg"), "در out/ نیست"),
        (lambda d: d["posts"][4].update(voice="tg_02_card.jpg"), "از نوع voice نیست"),
        (lambda d: d["posts"][4].update(voice=None, video="big.mp4"), "بزرگ‌تر از 50"),
        (lambda d: d["posts"][1].update(at="08:40"), "دست‌کم 15 دقیقه"),
        (lambda d: d["posts"][0].update(at="07:00"), "پیش از ساعت شروع"),
        (lambda d: d["posts"][5].update(topic="صبحانه‌ی هوش مصنوعی ۲۹ آبان"), "تکراری"),
        (lambda d: d["posts"][5].update(topic="موضوع دیروز"), "تکراری"),
        (lambda d: d["posts"][0].update(color="red"), "کلیدهای ناشناخته"),
        (lambda d: d["posts"][0].update(photo="tg_02_card.jpg", video="big.mp4"), "فقط یکی از"),
    ],
)
def test_every_fault_is_said(change: Callable[[dict[str, Any]], Any], fault: str) -> None:
    doc = a_day()
    change(doc)
    _, errors = TG.check(doc, FILES, day=DAY, first=FIRST, done=["موضوع دیروز"])
    assert any(fault in e for e in errors), errors


def test_a_breaking_package_is_one_post_with_no_hour() -> None:
    one = {
        "posts": [
            {
                "type": "breaking",
                "topic": "فوری: GPT-6.2",
                "photo": "tg_02_card.jpg",
                "text": "🔴 <b>فوری</b>" + SIG,
                "buttons": [[{"text": "منبع رسمی", "url": "https://openai.com/index/x"}]],
            }
        ]
    }
    posts, errors = TG.check(one, FILES, day=DAY, first=None, asap=True)
    assert errors == [] and len(posts) == 1 and posts[0].at is None
    two = {"posts": [one["posts"][0], dict(one["posts"][0], topic="دیگری")]}
    assert any("حداکثر 1 پست" in e for e in TG.check(two, FILES, day=DAY, first=None, asap=True)[1])


def test_each_message_is_one_bot_api_call_in_telegrams_own_shape() -> None:
    posts, _ = TG.check(a_day(), FILES, day=DAY, first=FIRST)
    by = {p.type: TG.calls({"parts": p.parts}, "@chan_test") for p in posts}
    [(m, p, f)] = by["brief"]
    assert m == "sendMessage" and f == [] and p["parse_mode"] == "HTML"
    assert p["link_preview_options"] == {"is_disabled": True}
    assert p["reply_markup"] == {"inline_keyboard": LINKS} and p["chat_id"] == "@chan_test"
    (m1, p1, f1), (m2, p2, _) = by["tool"]
    assert (m1, p1["photo"], f1[0]["name"], "reply_markup" in p1) == (
        "sendPhoto",
        "attach://file0",
        "tg_02_card.jpg",
        False,
    )
    assert m2 == "sendMessage" and p2["reply_markup"]["inline_keyboard"][0][0]["text"] == "GitHub"
    [(m, p, f)] = by["poll"]
    assert (
        m == "sendPoll"
        and p["type"] == "quiz"
        and p["correct_option_id"] == 1
        and p["is_anonymous"] is True
    )
    assert p["explanation_parse_mode"] == "HTML" and "parse_mode" not in p and f == []
    [(m, p, f)] = by["table"]
    assert m == "sendMediaGroup" and len(f) == 2 and "reply_markup" not in p
    assert p["media"][0] == {
        "type": "photo",
        "media": "attach://file0",
        "caption": "⚖️ <b>مقایسه</b>" + SIG,
        "parse_mode": "HTML",
    } and p["media"][1] == {"type": "photo", "media": "attach://file1"}
    [(m, p, f)] = by["voice"]
    assert (
        m == "sendVoice"
        and p["voice"] == "attach://file0"
        and p["caption"].startswith("🎙")
        and f[0]["mime"] == "audio/ogg"
    )
    [(m, p, _)] = by["tip"]
    assert p["disable_notification"] is True


def test_a_telegram_flow_has_its_own_map() -> None:
    daily = a_flow("XX", "bj_tg", kind="tg_post", channel="telegram")
    news = a_flow("XX", "bj_tg_news", kind="tg_post", channel="telegram", recipe="breaking")
    keys = [s.key for s in FV.steps_of(daily)]
    assert {"write", "package", "tg_queue", "tg_send"} <= set(keys) and "render" not in keys
    assert FV.steps_of(news)[0].title_fa == "دیده‌بان خبرهای فوری"
    assert "voice" not in [s.key for s in FV.steps_of(news)]
    assert "telegram.txt" in FL.brief_of(daily, DAY, FIRST, done=["الف"], ig=["ریلز دیروز"])
    assert "«ریلز دیروز»" in FL.brief_of(daily, DAY, FIRST, ig=["ریلز دیروز"])


# ------------------------------------------------------------------ the whole way --
class FakeBot:
    """The Bot API through egress, as the worker sees it: the bot is not an admin until `admin`."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.admin = False
        self.limit = False

    async def call(
        self, hub: Any, call: dict[str, Any], files: list[tuple[str, bytes, str]]
    ) -> dict[str, Any]:
        self.calls.append({**call, "files": [(n, m) for n, _, m in files]})
        method = call["method"]
        if method == "getMe":
            return {"outcome": "ok", "data": {"id": 777, "is_bot": True, "username": "bj_test_bot"}}
        if method == "getChatMember":
            if not self.admin:
                return {
                    "outcome": "error",
                    "code": "publish_error",
                    "data": {
                        "status": 400,
                        "description": "Bad Request: member list is inaccessible",
                    },
                }
            return {
                "outcome": "ok",
                "data": {"status": "administrator", "user_id": 777, "can_post_messages": True},
            }
        if self.limit:
            return {
                "outcome": "error",
                "code": "platform_limit",
                "data": {"status": 429, "retry_after": 30},
            }
        return {
            "outcome": "ok",
            "data": {"message_id": 42, "chat_id": -1003839061584, "chat_username": "bj_chan"},
        }

    def sends(self) -> list[dict[str, Any]]:
        return [c for c in self.calls if c["method"].startswith("send")]


async def test_a_breaking_post_goes_out_once_and_only_when_the_bot_may_post(
    client: httpx.AsyncClient,
    hub: Hub,
    owner_session: dict[str, Any],
    new_company: Callable[..., Any],
    su: Any,
    no_model: list[Any],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from .test_p17_runners import take
    from .test_w14_workshop import refuse_queued, run_ask, send_file, workshop
    from .test_w26_flows import a_pic

    co = await new_company()
    key = fk()
    account = f"p39.{key}"
    await seed(
        su,
        monkeypatch,
        a_flow(co["code"], key, recipe="breaking", hours=("12:00",), trigger_at="09:00"),
    )
    await su.execute(
        "UPDATE automations.flows SET kind = 'tg_post', channel = 'telegram' WHERE key = $1", key
    )
    item = {
        "id": "openai:gpt-6.2-tg",
        "vendor": "OpenAI",
        "title": "GPT-6.2",
        "url": "https://openai.com/index/x",
    }
    # no Telegram connection yet: no session at all
    held = await EV.start_event(hub, key, item)
    assert (held["work"], held["why_fa"]) == (None, TG.WAIT_TOKEN_FA)
    await su.execute(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config, secret_set)
           VALUES ((SELECT id FROM core.companies WHERE code = $1), 'telegram', 'تلگرام', $2::jsonb, true)""",
        co["code"],
        json.dumps({"channels": [{"chat": "@bj_chan", "page": account, "title_fa": "کانال"}]}),
    )
    ws = await workshop(client, hub, owner_session, su)
    bot = FakeBot()
    monkeypatch.setattr(SP, "OVERRIDE", bot)
    monkeypatch.setattr(TG, "RIGHTS", {})

    async def fake_secret(hub: Any, company: str) -> str:
        return "123456:" + "A" * 35

    monkeypatch.setattr(TG, "read_secret", fake_secret)
    try:
        got = await EV.start_event(hub, key, item)
        assert got["new"] and got["work"]
        wid = await su.fetchval("SELECT id FROM work.work WHERE ref = $1", got["work"])
        meta = json.loads(
            await su.fetchval("SELECT run_meta -> 'flow' FROM work.work WHERE id = $1", wid)
        )
        assert meta["kind"] == "tg_post" and meta["asap"] is True
        holder = await su.fetchval(
            "SELECT e.code FROM work.work w JOIN core.employees e ON e.id = w.assignee_id WHERE w.id = $1",
            wid,
        )
        await refuse_queued(su, str(wid))
        r = await run_ask(client, holder, {"work": got["work"], "brief": "خبر فوری"})
        assert r.status_code == 201, r.text
        job = await take(client, ws)
        package = {
            "posts": [
                {
                    "type": "breaking",
                    "topic": "فوری: GPT-6.2 در تلگرام",
                    "photo": "tg_01.png",
                    "text": '🔴 <b>فوری</b> <a href="https://openai.com/index/x">منبع</a>' + SIG,
                    "buttons": [[{"text": "منبع رسمی", "url": "https://openai.com/index/x"}]],
                }
            ]
        }
        files = []
        for name, ctype, data in (
            ("tg_01.png", "image/png", a_pic(1)),
            ("telegram.txt", "text/plain", json.dumps(package, ensure_ascii=False).encode()),
        ):
            r = await send_file(client, ws, job["id"], name, ctype, data)
            assert r.status_code == 201, r.text
            files.append(r.json()["id"])
        await refuse_queued(su, str(wid))
        r = await client.post(
            f"/api/v1/runners/jobs/{job['id']}/result",
            json={
                "exit_code": 0,
                "summary_fa": "تمام.",
                "data": {"session_id": "cs-tg-1", "result_fa": "تمام.", "files": files},
            },
            headers=ws["h"],
        )
        assert r.status_code == 200, r.text
        row = await su.fetchrow(
            "SELECT * FROM media.publications WHERE channel = 'telegram' AND source ->> 'work' = $1",
            got["work"],
        )
        assert row is not None and (row["kind"], row["state"], row["account"]) == (
            "tg_post",
            "scheduled",
            account,
        )
        src = json.loads(row["source"]) if isinstance(row["source"], str) else row["source"]
        assert src["chat"] == "@bj_chan" and src["type"] == "breaking" and src["flow_key"] == key
        assert (
            row["scheduled_at"] <= datetime.now(UTC)
            and row["topic_fa"] == "فوری: GPT-6.2 در تلگرام"
        )
        assert await su.fetchval(
            "SELECT closed_at IS NOT NULL FROM owner.order_reports WHERE ref = $1", got["order"]
        )

        # (other runs' Telegram posts in this database are not this test's)
        await su.execute(
            """UPDATE media.publications SET state = 'cancelled' WHERE channel = 'telegram'
                   AND state IN ('scheduled', 'publishing') AND source ->> 'work' <> $1""",
            got["work"],
        )
        # the bot is not an admin yet: nothing goes, the post says why
        out = await TG.tick(hub)
        assert out["sent"] == [] and bot.sends() == []
        assert (
            await su.fetchval(
                "SELECT state_note_fa FROM media.publications WHERE id = $1", row["id"]
            )
            == TG.WAIT_RIGHTS_FA
        )
        # the owner makes it admin: the next read of its rights (no older than RIGHTS_NO_TTL) lets it post
        bot.admin = True
        monkeypatch.setattr(TG, "RIGHTS", {})
        out = await TG.tick(hub)
        assert out["sent"] == [str(row["ref"])], out
        [sent] = bot.sends()
        assert sent["method"] == "sendPhoto" and sent["payload"]["chat_id"] == "@bj_chan"
        assert sent["payload"]["parse_mode"] == "HTML" and sent["files"] == [
            ("tg_01.png", "image/png")
        ]
        done = await su.fetchrow("SELECT * FROM media.publications WHERE id = $1", row["id"])
        assert (done["state"], done["url"], done["external_id"]) == (
            "published",
            "https://t.me/bj_chan/42",
            "42",
        )
        # once: another minute sends nothing
        await TG.tick(hub)
        assert len(bot.sends()) == 1

        # a post far past its hour is cancelled, never sent late; Telegram's own limit makes one wait
        late = row["scheduled_at"] - timedelta(hours=5)
        for n, at in ((2, late), (3, datetime.now(UTC) - timedelta(minutes=1))):
            await su.execute(
                """INSERT INTO media.publications (company_id, channel, account, kind, state, scheduled_at, title_fa,
                       files, source, chain)
                   SELECT company_id, 'telegram', account, 'tg_post', 'scheduled', $2, $3, '[]'::jsonb,
                          (source - 'sent_ids' - 'retry_at') || jsonb_build_object('n', $4::int), ARRAY[gen_random_uuid()]
                   FROM media.publications WHERE id = $1""",
                row["id"],
                at,
                f"پست {n}",
                n,
            )
        bot.limit = True
        out = await TG.tick(hub)
        assert len(out["stale"]) == 1 and out["sent"] == [], out
        wait = await su.fetchrow(
            "SELECT * FROM media.publications WHERE title_fa = 'پست 3' AND source ->> 'work' = $1",
            got["work"],
        )
        wsrc = json.loads(wait["source"]) if isinstance(wait["source"], str) else wait["source"]
        assert wait["state"] == "scheduled" and wsrc["retry_at"] > datetime.now(UTC).isoformat()
        stale = await su.fetchrow(
            "SELECT * FROM media.publications WHERE title_fa = 'پست 2' AND source ->> 'work' = $1",
            got["work"],
        )
        assert stale["state"] == "cancelled" and "زمانش گذشته" in stale["state_note_fa"]
    finally:
        await all_off(su, key)
