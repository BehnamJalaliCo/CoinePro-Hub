"""Connections: what can be measured and managed (contract §29.12 ⟨1.11⟩).

One row per company and kind (the ten kinds), its non-secret config only.
The secret lives in OpenBao alone (kv/hq/growth/<company>/<kind>, key
`secret`): the owner puts it in through the write-only API route (🔏
connection.secret) or `make growth-secret` in their own terminal; the hub
shows only `set` or `missing`, never the value.

The daily read (the worker, by code, no model) puts each connected kind's
figures into growth.metrics_daily (company, kind, day, key, subject, value,
source). Every outside call leaves through the egress service
(POST /v1/http on egress; the worker is on hq-egress-api), with the
credential as that one call's account (scrubbed from every answer) and its
entries in the egress log; nothing here opens a socket of its own.

  telegram        Bot API getChatMemberCount per channel -> followers (a bot
                  never sees a channel post's views: not read)
  pagespeed       PageSpeed Insights (mobile, lab): performance (0-100),
                  lcp_ms, cls per site (the company's checked sites, or the
                  config's urls); an API key is optional
  search_console  a service account's JWT (RS256) -> an OAuth2 token ->
                  searchanalytics by date: clicks, impressions, ctr, position
  ga4             the same token flow -> runReport by date: sessions, users,
                  conversions (key events)
  youtube         Data API v3 channels.statistics: followers, views, videos
  instagram       through IG-Hub's own runner: a fixed read-only `exec` job
                  whose command is the connection's config, its stdout JSON
                  parsed; the hub never holds an Instagram token
  x, trends, bing, play_console
                  state, guide and config only: «خواندن خودکار این اتصال هنوز
                  ساخته نشده» (no free API, or not built yet)

Besides the connections, the daily read stores the hub's own figures of each
company (kind `hub`): items published, the cost per published item, the
experiments closed (the content group's KPIs, §4.3).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote, urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel

from hq_api import events
from hq_api.db import Tx
from hq_api.domain import gate

log = logging.getLogger("hq_api.connections")

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
GUIDES_DIR = SEED_DIR / "connection_guides"
CHANNELS_FILE = SEED_DIR / "channels.yaml"

Kind = Literal[
    "search_console",
    "ga4",
    "instagram",
    "telegram",
    "youtube",
    "x",
    "pagespeed",
    "trends",
    "bing",
    "play_console",
    "google_ads",
    "meta_ads",
]
# The contract's order of work (§29.12): the order every list follows.
KINDS: tuple[str, ...] = (
    "search_console",
    "ga4",
    "instagram",
    "telegram",
    "youtube",
    "x",
    "pagespeed",
    "trends",
    "bing",
    "play_console",
    "google_ads",  # ⟨1.13⟩ §31.6
    "meta_ads",
)
PUBLISHING = ("instagram", "telegram", "youtube", "x")
LABEL_FA = {
    "search_console": "Google Search Console",
    "ga4": "Google Analytics",
    "instagram": "اینستاگرام (از راه IG-Hub)",
    "telegram": "کانال‌های تلگرام",
    "youtube": "یوتیوب",
    "x": "X",
    "pagespeed": "سرعت سایت (PageSpeed)",
    "trends": "روند جست‌وجو (Google Trends)",
    "bing": "Bing Webmaster",
    "play_console": "Google Play Console",
    "google_ads": "تبلیغات گوگل (Google Ads)",
    "meta_ads": "تبلیغات متا (Instagram و Facebook)",
}
# The secret a kind needs (True), may take (None: optional) or never takes (False).
SECRET: dict[str, bool | None] = {
    "search_console": True,
    "ga4": True,
    "instagram": False,
    "telegram": True,
    "youtube": True,
    "x": None,
    "pagespeed": None,
    "trends": False,
    "bing": True,
    "play_console": True,
    "google_ads": True,
    "meta_ads": True,
}
BUILT = ("search_console", "ga4", "instagram", "telegram", "youtube", "pagespeed", "google_ads",
         "meta_ads")  # fmt: skip
NOT_BUILT_FA = "خواندن خودکار این اتصال هنوز ساخته نشده"
ACTOR = "growth-read"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret
GOOGLE_SITE = "googleapis.com"
SC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GA_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DAILY_DAYS = 7  # what a connection shows of its figures
IG_JOB_TIMEOUT_S = 180
IG_JOB_STALE = timedelta(hours=6)
IG_KEYS = ("followers", "reach", "views", "impressions", "likes", "comments", "saves", "shares",
           "posts", "profile_views")  # fmt: skip
CHAT = r"^(@[A-Za-z0-9_]{4,64}|-?[0-9]{5,20})$"
# What a read-only command never does (§29.12: IG-Hub's job only reads): a
# program that changes files, processes, services or packages, sudo, or an
# output redirect other than onto /dev/null (besides the destructive
# categories of server_classify).
WRITERS = re.compile(
    r"(?:^|[;&|(`]|\$\()\s*(?:sudo|su|rm|mv|cp|dd|tee|chmod|chown|chgrp|ln|mkdir|rmdir|touch|"
    r"truncate|install|kill|pkill|killall|systemctl|service|docker|podman|reboot|shutdown|"
    r"poweroff|crontab|git|apt|apt-get|yum|dnf|pip|npm|curl|wget|scp|rsync|sed\s+-i)\b"
)
REDIRECT = re.compile(r"(?<![0-9&<>])>{1,2}(?!&)(?!\s*/dev/null)")


# ⟨2026-11-08⟩ H3 (the owner: «اکانت اینستاگرامم ثبت شده توی سرور IG-Hub، API رسمی متا دارم»):
# every company's Instagram account lives on IG-Hub (company IG's server, the `ig_hub` setting of
# seed/channels.yaml); the hub's own connection row only names the accounts and how they are read.
IG_HUB_OWNER_FA = "حساب روی {server} است؛ تیم فنی آن را به هاب معرفی میکند"


def ig_hub() -> dict[str, str]:
    """{company, server} of IG-Hub, from the `ig_hub` setting (default IG / IG-Hub)."""
    try:
        data = channels_file().get("ig_hub") or {}
    except OSError:
        data = {}
    return {
        "company": str(data.get("company") or "IG"),
        "server": str(data.get("server") or "IG-Hub"),
    }


def ig_hub_note(company_code: str | None = None) -> str:
    """What an agent reads when a company's Instagram connection is not connected: the account is
    on IG-Hub; who registers it here and how; publishing goes through IG-Hub's API."""
    hub = ig_hub()
    who = f"{company_code}'s" if company_code else "the company's"
    return (
        f"the Instagram account is on {hub['server']} (company {hub['company']}'s server, with "
        f"Meta's official API); it is NOT missing. {hub['company']}'s technical team (or {who} own "
        "technical role, under the linked rule) reads it there with server.map / server.read and "
        "registers it here with connection.set {kind: instagram, accounts: [handles], via: "
        f"ig_hub, server: {{company: {hub['company']}, name: {hub['server']}}}, read_command?}}; "
        f"publishing goes through {hub['server']}'s API (docs/server-prompts/IGHUB_PUBLISH_API.md) "
        "whose key the owner stores once. Never tell the owner Instagram is not connected."
    )


