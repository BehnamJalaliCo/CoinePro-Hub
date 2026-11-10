"""What the holding gives every employee (the owner, 2026-11-06: a media director said «ابزارهای من به
ChatGPT، Gemini یا DeepSeek اتصالی ندارند», another «نمیدونه n8n کجاست»). By code, no model: the
live state of each shared helper and the one way to use it, put in every agent run's context and in
every talk persona's, so that nobody claims a capability does not exist or invents one.

    outside players   ChatGPT (gpt), Gemini (gemini), DeepSeek (deepseek): their state and seats;
                      `substitute.call` (drafts, long reads, searches, third opinions, errands) and
                      the `creative` seat for a cover or an image (a creative that waits for
                      review before anything is published)
    workshop          ⟨2026-11-09⟩ §43 hands for any task no tool covers: Claude Code on the hub
                      (`workshop.run`), its state (ready or not set up yet); a video made without a
                      camera is made there, a filmed one is the «بسته‌ی ساخت ویدیو» for the owner
    instagram         ⟨2026-11-08⟩ every company's Instagram is read and published through IG-Hub;
                      accounts not registered here are the technical team's `connection.set`
    automations       the holding's rule engine (`automation.propose`: one Persian sentence; the
                      owner seals it), which can also start an n8n workflow (`n8n.run`) when n8n is up
    the company       its connections (Instagram, Telegram, Search Console…: connected or not), its
                      links to other companies (what to ask whom), its working groups and its
                      production lines (ref, title, platform, state, mode: what line.run can name)
    the holding       ⟨2026-11-06⟩ every active company in short (who it is, its departments, sites,
                      channels and accounts with what they are read through, e.g. Instagram via
                      IG-Hub of company IG, its servers by name, its lines and groups): nobody asks
                      «IG کدام شرکت است» again; the full profile and figures are `linked.read`
    technical         ⟨1.20⟩ §38.2 for this role: the server tools it holds and the servers it may use
                      (names only), whether it holds `hub.ops` (the hub itself), and for a role with
                      neither the one way: work.request to its company's CTO or the holding's AIOPS
                      («nobody says دسترسی ندارم»)
    how               hire, delegate, split, ask another company, ask the owner, report, the hub
"""

from __future__ import annotations

