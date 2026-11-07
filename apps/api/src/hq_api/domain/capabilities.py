"""What the holding gives every employee (the owner, 2026-11-06: a media director said «ابزارهای من به
ChatGPT، Gemini یا DeepSeek اتصالی ندارند», another «نمیدونه n8n کجاست»). By code, no model: the
live state of each shared helper and the one way to use it, put in every agent run's context and in
every talk persona's, so that nobody claims a capability does not exist or invents one.

    outside players   ChatGPT (gpt), Gemini (gemini), DeepSeek (deepseek): their state and seats;
                      `substitute.call` (drafts, long reads, searches, third opinions, errands) and
                      the `creative` seat for a cover, an image or a short video (a creative that
                      waits for review before anything is published)
    automations       the holding's rule engine (`automation.propose`: one Persian sentence; the
                      owner seals it), which can also start an n8n workflow (`n8n.run`) when n8n is up
    the company       its connections (Instagram, Telegram, Search Console…: connected or not), its
                      links to other companies (what to ask whom), its working groups and its
                      production lines (ref, title, platform, state, mode: what line.run can name)
    the holding       ⟨2026-11-06⟩ every active company in short (who it is, its departments, sites,
                      channels and accounts with what they are read through, e.g. Instagram via
                      IG-Hub of company IG, its servers by name, its lines and groups): nobody asks
                      «IG کدام شرکت است» again; the full profile and figures are `linked.read`
    voice             Google AI Studio's state for `speech.make` (the media roles)
    how               hire, delegate, split, ask another company, ask the owner, report
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from hq_api.db import Tx

PLAYER_FA = {"gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}
LINES_MAX = 20  # the company's production lines named in the brief (the ones on first)
STATE_FA = {
    "ready": "آماده",
    "limited": "سهمیه‌ی امروزش پر است",
    "off": "خاموش",
    "error": "خطا دارد",
}

HOW = {
    "outside_model": (
        "substitute.call {seat: content_draft | long_read | quick_search | third_opinion | "
        "assistant_errand, player?: gpt | gemini | deepseek, input_md}: masked input only; the "
        "answer is labelled and is a helper's view, never evidence"
    ),
    "cover_image_video": (
        "substitute.call {seat: creative, kind: image | video, player?: gpt | gemini, input_md: the "
        "brief, placement: instagram_post | instagram_story | telegram_post | …, overlay?: the "
        "Persian words}: a creative CR-… that waits for review; deliver its ref with your work; "
        "the owner accepts it on the creatives screen. Publishing it once is the owner's: propose "
        "{kind: a3_action, payload: {action: publish, target: 'CR-… → the channel', preview}} (A3); "
        "nothing is published by itself"
    ),
    "automation": (
        "a CEO or a manager only (an employee asks its manager): automation.propose {sentence_fa}: "
        "one Persian sentence (when / what); the hub checks it and the owner seals it; it can "
        "create work, run or pause a production line, notify, or start an n8n workflow (n8n.run "
        "names a workflow that already exists in n8n). A brand-new n8n workflow is a propose "
        "{kind: proposal} with its steps, for the owner"
    ),
    "production_line": (
        "to run a line of your company on a schedule or an event: automation.propose with "
        "line.run <its ref LN-…> (or line.pause); the lines are under your_company.production_lines"
    ),
    "hire": "propose {kind: hire} (a CEO decides inside its envelope; hiring rules in company.state)",
    "delegate": "work.delegate / work.split; another company: work.request to a linked company",
    "other_companies": (
        "the_holding names every company (beyond its room by code and name, the_holding_more counts "
        "the rest); before you say you do not know a company, its accounts "
        "or its figures, read it: linked.read {company: CODE, what: profile | kpis | outputs | "
        "catalogue | connections | links, ref?} (connections: Instagram accounts as IG-Hub reads "
        "them); then ask it for work with work.request"
    ),
    "voice": (
        "the media roles: speech.make {text_fa, voice?, style?}: a Google AI Studio voice (file of "
        "your company); the first answer is running with a job, call again with {job} until done"
    ),
    "owner": "order.ask only when you truly cannot go on; report steps with order.progress",
}


async def _players(tx: Tx) -> list[dict[str, Any]]:
    rows = await tx.all(
        """SELECT p.player, p.status, p.login_state, p.web_state,
                  COALESCE(array_agg(s.seat ORDER BY s.seat) FILTER (WHERE s.enabled), '{}') AS seats
           FROM substitutes.players p LEFT JOIN substitutes.seats s ON s.player = p.player
           GROUP BY p.player, p.status, p.login_state, p.web_state ORDER BY p.player"""
    )
    out = []
    for r in rows:
        signed_in = "signed_in" in (r["login_state"], r["web_state"])
        state = r["status"] if signed_in else "off"
        out.append(
            {
                "player": r["player"],
                "name": PLAYER_FA.get(r["player"], r["player"]),
                "state": STATE_FA.get(state, state),
                "usable": state == "ready",
                "seats": list(r["seats"] or []),
            }
        )
    return out


async def _company(tx: Tx, company_id: UUID) -> dict[str, Any]:
    conns = await tx.all(
        """SELECT kind, state FROM growth.connections WHERE company_id = :co ORDER BY kind""",
        co=company_id,
    )
    links = await tx.all(
        "SELECT * FROM core.company_links_of(:co)",
        co=company_id,
    )
    groups = await tx.all(
        """SELECT g.key, g.title_fa, m.state FROM growth.memberships m
           JOIN growth.groups g ON g.id = m.group_id WHERE m.company_id = :co ORDER BY g.key""",
        co=company_id,
    )
    lines = await tx.all(
        """SELECT ref, title_fa, platform, state, mode FROM lines.lines
           WHERE company_id = :co ORDER BY (state = 'on') DESC, created_at LIMIT :l""",
        co=company_id,
        l=LINES_MAX,
    )
    on = await tx.scalar(
        "SELECT count(*) FROM lines.lines WHERE company_id = :co AND state = 'on'", co=company_id
    )
    return {
        "connections": [{"kind": c["kind"], "state": c["state"]} for c in conns],
        "links": [dict(x) for x in links],
        "working_groups": [
            {"key": g["key"], "title_fa": g["title_fa"], "state": g["state"]} for g in groups
        ],
        "production_lines": [dict(x) for x in lines],
        "production_lines_on": int(on or 0),
    }


MAP_LIST_MAX = 12  # departments, sites, servers or accounts named per company in the map


def _few(items: list[Any]) -> list[Any]:
    return items[:MAP_LIST_MAX]


# The map's room in a brief, in JSON characters: the holding, the reader's own company and then
# the others in full while they fit, then the rest by code and name, then only how many more
# there are. The number of companies is data (owner rule 9): it never grows the brief past this
# room. With the rest of the brief it stays inside agents.runner.CAPS_CHARS (12 000), and the map
# comes last so a trim never reaches the reader's own company.
MAP_CHARS = 5000
MAP_NAMES_CHARS = 1500


def _size(item: Any) -> int:
    return len(json.dumps(item, ensure_ascii=False, default=str))


def _entry(p: dict[str, Any]) -> dict[str, Any]:
    channels = []
    for c in p.get("connections") or []:
        ch: dict[str, Any] = {"kind": c.get("kind"), "state": c.get("state")}
        ch.update({k: v for k, v in (c.get("handles") or {}).items() if v})
        if c.get("accounts_seen"):
            ch["accounts_seen"] = _few(list(c["accounts_seen"]))
        channels.append(ch)
    return {
        "code": p.get("code"),
        "name_fa": p.get("name_fa"),
        "name_en": p.get("name_en"),
        "kind": p.get("kind"),
        "departments": _few(
            [
                f"{d.get('code')}: {d.get('name_fa') or d.get('name_en') or ''}".strip()
                for d in p.get("departments") or []
            ]
        ),
        "sites": _few(list(p.get("sites") or [])),
        "channels": channels,
        "servers": _few([s.get("name") for s in p.get("servers") or []]),
        "lines_on": len(p.get("lines") or []),
        "groups": [g.get("key") for g in p.get("groups") or []],
    }


async def _holding_map(tx: Tx, first: UUID | None = None) -> tuple[list[dict[str, Any]], int]:
    """Every active company in short, from linked.profile (masked, public handles only), within
    MAP_CHARS (then by code and name within MAP_NAMES_CHARS); and how many are left out."""
    from hq_api.domain import linked as LK

    rows = await tx.all(
        """SELECT id, code, name_fa FROM core.companies WHERE status = 'active'
           ORDER BY (kind = 'holding') DESC, (id = CAST(:first AS uuid)) DESC NULLS LAST, code""",
        first=str(first) if first is not None else None,
    )
    out: list[dict[str, Any]] = []
    used = names = 0
    full = True
    for i, r in enumerate(rows):
        if full:
            p = await _safe(tx, LK.profile, r["id"])
            if p is None:
                continue
            entry = _entry(p)
            if used + _size(entry) <= MAP_CHARS:
                out.append(entry)
                used += _size(entry)
                continue
            full = False
        short = {"code": r["code"], "name_fa": r["name_fa"]}
        if names + _size(short) > MAP_NAMES_CHARS:
            return out, len(rows) - i
        out.append(short)
        names += _size(short)
    return out, 0


async def _safe(tx: Tx, fn: Any, *args: Any) -> Any:
    """One part that cannot be read (a table not there yet) never hides the others."""
    try:
        async with tx.conn.begin_nested():
            return await fn(tx, *args)
    except Exception:  # noqa: BLE001 - a missing part is left out, never a failed run
        return None


async def brief(tx: Tx, company_id: UUID | None, *, n8n_up: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "outside_players": await _safe(tx, _players) or [],
        "automations": {"engine": "the hub's rule engine", "n8n": "up" if n8n_up else "not set up"},
        "how": HOW,
    }
    from hq_api.domain import speech_make as SM

    voice = await _safe(tx, SM.speech_state)
    if voice is not None:
        out["voice"] = voice
    if company_id is not None:
        company = await _safe(tx, _company, company_id)
        if company is not None:
            out["your_company"] = company
    mapped = await _safe(tx, _holding_map, company_id)
    if mapped:
        holding, more = mapped
        if more:
            out["the_holding_more"] = {
                "companies": more,
                "read": "linked.read {company: CODE, what: profile}",
            }
        if holding:
            out["the_holding"] = holding
    return out