# ⟨2026-11-08⟩ the owner's decision: Instagram, for every company, is read and published through
# IG-Hub. The owner never reads an Instagram blocker, «وصل نیست» or a step of his own; a company
# whose accounts are not registered here yet gets the holding's technical work made by code.
IG_HUB_LINE_FA = "از راه {server} خوانده و منتشر میشود"
IG_HUB_TEAM_FA = (
    "اینستاگرام از راه {server} خوانده و منتشر میشود؛ تیم فنی حساب‌ها را به هاب معرفی میکند"
)
IG_SETUP_TITLE_FA = "ثبت حساب‌های اینستاگرام {company} روی هاب (از راه {server})"
IG_SETUP_PRIORITY = "P2"


def ig_hub_line(row: dict[str, Any] | None) -> str:
    """What the owner reads of a company's Instagram: through IG-Hub, with its accounts when they
    are registered, else the technical team's registration (never «not connected»)."""
    hub = ig_hub()
    cfg = (row or {}).get("config") or {}
    srv = cfg.get("server") if isinstance(cfg.get("server"), dict) else {}
    server = str((srv or {}).get("name") or hub["server"])
    accounts = [str(a) for a in cfg.get("accounts") or []] if row is not None else []
    if accounts and cfg.get("command"):
        return IG_HUB_LINE_FA.format(server=server) + f" ({len(accounts)} حساب)."
    return IG_HUB_TEAM_FA.format(server=server) + "."


def ig_setup_brief(company_code: str) -> str:
    hub = ig_hub()
    return (
        f"Register {company_code}'s Instagram accounts on the hub. Instagram, for every company, is "
        f"read and published through {hub['server']} (company {hub['company']}'s server, Meta's "
        f"official API); the accounts are there already. Steps: (1) server.map, then server.read / "
        f"server.exec (read-only) on {hub['company']}'s server {hub['server']} to find "
        f"{company_code}'s account handles and the read-only command that prints their daily "
        f"figures as JSON ({{accounts: [{{account, followers, reach, views}}]}}); (2) connection.set "
        f"{{company: {company_code}, kind: instagram, accounts: [handles], via: ig_hub, server: "
        f"{{company: {hub['company']}, name: {hub['server']}}}, read_command}}; (3) deliver one "
        f"Persian line: the accounts registered. When you can also find (or write there) the one "
        f"command that publishes a file on {hub['server']} and prints {{external_id, url}}, pass it "
        "in the same call as publish_command (the owner's «تأیید و انتشار» runs it through that "
        "server's own runner). Never ask the owner for anything here and never say Instagram is "
        "not connected: it is, through IG-Hub."
    )


IG_PUBLISH_TITLE_FA = "وصل کردن مسیر انتشار اینستاگرام {company} (از راه {server})"


def ig_publish_brief(company_code: str) -> str:
    """⟨2026-11-10⟩ §44.5 what the technical team registers so the owner's «تأیید و انتشار»
    publishes: the company's handles and the command IG-Hub's own runner runs."""
    hub = ig_hub()
    return (
        f"Connect {company_code}'s Instagram PUBLISHING on the hub. The owner tapped «تأیید و "
        f"انتشار» on a file in his session and nothing could go out. Instagram, for every company, "
        f"is published through {hub['server']} (company {hub['company']}'s server, Meta's official "
        f"API); the hub sends that server's own runner one `publish` job. Steps: (1) server.map, "
        f"then server.read / server.exec (read-only) on {hub['company']}'s server {hub['server']} "
        f"to find how it publishes a reel, a post and a story for {company_code}'s account(s). "
        "(2) Find, or write there in the application's own folder, ONE command that publishes "
        "what the job gives it and prints one JSON line. The job sets: HQ_PUBLISH_FILE_1 (the "
        "video or image, already downloaded), HQ_PUBLISH_FILE_2 (a reel's cover image, only "
        'when meta "cover" is true), HQ_PUBLISH_CAPTION_FILE (UTF-8 text), '
        'HQ_PUBLISH_META (JSON: {"channel": "instagram", "kind": "reel" | "post" | "story", '
        '"account": "<handle>", "company": "<code>", "cover": true | false}). It must print '
        '{"external_id": "<id>", '
        '"url": "<permalink or null>"} and exit 0, or exit non-zero with one plain line of why. '
        "It never deletes, edits or messages anyone. Try it once with a dry run if the "
        "application has one; never publish a test post. What is known of IG-Hub's own "
        "application (its repository, read 2026-11-10; check it on the server): it has a "
        "publishing API for other servers, `docs/API_PUBLISH.md`: a key made in its panel "
        "(Settings, API keys), `POST /api/v1/media` (multipart `file`) then `POST "
        "/api/v1/publish {account, kind, items: [{media_id}], caption}` and `GET "
        "/api/v1/publish/{id}` until `status` is `published` (its `permalink` is the url, "
        "`media_ig_id` the external id) or `failed` (its `error` is the plain line). The hub's "
        "`post` is that API's `image`; `reel` and `story` are the same. It publishes JPEG "
        "pictures only: convert a PNG or WebP picture to JPEG before the upload. Its reel has "
        "no cover field yet: publish the reel without HQ_PUBLISH_FILE_2 and never fail for it. "
        "The key stays in a file of that server readable only by the application's user. "
        f"(3) connection.set {{company: "
        f"{company_code}, kind: instagram, accounts: [handles], via: ig_hub, server: {{company: "
        f"{hub['company']}, name: {hub['server']}}}, publish_command}} (no token ever goes in the "
        "command: the application's own configuration on the server holds it). (4) deliver one "
        "Persian line: «مسیر انتشار وصل شد؛ «تأیید و انتشار» را دوباره بزنید». Never ask the owner "
        "for anything here and never say Instagram is not connected."
    )


async def ensure_ig_publish_work(
    tx: Tx, company_id: UUID, *, requested_by: UUID | None = None
) -> str | None:
    """⟨2026-11-10⟩ §44.5 A company whose publish command is not registered gets the technical
    work made by code, once (one open work per company), under the order's work when
    `requested_by` names one (the session sees the step; its holder is woken when it is
    delivered). The work's ref, or None when nobody can take it."""
    from hq_api.domain import work as W
    from hq_api.principal import Principal

    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :c", c=company_id)
    found: str | None = await tx.scalar(
        """SELECT ref FROM work.work WHERE run_meta ->> 'ig_publish' = :code
             AND status <> ALL(CAST(:closed AS text[])) ORDER BY created_at LIMIT 1""",
        code=code,
        closed=list(W.CLOSED),
    )
    if found is not None:
        return found
    co = await tx.first("SELECT code, name_fa FROM core.companies WHERE id = :c", c=company_id)
    who = await ig_setup_assignee(tx)
    if co is None or who is None:
        return None
    hub = ig_hub()
    w = await W.create(
        tx,
        Principal(kind="service", code="connections", role="service"),
        company_id=who["company_id"],
        company_code=str(who["company"]),
        title=IG_PUBLISH_TITLE_FA.format(company=co["name_fa"] or co["code"], server=hub["server"]),
        brief=ig_publish_brief(str(co["code"])),
        kind="one_off",
        priority="P1",
        assignee_code=str(who["code"]),
        requested_by_work_id=requested_by,
    )
    await tx.exec(
        """UPDATE work.work SET run_meta = COALESCE(run_meta, '{}'::jsonb) || CAST(:m AS jsonb)
           WHERE id = :id""",
        id=w["id"],
        m=json.dumps({"ig_publish": co["code"]}),
    )
    return str(w["ref"])