import json
from collections.abc import Collection
from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.principal import Principal

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
    "cover_image": (
        "substitute.call {seat: creative, kind: image, player?: gpt | gemini, input_md: the "
        "brief, placement: instagram_post | instagram_story | telegram_post | …, overlay?: the "
        "Persian words}: a creative CR-… that waits for review; deliver its ref with your work; "
        "the owner accepts it on the creatives screen. Publishing it once is the owner's: propose "
        "{kind: a3_action, payload: {action: publish, target: 'CR-… → the channel', preview}} (A3); "
        "nothing is published by itself"
    ),
    "workshop": (
        "⟨2026-11-09⟩ any task none of your tools covers (a video, a site page, an SEO crawl, a PDF "
        "report, a scraper, a data file, anything): workshop.run {brief, title?, work?}: Claude "
        "Code with a whole computer on the hub (ffmpeg, Chromium, node, python, IRANYekanX, the "
        "internet), Opus 5.5, no token cap, up to 60 minutes; write the whole ask, then finish your "
        "run. Every file it puts in out/ comes back into the session as an output of your work "
        "with open and download; you get a run to show the owner and ask «تأیید یا اصلاح؟»; a "
        "fix is the next workshop.run on the same work. Never say a tool is missing"
    ),
    "video": (
        "a video made without a camera (a motion graphic, an animated reel, a chart explainer, a "
        "slideshow): workshop.run renders it and the MP4 comes back into the session. A filmed "
        "video (a person on camera): the «بسته‌ی ساخت ویدیو» with `deliver`: script, shot list, "
        "on-screen text, voice text (what the narrator reads), caption, hashtags, cover prompt, for "
        "the owner to shoot. No render or ffmpeg is ever a blocker, a readiness item or a step of "
        "the owner's. Publishing, after the owner approves, goes on through IG-Hub"
    ),
    "narration": (
        "⟨2026-11-10⟩ the narrator of a reel or a video is ON (what the owner switched off is his "
        "own voice talk with the app): speech.make {text_fa, voice?, style?} makes the voice with "
        "Google AI Studio on his account and answers an audio file; deliver it so he hears it, "
        "then give it to the workshop as an input: workshop.run {brief, files: [<file id>]} (the "
        "workshop finds it in in/ and cuts the picture to it). Never a silent video in place of a "
        "narrated one. `narration.state` below says whether AI Studio is signed in; signed out: "
        "say so in one line (he signs in once) and do what does not need the voice"
    ),
    "instagram": (
        "Instagram, for every company, is read and published through IG-Hub (company IG's server, "
        "Meta's official API): the figures with connection.read; a reviewed item goes out as a "
        "media_publish card or by the publisher through IG-Hub's API; a company whose accounts are "
        "not registered here yet is the technical team's connection.set on IG-Hub, made by code — "
        "never the owner's step, never «not connected»"
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
    "owner": "order.ask only when you truly cannot go on; report steps with order.progress",
    "hub": (
        "the hub itself (services, logs, memory, a service on or off, n8n, backup): hub.ops {op, "
        "args?} for the holding's AIOPS head, platform SRE and the holding's CTO; anyone else: "
        "work.request to the holding's AIOPS saying exactly what to do. Never say an access is "
        "missing: do it, or hand it to who has it and tell the owner who"
    ),
}
SERVER_TOOLS = ("server.map", "server.read", "server.exec", "server.write", "server.claude")
TECH_DEPARTMENT = "TECH"


async def _tech_roles(tx: Tx) -> set[str]:
    """The technical charters: the TECH department's company roles (read from the charters the
    hub loaded, never a hardcoded list)."""
    from hq_common import charters as CHL

    lib = _CHARTERS.get("lib")
    if lib is None:
        lib = CHL.load()
        _CHARTERS["lib"] = lib
    return {
        r for r, c in lib.roles.items() if c.department == TECH_DEPARTMENT and c.scope == "company"
    }


_CHARTERS: dict[str, Any] = {}
HOLDING_SERVER_ROLES = ("hub_platform_sre", "overseer")  # every paired server (contract §26.6)
SERVERS_MAX = 30


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


def connection_entry(c: dict[str, Any], company_code: str | None) -> dict[str, Any]:
    """One connection as the brief shows it; ⟨2026-11-08⟩ H3 an Instagram account that is not
    connected here is on IG-Hub: the note says so and who registers it (never «not connected»)."""
    from hq_api.domain import connections as CN

    out: dict[str, Any] = {"kind": c["kind"], "state": c["state"]}
    if c["kind"] == "instagram" and c["state"] != "connected":
        out["note"] = CN.ig_hub_note(company_code)
    return out


async def _company(tx: Tx, company_id: UUID) -> dict[str, Any]:
    conns = await tx.all(
        """SELECT kind, state FROM growth.connections WHERE company_id = :co ORDER BY kind""",
        co=company_id,
    )
    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :co", co=company_id)
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
        "connections": [connection_entry(dict(c), code) for c in conns],
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


async def _code_of(tx: Tx, company_id: UUID | None, role: str) -> str | None:
    if company_id is None:
        return None
    code: str | None = await tx.scalar(
        """SELECT code FROM core.employees WHERE company_id = :co AND role = :r AND status = 'active'
           ORDER BY created_at LIMIT 1""",
        co=company_id,
        r=role,
    )
    return code


async def _holding_row(tx: Tx) -> dict[str, Any] | None:
    row = await tx.first(
        "SELECT id, code FROM core.companies WHERE kind = 'holding' ORDER BY created_at LIMIT 1"
    )
    return dict(row) if row else None


