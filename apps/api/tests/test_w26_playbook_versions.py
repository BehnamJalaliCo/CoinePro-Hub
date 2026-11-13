"""W26 (2026-11-13), contract §59.1 and §59.3: the library of working groups. The owner: «این
کارگروه رو که راه انداختیم رو باید ببندیم و یه نسخه‌ای ازش بسازیم که بتونیم توی شرکت‌های دیگه ازش
استفاده بکنیم».

A. one playbook, many versions: a file comes in as a draft (what the hub cannot run dropped with a
   note), the draft is edited, sealed as v1; a change makes v2 as a draft while v1 keeps running;
   v2's seal carries code's changelog; compare is the same lines;
B. a member's version (the owner's tap): its membership and its flow automation move, a draft or
   a retired version refuses; the library filters, its Persian search and the flow's 30-day
   stats; copy (another platform, `parent` at that version), export (no company, account or
   link) and import round trip; retire stops every member's flow;
C. closing a session makes the playbook's next version (§59.3): the owner's steps in his order and
   the lessons from the session's fault log, each lesson's rule on its step.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hq_api.domain import flow_shapes as FS
from hq_api.domain import playbook_versions as PV
from hq_api.domain import playbooks as PB
from hq_api.hub import Hub

from .conftest import idem
from .p14_support import upload
from .test_p21_routing_orders import auto_hiring, envelope, report  # noqa: F401
from .test_p21_secretary import no_model, post_order, words  # noqa: F401 - the fixture
from .test_p22_ops import route_answer
from .test_p23_talk import talk  # noqa: F401 - the fixture
from .test_w10_playbooks import REEL_TEXT, a_draft, hire, join, model

LOG_MD = """# دفتر خرابی‌های کارگروه

## جزئیات

### ۱. کاور با ChatGPT ساخته نشد
- **چه دیده شد:** شش کار تصویر شکست خورد.
- **علت:** چت موقت تصویر نمیسازد.
- **رفع:** تصویر در چت معمولیِ تازه ساخته میشود.
- **درس:** هر تصویر در یک چت معمولیِ تازه.

### ۲. صدا
- **علت:**
  - مدل lite صدای بد داد.