async def ig_setup_assignee(tx: Tx) -> dict[str, Any] | None:
    """Who registers a company's Instagram here: IG-Hub's company's CTO (the TECH department's
    manager), else the holding's AIOPS manager; None when neither seat is filled."""
    hub = ig_hub()
    sql = """SELECT e.code, e.company_id, c.code AS company FROM core.employees e
             JOIN core.companies c ON c.id = e.company_id
             JOIN core.departments d ON d.id = e.department_id
             WHERE e.status = 'active' AND e.kind = 'manager' AND d.code = :dept AND {where}
             ORDER BY e.created_at LIMIT 1"""
    row = await tx.first(sql.format(where="c.code = :c"), dept="TECH", c=hub["company"])
    if row is None:
        row = await tx.first(sql.format(where="c.kind = 'holding'"), dept="AIOPS")
    return dict(row) if row is not None else None


async def ig_setup_work(tx: Tx, company_id: UUID) -> str | None:
    """The open technical work that registers this company's Instagram here, or None."""
    from hq_api.domain import work as W

    code = await tx.scalar("SELECT code FROM core.companies WHERE id = :c", c=company_id)
    ref: str | None = await tx.scalar(
        """SELECT ref FROM work.work WHERE run_meta ->> 'ig_setup' = :code
             AND status <> ALL(CAST(:closed AS text[])) ORDER BY created_at LIMIT 1""",
        code=code,
        closed=list(W.CLOSED),
    )
    return ref


async def ensure_ig_setup_work(
    tx: Tx, company_id: UUID, *, requested_by: UUID | None = None
) -> str | None:
    """The owner, 2026-11-08: a company whose Instagram accounts are not registered on the hub
    gets the technical work made by code, once (one open work per company): IG-Hub's CTO (else
    the holding's AIOPS) reads the accounts on IG-Hub (`server.*` by the linked rule, H1) and
    registers them with `connection.set` (H2). Under an order's work when `requested_by` names
    one, so the session sees the step and the holder is woken when it is delivered. The work's
    ref, or None when nobody can take it."""
    from hq_api.domain import work as W
    from hq_api.principal import Principal

    found = await ig_setup_work(tx, company_id)
    if found is not None:
        return found
    co = await tx.first("SELECT code, name_fa FROM core.companies WHERE id = :c", c=company_id)
    who = await ig_setup_assignee(tx)
    if co is None or who is None:
        return None
    hub = ig_hub()
    w = await W.create(
        tx,
        Principal(kind="service", code="connections", role="service"),
        company_id=who["company_id"],
        company_code=str(who["company"]),
        title=IG_SETUP_TITLE_FA.format(company=co["name_fa"] or co["code"], server=hub["server"]),
        brief=ig_setup_brief(str(co["code"])),
        kind="one_off",
        priority=IG_SETUP_PRIORITY,
        assignee_code=str(who["code"]),
        requested_by_work_id=requested_by,
    )
    await tx.exec(
        """UPDATE work.work SET run_meta = COALESCE(run_meta, '{}'::jsonb) || CAST(:m AS jsonb)
           WHERE id = :id""",
        id=w["id"],
        m=json.dumps({"ig_setup": co["code"]}),
    )
    return str(w["ref"])


# ⟨2026-11-08⟩ H2 connection.set: what an agent may write of a connection (never a secret)
SECRET_WORDS = re.compile(
    r"(secret|token|password|passwd|api[_-]?key|private[_-]?key|bearer)", re.I
)
TOKEN_LIKE = re.compile(r"^[A-Za-z0-9+/=_\-]{32,}$")
SET_FIELDS = ("accounts", "via", "server", "read_command", "publish_command", "channels",
              "site_url", "channel_id", "handle", "property_id")  # fmt: skip
COMMAND_FIELDS = ("read_command", "publish_command")
DESTRUCTIVE_FA = (
    "این دستور میتواند به سرور آسیب بزند؛ دستور انتشار فقط فایل و کپشن را میگیرد و منتشر میکند."
)
NOT_READ_ONLY_FA = (
    "این دستور فقط‌خواندنی نیست؛ روی سرور فقط دستوری اجرا میشود که چیزی را تغییر ندهد."
)
NO_SECRET_FA = (
    "رمز، توکن یا کلید از اینجا ثبت نمیشود؛ رمز اتصال را مالک با فرمان ترمینال خودش میدهد."  # noqa: S105 - a sentence, not a secret
)


def looks_secret(value: Any) -> bool:
    s = str(value or "")
    return bool(SECRET_WORDS.search(s)) or bool(TOKEN_LIKE.match(s.strip()))