async def technical(
    tx: Tx,
    company_id: UUID | None,
    *,
    role: str | None,
    tools: Collection[str],
    scope: str = "company",
) -> dict[str, Any]:
    """⟨1.20⟩ §38.2 what this role may do on servers and on the hub, and whom to ask otherwise:
    the same rule as server.map's «the servers the role may work on» (own company; every company
    for the holding's platform SRE and the overseer) and as hub.ops (hub_ops.is_technical)."""
    from hq_api.domain import hub_ops as HO

    holding = await _holding_row(tx)
    holding_id = holding["id"] if holding else None
    held = [t for t in SERVER_TOOLS if t in tools]
    servers: list[str] = []
    if held:
        from hq_api.domain import links as LKS

        wide = scope == "holding" and role in HOLDING_SERVER_ROLES
        # ⟨2026-11-08⟩ H1: a company's technical role (the TECH department's charters) reaches
        # the other companies' servers by the rule of linked.read: every active company while
        # the owner does not enforce links, else those sharing an `on` link
        technical = scope == "company" and role in await _tech_roles(tx)
        codes: list[str] = []
        if technical and not wide and company_id is not None:
            if not await LKS.enforced(tx):
                wide = True
            else:
                codes = [str(x["company"]) for x in await LKS.links_of(tx, company_id)]
        rows = await tx.all(
            """SELECT c.code, s.name FROM infra.servers s JOIN core.companies c ON c.id = s.company_id
               WHERE s.state IS NOT NULL AND s.state <> 'revoked'
                 AND (CAST(:wide AS boolean) OR s.company_id = CAST(:co AS uuid)
                      OR c.code = ANY(CAST(:codes AS text[])))
               ORDER BY (s.company_id = CAST(:co AS uuid)) DESC, c.code, s.name LIMIT :l""",
            wide=wide,
            co=str(company_id) if company_id else None,
            codes=codes,
            l=SERVERS_MAX,
        )
        servers = [f"{r['code']} · {r['name']}" for r in rows]
        if technical:
            out_reach = (
                "every company's servers while the owner does not enforce links; else those of "
                "a linked company or one present in your session (server.map lists them; a "
                "destructive command still waits for the owner's seal)"
            )
        else:
            out_reach = "your company's servers"
    who = Principal(kind="agent", code="-", role="employee", company_id=company_id,
                    charter=role, scope=scope)  # fmt: skip
    hub_ops = "hub.ops" in tools and HO.is_technical(who, holding_id=holding_id)
    out: dict[str, Any] = {"server_tools": held, "servers": servers, "hub_ops": hub_ops}
    if held:
        out["reach"] = out_reach
    if hub_ops:
        out["hub"] = (
            "hub.ops: the hub itself (status, logs, stats, restart, a profile, n8n, backup)"
        )
    if not held or not hub_ops:
        cto = await _code_of(tx, company_id, "cto") if company_id != holding_id else None
        aiops = await _code_of(tx, holding_id, "aiops_head")
        cto_s = cto or "your company's CEO (no CTO yet)"
        aiops_s = aiops or "the holding's AI operations (AIOPS)"
        if not held and not hub_ops:
            out["ask"] = (
                f"work.request to {cto_s} (servers of your company) or {aiops_s} (the hub): "
                "say exactly what to do"
            )
        elif not hub_ops:
            out["ask"] = f"the hub itself: work.request to {aiops_s}, saying exactly what to do"
        else:
            out["ask"] = f"a company's servers: work.request to that company's CTO, or {aiops_s}"
    return out


LEAN_HOW = ("owner", "hub", "delegate")  # what a watcher's run still needs of HOW


async def _narration(tx: Tx) -> dict[str, Any]:
    """⟨2026-11-10⟩ speech.make: whether Google AI Studio answered signed in the last time it was
    asked (signed_in · signed_out · unknown: nothing in the last days, try it)."""
    from hq_api.domain import speech_make as SM

    state = (await SM.speech_state(tx)).get("aistudio", "unknown")
    return {"state": state, "tool": "speech.make"}