- **درس:** هرگز مدل lite برای صدا.
"""


def a_file(tag: str, **over: Any) -> dict[str, Any]:
    """A playbook file as another hub would export it: two real roles and one nobody has, a
    step of a kind the line engine does not run, a helper the hub does not have, a lesson on
    its step, and a step's settings with an account and a link (an import keeps what it is
    given; only an export strips them)."""
    playbook = {
        "title_fa": f"ریلز روزانه‌ی آزمایشی آزمون{tag}",
        "purpose_fa": "هر روز یک ریلز آموزشی با صدای گوینده",
        "platform": "instagram",
        "seats": [
            {"seat": "director", "role": "media_director", "title_fa": "مدیر محتوا", "helpers": []},
            {"seat": "writer", "role": "scriptwriter", "title_fa": "نویسنده", "helpers": ["gpt"]},
            {"seat": "pilot", "role": "خلبان", "title_fa": "خلبان", "helpers": []},
        ],
        "steps": [
            {"key": "topic", "title_fa": "موضوع", "seat": "writer", "kind": "topic",
             "helper": "model", "model": "claude-sonnet-5-5"},
            {"key": "script", "title_fa": "سناریو", "seat": "writer", "kind": "gpt_text",
             "helper": "gpt", "inputs": ["topic", "nowhere"]},
            {"key": "cover", "title_fa": "کاور", "seat": "writer", "kind": "cover", "helper": "gpt",
             "inputs": ["script"], "settings": {"style": "bold", "account": "@pro", "ref": "https://x.y"}},
            {"key": "dream", "title_fa": "خواب دیدن", "seat": "writer", "kind": "telepathy"},
            {"key": "voice", "title_fa": "صدا", "seat": "director", "kind": "tts", "helper": "bing"},
            {"key": "video", "title_fa": "ساخت ویدیو", "seat": "director", "kind": "workshop",
             "helper": "workshop", "effort": "max", "inputs": ["script", "voice", "cover"]},
            {"key": "pack", "title_fa": "بسته", "seat": "director", "kind": "package", "helper": "code"},
        ],
        "package": [{"name": "caption.txt", "title_fa": "کپشن", "step": "pack"},
                    {"name": "comment.txt", "title_fa": "کامنت", "step": "nowhere"}],
        "routines": [],
        "kpis": [{"key": "views", "title_fa": "بازدید", "source": "instagram", "unit": "count"}],
        "connections": ["instagram"],
        "rules_fa": ["هر ریلز با فونت شرکت تیتر میخورد."],
        "lessons": [{"n": 1, "title_fa": "کاور با ChatGPT ساخته نشد", "cause_fa": "چت موقت",
                     "fix_fa": "چت معمولی", "rule_fa": "هر تصویر در یک چت معمولیِ تازه",
                     "step": "cover"}],
    }  # fmt: skip
    return {"format": PV.FORMAT, "version": 3, "exported_at": "2026-11-13T10:00:00+00:00",
            "playbook": {**playbook, **over}}  # fmt: skip


async def imported(
    client: httpx.AsyncClient, owner: dict[str, str], doc: dict[str, Any]
) -> dict[str, Any]:
    r = await client.post("/api/v1/playbooks/import", headers={**owner, **idem()}, json=doc)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def flow_line(su: Any, company: dict[str, Any], ref: str, version: int) -> tuple[str, str]:
    """A member's flow automation (as `POST /playbooks/{ref}/use` makes it) on a line of its own:
    (the automation's ref, the line's ref)."""
    line = await su.fetchrow(
        """INSERT INTO lines.lines (company_id, template, template_version, platform, title_fa, caps, steps)
           VALUES ($1, 'reels_daily', 1, 'instagram', 'خط آزمون', '{}', '[]') RETURNING id, ref""",
        company["id"],
    )
    at = await su.fetchval(
        """INSERT INTO growth.automations (company_id, scope, sentence_fa, rule, state, sealed_at,
               kind, playbook, playbook_version, line, schedule)
           VALUES ($1, 'company', 'ریلز روزانه', '{}', 'on', now(), 'flow', $2, $3, $4, '{"mode": "best"}')
           RETURNING ref""",
        company["id"],
        ref,
        version,
        line["ref"],
    )
    for state, cost, minutes, ago in (("done", 1.5, 20, 1), ("done", 2.5, 40, 2),
                                      ("failed", 0.5, 5, 3), ("skipped", 0, 0, 4)):  # fmt: skip
        await su.execute(
            """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, at,
                   started_at, ended_at, usd_equiv)
               VALUES ($1, $2, 1, 'n8n', $3, now() - make_interval(days => $4),
                       now() - make_interval(days => $4),
                       now() - make_interval(days => $4) + make_interval(mins => $5), $6)""",
            company["id"],
            line["id"],
            state,
            ago,
            minutes,
            cost,
        )
    # a run older than 30 days and a dry run count for nothing
    await su.execute(
        """INSERT INTO lines.runs (company_id, line_id, line_version, trigger, state, at, usd_equiv, dry)
           VALUES ($1, $2, 1, 'n8n', 'done', now() - interval '40 days', 9, false),
                  ($1, $2, 1, 'test', 'done', now(), 9, true)""",
        company["id"],
        line["id"],
    )
    return str(at), str(line["ref"])


# ================================================================ A. versions ==
async def test_a_playbook_has_versions_a_change_makes_the_next_draft_and_the_seal_its_changelog(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    tag = secrets.token_hex(3)
    # a file comes in as a draft: what the hub cannot run is dropped and named
    pb = await imported(client, owner, a_file(tag))
    ref = pb["ref"]
    assert pb["state"] == "draft" and pb["version"] == 1 and pb["edits"] == 0
    assert pb["draft_version"] == 1 and pb["parent"] is None
    assert [(v["version"], v["state"]) for v in pb["versions"]] == [(1, "draft")]
    assert [s["seat"] for s in pb["seats"]] == ["director", "writer"]
    assert [s["key"] for s in pb["steps"]] == ["topic", "script", "cover", "voice", "video", "pack"]
    steps = {s["key"]: s for s in pb["steps"]}
    assert steps["script"]["inputs"] == ["topic"] and steps["voice"]["helper"] is None
    assert steps["video"]["effort"] == "max" and steps["video"]["inputs"] == [
        "script",
        "voice",
        "cover",
    ]
    # a lesson's rule joins its step's rules
    assert steps["cover"]["rules_fa"] == ["هر تصویر در یک چت معمولیِ تازه"]
    assert pb["lessons"][0]["step"] == "cover" and pb["lessons"][0]["n"] == 1
    assert [(p["name"], p["step"]) for p in pb["package"]] == [
        ("caption.txt", "pack"),
        ("comment.txt", None),
    ]
    note = pb["note_fa"]
    assert "نسخه‌ی 3" in note and "«خلبان»" in note and "«خواب دیدن»" in note and "«bing»" in note
    assert pb["source"] == {"order": "", "company": None, "conversation": None}
    # nothing else is a playbook file; an upload's id is read too
    bad = await client.post("/api/v1/playbooks/import", headers={**owner, **idem()},
                            json={**a_file(tag), "format": "other/1"})  # fmt: skip
    assert bad.status_code == 422 and bad.json()["message_fa"] == PV.NOT_A_PLAYBOOK_FA
    missing = await client.post("/api/v1/playbooks/import", headers={**owner, **idem()},
                                json={"file_id": "00000000-0000-0000-0000-000000000000"})  # fmt: skip
    assert missing.status_code == 404
    file_id = await upload(client, owner, json.dumps(a_file(tag)).encode(), "text/plain", "pb.json")
    r = await client.post(
        "/api/v1/playbooks/import", headers={**owner, **idem()}, json={"file_id": file_id}
    )
    assert r.status_code == 201 and r.json()["ref"] != ref and len(r.json()["steps"]) == 6
    junk = await upload(client, owner, b"just some words", "text/plain", "junk.txt")
    r = await client.post(
        "/api/v1/playbooks/import", headers={**owner, **idem()}, json={"file_id": junk}
    )
    assert r.status_code == 422
    # the draft is edited whole: a step's settings left out stay as they were
    new_steps = [{k: v for k, v in s.items() if k != "settings"} for s in pb["steps"]]
    r = await client.patch(
        f"/api/v1/playbooks/{ref}", headers=owner, json={"steps": new_steps[::-1]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["edits"] == 1 and r.json()["version"] == 1
    assert r.json()["steps"][0]["key"] == "pack"
    stored = await su.fetchval(
        """SELECT body FROM owner.playbook_versions v JOIN owner.playbooks p ON p.id = v.playbook_id
           WHERE p.ref = $1 AND v.version = 1""",
        ref,
    )
    cover = next(s for s in json.loads(stored)["steps"] if s["key"] == "cover")
    assert cover["settings"]["style"] == "bold"
    r = await client.patch(f"/api/v1/playbooks/{ref}", headers=owner, json={"steps": pb["steps"]})
    assert r.status_code == 200
    # not sealed yet: nothing to revise
    assert (
        await client.post(f"/api/v1/playbooks/{ref}/revise", headers={**owner, **idem()})
    ).status_code == 409
    # v1 sealed: a group in the database, frozen; a change refuses until a new version is drafted
    r = await client.post(f"/api/v1/playbooks/{ref}/seal", headers=owner)
    assert r.status_code == 200, r.text
    pb = r.json()
    assert pb["state"] == "sealed" and pb["version"] == 1 and pb["draft_version"] is None
    assert pb["versions"] == [{"version": 1, "state": "sealed", "at": pb["versions"][0]["at"],
                               "by_fa": "مدیر کل", "changelog_fa": [], "members": 0}]  # fmt: skip
    r = await client.patch(f"/api/v1/playbooks/{ref}", headers=owner, json={"title_fa": "x"})
    assert r.status_code == 409 and r.json()["message_fa"] == PB.SEALED_FA
    # v2: a copy of v1 as a draft; v1 keeps running (the default view stays v1)
    key = idem()
    r = await client.post(f"/api/v1/playbooks/{ref}/revise", headers={**owner, **key})
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2 and r.json()["state"] == "draft"
    assert r.json()["steps"] == pb["steps"]
    again = await client.post(f"/api/v1/playbooks/{ref}/revise", headers={**owner, **key})
    assert again.headers.get("Idempotent-Replay") == "true" and again.json()["version"] == 2
    r = await client.post(f"/api/v1/playbooks/{ref}/revise", headers={**owner, **idem()})
    assert r.status_code == 201 and r.json()["version"] == 2  # the draft already there
    assert await su.fetchval(
        "SELECT count(*) FROM owner.playbook_versions v JOIN owner.playbooks p ON p.id = v.playbook_id WHERE p.ref = $1",
        ref,
    ) == 2  # fmt: skip
    cur = (await client.get(f"/api/v1/playbooks/{ref}", headers=owner)).json()
    assert cur["version"] == 1 and cur["state"] == "sealed" and cur["draft_version"] == 2
    assert [(v["version"], v["state"]) for v in cur["versions"]] == [(2, "draft"), (1, "sealed")]
    # the draft changes: the title, a step gone, a step changed, a lesson and a rule added
    v2_steps = [s for s in pb["steps"] if s["key"] != "pack"]
    v2_steps[0] = {**v2_steps[0], "effort": "low"}
    r = await client.patch(
        f"/api/v1/playbooks/{ref}",
        headers=owner,
        json={"title_fa": f"ریلز روزانه‌ی تازه آزمون{tag}", "steps": v2_steps,
              "rules_fa": [*pb["rules_fa"], "هر روز ساعت هشت."],
              "lessons": [*pb["lessons"], {"n": 2, "title_fa": "صدای lite", "rule_fa": "هرگز lite",
                                           "step": "voice"}]},
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2 and r.json()["state"] == "draft"
    assert next(s for s in r.json()["steps"] if s["key"] == "voice")["rules_fa"] == ["هرگز lite"]
    v1 = (await client.get(f"/api/v1/playbooks/{ref}", headers=owner, params={"version": 1})).json()
    assert v1["title_fa"] == f"ریلز روزانه‌ی آزمایشی آزمون{tag}" and v1["state"] == "sealed"
    assert (
        await su.fetchval("SELECT title_fa FROM owner.playbooks WHERE ref = $1", ref)
        == v1["title_fa"]
    )
    assert (
        await client.get(f"/api/v1/playbooks/{ref}", headers=owner, params={"version": 9})
    ).status_code == 404
    # compare, by code
    r = await client.get(f"/api/v1/playbooks/{ref}/compare", headers=owner, params={"a": 1, "b": 2})
    assert r.status_code == 200, r.text
    diff = r.json()
    assert (diff["a"], diff["b"]) == (1, 2)
    got = {(c["part"], c["key"], c["kind"]) for c in diff["changes"]}
    assert got == {("title", "title_fa", "changed"), ("step", "pack", "removed"),
                   ("step", "topic", "changed"), ("step", "voice", "changed"),
                   ("package", "caption.txt", "changed"), ("lesson", "صدای lite", "added"),
                   ("rule", "هر روز ساعت هشت.", "added")}, got  # fmt: skip
    # v2 sealed: its changelog is the same lines; members stay; the group follows the body
    r = await client.post(f"/api/v1/playbooks/{ref}/seal", headers=owner)
    assert r.status_code == 200, r.text
    pb = r.json()
    assert (
        pb["version"] == 2
        and pb["state"] == "sealed"
        and pb["title_fa"].startswith("ریلز روزانه‌ی تازه")
    )
    log = pb["versions"][0]["changelog_fa"]
    assert pb["versions"][0]["state"] == "sealed" and len(log) == 7, log
    assert f"نام: «ریلز روزانه‌ی آزمایشی آزمون{tag}» ← «ریلز روزانه‌ی تازه آزمون{tag}»" in log
    assert "قدم «بسته» برداشته شد" in log and "درس «صدای lite» اضافه شد" in log
    assert "قدم «موضوع» عوض شد" in log
    assert log == [PV.line_fa(FS.PlaybookChange(**c)) for c in diff["changes"]]
    group = await su.fetchrow(
        "SELECT version, title_fa FROM growth.groups WHERE key = $1", PB.group_key(ref)
    )
    assert group["version"] == 2 and group["title_fa"] == pb["title_fa"]
    assert (await client.post(f"/api/v1/playbooks/{ref}/seal", headers=owner)).status_code == 409
    versions = (await client.get(f"/api/v1/playbooks/{ref}/versions", headers=owner)).json()
    assert [(v["version"], v["state"]) for v in versions] == [(2, "sealed"), (1, "sealed")]


# ======================================= B. members, library, copy, export, retire ==
async def test_members_run_a_version_the_library_finds_and_counts_and_a_file_goes_out_and_back(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    new_company: Callable[..., Any],
) -> None:
    tag = secrets.token_hex(3)
    pb = await imported(client, owner, a_file(tag))
    ref = pb["ref"]
    assert (await client.post(f"/api/v1/playbooks/{ref}/seal", headers=owner)).status_code == 200
    r = await client.post(f"/api/v1/playbooks/{ref}/revise", headers={**owner, **idem()})
    assert r.status_code == 201
    r = await client.patch(
        f"/api/v1/playbooks/{ref}", headers=owner, json={"purpose_fa": "نسخه‌ی دوم"}
    )
    assert r.status_code == 200
    assert (await client.post(f"/api/v1/playbooks/{ref}/seal", headers=owner)).status_code == 200
    # a company joins as is: it runs the newest sealed version
    company = await new_company()
    co = company["code"]
    r = await client.post(f"/api/v1/playbooks/{ref}/apply", headers={**owner, **idem()},
                          json={"company": co, "as_is": True})  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["member"]["version"] == 2 and r.json()["member"]["automation"] is None
    at, line = await flow_line(su, company, ref, 2)
    # «استفاده از این نسخه»: its membership and its flow move to v1
    r = await client.put(
        f"/api/v1/playbooks/{ref}/members/{co}/version", headers=owner, json={"version": 1}
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1 and r.json()["automation"] == at and r.json()["company"] == co
    assert (
        await su.fetchval("SELECT playbook_version FROM growth.automations WHERE ref = $1", at) == 1
    )
    assert await su.fetchval(
        """SELECT m.version FROM growth.memberships m JOIN core.companies c ON c.id = m.company_id
           WHERE c.code = $1""",
        co,
    ) == 1  # fmt: skip
    audit = await su.fetchrow(
        "SELECT action_class, summary FROM audit.entries WHERE action = 'playbook.version' AND target_ref = $1",
        f"{ref}:{co}",
    )
    assert audit["action_class"] == "A2" and audit["summary"] == "v2 -> v1"
    pbv = (await client.get(f"/api/v1/playbooks/{ref}", headers=owner)).json()
    assert {v["version"]: v["members"] for v in pbv["versions"]} == {2: 0, 1: 1}
    assert (await client.put(f"/api/v1/playbooks/{ref}/members/{co}/version", headers=owner,
                             json={"version": 7})).status_code == 404  # fmt: skip
    assert (await client.put(f"/api/v1/playbooks/{ref}/members/ZZZZ/version", headers=owner,
                             json={"version": 1})).status_code == 404  # fmt: skip
    assert (
        await client.post(f"/api/v1/playbooks/{ref}/revise", headers={**owner, **idem()})
    ).status_code == 201
    r = await client.put(
        f"/api/v1/playbooks/{ref}/members/{co}/version", headers=owner, json={"version": 3}
    )
    assert r.status_code == 409  # a draft does not run
    # the library: its stats (the last 30 days of the flow, dry and old runs left out), the
    # member companies, filters and the Persian search
    r = await client.get("/api/v1/playbooks", headers=owner, params={"company": co})
    assert r.status_code == 200, r.text
    (item,) = [x for x in r.json() if x["ref"] == ref]
    assert item["steps"] == [] and item["lessons"] == [] and item["package"] == []
    assert item["companies_fa"] == [f"شرکت آزمایشی {co}"] and len(item["versions"]) == 3
    stats = item["stats"]
    assert (stats["runs"], stats["done"], stats["companies"]) == (3, 2, 1), stats
    assert stats["success_pct"] == pytest.approx(66.7) and stats["avg_cost_usd"] == pytest.approx(
        1.5
    )
    assert stats["avg_minutes"] == pytest.approx(30.0) and stats["last_run_at"]
    found = (
        await client.get("/api/v1/playbooks", headers=owner, params={"q": f"روزانه آزمون{tag}"})
    ).json()
    assert [x["ref"] for x in found] == [ref]
    assert (
        await client.get("/api/v1/playbooks", headers=owner, params={"q": f"یوتیوب آزمون{tag}"})
    ).json() == []
    found = (await client.get("/api/v1/playbooks", headers=owner,
                              params={"q": f"آزمون{tag}", "platform": "youtube"})).json()  # fmt: skip
    assert found == []
    found = (await client.get("/api/v1/playbooks", headers=owner,
                              params={"q": f"آزمون{tag}", "state": "sealed", "platform": "instagram"})).json()  # fmt: skip
    assert [x["ref"] for x in found] == [ref]
    # export: the version's file, without any company, account or link
    r = await client.get(f"/api/v1/playbooks/{ref}/export", headers=owner, params={"version": 1})
    assert r.status_code == 200, r.text
    assert (
        "attachment" in r.headers["content-disposition"]
        and "v1.playbook.json" in r.headers["content-disposition"]
    )
    doc = r.json()
    assert doc["format"] == PV.FORMAT and doc["version"] == 1
    assert set(doc["playbook"]) == {"title_fa", "purpose_fa", "platform", "seats", "steps", "package",
                                    "routines", "kpis", "connections", "rules_fa", "lessons"}  # fmt: skip
    text = json.dumps(doc, ensure_ascii=False)
    assert (
        co not in text and "@pro" not in text and "https://" not in text and "members" not in text
    )
    cover = next(s for s in doc["playbook"]["steps"] if s["key"] == "cover")
    assert cover["settings"] == {"style": "bold"}
    # … and back in: the same flow as a new draft
    back = await imported(client, owner, doc)
    assert back["ref"] != ref and back["state"] == "draft" and back["version"] == 1
    assert [s["key"] for s in back["steps"]] == [s["key"] for s in doc["playbook"]["steps"]]
    assert (
        back["lessons"] == doc["playbook"]["lessons"] and back["seats"] == doc["playbook"]["seats"]
    )
    # copy: a new draft from v1 on another platform, `parent` this playbook at that version
    r = await client.post(f"/api/v1/playbooks/{ref}/copy", headers={**owner, **idem()},
                          json={"version": 1, "platform": "telegram", "title_fa": "کانال روزانه"})  # fmt: skip
    assert r.status_code == 201, r.text
    copied = r.json()
    assert copied["order"] is None and copied["conversation"] is None
    cp = copied["playbook"]
    assert cp["ref"] != ref and cp["state"] == "draft" and cp["version"] == 1
    assert (
        cp["parent"] == f"{ref}@1"
        and cp["platform"] == "telegram"
        and cp["title_fa"] == "کانال روزانه"
    )
    assert [s["key"] for s in cp["steps"]] == [s["key"] for s in doc["playbook"]["steps"]]
    assert cp["members"] == [] and "نسخه‌ی 1" in cp["note_fa"]
    # retire: every member's flow stops, the sealed versions are retired, nothing deleted
    r = await client.post(f"/api/v1/playbooks/{ref}/retire", headers=owner)
    assert r.status_code == 200, r.text
    assert await su.fetchval("SELECT state FROM growth.automations WHERE ref = $1", at) == "off"
    states = [(v["version"], v["state"]) for v in r.json()["versions"]]
    assert (
        states == [(3, "draft"), (2, "retired"), (1, "retired")]
        and r.json()["draft_version"] is None
    )
    r = await client.put(
        f"/api/v1/playbooks/{ref}/members/{co}/version", headers=owner, json={"version": 2}
    )
    assert r.status_code == 409
    assert (
        await client.patch(f"/api/v1/playbooks/{ref}", headers=owner, json={"title_fa": "x"})
    ).status_code == 409
    assert (
        await su.fetchval(
            "SELECT count(*) FROM lines.runs r JOIN lines.lines l ON l.id = r.line_id WHERE l.ref = $1",
            line,
        )
        == 6
    )


def test_the_fault_log_reads_as_lessons_and_the_flow_is_checked_by_code() -> None:
    lessons = PV.lessons_from_log(LOG_MD)
    assert [x["title_fa"] for x in lessons] == ["کاور با ChatGPT ساخته نشد", "صدا"]
    assert (
        lessons[0]["cause_fa"] == "چت موقت تصویر نمیسازد."
        and lessons[0]["rule_fa"] == "هر تصویر در یک چت معمولیِ تازه."
    )
    assert lessons[1]["cause_fa"] == "مدل lite صدای بد داد." and lessons[1]["fix_fa"] == ""
    notes: list[str] = []
    flow = PV.normalise_flow(
        {"steps": [{"key": "A b", "title_fa": "یک", "kind": "tts", "max_attempts": 9, "gate": "x"},
                   {"key": "a_b", "title_fa": "دو", "kind": "report", "seat": "nobody"}]},
        [], notes,
    )  # fmt: skip
    assert [(s["key"], s["max_attempts"], s["gate"]) for s in flow["steps"]] == [
        ("a_b", 3, "auto"),
        ("a_b_2", 1, "auto"),
    ]
    assert any("«دو»" in n for n in notes)
    assert PV.export_name("ریلز / روزانه", 2) == "ریلز-روزانه-v2.playbook.json"


# ============================================== C. the session's next version (§59.3) ==
async def test_closing_a_session_makes_the_playbooks_next_version_with_its_steps_and_lessons(
    client: httpx.AsyncClient,
    hub: Hub,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
    auto_hiring: None,  # noqa: F811
    new_company: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await new_company()
    co = company["code"]
    await envelope(su, company)
    out = await post_order(client, owner, REEL_TEXT.format(co=co, w=words()))
    ref = out["ref"]
    await hire(hub, company, "scriptwriter")
    await join(client, owner, ref, f"scriptwriter@{co}")
    route_answer(monkeypatch, model(a_draft(co)))
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **idem()})
    assert r.status_code == 201, r.text
    pref = r.json()["ref"]
    assert r.json()["steps"] == [] and r.json()["versions"][0]["state"] == "draft"
    assert (await client.post(f"/api/v1/playbooks/{pref}/seal", headers=owner)).status_code == 200
    # the session goes on; the owner closes it into the playbook's next version: the steps in
    # his order, the lessons from the fault log, each rule on its step, the drafter's summary
    nxt = {**a_draft(co), "summary_fa": "قدم‌ها و درس‌های جلسه اضافه شد.",
           "steps": [{"key": "topic", "title_fa": "موضوع", "seat": "topic_finder", "kind": "topic"},
                     {"key": "cover", "title_fa": "کاور", "seat": "topic_finder", "kind": "cover",
                      "helper": "gpt"},
                     {"key": "voice", "title_fa": "صدا", "seat": "director", "kind": "tts"}],
           "lessons": [{"title_fa": "کاور با ChatGPT ساخته نشد", "cause_fa": "چت موقت",
                        "fix_fa": "چت معمولی", "rule_fa": "هر تصویر در یک چت معمولیِ تازه.",
                        "step": "cover"}]}  # fmt: skip
    seen = route_answer(monkeypatch, model(nxt))
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **idem()},
                          json={"playbook": pref, "log_md": LOG_MD})  # fmt: skip
    assert r.status_code == 201, r.text
    pb = r.json()
    assert pb["ref"] == pref and pb["version"] == 2 and pb["state"] == "draft"
    assert [s["key"] for s in pb["steps"]] == ["topic", "cover", "voice"]
    cover = next(s for s in pb["steps"] if s["key"] == "cover")
    assert cover["rules_fa"] == ["هر تصویر در یک چت معمولیِ تازه."]
    # the model's lesson kept; the log's other entry joined by code (no step)
    assert [(x["title_fa"], x["step"]) for x in pb["lessons"]] == [
        ("کاور با ChatGPT ساخته نشد", "cover"), ("صدا", None)
    ]  # fmt: skip
    prompt = json.loads(seen[-1]["prompt"])
    assert prompt["current_playbook"]["title_fa"] == a_draft(co)["title_fa"]
    assert "### ۲. صدا" in prompt["fault_log"] and "topic" in prompt["step_kinds"]
    assert (
        await su.fetchval("SELECT count(*) FROM owner.playbooks WHERE source->>'order' = $1", ref)
        == 1
    )
    # v1 keeps running; the card in the session points at the same playbook
    cur = (await client.get(f"/api/v1/playbooks/{pref}", headers=owner)).json()
    assert cur["version"] == 1 and cur["state"] == "sealed" and cur["draft_version"] == 2
    rep = await report(client, owner, ref)
    assert rep["steps"][-1]["what_fa"].startswith(f"نسخه‌ی 2 کارگروه {pref} از این جلسه پیش‌نویس شد")
    # once more without the model: the same draft, rewritten by code from the version it had
    route_answer(monkeypatch, model(None))
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **idem()},
                          json={"playbook": pref, "log_md": LOG_MD})  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2 and PB.NO_MODEL_NEXT_FA in r.json()["note_fa"]
    assert [x["title_fa"] for x in r.json()["lessons"]] == ["کاور با ChatGPT ساخته نشد", "صدا"]
    r = await client.post(f"/api/v1/playbooks/{pref}/seal", headers=owner)
    assert r.status_code == 200, r.text
    log = r.json()["versions"][0]["changelog_fa"]
    assert "قدم «کاور» اضافه شد" in log and "درس «صدا» اضافه شد" in log, log
    # the member stays on v1 until the owner moves it
    (m,) = r.json()["members"]
    assert m["company"] == co and m["version"] == 1
    # a playbook that does not exist, or a retired one, is no target
    r = await client.post(f"/api/v1/orders/{ref}/playbook", headers={**owner, **idem()},
                          json={"playbook": "PB-999999"})  # fmt: skip
    assert r.status_code == 404


async def test_a_copy_with_a_note_opens_the_session_that_adapts_it(
    client: httpx.AsyncClient,
    owner: dict[str, str],
    su: Any,
    no_model: list[Any],  # noqa: F811
    talk: dict[str, Any],  # noqa: F811
) -> None:
    tag = secrets.token_hex(3)
    pb = await imported(client, owner, a_file(tag))
    ref = pb["ref"]
    r = await client.post(f"/api/v1/playbooks/{ref}/copy", headers={**owner, **idem()},
                          json={"platform": "youtube", "note_fa": "برای یوتیوب، ویدیوی بلند"})  # fmt: skip
    assert r.status_code == 201, r.text
    out = r.json()
    cp = out["playbook"]
    assert out["order"] and cp["platform"] == "youtube" and cp["parent"] == f"{ref}@1"
    assert cp["source"]["order"] == out["order"] and cp["source"]["company"] is None
    text = await su.fetchval("SELECT text FROM owner.orders WHERE ref = $1", out["order"])
    assert text.startswith("این کارگروه را برای یوتیوب جور کن: برای یوتیوب، ویدیوی بلند")
    assert ref not in text and "# کارگروه «" in text
    assert await su.fetchval(
        "SELECT source_playbook FROM owner.order_reports WHERE ref = $1", out["order"]
    ) == cp["ref"]  # fmt: skip
    # the draft made in that session is the copy's (its v1 rewritten), not a third playbook
    assert (
        await client.post(f"/api/v1/orders/{out['order']}/playbook", headers={**owner, **idem()})
    ).json()["ref"] == cp["ref"]