def agent_config(kind: str, current: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """⟨2026-11-08⟩ H2: the connection's config after an agent's `connection.set`: the public,
    non-secret settings merged over what is there (handles as linked.handles accepts them, a
    read-only command, public channels, a site's public address); anything secret-looking, an
    unknown field or a command that could change the server is refused with the field named."""
    from hq_api.domain import linked as LD
    from hq_api.errors import ApiError

    out = dict(current or {})
    bad: dict[str, str] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key not in SET_FIELDS:
            bad[key] = "not a field an agent sets"
            continue
        flat = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        if SECRET_WORDS.search(key) or (looks_secret(flat) and key not in COMMAND_FIELDS):
            raise ApiError(422, "validation_failed", fields={key: "a secret never goes here"},
                           message_fa=NO_SECRET_FA)  # fmt: skip
        if key == "accounts":
            handles = [LD._handle(a) for a in (value if isinstance(value, list) else [value])]
            if not handles or any(h is None for h in handles):
                bad[key] = "handles like @name (2-64 letters, digits, . _ -)"
                continue
            out["accounts"] = [str(h).lstrip("@") for h in handles]
        elif key == "via":
            if value != "ig_hub":
                bad[key] = "ig_hub"
                continue
            out["via"] = "ig_hub"
        elif key == "server":
            srv = value if isinstance(value, dict) else {}
            co, name = LD._handle(srv.get("company")), LD._handle(srv.get("name"))
            if not co or not name:
                bad[key] = "{company, name}"
                continue
            out["server"] = {"company": co, "name": name}
        elif key == "read_command":
            cmd = str(value).strip()
            if looks_secret(cmd) or not read_only(cmd):
                raise ApiError(422, "validation_failed", fields={key: "a read-only command"},
                               message_fa=NOT_READ_ONLY_FA)  # fmt: skip
            out["command"] = cmd[:500]
        elif key == "publish_command":
            # ⟨2026-11-10⟩ §44.5 the command the server's runner runs to publish a file (§26.1b:
            # HQ_PUBLISH_FILE_1, HQ_PUBLISH_CAPTION_FILE, HQ_PUBLISH_META; it prints
            # {"external_id", "url"}). Never a secret, never a command the hub's own classifier
            # calls destructive.
            from hq_api.domain import server_classify

            cmd = str(value).strip()
            if not cmd or looks_secret(cmd):
                raise ApiError(422, "validation_failed", fields={key: "a command, never a secret"},
                               message_fa=NO_SECRET_FA)  # fmt: skip
            if server_classify.classify(cmd) is not None:
                raise ApiError(422, "validation_failed", fields={key: "not a destructive command"},
                               message_fa=DESTRUCTIVE_FA)  # fmt: skip
            out["publish_command"] = cmd[:500]
        elif key == "channels":
            chans = []
            for c in value if isinstance(value, list) else []:
                if not isinstance(c, dict) or not re.match(CHAT, str(c.get("chat") or "")):
                    bad[key] = "[{chat: @name | id, title_fa?, role?}]"
                    break
                chans.append({k: str(v)[:120] for k, v in c.items()
                              if k in ("chat", "title_fa", "role") and v is not None})  # fmt: skip
            else:
                if chans:
                    out["channels"] = chans
                    continue
                bad[key] = "[{chat: @name | id, title_fa?, role?}]"
        elif key == "site_url":
            url = LD._public_url(value)
            if not url:
                bad[key] = "a public https address without credentials or a query"
                continue
            out["site_url"] = url
        else:  # channel_id, handle, property_id
            h = LD._handle(value)
            if not h:
                bad[key] = "letters, digits, . _ - (2-64)"
                continue
            out[key] = h
    if bad:
        raise ApiError(422, "validation_failed", fields=bad,
                       message_fa="یکی از مقدارها درست نیست: " + "، ".join(bad))  # fmt: skip
    if kind != "instagram":
        out.pop("via", None)
        out.pop("server", None)
    return out


def read_only(cmd: str) -> bool:
    """A command the hub may run on IG-Hub for the daily read."""
    from hq_api.domain.server_classify import classify_detail

    text = cmd.strip()
    return (
        bool(text)
        and classify_detail(text) is None
        and not WRITERS.search(text)
        and not (REDIRECT.search(text))
    )


# ------------------------------------------------------------------ shapes --
class Daily(BaseModel):
    day: date
    key: str
    value: float
    subject: str = ""  # ⟨additive⟩ which channel, site or account


class Connection(BaseModel):
    company: str
    kind: Kind
    label_fa: str
    state: Literal["not_connected", "connected", "error"]
    config: dict[str, Any]
    secret: Literal["set", "missing"]
    last_read_at: datetime | None
    last_error_fa: str | None
    daily: list[Daily]
    # ⟨additive⟩ what is still missing (plain Persian), whether the hub reads it by itself
    missing_fa: list[str] = []
    reader: bool = True
    secret_needed: bool | None = None


class Guide(BaseModel):
    kind: Kind
    title_fa: str
    body_md: str


# -------------------------------------------------------------- the rules --
def _chats(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in config.get("channels") or [] if isinstance(c, dict) and c.get("chat")]


def missing(kind: str, config: dict[str, Any], secret_set: bool) -> list[str]:
    """What the connection still needs before it can be read, in Persian."""
    need: list[str] = []
    if kind == "search_console" and not config.get("site_url"):
        need.append("نشانی سایت در Search Console")
    elif kind == "ga4" and not str(config.get("property_id") or "").isdigit():
        need.append("شماره‌ی ویژگی Analytics")
    elif kind == "instagram":
        if config.get("via") == "ig_hub" and not (config.get("accounts") and config.get("command")):
            # ⟨2026-11-08⟩ H3: the account exists on IG-Hub; registering it here is the technical
            # team's step (connection.set), never the owner's
            srv = (config.get("server") or {}) if isinstance(config.get("server"), dict) else {}
            need.append(IG_HUB_OWNER_FA.format(server=srv.get("name") or ig_hub()["server"]))
        else:
            if not config.get("accounts"):
                need.append("نام حساب‌های اینستاگرام")
            if not config.get("command"):
                need.append("دستور فقط‌خواندنی خواندن عددها روی IG-Hub")
    elif kind == "telegram" and not _chats(config):
        need.append("نشانی کانال‌ها")
    elif kind == "youtube" and not config.get("channel_id"):
        need.append("شناسه‌ی کانال یوتیوب")
    elif kind == "google_ads" and len(str(config.get("customer_id") or "").replace("-", "")) != 10:
        need.append("شماره‌ی ۱۰ رقمی حساب Google Ads")
    elif (
        kind == "meta_ads"
        and not str(config.get("account_id") or "").removeprefix("act_").isdigit()
    ):
        need.append("شماره‌ی حساب تبلیغاتی Meta")
    if SECRET.get(kind) is True and not secret_set:
        need.append("رمز اتصال")
    return need


def state_of(kind: str, row: dict[str, Any] | None) -> str:
    if row is None:
        return "not_connected"
    if missing(kind, row.get("config") or {}, bool(row.get("secret_set"))):
        return "not_connected"
    return "error" if row.get("last_error_fa") else "connected"


def widens(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """A config reads more than before (a new key, a new list item, a changed
    value): the owner's step-up `connection.config`. Removing never widens."""

    def items(v: Any, path: str = "") -> set[str]:
        if isinstance(v, dict):
            out: set[str] = set()
            for k, x in v.items():
                out |= items(x, f"{path}/{k}")
            return out
        if isinstance(v, list):
            out = set()
            for x in v:
                out |= items(x, f"{path}[]")
            return out
        return {f"{path}={json.dumps(v, sort_keys=True, ensure_ascii=False)}"}

    return bool(items(new) - items(old))


def render(
    company: str, kind: str, row: dict[str, Any] | None, daily: list[dict[str, Any]]
) -> Connection:
    cfg = dict((row or {}).get("config") or {})
    secret_set = bool((row or {}).get("secret_set"))
    return Connection(
        company=company,
        kind=kind,
        label_fa=(row or {}).get("label_fa") or LABEL_FA[kind],
        state=state_of(kind, row),
        config=cfg,
        secret="set" if secret_set else "missing",
        last_read_at=(row or {}).get("last_read_at"),
        last_error_fa=(row or {}).get("last_error_fa"),
        daily=[
            Daily(day=d["day"], key=d["key"], value=float(d["value"]), subject=d["subject"])
            for d in daily
        ],
        missing_fa=missing(kind, cfg, secret_set),
        reader=kind in BUILT,
        secret_needed=SECRET.get(kind),
    )


async def rows_of(tx: Tx, company_id: UUID) -> dict[str, dict[str, Any]]:
    found = await tx.all("SELECT * FROM growth.connections WHERE company_id = :co", co=company_id)
    return {r["kind"]: r for r in found}


async def daily_of(
    tx: Tx, company_id: UUID, kind: str | None = None, days: int = DAILY_DAYS
) -> dict[str, list[dict[str, Any]]]:
    found = await tx.all(
        """SELECT kind, day, key, subject, value FROM growth.metrics_daily
           WHERE company_id = :co AND (CAST(:k AS text) IS NULL OR kind = :k)
             AND day > current_date - CAST(:days AS int)
           ORDER BY kind, day, key, subject""",
        co=company_id,
        k=kind,
        days=days,
    )
    out: dict[str, list[dict[str, Any]]] = {}
    for r in found:
        out.setdefault(r["kind"], []).append(r)
    return out


async def list_for(tx: Tx, company: Any, days: int = DAILY_DAYS) -> list[Connection]:
    """Every kind of the company (a kind without a row reads not_connected)."""
    have = await rows_of(tx, company.id)
    daily = await daily_of(tx, company.id, days=days)
    return [render(company.code, k, have.get(k), daily.get(k, [])) for k in KINDS]


async def one_for(tx: Tx, company: Any, kind: str) -> Connection:
    row = await tx.first(
        "SELECT * FROM growth.connections WHERE company_id = :co AND kind = :k",
        co=company.id,
        k=kind,
    )
    daily = await daily_of(tx, company.id, kind)
    return render(company.code, kind, row, daily.get(kind, []))


def guide(kind: str) -> Guide:
    path = GUIDES_DIR / f"{kind}.md"
    text = path.read_text(encoding="utf-8")
    first = text.splitlines()[0].lstrip("# ").strip() if text else LABEL_FA[kind]
    return Guide(kind=kind, title_fa=first, body_md=text)


# -------------------------------------------------------------------- seed --
def channels_file(path: Path | None = None) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((path or CHANNELS_FILE).read_text(encoding="utf-8")) or {}
    return data


async def seed(tx: Tx, path: Path | None = None) -> int:
    """seed/channels.yaml: each company's publishing channels as connections
    (only added, never overwritten; a code not in the database is skipped)."""
    data = channels_file(path)
    ig_hub = data.get("ig_hub") or {"company": "IG", "server": "IG-Hub"}
    added = 0
    for ch in data.get("channels") or []:
        kind = str(ch.get("kind") or "")
        if kind not in KINDS:
            continue
        co = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=ch.get("company"))
        if co is None:
            continue
        cfg = dict(ch.get("config") or {})
        if kind == "instagram" and cfg.get("via") == "ig_hub":
            cfg.setdefault(
                "server", {"company": ig_hub.get("company"), "name": ig_hub.get("server")}
            )
        made = await tx.scalar(
            """INSERT INTO growth.connections (company_id, kind, label_fa, config, origin)
               VALUES (:co, :k, :l, CAST(:c AS jsonb), 'seed')
               ON CONFLICT (company_id, kind) DO NOTHING RETURNING id""",
            co=co,
            k=kind,
            l=str(ch.get("label_fa") or LABEL_FA[kind])[:200],
            c=json.dumps(cfg, ensure_ascii=False),
        )
        added += 1 if made else 0
    return added


# ----------------------------------------------------------------- secrets --
def secret_path(company: str, kind: str) -> str:
    """kv/hq/growth/<company>/<kind> (the client adds the mount)."""
    return f"hq/growth/{company}/{kind}"


async def read_secret(bao: Any, company: str, kind: str) -> str | None:
    if bao is None:
        return None
    from hq_common.openbao import OpenBaoError

    try:
        data = await bao.read_kv(secret_path(company, kind))
    except OpenBaoError:
        return None
    value = data.get("secret") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


async def write_secret(bao: Any, company: str, kind: str, value: str) -> None:
    await bao.write_kv(secret_path(company, kind), {"secret": value})


# -------------------------------------------------------------- the egress --
@dataclass
class Answer:
    outcome: str
    status: int | None = None
    body: str = ""
    code: str | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            return None


class Http(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        company: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        json_body: Any = None,
        account: dict[str, Any] | None = None,
    ) -> Answer: ...


class EgressHttp:
    """POST /v1/http on egress: the hub's only way out for these reads."""

    def __init__(self, base_url: str, timeout_s: float = 90.0, cls: str = "A0") -> None:
        self.url = base_url.rstrip("/") + "/v1/http"
        self.timeout_s = timeout_s
        self.cls = cls  # A0 for the daily reads; A2 for a reversible change (an ad paused)

    async def request(
        self,
        method: str,
        url: str,
        *,
        company: str,
        headers: dict[str, str] | None = None,
        body: str | None = None,
        json_body: Any = None,
        account: dict[str, Any] | None = None,
    ) -> Answer:
        payload: dict[str, Any] = {
            "ctx": {"company": company, "actor": ACTOR, "cls": self.cls},
            "method": method,
            "url": url,
            "headers": headers or {},
            "max_chars": 200_000,
        }
        if json_body is not None:
            payload["json_body"] = json_body
        elif body is not None:
            payload["body"] = body
        if account is not None:
            payload["account"] = account
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as http:
                resp = await http.post(self.url, json=payload)
            out = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("egress call failed", extra={"error": type(exc).__name__})
            return Answer("error", code="egress_unavailable")
        if not isinstance(out, dict):
            return Answer("error", code="egress_unavailable")
        data: dict[str, Any] = out["data"] if isinstance(out.get("data"), dict) else {}
        return Answer(
            outcome=str(out.get("outcome") or "error"),
            status=data.get("status") if isinstance(data.get("status"), int) else None,
            body=str(data.get("body") or ""),
            code=out.get("code"),
            entries=[e for e in out.get("entries") or [] if isinstance(e, dict)],
        )


OVERRIDE: Http | None = None  # tests put a fake egress here


def http_for(hub: Any, cls: str = "A0") -> Http:
    return OVERRIDE or EgressHttp(hub.settings.support_egress_url, cls=cls)


class ReadError(Exception):
    """A read that failed, with the owner's plain Persian reason."""

    def __init__(self, reason_fa: str) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa


@dataclass
class Figure:
    day: date
    key: str
    value: float
    subject: str = ""
    source: str = ""


@dataclass
class ReadCtx:
    hub: Any
    tx_factory: Any
    company_id: UUID
    company: str
    kind: str
    config: dict[str, Any]
    secret: str | None
    today: date
    http: Http
    entries: list[dict[str, Any]] = field(default_factory=list)
    pending: dict[str, Any] | None = None  # set by a reader whose result comes later
    clear_pending: bool = False

    async def call(self, method: str, url: str, **kw: Any) -> Answer:
        ans = await self.http.request(method, url, company=self.company, **kw)
        self.entries.extend(ans.entries)
        if ans.outcome != "ok":
            raise ReadError(_egress_reason(ans))
        return ans


def _egress_reason(ans: Answer) -> str:
    if ans.code in ("egress_unavailable", "call_timeout", "egress_failed"):
        return "راه بیرون هاب پاسخ نداد؛ فردا دوباره خوانده میشود."
    return "راه بیرون هاب این درخواست را نپذیرفت؛ نشانی یا تنظیم اتصال را ببینید."


def _http_reason(status: int | None, who: str) -> str:
    if status in (401, 403):
        return f"{who} اجازه‌ی خواندن نداد؛ دسترسی را طبق راهنما دوباره بدهید."
    if status == 404:
        return f"{who} این نشانی یا شناسه را نشناخت؛ تنظیم اتصال را ببینید."
    if status == 429:
        return f"سهمیه‌ی روزانه‌ی {who} پر شده است؛ فردا دوباره خوانده میشود."
    return f"{who} پاسخ درستی نداد؛ فردا دوباره خوانده میشود."


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------- google token --
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def service_account(secret: str | None) -> dict[str, Any]:
    try:
        sa = json.loads(secret or "")
    except ValueError:
        sa = None
    if not isinstance(sa, dict) or not sa.get("client_email") or not sa.get("private_key"):
        raise ReadError("متن حساب سرویس گوگل درست نیست؛ کل فایل JSON را دوباره بچسبانید.")
    return sa


def signed_assertion(sa: dict[str, Any], scope: str, now: float | None = None) -> str:
    """The OAuth2 JWT bearer assertion of a Google service account (RS256)."""
    t = int(time.time() if now is None else now)
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"],
        "scope": scope,
        "aud": TOKEN_URI,
        "iat": t,
        "exp": t + 3600,
    }
    signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    try:
        key = serialization.load_pem_private_key(str(sa["private_key"]).encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise ReadError(
            "کلید حساب سرویس گوگل خوانده نشد؛ کل فایل JSON را دوباره بچسبانید."
        ) from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ReadError("کلید حساب سرویس گوگل از نوع درست نیست.")
    sig = key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing}.{_b64(sig)}"


