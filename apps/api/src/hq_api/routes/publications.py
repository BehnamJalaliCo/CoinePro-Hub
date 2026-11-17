"""⟨1.39⟩ Contract §60.2 (prompt 39): the publish centre, owner only. Every answer is read from
`media.publications` (domain/publications.py); what is still to be made comes from the flows
through `publications.planned_today`.

GET  /publications/today?company=&account=&channel=      the owner's day (Tehran): cards, planned,
                                                         the next one, the counts
GET  /publications/tree?from=&to=                        companies → pages → kinds (default 30 days)
GET  /publications?company=&account=&channel=&kind=&state=&from=&to=&q=&automation=&group=set
                    &cursor=&limit=                      newest first; `q` Persian-folded
GET  /publications/calendar?from=&to=&company=&account=  Tehran days, the future's planned count
GET  /publications/waiting                               only what cannot move without the owner
POST /publications/waiting/{id}/{key}                    its action (a tap; a cap above the month
                                                         envelope: 🔏 automation.budget)
GET  /publications/{ref}                                 one row, with its set

`404` for an unknown company or account. The fixed paths are declared before `/{ref}`."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, Path, Query

from hq_api.context import Ctx, owner_ctx
from hq_api.domain import publications as PB
from hq_api.errors import responses

router = APIRouter(tags=["publications"])
E = responses(401, 403, 404, 422)
CODE = r"^[A-Z][A-Z0-9]{1,9}$"
ACCOUNT = r"^@?[A-Za-z0-9._]{1,100}$"
REF = r"^P-[0-9]{6,}$"
WAIT_ID = r"^(ask|line|cap):[A-Za-z0-9_.:-]{1,80}$"
Channel = PB.Channel


@router.get("/publications/today", response_model=PB.PublishToday, responses=E)
async def publications_today(
    company: str | None = Query(default=None, pattern=CODE),
    account: str | None = Query(default=None, pattern=ACCOUNT),
    channel: Channel | None = Query(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> PB.PublishToday:
    """⟨1.39⟩ §60.2 the owner's day in Tehran: every publication of the day in time order (a set
    of story slides as one card with its progress), `planned` (what the automations will still
    make today, not yet a row), `next` (the next to go out) and the day's counts."""
    async with ctx.tx() as tx:
        return await PB.today(tx, company=company, account=account, channel=channel)


@router.get("/publications/tree", response_model=PB.PublishTree, responses=E)
async def publications_tree(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> PB.PublishTree:
    """⟨1.39⟩ §60.2 the archive's tree: every company and page with at least one publication in
    the range (default the last 30 days), totals by kind and how many automations made them."""
    async with ctx.tx() as tx:
        return await PB.tree(tx, from_, to)


@router.get("/publications/calendar", response_model=PB.PublishCalendar, responses=E)
async def publications_calendar(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    company: str | None = Query(default=None, pattern=CODE),
    account: str | None = Query(default=None, pattern=ACCOUNT),
    ctx: Ctx = Depends(owner_ctx),
) -> PB.PublishCalendar:
    """⟨1.39⟩ §60.2 each Tehran day of the range (default 14 days back and ahead, at most 62): its
    publications by state, the pages, and for today and the days ahead what the flows will make.
    A day's list is `GET /publications?from=day&to=day`."""
    async with ctx.tx() as tx:
        return await PB.calendar(tx, from_, to, company, account)


@router.get("/publications/waiting", response_model=PB.WaitingList, responses=E)
async def publications_waiting(ctx: Ctx = Depends(owner_ctx)) -> PB.WaitingList:
    """⟨1.39⟩ §60.2 «منتظر شما»: only what cannot move without the owner: a working group or a flow
    in `ask` mode at its publish step (`publish_ask`: `publish`, `skip`) and a run at its day's
    cap (`budget_cap`: `raise_cap` with `usd_cap`, `skip`). Empty: the app hides the place."""
    async with ctx.tx() as tx:
        return await PB.waiting(tx)


@router.post(
    "/publications/waiting/{wid}/{key}",
    response_model=PB.WaitingList,
    responses=responses(401, 403, 404, 409, 422),
)
async def publications_waiting_act(
    wid: str = Path(pattern=WAIT_ID),
    key: str = Path(pattern=r"^(publish|skip|raise_cap)$"),
    body: PB.WaitingIn | None = Body(default=None),
    ctx: Ctx = Depends(owner_ctx),
) -> PB.WaitingList:
    """⟨1.39⟩ §60.2 runs one waiting item's action, as a tap; raising a cap above the company's
    month envelope (the day's cap × 30 over its USD month budget, or no such budget) needs
    🔏 `automation.budget` on `<ref>:<usd_cap>`. Answers what still waits."""
    from hq_api.lines import engine

    async with ctx.tx() as tx:
        kick, wake = await PB.act(ctx, tx, wid, key, body or PB.WaitingIn())
    for ref in kick:
        await engine.kick(ctx.hub, ref)
    for ref in wake:
        await engine.wake(ctx.hub, ref)
    async with ctx.tx() as tx:
        return await PB.waiting(tx)


@router.get("/publications", response_model=PB.PublicationPage, responses=E)
async def publications_list(
    company: str | None = Query(default=None, pattern=CODE),
    account: str | None = Query(default=None, pattern=ACCOUNT),
    channel: Channel | None = Query(default=None),
    kind: PB.PubKind | None = Query(default=None),
    state: PB.PubState | None = Query(default=None),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    automation: str | None = Query(default=None, max_length=120),
    group: str | None = Query(default=None, pattern=r"^set$"),
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=PB.LIST_LIMIT, ge=1, le=PB.LIST_MAX),
    ctx: Ctx = Depends(owner_ctx),
) -> PB.PublicationPage:
    """⟨1.39⟩ §60.2 the archive, newest first. `q` searches the title, the topic, the caption, the
    comment's words and the story word, Persian-folded (ی/ي، ک/ك، spaces and ZWNJ, digits), so
    «بلاکچین», «بلاک چین» and «بلاک‌چین» find the same; each item then says `match` and gives a
    `snippet_fa` (≤ 80 characters). `group=set`: a set of slides as one card."""
    async with ctx.tx() as tx:
        return await PB.page(
            tx, company=company, account=account, channel=channel, kind=kind, state=state,
            from_=from_, to=to, q=q, automation=automation, group=group, cursor=cursor,
            limit=limit,
        )  # fmt: skip


@router.get("/publications/{ref}", response_model=PB.Publication, responses=E)
async def publication_get(
    ref: str = Path(pattern=REF), ctx: Ctx = Depends(owner_ctx)
) -> PB.Publication:
    """⟨1.39⟩ §60.1 one publication: every text, the files with their roles, the times, the source
    («ساخته‌شده با»), `set` (every slide of its set, in order) for a slide of a set."""
    async with ctx.tx() as tx:
        return await PB.get(tx, ref)
