"""⟨1.37⟩ Contract §59.5, §59.6 (prompt 38): a company's own links, and a flow's reply policy and its
preview (domain/site_links.py).

GET  /companies/{code}/site-links         the company's site, its sections and UTM defaults
PUT  /companies/{code}/site-links         the owner's tap (audit `company.site_links`, A2)
PUT  /automations/{ref}/replies           a flow's reply policy (audit `automation.replies`, A2)
POST /automations/{ref}/replies/preview   what a person sees with it, built by the same code
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from hq_api.context import Ctx, owner_ctx
from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS
from hq_api.domain import site_links as SL
from hq_api.domain.gov_common import owner_tz
from hq_api.errors import ApiError, responses

router = APIRouter(tags=["automations"])
E = responses(401, 403, 404, 409, 422)
OWNER_FA = "مدیر کل"
NOT_FLOW_FA = "این اتوماسیون روند روزانه نیست؛ جواب‌ها فقط برای روندها تنظیم میشود."


@router.get("/companies/{code}/site-links", response_model=FS.SiteLinks, responses=E)
async def get_site_links(code: str, ctx: Ctx = Depends(owner_ctx)) -> FS.SiteLinks:
    """§59.5 the company's own links. A company with none yet answers an empty site (the app's form
    starts empty)."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        got = await SL.load_links(tx, company.id, company.code)
    return got or FS.SiteLinks(company=company.code, site=FS.SiteUrl(url=""))


@router.put("/companies/{code}/site-links", response_model=FS.SiteLinks, responses=E)
async def put_site_links(
    code: str, body: FS.SiteLinksIn, ctx: Ctx = Depends(owner_ctx)
) -> FS.SiteLinks:
    """§59.5 the owner sets the company's links (a tap): https only (422 `fields.site.url`,
    `fields.sections[i].url`), keys `[a-z0-9_]{1,24}`, at most 30 sections."""
    company = await ctx.hub.companies.by_code(code)
    async with ctx.tx() as tx:
        got = await SL.save_links(tx, company.id, company.code, body, OWNER_FA)
        await ctx.audit(
            tx,
            company_id=company.id,
            action="company.site_links",
            action_class="A2",
            target_kind="company",
            target_ref=company.code,
            summary=f"the site {got.site.url} and {len(got.sections)} sections"[:500],
        )
        return got


# ------------------------------------------------------------- §59.6 replies --
FLOW_SQL = """SELECT a.*, c.code AS company, c.name_fa AS company_fa, p.title_fa AS playbook_fa
    FROM growth.automations a JOIN core.companies c ON c.id = a.company_id
    LEFT JOIN owner.playbooks p ON p.ref = a.playbook
    WHERE a.ref = :r"""


async def _flow(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    row = await tx.first(FLOW_SQL + (" FOR UPDATE OF a" if lock else ""), r=ref)
    if row is None:
        raise ApiError(404, "not_found", f"no automation {ref}")
    if row["kind"] != "flow":
        raise ApiError(
            409, "validation_failed", f"{ref} is a {row['kind']}", message_fa=NOT_FLOW_FA
        )
    return dict(row)


def _j(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


@router.put("/automations/{ref}/replies", response_model=FS.FlowAutomation, responses=E)
async def put_replies(
    ref: str, body: FS.ReplyPolicy, ctx: Ctx = Depends(owner_ctx)
) -> FS.FlowAutomation:
    """§59.6 a flow's reply policy, from its next publication (a tap). 422 `fields.*`: the DM's
    text over 640, more than 3 buttons, a title over 20, a section that is not the company's, the
    pool over 30 or a line of it over 300. Fewer than ten replies is fine: the hub's pool fills
    them, the policy's own first, in the order given (the order they go out in)."""
    from hq_api.domain import flow_view as FV

    if FV.flow_of(ref) is not None:  # ⟨2026-11-14⟩ an n8n flow's replies come from its kit
        raise FV.not_here()
    async with ctx.tx() as tx:
        row = await _flow(tx, ref, lock=True)
        policy = await SL.fill_policy(tx, row["company"], body)
        # stored as the owner gave it (the pool filled on reading), so a later pool change reaches it
        given = body.model_copy(
            update={"public_pool": [x.strip() for x in body.public_pool if x.strip()]}
        )
        before = _j(row.get("replies")) or {}
        after = given.model_dump()
        await tx.exec(
            """UPDATE growth.automations SET replies = CAST(:r AS jsonb), updated_at = now()
               WHERE id = :id""",
            id=row["id"],
            r=json.dumps(after, ensure_ascii=False),
        )
        await ctx.audit(
            tx,
            company_id=row["company_id"],
            action="automation.replies",
            action_class="A2",
            target_kind="automation",
            target_ref=ref,
            summary=json.dumps(
                {"before": _brief(before), "after": _brief(after)}, ensure_ascii=False
            )[:500],
        )
        from hq_api.domain import flow_auto as FA

        # the flow as every other route shows it, its pool filled as it will go out
        out = await FA.render(tx, await FA.load(tx, ref))
        return out.model_copy(update={"replies": policy})


def _brief(p: dict[str, Any]) -> dict[str, Any]:
    if not p:
        return {}
    return {
        "comment": (p.get("comment") or {}).get("match"),
        "story": p.get("story"),
        "dm": p.get("dm"),
        "pool": len(p.get("public_pool") or []),
        "buttons": len((p.get("dm_template") or {}).get("buttons") or []),
        "repeat": (p.get("repeat") or {}).get("mode"),
        "section": p.get("section"),
    }


@router.post("/automations/{ref}/replies/preview", response_model=FS.RepliesPreview, responses=E)
async def preview_replies(
    ref: str, body: FS.RepliesPreviewIn, ctx: Ctx = Depends(owner_ctx)
) -> FS.RepliesPreview:
    """§59.6 what a person sees with the flow's policy: the DM with `{topic}` filled (`topic_fa`,
    else a stand-in) and its buttons with their real UTM links, every public reply in the order
    they go out (the first commenter gets the first), and one plain line for each path."""
    async with ctx.tx() as tx:
        row = await _flow(tx, ref)
        links = await SL.load_links(tx, row["company_id"], row["company"])
        day = datetime.now(UTC).astimezone(ZoneInfo(await owner_tz(tx))).date()
    return SL.preview(
        SL.lenient(row.get("replies")),
        links,
        flow=SL.flow_name(ref),
        day=day,
        topic=body.topic_fa,
    )