async def google_token(ctx: ReadCtx, scope: str) -> str:
    sa = service_account(ctx.secret)
    form = urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_assertion(sa, scope),
        }
    )
    ans = await ctx.call(
        "POST",
        TOKEN_URI,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=form,
    )
    data = ans.json()
    token = data.get("access_token") if isinstance(data, dict) else None
    if ans.status != 200 or not isinstance(token, str) or not token:
        raise ReadError(_http_reason(ans.status if ans.status != 400 else 401, "گوگل"))
    return token


def bearer(token: str) -> dict[str, Any]:
    return {"key": "growth-google", "site": GOOGLE_SITE, "secret": token,
            "inject": {"kind": "bearer"}}  # fmt: skip


def api_key(key: str) -> dict[str, Any]:
    return {"key": "growth-google-key", "site": GOOGLE_SITE, "secret": key,
            "inject": {"kind": "header", "name": "X-goog-api-key"}}  # fmt: skip


# ----------------------------------------------------------------- readers --
async def read_telegram(ctx: ReadCtx) -> list[Figure]:
    """Each channel's member count (Bot API getChatMemberCount). A bot is
    never told a channel post's views, so none are read."""
    token = ctx.secret or ""
    acct = {"key": "growth-telegram", "site": "api.telegram.org", "secret": token,
            "inject": {"kind": "header", "name": "X-Hub-Unused"}}  # fmt: skip
    out: list[Figure] = []
    failed: list[str] = []
    for ch in _chats(ctx.config):
        chat = str(ch["chat"])
        url = f"https://api.telegram.org/bot{token}/getChatMemberCount?" + urlencode(
            {"chat_id": chat}
        )
        ans = await ctx.call("GET", url, account=acct)
        data = ans.json()
        if ans.status == 401:
            raise ReadError("تلگرام توکن ربات را نپذیرفت؛ توکن تازه را در اپ بگذارید.")
        n = data.get("result") if isinstance(data, dict) and data.get("ok") else None
        if not isinstance(n, int):
            failed.append(str(ch.get("title_fa") or chat))
            continue
        out.append(Figure(ctx.today, "followers", float(n), chat, "telegram"))
    if failed and not out:
        raise ReadError(
            "ربات به کانال‌ها دسترسی ندارد؛ ربات را مدیر کانال کنید: " + "، ".join(failed[:3])
        )
    return out