async def _workshop(tx: Tx) -> dict[str, Any]:
    """⟨2026-11-09⟩ §43 the holding's workshop: ready (a paired holding server on a runner that
    sends files back, online now or not) or not set up yet."""
    from hq_api.domain.hands import RUNNER_MIN
    from hq_api.domain.workspace import version_ok

    rows = await tx.all(
        """SELECT s.state, s.runner_version FROM infra.servers s
           JOIN core.companies c ON c.id = s.company_id
           WHERE c.kind = 'holding' AND s.origin = 'attached' AND s.state IN ('online', 'offline')"""
    )
    if any(version_ok(r["runner_version"], RUNNER_MIN) for r in rows):
        return {"state": "ready", "tool": "workshop.run"}
    return {
        "state": "not set up yet",
        "note": "say so in one line and do the rest of the work; never say a tool is missing",
    }


async def brief(
    tx: Tx,
    company_id: UUID | None,
    *,
    n8n_up: bool,
    employee_code: str | None = None,
    role: str | None = None,
    tools: Collection[str] | None = None,
    scope: str | None = None,
    holding_map: bool = True,
    lean: bool = False,
) -> dict[str, Any]:
    """Every agent run and every talk persona. With the caller (`employee_code`, or its charter
    `role`, `tools` and `scope`) the brief gains `technical` (§38.2). ⟨2026-11-07⟩ W9 E:
    `holding_map=False` leaves the map of every company out (a consult-only persona's talk);
    `lean=True` is the brief of a run that is not work for a person (an ops alert, a watcher, a
    review, a digest): `technical`, who to hand things to, and nothing else."""
    if lean:
        out: dict[str, Any] = {"how": {k: HOW[k] for k in LEAN_HOW}}
    else:
        out = {
            "outside_players": await _safe(tx, _players) or [],
            "automations": {
                "engine": "the hub's rule engine",
                "n8n": "up" if n8n_up else "not set up",
            },
            "how": HOW,
            # ⟨2026-11-09⟩ §43 whether the workshop takes work now (never a reason to say «no tool»)
            "workshop": await _safe(tx, _workshop) or {"state": "not set up yet"},
        }
        # ⟨2026-11-10⟩ the narrator of content (speech.make): on. What the owner switched off
        # (2026-11-08) is his own voice talk with the app, which is never mentioned here.
        out["narration"] = await _safe(tx, _narration) or {
            "state": "unknown",
            "tool": "speech.make",
        }
        if company_id is not None:
            company = await _safe(tx, _company, company_id)
            if company is not None:
                out["your_company"] = company
    if employee_code is not None and role is None:
        row = await _safe(tx, _employee, employee_code)
        if row is not None:
            role, company_id = row["role"], row["company_id"]
    if role is not None:
        tech = await _safe(tx, _technical, company_id, role, tuple(tools or ()), scope or "company")
        if tech is not None:
            if lean and len(tech.get("servers") or []) > MAP_LIST_MAX:
                # a lean run (an alert, a watcher) names a few servers; server.map lists them all
                more = len(tech["servers"]) - MAP_LIST_MAX
                tech = {
                    **tech,
                    "servers": [*tech["servers"][:MAP_LIST_MAX], f"+{more} (server.map)"],
                }
            out["technical"] = tech
    if lean or not holding_map:
        return out
    # the map last: a trim from the end never reaches the reader's own parts
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


async def _employee(tx: Tx, code: str) -> dict[str, Any] | None:
    row = await tx.first("SELECT role, company_id FROM core.employees WHERE code = :c", c=code)
    return dict(row) if row else None


async def _technical(
    tx: Tx, company_id: UUID | None, role: str, tools: tuple[str, ...], scope: str
) -> dict[str, Any]:
    return await technical(tx, company_id, role=role, tools=tools, scope=scope)
