"""⟨1.37⟩ Contract §59.5-§59.6 (prompt 38): a company's own links (UTM built by code) and a flow's
reply policy (validated, its public pool filled to ten from the hub's warm pool, in order).

The owner, 2026-11-13: «جواب‌های عمومی به نوبت میروند، نه به تصادف». IG-Hub sends a comment's
public replies in turn (1806b86, `rules.public_turn`), so the pool's order is the order they go out
in: the policy's own lines first, then the hub's pool, and every list made from it (the package's
`comment.txt`, the rule's body, the preview) keeps that order.

A reply's link is built by code, never by a model: the section's url (else the site's) with
`utm_source`, `utm_medium` (the path's: comment, story, dm), `utm_campaign` (the flow's short
name) and `utm_content` (the run's day, YYYYMMDD); parameters already on the url are kept.

The use form (§59.4) calls `save_links` and `fill_policy`; the flow's `package` step writes
`comment.txt` with `comment_txt` and the three rules with `flow_rules`; the publish step sends them.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from hq_api import audit
from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS
from hq_api.errors import ApiError
from hq_api.principal import Principal

HTTPS = re.compile(r"https://[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?")
URL_MAX = 1900
UTM_VALUE = re.compile(r"[A-Za-z0-9_.{}-]{1,60}")
DM_MAX = 640
BUTTONS_MAX = 3
BUTTON_TITLE_MAX = 20
POOL_MAX = 30
POOL_LINE_MAX = 300
PUBLIC_MIN = 10
PATHS = ("comment", "story", "dm")
DEFAULT_BUTTON_FA = "باز کردن"
DEFAULT_DM_FA = "سلام 🌱 این هم چیزی که درباره‌ی «{topic}» خواستی 👇"
NO_TOPIC_FA = "این ویدیو"
WORD_FA = "کلمه‌ی ویدیو"
LINKS_FA = "نشانی‌ها باید با https:// شروع شوند."
POLICY_FA = "تنظیم جواب‌ها درست نیست؛ بخش‌های قرمز را درست کن."
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# --------------------------------------------------------------------- links --
def _https(url: str) -> bool:
    url = url.strip()
    return len(url) <= URL_MAX and HTTPS.fullmatch(url) is not None


def check_links(links: FS.SiteLinksIn) -> None:
    """422 `fields.*` for a link that is not https, a key used twice, a UTM value that is not one."""
    fields: dict[str, str] = {}
    if not _https(links.site.url):
        fields["site.url"] = "an https address"
    seen: set[str] = set()
    for i, s in enumerate(links.sections):
        if not _https(s.url):
            fields[f"sections[{i}].url"] = "an https address"
        if s.key in seen:
            fields[f"sections[{i}].key"] = "used twice"
        seen.add(s.key)
    if links.utm is not None:
        u = links.utm
        values = {"utm.source": u.source, "utm.campaign": u.campaign, "utm.medium.comment":
                  u.medium.comment, "utm.medium.story": u.medium.story, "utm.medium.dm": u.medium.dm}  # fmt: skip
        for name, value in values.items():
            if UTM_VALUE.fullmatch(value or "") is None:
                fields[name] = "letters, digits, _ . - (at most 60)"
    if fields:
        raise ApiError(422, "validation_failed", fields=fields, message_fa=LINKS_FA)


def _j(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def render_links(row: dict[str, Any], company: str) -> FS.SiteLinks:
    site = _j(row["site"]) or {}
    utm = _j(row.get("utm")) or {}
    return FS.SiteLinks(
        company=company,
        site=FS.SiteUrl(url=str(site.get("url") or ""), title_fa=str(site.get("title_fa") or "")),
        sections=[FS.SiteSection.model_validate(s) for s in _j(row.get("sections")) or []],
        utm=FS.SiteUtm.model_validate(utm) if utm else FS.SiteUtm(),
        updated_at=row.get("updated_at"),
        by_fa=str(row.get("by_fa") or ""),
    )


async def save_links(
    tx: Tx, company_id: UUID, company: str, links: FS.SiteLinksIn, by_fa: str,
    *, who: Principal | None = None, request_id: str | None = None,
) -> FS.SiteLinks:  # fmt: skip
    """PUT /companies/{code}/site-links (and the use form's `links`): validated (422 `fields.*`)
    and saved; audited (`company.site_links`, A2) when `who` is given (the route audits itself)."""
    check_links(links)
    site = {"url": links.site.url.strip(), "title_fa": links.site.title_fa.strip()[:200]}
    sections = [
        {"key": s.key, "title_fa": s.title_fa.strip()[:200], "url": s.url.strip()}
        for s in links.sections
    ]
    utm = (links.utm or FS.SiteUtm()).model_dump()
    row = await tx.one(
        """INSERT INTO growth.site_links (company_id, site, sections, utm, by_fa)
           VALUES (:co, CAST(:site AS jsonb), CAST(:sec AS jsonb), CAST(:utm AS jsonb), :by)
           ON CONFLICT (company_id) DO UPDATE SET site = EXCLUDED.site,
               sections = EXCLUDED.sections, utm = EXCLUDED.utm, by_fa = EXCLUDED.by_fa,
               updated_at = now()
           RETURNING *""",
        co=company_id,
        site=json.dumps(site, ensure_ascii=False),
        sec=json.dumps(sections, ensure_ascii=False),
        utm=json.dumps(utm, ensure_ascii=False),
        by=by_fa[:200],
    )
    if who is not None:
        await audit.record(
            tx, who, company_id=company_id, action="company.site_links", action_class="A2",
            target_kind="company", target_ref=company,
            summary=f"the site {site['url']} and {len(sections)} sections"[:500],
            request_id=request_id,
        )  # fmt: skip
    return render_links(dict(row), company)


async def load_links(tx: Tx, company_id: UUID, company: str) -> FS.SiteLinks | None:
    row = await tx.first("SELECT * FROM growth.site_links WHERE company_id = :co", co=company_id)
    return render_links(dict(row), company) if row is not None else None


def flow_name(automation: str | None) -> str:
    """The flow's short name for `utm_campaign` (`{flow}`): its automation's ref, as a slug."""
    return re.sub(r"[^a-z0-9]+", "_", (automation or "flow").lower()).strip("_") or "flow"


def day_code(day: Any) -> str:
    """`utm_content`: the run's day as YYYYMMDD."""
    if isinstance(day, datetime):
        day = day.date()
    if isinstance(day, date):
        return f"{day:%Y%m%d}"
    digits = re.sub(r"\D", "", str(day or ""))
    return digits[:8]


def link_for(
    links: FS.SiteLinks | None, section: str | None, path: str, flow: str, day: Any
) -> str:
    """The reply's link: the section's url (else the site's) + utm_source, utm_medium (the path's),
    utm_campaign (`{flow}`), utm_content (YYYYMMDD); parameters already on the url are kept.
    "" when the company has no link."""
    if links is None:
        return ""
    base = next((s.url for s in links.sections if section and s.key == section), None)
    base = (base or links.site.url or "").strip()
    if not base:
        return ""
    medium = getattr(links.utm.medium, path, None) or path
    campaign = (links.utm.campaign or "{flow}").replace("{flow}", flow)
    parts = urlsplit(base)
    query = parse_qsl(parts.query, keep_blank_values=True)
    have = {k for k, _ in query}
    for key, value in (("utm_source", links.utm.source or "instagram"), ("utm_medium", medium),
                       ("utm_campaign", campaign), ("utm_content", day_code(day))):  # fmt: skip
        if key not in have and value:
            query.append((key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


# -------------------------------------------------------------------- policy --
def check_policy(policy: FS.ReplyPolicy, links: FS.SiteLinks | None) -> None:
    """422 `fields.*` (the wire's names): the DM's text over 640, more than 3 buttons, a title over
    20, a section that is not one of the company's, the pool over 30 or a line of it over 300."""
    fields: dict[str, str] = {}
    keys = {s.key for s in links.sections} if links is not None else set()
    dm = policy.dm_template
    if len(dm.text_fa) > DM_MAX:
        fields["dm_template.text_fa"] = f"at most {DM_MAX} characters"
    if len(dm.buttons) > BUTTONS_MAX:
        fields["dm_template.buttons"] = f"at most {BUTTONS_MAX} buttons"
    for i, b in enumerate(dm.buttons):
        if len(b.title_fa.strip()) > BUTTON_TITLE_MAX:
            fields[f"dm_template.buttons[{i}].title_fa"] = f"at most {BUTTON_TITLE_MAX} characters"
        if b.section is not None and b.section not in keys:
            fields[f"dm_template.buttons[{i}].section"] = "one of the company's sections"
    if policy.section is not None and policy.section not in keys:
        fields["section"] = "one of the company's sections"
    if len(policy.public_pool) > POOL_MAX:
        fields["public_pool"] = f"at most {POOL_MAX} replies"
    for i, line in enumerate(policy.public_pool):
        if len(line.strip()) > POOL_LINE_MAX:
            fields[f"public_pool[{i}]"] = f"at most {POOL_LINE_MAX} characters"
    if policy.repeat.mode == "after_days" and policy.repeat.days is None:
        fields["repeat.days"] = "1 to 365"
    if fields:
        raise ApiError(422, "validation_failed", fields=fields, message_fa=POLICY_FA)


def fill_pool(own: list[str], first: list[str] | None = None) -> list[str]:
    """The public replies in the order they go out: `first` (a video's own), then `own` (the
    policy's), then the hub's warm pool up to ten; each once, at most 30."""
    from hq_api.domain import session_publish as SPB

    out: list[str] = []
    for line in [*(first or []), *own]:
        text = str(line).strip()[:POOL_LINE_MAX]
        if text and text not in out:
            out.append(text)
    for text in SPB.PUBLIC_POOL:
        if len(out) >= PUBLIC_MIN:
            break
        if text not in out:
            out.append(text)
    return out[:POOL_MAX]


async def fill_policy(tx: Tx, company: str, policy: FS.ReplyPolicy | None) -> FS.ReplyPolicy:
    """A policy validated against the company's sections (422 `fields.*`) with its public pool
    filled to ten from the hub's pool, the policy's own lines first, order kept."""
    got = policy or FS.ReplyPolicy()
    links = None
    company_id = await tx.scalar("SELECT id FROM core.companies WHERE code = :c", c=company)
    if company_id is not None:
        links = await load_links(tx, company_id, company)
    check_policy(got, links)
    return lenient(got)


def lenient(policy: FS.ReplyPolicy | dict[str, Any] | str | None) -> FS.ReplyPolicy:
    """A stored policy as code reads it (never refused: what was saved was checked then), its pool
    filled in order."""
    raw = _j(policy) if not isinstance(policy, FS.ReplyPolicy) else policy
    got = (
        raw
        if isinstance(raw, FS.ReplyPolicy)
        else FS.ReplyPolicy.model_validate(raw)
        if isinstance(raw, dict) and raw
        else FS.ReplyPolicy()
    )
    return got.model_copy(update={"public_pool": fill_pool(got.public_pool)})


def cooldown_days(policy: FS.ReplyPolicy) -> int:
    """`repeat` as IG-Hub's `cooldown_days`: 365 a year, else N."""
    if policy.repeat.mode == "after_days" and policy.repeat.days:
        return max(1, min(365, int(policy.repeat.days)))
    return 365


def day_dm(policy: FS.ReplyPolicy, topic: str | None, video_reply: str | None = None) -> str:
    """The day's DM: the video's own `reply:` when the policy lets each video choose, else the
    policy's text (else the hub's), `{topic}` filled with the day's topic."""
    if policy.per_video_dm and (video_reply or "").strip():
        text = str(video_reply).strip()
    else:
        text = policy.dm_template.text_fa.strip() or DEFAULT_DM_FA
    return text.replace("{topic}", (topic or "").strip() or NO_TOPIC_FA)[:1000]


def buttons_for(
    policy: FS.ReplyPolicy, links: FS.SiteLinks | None, path: str, flow: str, day: Any
) -> list[dict[str, str]]:
    """The DM's buttons with their real links for one path: the policy's (at most three), else one
    «باز کردن» to the policy's section (else the site); a button with no link is left out."""
    out: list[dict[str, str]] = []
    for b in policy.dm_template.buttons[:BUTTONS_MAX]:
        url = link_for(links, b.section or policy.section, path, flow, day)
        if url:
            out.append({"title": b.title_fa.strip()[:BUTTON_TITLE_MAX], "url": url})
    if not out and not policy.dm_template.buttons:
        url = link_for(links, policy.section, path, flow, day)
        if url:
            out.append({"title": DEFAULT_BUTTON_FA, "url": url})
    return out


def flow_rules(
    policy: FS.ReplyPolicy, links: FS.SiteLinks | None, *, flow: str, day: Any, keyword: str | None,
    match_any: bool, dm_text: str, public: list[str], story: bool,
) -> dict[str, dict[str, Any]]:  # fmt: skip
    """§59.6 the three rules of one output, each with its own UTM: `comment` on the post (every
    comment when `match_any`), `story_reply` (when the story goes out and the policy answers it)
    and `dm` (when the policy answers DMs); the story and the DM answer the word only, so without
    a word there is only the comment rule (and only for every comment)."""
    words = [keyword.strip()] if keyword and keyword.strip() else []
    cool = cooldown_days(policy)
    out: dict[str, dict[str, Any]] = {}
    if words or match_any:
        out["comment"] = {
            "keywords": words, "match": "any" if match_any else "contains", "reply": dm_text,
            "buttons": buttons_for(policy, links, "comment", flow, day),
            "public_pool": list(public)[:POOL_MAX], "cooldown_days": cool,
        }  # fmt: skip
    if words and story and policy.story:
        out["story_reply"] = {
            "keywords": words, "match": "contains", "reply": dm_text,
            "buttons": buttons_for(policy, links, "story", flow, day), "cooldown_days": cool,
        }  # fmt: skip
    if words and policy.dm:
        out["dm"] = {
            "keywords": words, "match": "contains", "reply": dm_text,
            "buttons": buttons_for(policy, links, "dm", flow, day), "cooldown_days": cool,
        }  # fmt: skip
    return out


def comment_txt(rule: dict[str, Any] | None, dm_text: str, public: list[str]) -> str:
    """`comment.txt` of the package (the session's own format, §46): `keyword:`, `match: any`,
    `reply:` one line each, `link:` and `button:` (the comment path's first button) and every
    `public:` line in the pool's order."""
    lines: list[str] = []
    rule = rule or {}
    for w in rule.get("keywords") or []:
        lines.append(f"keyword: {w}")
    if rule.get("match") == "any":
        lines.append("match: any")
    lines += [f"reply: {x}" for x in dm_text.splitlines() if x.strip()]
    buttons = rule.get("buttons") or []
    if buttons:
        lines.append(f"link: {buttons[0]['url']}")
        lines.append(f"button: {buttons[0]['title']}")
    lines += [f"public: {x}" for x in public]
    return "\n".join(lines) + "\n"


def _n(n: int) -> str:
    return str(n).translate(FA_DIGITS)


def repeat_fa(policy: FS.ReplyPolicy) -> str:
    days = cooldown_days(policy)
    return "هر نفر سالی یک بار جواب میگیرد." if days >= 365 else (
        f"هر نفر هر {_n(days)} روز یک بار جواب میگیرد."
    )  # fmt: skip


def preview(
    policy: FS.ReplyPolicy, links: FS.SiteLinks | None, *, flow: str, day: Any,
    topic: str | None = None,
) -> FS.RepliesPreview:  # fmt: skip
    """What a person sees, built by the same code that writes the package and the rules: the DM
    (its text with the topic, its buttons with their real UTM links, as a commenter gets it), and
    every public reply in the order they go out."""
    filled = lenient(policy)
    text = day_dm(filled, topic)
    buttons = buttons_for(filled, links, "comment", flow, day)
    n = len(filled.public_pool)
    match = filled.comment.match
    if match == "any":
        comment = f"هر کامنتی زیر ویدیو جواب میگیرد: یکی از {_n(n)} جواب عمومی به نوبت، و همین پیام در دایرکت."
    elif match == "word":
        comment = f"هر کس {WORD_FA} را کامنت کند جواب میگیرد: یکی از {_n(n)} جواب عمومی به نوبت، و همین پیام در دایرکت."
    else:
        comment = (
            f"هر ویدیو خودش انتخاب میکند: هر کامنتی یا فقط {WORD_FA}؛ یکی از {_n(n)} جواب عمومی به "
            "نوبت، و همین پیام در دایرکت."
        )
    story = (
        f"هر کس {WORD_FA} را در جواب استوری بفرستد، همین پیام را در دایرکت میگیرد."
        if filled.story
        else "جواب استوری خاموش است."
    )
    dm = (
        f"هر کس {WORD_FA} را در دایرکت بفرستد، همین پیام را میگیرد."
        if filled.dm
        else "جواب دایرکت خاموش است."
    )
    again = repeat_fa(filled)
    return FS.RepliesPreview(
        dm=FS.PreviewDm(
            text=text, buttons=[FS.PreviewButton(title=b["title"], url=b["url"]) for b in buttons]
        ),
        public=list(filled.public_pool),
        comment_fa=f"{comment} {again}",
        story_fa=f"{story} {again}" if filled.story else story,
        dm_fa=f"{dm} {again}" if filled.dm else dm,
    )