async def _sites(ctx: ReadCtx) -> list[str]:
    urls = [str(u) for u in ctx.config.get("urls") or [] if str(u).startswith("https://")]
    if urls:
        return urls[:5]
    async with ctx.tx_factory() as tx:
        found = await tx.all(
            """SELECT url FROM ops.sites WHERE company_id = :co AND kind = 'web' AND enabled
                 AND NOT canary ORDER BY created_at LIMIT 5""",
            co=ctx.company_id,
        )
    return [r["url"] for r in found]


PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_FIELDS = (
    "lighthouseResult/categories/performance/score,"
    "lighthouseResult/audits/largest-contentful-paint/numericValue,"
    "lighthouseResult/audits/cumulative-layout-shift/numericValue"
)


async def read_pagespeed(ctx: ReadCtx) -> list[Figure]:
    sites = await _sites(ctx)
    if not sites:
        raise ReadError("سایتی برای سنجش ثبت نشده است؛ نشانی سایت را در اپ بنویسید.")
    acct = api_key(ctx.secret) if ctx.secret else None
    out: list[Figure] = []
    for url in sites:
        q = urlencode({"url": url, "strategy": "mobile", "category": "performance",
                       "fields": PSI_FIELDS})  # fmt: skip
        ans = await ctx.call("GET", f"{PSI}?{q}", account=acct)
        data = ans.json()
        if ans.status != 200 or not isinstance(data, dict):
            raise ReadError(_http_reason(ans.status, "PageSpeed"))
        lh = data.get("lighthouseResult") or {}
        score = _num(((lh.get("categories") or {}).get("performance") or {}).get("score"))
        audits = lh.get("audits") or {}
        lcp = _num((audits.get("largest-contentful-paint") or {}).get("numericValue"))
        cls = _num((audits.get("cumulative-layout-shift") or {}).get("numericValue"))
        if score is not None:
            out.append(Figure(ctx.today, "performance", round(score * 100, 1), url, "pagespeed"))
        if lcp is not None:
            out.append(Figure(ctx.today, "lcp_ms", round(lcp), url, "pagespeed"))
        if cls is not None:
            out.append(Figure(ctx.today, "cls", round(cls, 4), url, "pagespeed"))
    return out


SC_QUERY = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"


async def read_search_console(ctx: ReadCtx) -> list[Figure]:
    """The last week by date (Search Console's figures arrive a few days late)."""
    token = await google_token(ctx, SC_SCOPE)
    site = str(ctx.config["site_url"])
    body = {
        "startDate": (ctx.today - timedelta(days=8)).isoformat(),
        "endDate": (ctx.today - timedelta(days=1)).isoformat(),
        "dimensions": ["date"],
        "rowLimit": 31,
    }
    ans = await ctx.call(
        "POST", SC_QUERY.format(site=quote(site, safe="")), json_body=body, account=bearer(token)
    )
    data = ans.json()
    if ans.status != 200 or not isinstance(data, dict):
        raise ReadError(_http_reason(ans.status, "Search Console"))
    out: list[Figure] = []
    for row in data.get("rows") or []:
        try:
            day = date.fromisoformat(str((row.get("keys") or [""])[0]))
        except ValueError:
            continue
        for key in ("clicks", "impressions", "ctr", "position"):
            v = _num(row.get(key))
            if v is not None:
                if key == "ctr":
                    v = round(v * 100, 2)  # a percentage
                out.append(Figure(day, key, v, site, "search_console"))
    return out


GA_REPORT = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
GA_METRICS = (("sessions", "sessions"), ("totalUsers", "users"), ("keyEvents", "conversions"))


async def read_ga4(ctx: ReadCtx) -> list[Figure]:
    token = await google_token(ctx, GA_SCOPE)
    pid = str(ctx.config["property_id"])
    body = {
        "dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}],
        "dimensions": [{"name": "date"}],
        "metrics": [{"name": m} for m, _ in GA_METRICS],
    }
    ans = await ctx.call(
        "POST", GA_REPORT.format(pid=quote(pid, safe="")), json_body=body, account=bearer(token)
    )
    data = ans.json()
    if ans.status != 200 or not isinstance(data, dict):
        raise ReadError(_http_reason(ans.status, "Analytics"))
    out: list[Figure] = []
    for row in data.get("rows") or []:
        raw = str(((row.get("dimensionValues") or [{}])[0]).get("value") or "")
        try:
            day = datetime.strptime(raw, "%Y%m%d").date()
        except ValueError:
            continue
        values = row.get("metricValues") or []
        for i, (_, key) in enumerate(GA_METRICS):
            v = _num((values[i] if i < len(values) else {}).get("value"))
            if v is not None:
                out.append(Figure(day, key, v, pid, "ga4"))
    return out


YT = "https://www.googleapis.com/youtube/v3/channels"


async def read_youtube(ctx: ReadCtx) -> list[Figure]:
    cid = str(ctx.config["channel_id"])
    q = urlencode({"part": "statistics", "id": cid})
    ans = await ctx.call("GET", f"{YT}?{q}", account=api_key(ctx.secret or ""))
    data = ans.json()
    if ans.status != 200 or not isinstance(data, dict):
        raise ReadError(_http_reason(ans.status, "یوتیوب"))
    items = data.get("items") or []
    if not items:
        raise ReadError("یوتیوب این شناسه‌ی کانال را نشناخت؛ تنظیم اتصال را ببینید.")
    st = items[0].get("statistics") or {}
    out = []
    for src, key in (("subscriberCount", "followers"), ("viewCount", "views"),
                     ("videoCount", "videos")):  # fmt: skip
        v = _num(st.get(src))
        if v is not None:
            out.append(Figure(ctx.today, key, v, cid, "youtube"))
    return out


def parse_ig(text: str, accounts: list[str], today: date) -> list[Figure]:
    """IG-Hub's read-only command prints JSON: {day?, accounts: [{account,
    followers, reach, views, ...}]} or the list alone. Only this company's
    accounts, only the known keys, numbers only."""
    raw = text.strip()
    start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0), default=-1)
    try:
        data = json.loads(raw[start:]) if start >= 0 else None
    except ValueError:
        data = None
    if isinstance(data, list):
        data = {"accounts": data}
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise ReadError("خروجی دستور خواندن روی IG-Hub قابل خواندن نبود؛ دستور را ببینید.")
    try:
        day = date.fromisoformat(str(data.get("day"))) if data.get("day") else today
    except ValueError:
        day = today
    want = {a.lstrip("@").lower() for a in accounts}
    out: list[Figure] = []
    for a in data["accounts"]:
        if not isinstance(a, dict):
            continue
        name = str(a.get("account") or a.get("username") or "").lstrip("@").lower()
        if not name or (want and name not in want):
            continue
        for key in IG_KEYS:
            v = _num(a.get(key))
            if v is not None:
                out.append(Figure(day, key, v, name, "instagram"))
    return out


async def read_instagram(ctx: ReadCtx) -> list[Figure]:
    """Through IG-Hub's runner: queue the fixed read-only command once a day,
    collect its stdout when it is done (the next tick)."""
    from hq_api.domain import servers as SV

    cmd = str(ctx.config["command"])
    if not read_only(cmd):
        raise ReadError("دستور خواندن IG-Hub فقط‌خواندنی نیست؛ هاب آن را اجرا نمیکند.")
    srv_cfg = ctx.config.get("server") or {}
    srv_company, srv_name = srv_cfg.get("company") or "IG", srv_cfg.get("name") or "IG-Hub"
    accounts = [str(a) for a in ctx.config.get("accounts") or []]
    async with ctx.tx_factory() as tx:
        pend = ctx.pending or {}
        job = None
        if pend.get("job_id"):
            job = await tx.first(
                "SELECT id, state, created_at FROM infra.server_jobs WHERE id = CAST(:id AS uuid)",
                id=str(pend["job_id"]),
            )
        if job is not None and job["state"] in ("done", "failed", "cancelled"):
            ctx.clear_pending = True
            if job["state"] != "done":
                raise ReadError("دستور خواندن روی IG-Hub انجام نشد؛ فردا دوباره امتحان میشود.")
            lines = await tx.all(
                """SELECT data ->> 'text' AS text FROM infra.server_job_events
                   WHERE job_id = :j AND type = 'stdout' ORDER BY seq""",
                j=job["id"],
            )
            return parse_ig("\n".join(str(r["text"] or "") for r in lines), accounts, ctx.today)
        if job is not None and job["created_at"] > datetime.now(UTC) - IG_JOB_STALE:
            ctx.pending = pend  # still running: wait for the next tick
            return []
        try:
            srv = await SV.load_server(tx, srv_name, company=srv_company)
        except Exception as exc:
            raise ReadError("سرور IG-Hub پیدا نشد؛ دستیار سرور IG-Hub باید وصل باشد.") from exc
        if SV.state_of(srv) == "revoked":
            raise ReadError("دستیار سرور IG-Hub جدا شده است؛ دوباره وصلش کنید.")
        args = {"cmd": cmd, "timeout_s": IG_JOB_TIMEOUT_S}
        reuse = await tx.scalar(
            """SELECT id FROM infra.server_jobs WHERE server_id = :s AND actor_code = :a
                 AND args_sha256 = :sha AND created_at > now() - interval '6 hours'
                 AND state IN ('queued', 'running', 'done')
               ORDER BY created_at DESC LIMIT 1""",
            s=srv["id"],
            a=ACTOR,
            sha=SV.digest_of(args),
        )
        if reuse is None:
            j = await SV.create_job(
                tx,
                server=srv,
                kind="exec",
                args=args,
                actor_kind="service",
                actor_code=ACTOR,
                summary="read-only Instagram figures for the content group (contract §29.12)",
                timeout_s=IG_JOB_TIMEOUT_S,
            )
            reuse = j["id"]
        ctx.pending = {"job_id": str(reuse), "day": ctx.today.isoformat()}
    return []


async def read_not_built(ctx: ReadCtx) -> list[Figure]:
    raise ReadError(NOT_BUILT_FA)


async def read_ads(ctx: ReadCtx) -> list[Figure]:
    """⟨1.13⟩ §31.6: Google Ads and Meta Ads (hq_api.domain.ads)."""
    from hq_api.domain import ads

    return await ads.read_ads(ctx)


READERS = {
    "google_ads": read_ads,
    "meta_ads": read_ads,
    "telegram": read_telegram,
    "pagespeed": read_pagespeed,
    "search_console": read_search_console,
    "ga4": read_ga4,
    "youtube": read_youtube,
    "instagram": read_instagram,
}


# ------------------------------------------------------------ the read run --
def owner_today(tz: str, now: datetime | None = None) -> date:
    try:
        z = ZoneInfo(tz)
    except (KeyError, ValueError):
        z = ZoneInfo("Asia/Tehran")
    return (now or datetime.now(UTC)).astimezone(z).date()


async def store(tx: Tx, company_id: UUID, kind: str, figures: list[Figure]) -> int:
    n = 0
    for f in figures:
        n += await tx.exec(
            """INSERT INTO growth.metrics_daily (company_id, kind, day, key, subject, value, source)
               VALUES (:co, :k, :d, :key, :s, :v, :src)
               ON CONFLICT (company_id, kind, day, key, subject)
               DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source, at = now()""",
            co=company_id,
            k=kind,
            d=f.day,
            key=f.key,
            s=f.subject[:200],
            v=f.value,
            src=(f.source or kind)[:200],
        )
    return n


async def read_one(
    hub: Any, company_id: UUID, kind: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """One connection's read now: its figures stored, its state, last read
    and Persian error set. Returns the connection row after it."""
    from hq_api.domain import egress as G
    from hq_api.domain.gov_common import owner_tz

    ids = await hub.companies.ids()

    def factory() -> Any:
        return hub.db.tx(ids)

    async with factory() as tx:
        row = await tx.first(
            """SELECT k.*, c.code AS company FROM growth.connections k
               JOIN core.companies c ON c.id = k.company_id
               WHERE k.company_id = :co AND k.kind = :kind""",
            co=company_id,
            kind=kind,
        )
        tz = await owner_tz(tx)
    if row is None:
        return {}
    secret = await read_secret(getattr(hub, "bao", None), row["company"], kind)
    secret_set = bool(secret) or (row["secret_set"] and getattr(hub, "bao", None) is None)
    ctx = ReadCtx(
        hub=hub,
        tx_factory=factory,
        company_id=company_id,
        company=row["company"],
        kind=kind,
        config=dict(row["config"] or {}),
        secret=secret,
        today=owner_today(tz, now),
        http=http_for(hub),
        pending=row["pending"],
    )
    figures: list[Figure] = []
    error: str | None = None
    need = missing(kind, ctx.config, secret_set)
    async with factory() as tx:
        locked = await gate.automation_lock(tx, company_id)
    if locked is not None and not need:
        # the launch gate: no outside call while the holding or the company is locked
        error = "کلید توقف روشن است؛ تا باز شدن آن چیزی خوانده نمیشود."
    elif not need:
        reader = READERS.get(kind, read_not_built)
        try:
            figures = await reader(ctx)
        except ReadError as exc:
            error = exc.reason_fa
        except Exception:
            log.warning("connection read failed", extra={"kind": kind}, exc_info=True)
            error = "خواندن عددها نشد؛ فردا دوباره امتحان میشود."
    waiting = ctx.pending is not None and not ctx.clear_pending and not figures and error is None
    async with factory() as tx:
        if ctx.entries:
            await G.record(tx, company_id=company_id, actor=ACTOR, run_id=None, entries=ctx.entries)
        await store(tx, company_id, kind, figures)
        await tx.exec(
            """UPDATE growth.connections SET
                   secret_set = :ss,
                   secret_set_at = CASE WHEN :ss AND NOT secret_set THEN now() ELSE secret_set_at END,
                   last_read_at = CASE WHEN :read THEN now() ELSE last_read_at END,
                   last_error_fa = :err,
                   pending = CAST(:pend AS jsonb),
                   state = :st, updated_at = now()
               WHERE company_id = :co AND kind = :kind""",
            co=company_id,
            kind=kind,
            ss=secret_set,
            read=not need and not waiting,
            err=error,
            pend=json.dumps(ctx.pending) if waiting else None,
            st="not_connected" if need else ("error" if error else "connected"),
        )
        after = await tx.one(
            "SELECT * FROM growth.connections WHERE company_id = :co AND kind = :kind",
            co=company_id,
            kind=kind,
        )
        await events.emit(
            tx,
            row["company"],
            "connection.updated",
            None,
            {"kind": kind, "state": after["state"], "figures": len(figures)},
        )
    return dict(after)


async def hub_figures(tx: Tx, company_id: UUID, day: date, tz: str) -> list[Figure]:
    """The hub's own figures of a company's day (kind `hub`): items published,
    the cost per published item (thousands of tokens of its media
    department), experiments closed. Real counts only."""
    published = int(
        await tx.scalar(
            """SELECT count(*) FROM media.items i, jsonb_array_elements(i.publish) e
               WHERE i.company_id = :co AND e ? 'at' AND e ->> 'at' IS NOT NULL
                 AND (CAST(e ->> 'at' AS timestamptz) AT TIME ZONE :tz)::date = :day""",
            co=company_id,
            day=day,
            tz=tz,
        )
        or 0
    )
    out = [Figure(day, "published", float(published), "", "hub")]
    if published:
        tokens = await tx.scalar(
            """SELECT COALESCE(sum(COALESCE(k.input_tokens, 0) + COALESCE(k.output_tokens, 0)
                                   + COALESCE(k.cache_write_tokens, 0)), 0)
               FROM llm.calls k
               WHERE k.company_id = :co AND k.department = 'MEDIA'
                 AND (k.started_at AT TIME ZONE :tz)::date = :day""",
            co=company_id,
            day=day,
            tz=tz,
        )
        out.append(
            Figure(day, "cost_per_post", round(float(tokens or 0) / 1000 / published, 1), "", "hub")
        )
    closed = int(
        await tx.scalar(
            """SELECT count(*) FROM growth.experiments WHERE company_id = :co
                 AND (closed_at AT TIME ZONE :tz)::date = :day""",
            co=company_id,
            day=day,
            tz=tz,
        )
        or 0
    )
    if closed:
        out.append(Figure(day, "experiments", float(closed), "", "hub"))
    return out


async def read_due(hub: Any, now: datetime | None = None) -> dict[str, Any]:
    """The daily read: every connection whose figures are not read today (or
    whose read waits on IG-Hub), and the hub's own figures of yesterday.
    Nothing while the holding is locked (an outside call)."""
    from hq_api.domain.gov_common import owner_tz

    now = now or datetime.now(UTC)
    ids = await hub.companies.ids()
    async with hub.db.tx(ids) as tx:
        if (lock := await gate.automation_lock(tx)) is not None:
            return gate.skipped(lock)
        tz = await owner_tz(tx)
        today = owner_today(tz, now)
        due = await tx.all(
            """SELECT k.company_id, k.kind, k.config, k.secret_set, k.last_read_at, k.pending,
                      c.code, control.lock_state(k.company_id) AS lock
               FROM growth.connections k JOIN core.companies c ON c.id = k.company_id
               WHERE c.status = 'active' ORDER BY c.code, k.kind"""
        )
        yesterday = today - timedelta(days=1)
        companies = await tx.all(
            "SELECT id FROM core.companies WHERE kind = 'company' AND status = 'active'"
        )
        hub_n = 0
        for co in companies:
            hub_n += await store(
                tx, co["id"], "hub", await hub_figures(tx, co["id"], yesterday, tz)
            )
        # ⟨2026-11-08⟩ the owner: an Instagram read path not registered here is the technical
        # team's work, made by code (once per company), never a step of his
        setup = 0
        for r in due:
            cfg = r["config"] or {}
            if (
                r["kind"] == "instagram"
                and cfg.get("via") == "ig_hub"
                and missing("instagram", cfg, True)
            ):
                try:
                    async with tx.conn.begin_nested():
                        if await ensure_ig_setup_work(tx, r["company_id"]) is not None:
                            setup += 1
                except Exception:  # noqa: BLE001 - never fails the daily read
                    log.warning("ig setup work could not be made", extra={"company": r["code"]})
    out: dict[str, Any] = {"read": 0, "failed": 0, "waiting": 0, "hub": hub_n, "ig_setup": setup}
    for r in due:
        if r["lock"] is not None:
            continue
        last = r["last_read_at"]
        read_today = last is not None and owner_today(tz, last) >= today
        if read_today and not r["pending"]:
            continue
        if missing(r["kind"], r["config"] or {}, True) and not r["pending"]:
            continue  # nothing to read with (the secret is checked in read_one)
        after = await read_one(hub, r["company_id"], r["kind"], now=now)
        if after.get("pending"):
            out["waiting"] += 1
        elif after.get("last_error_fa"):
            out["failed"] += 1
        else:
            out["read"] += 1
    return out


async def set_config(
    tx: Tx, company: Any, kind: str, config: dict[str, Any], label_fa: str | None
) -> dict[str, Any]:
    await tx.exec(
        """INSERT INTO growth.connections (company_id, kind, label_fa, config)
           VALUES (:co, :k, :l, CAST(:c AS jsonb))
           ON CONFLICT (company_id, kind) DO UPDATE SET config = EXCLUDED.config,
               label_fa = COALESCE(:lnew, growth.connections.label_fa),
               last_error_fa = NULL, pending = NULL, updated_at = now()""",
        co=company.id,
        k=kind,
        l=label_fa or LABEL_FA[kind],
        lnew=label_fa,
        c=json.dumps(config, ensure_ascii=False),
    )
    row = await tx.one(
        "SELECT * FROM growth.connections WHERE company_id = :co AND kind = :k",
        co=company.id,
        k=kind,
    )
    await tx.exec(
        "UPDATE growth.connections SET state = :st WHERE id = :id",
        id=row["id"],
        st=state_of(kind, row),
    )
    return row
