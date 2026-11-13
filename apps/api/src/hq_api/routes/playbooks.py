"""⟨1.22⟩ A session becomes a working group the owner can give to any company (contract §40.2,
§40.3); ⟨1.37⟩ the library of working groups (§59.1, §59.3): the owner's routes.

    POST   /orders/{ref}/playbook {playbook?, log_md?}
                                                 the holder drafts a playbook from the session
                                                 (Idempotency-Key) → Playbook (draft), a card in
                                                 the session; ⟨1.37⟩ with `playbook` (or the one
                                                 the session came from) that playbook's next
                                                 version
    GET    /playbooks?state=&platform=&company=&q=
                                                 the library (with stats, companies, versions)
    POST   /playbooks/import                     ⟨1.37⟩ a `coinepro.playbook/1` file ({file_id} of
                                                 an upload, or the file itself) → a new draft
    GET    /playbooks/{ref}?version=             a version's body (without: the newest sealed,
                                                 else the newest draft)
    GET    /playbooks/{ref}/versions             ⟨1.37⟩ [VersionRef], newest first
    GET    /playbooks/{ref}/compare?a=&b=        ⟨1.37⟩ PlaybookDiff, by code
    GET    /playbooks/{ref}/export?version=      ⟨1.37⟩ the file, no company, account or link
    PATCH  /playbooks/{ref}                      the newest draft only (409 on a sealed one with
                                                 no draft); any field but ref, state, source
    POST   /playbooks/{ref}/revise               ⟨1.37⟩ (Idempotency-Key) the next version as a
                                                 draft, a copy of the newest sealed body
    POST   /playbooks/{ref}/seal {publish?}      the owner's tap (⟨§45⟩ no step-up since
                                                 2026-11-10): ⟨1.37⟩ the newest draft becomes
                                                 version n with its changelog; the first seal
                                                 makes the working group in the database, the
                                                 session's company its first member, with his
                                                 standing word on publishing when he gives it
    PUT    /playbooks/{ref}/members/{code}/version {version}
                                                 ⟨1.37⟩ the owner's tap: that company runs that
                                                 sealed version from its flow's next run
    POST   /playbooks/{ref}/copy {version?, platform?, title_fa?, note_fa?}
                                                 ⟨1.37⟩ (Idempotency-Key) a new draft from a
                                                 version; with a note, a session adapts it
    POST   /playbooks/{ref}/apply {company, platform?, note_fa?, as_is?, publish?}
                                                 (Idempotency-Key) as_is: the company joins the
                                                 sealed group; else a new session for that company
                                                 with the playbook as its first word
    POST   /playbooks/{ref}/retire               the owner's tap: its routines and ⟨1.37⟩ its
                                                 flows stop for every member; nothing deleted

Owner only (owner_ctx). Every write is audited (A1/A2); the seal and the retire are A3.
⟨§45⟩ The owner, 2026-11-10: the passkey is for money, deleting for good, keys and access, and a
destructive command on a server. Sealing a working group hires inside the month's envelope and
retiring it deletes nothing, so both are his tap; a client that still sends a step-up assertion
is answered the same.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query, Request
from fastapi.responses import JSONResponse

from hq_api import idempotency, workflows_client
from hq_api.context import Ctx, owner_ctx
from hq_api.domain import flow_shapes as FS
from hq_api.domain import live as LV
from hq_api.domain import order_report as OR
from hq_api.domain import playbook_versions as PV
from hq_api.domain import playbooks as PB
from hq_api.domain import sessions as SE
from hq_api.errors import ApiError, responses
from hq_api.schemas import Model

router = APIRouter(tags=["playbooks"])
E = responses(401, 403, 404, 409, 422)
IMPORT_MAX_BYTES = 2_000_000


class SealIn(Model):
    """⟨§45⟩ The owner's standing word on publishing for the session's company, given with
    the seal (`PUT /groups/{key}/members/{code}/publish` changes it later)."""

    publish: PB.PublishRuleIn | None = None


async def _standing(ctx: Ctx, tx: Any, ref: str, company: Any, rule: PB.PublishRuleIn) -> None:
    """The owner's standing word for one member of the playbook's group, audited as his."""
    from hq_api.domain import session_publish as SPB

    row = await PB.row_of(tx, ref)
    if row.get("group_id") is None:
        return
    set_to = await SPB.set_rule(
        tx, row["group_id"], company.id, mode=rule.mode, account=rule.account,
        story=rule.story, at=rule.at, best=rule.best,
    )  # fmt: skip
    key = PB.group_key(ref)
    await ctx.audit(tx, company_id=company.id, action="group.publish", action_class="A3",
                    target_kind="group", target_ref=f"{key}:{company.code}",
                    summary=f"the owner's standing permission to publish: {set_to['mode']}")  # fmt: skip


async def _out(tx: Any, ref: str, version: int | None = None) -> PB.Playbook:
    return await PB.render(tx, await PB.row_of(tx, ref), version)


async def _holding_id(ctx: Ctx) -> UUID:
    return (await ctx.hub.companies.holding()).id


# ------------------------------------------------------------------- draft --
@router.post("/orders/{ref}/playbook", response_model=PB.Playbook, status_code=201, responses=E)
async def draft_playbook(
    ref: str, request: Request, body: PB.DraftIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """The holder drafts a working group from this session (open or closed): one model call over
    the memory, the plan, the people hired into it, its automations, lines and cards, checked by
    code (a seat's role must be a real charter, a routine's schedule a rule the calendar holds;
    the rest is dropped with a note in `note_fa`). Stored `draft`; a card «کارگروه از این جلسه»
    is posted in the session. ⟨1.37⟩ §59.3 with `playbook` (or when the session came from one of
    the same working group) the draft is that playbook's next version, with its `steps` (the
    owner's steps in his order) and `lessons` (the session's fault log, `log_md`). Requires
    `Idempotency-Key`."""
    # The key is claimed with the draft it answers (as apply does): a claim committed before
    # the model call would answer every retry 409 «still running» for 24 h once a later step
    # failed.
    given = body or PB.DraftIn()
    async with ctx.tx() as tx:
        idempotency.read_key(request, required=True)
        if await OR.ensure(tx, ref) is None:
            raise ApiError(404, "not_found", "unknown order", message_fa=SE.NOT_FOUND_FA)
        if given.playbook:
            await PB.row_of(tx, given.playbook)
    d, m, notes = await PB.draft(ctx, ref, playbook=given.playbook, log_md=given.log_md)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        holding = await ctx.hub.companies.holding()
        row = await PB.store_draft(tx, holding.id, m, d, notes)
        what = f"v{row['version']} of {m.target}" if m.target else f"{len(d['seats'])} seats"
        what += f", {len(d['steps'])} steps, {len(d['lessons'])} lessons"
        await ctx.audit(tx, company_id=holding.id, action="playbook.draft", action_class="A1",
                        target_kind="playbook", target_ref=row["ref"], summary=f"from {ref}: {what}")  # fmt: skip
        result = await PB.render(tx, await PB.row_of(tx, row["ref"]), int(row["version"]))
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# ----------------------------------------------------------------- library --
@router.get("/playbooks", response_model=list[PB.Playbook], responses=E)
async def list_playbooks(
    state: Literal["draft", "sealed", "retired"] | None = None,
    platform: PB.Platform | None = None,
    company: str | None = Query(default=None, max_length=10),
    q: str | None = Query(default=None, max_length=200),
    ctx: Ctx = Depends(owner_ctx),
) -> list[PB.Playbook]:
    """The library: every playbook, newest first, with its versions, the member companies and
    the last 30 days of its flow runs (`steps`, `package` and `lessons` left empty here).
    `state`, `platform`, `company` (a member or the source company) and `q` (Persian words over
    the title and the purpose) narrow it."""
    async with ctx.tx() as tx:
        return await PB.listing(tx, state, platform, company, q)


@router.post("/playbooks/import", response_model=PB.Playbook, status_code=201, responses=E)
async def import_playbook(
    request: Request, body: dict[str, Any] = Body(...), ctx: Ctx = Depends(owner_ctx)
) -> Any:
    """⟨1.37⟩ §59.1 a playbook file (`coinepro.playbook/1`) becomes a new draft: `{file_id}` of a
    file already uploaded (`POST /files`), or the file's JSON itself. What the hub cannot run
    (a role no charter has, a step kind the line engine does not run, a helper it does not
    have) is dropped and named in `note_fa`. 422 for anything else. Requires
    `Idempotency-Key`. (The api has no multipart parser: a phone uploads first.)"""
    idempotency.read_key(request, required=True)
    raw: Any = body
    if body.get("format") is None:
        try:
            file_id = UUID(str(body.get("file_id") or ""))
        except ValueError as exc:
            raise ApiError(422, "validation_failed", fields={"file_id": "a file id or the file"},
                           message_fa=PV.NOT_A_PLAYBOOK_FA) from exc  # fmt: skip
        async with ctx.tx() as tx:
            f = await tx.first(
                "SELECT storage_key, size FROM files.files WHERE id = :id", id=file_id
            )
        if f is None:
            raise ApiError(404, "not_found", "unknown file", message_fa="این فایل پیدا نشد.")
        if int(f["size"] or 0) > IMPORT_MAX_BYTES:
            raise ApiError(422, "validation_failed", fields={"file_id": "too large"},
                           message_fa="این فایل برای یک کارگروه بزرگ است.")  # fmt: skip
        raw = await ctx.hub.storage.get(str(f["storage_key"]))
    doc = PV.read_doc(raw)
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        holding_id = await _holding_id(ctx)
        row = await PB.import_file(tx, ctx.hub, holding_id, doc)
        await ctx.audit(tx, company_id=holding_id, action="playbook.import", action_class="A1",
                        target_kind="playbook", target_ref=row["ref"],
                        summary=f"from a file (v{doc.get('version')})")  # fmt: skip
        result = await _out(tx, row["ref"])
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


@router.get("/playbooks/{ref}", response_model=PB.Playbook, responses=E)
async def get_playbook(
    ref: str, version: int | None = Query(default=None, ge=1), ctx: Ctx = Depends(owner_ctx)
) -> PB.Playbook:
    """One playbook: its seats, routines, KPIs, connections, rules, source and members; ⟨1.37⟩ at
    `version` (its state is that version's), else its newest sealed body, else its newest
    draft; with every version, its flow, its package and its lessons."""
    async with ctx.tx() as tx:
        return await _out(tx, ref, version)


@router.get("/playbooks/{ref}/versions", response_model=list[FS.VersionRef], responses=E)
async def playbook_versions(ref: str, ctx: Ctx = Depends(owner_ctx)) -> list[FS.VersionRef]:
    """⟨1.37⟩ Every version, newest first, with what changed and how many companies run it."""
    async with ctx.tx() as tx:
        return (await _out(tx, ref)).versions


@router.get("/playbooks/{ref}/compare", response_model=FS.PlaybookDiff, responses=E)
async def compare_playbook(
    ref: str,
    a: int = Query(ge=1),
    b: int = Query(ge=1),
    ctx: Ctx = Depends(owner_ctx),
) -> FS.PlaybookDiff:
    """⟨1.37⟩ What differs from version `a` to version `b`, by code (never a model): the same lines
    a sealed version's `changelog_fa` is made of."""
    async with ctx.tx() as tx:
        _, body_a, _ = await PB.body_at(tx, ref, a)
        _, body_b, _ = await PB.body_at(tx, ref, b)
    return FS.PlaybookDiff(a=a, b=b, changes=PV.compare(body_a, body_b))


@router.get("/playbooks/{ref}/export", response_class=JSONResponse, responses=E)
async def export_playbook(
    ref: str, version: int | None = Query(default=None, ge=1), ctx: Ctx = Depends(owner_ctx)
) -> JSONResponse:
    """⟨1.37⟩ The playbook as its own file, `coinepro.playbook/1` (`<title>-v<n>.playbook.json`):
    its seats, flow, package, routines, KPIs, connections, rules and lessons; no company,
    account, link, narrator or member."""
    async with ctx.tx() as tx:
        _, body, number = await PB.body_at(tx, ref, version)
    name = PV.export_name(str(body.get("title_fa") or ref), number)
    return JSONResponse(
        PV.export_doc(body, number),
        headers={
            "Content-Disposition": (
                f'attachment; filename="playbook-v{number}.playbook.json"; '
                f"filename*=UTF-8''{quote(name)}"
            ),
            "Cache-Control": "no-store",
        },
    )


@router.patch("/playbooks/{ref}", response_model=PB.Playbook, responses=E)
async def patch_playbook(
    ref: str, body: PB.PlaybookPatch, ctx: Ctx = Depends(owner_ctx)
) -> PB.Playbook:
    """The owner edits the newest draft directly (⟨1.37⟩ 409 «این نسخه مُهر شده؛ تغییر، نسخه‌ی
    تازه میسازد» on a sealed playbook with no draft: `POST …/revise` first): any field of the
    shape but `ref`, `state`, `source`, and `steps`, `package`, `lessons` (each list whole). What
    does not hold (an unknown role, a bad schedule, a step kind the hub does not run) is
    dropped with a note in `note_fa`; `edits` counts up. Answers the draft."""
    async with ctx.tx() as tx:
        row = await PB.patch(tx, ctx.hub, ref, body.model_dump())
        holding = await ctx.hub.companies.holding()
        changed = ", ".join(k for k, v in body.model_dump().items() if v is not None)
        await ctx.audit(tx, company_id=holding.id, action="playbook.edit", action_class="A1",
                        target_kind="playbook", target_ref=ref,
                        summary=f"v{row['version']}: {changed}")  # fmt: skip
        return await PB.render(tx, await PB.row_of(tx, ref), int(row["version"]))


@router.post("/playbooks/{ref}/revise", response_model=PB.Playbook, status_code=201, responses=E)
async def revise_playbook(ref: str, request: Request, ctx: Ctx = Depends(owner_ctx)) -> Any:
    """⟨1.37⟩ §59.1 the next version as a draft, a copy of the newest sealed body; the sealed one
    keeps running for every member. A draft already there is answered as it is. Requires
    `Idempotency-Key`."""
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        row, number, made = await PB.revise(tx, ref)
        if made:
            await ctx.audit(tx, company_id=row["company_id"], action="playbook.revise",
                            action_class="A1", target_kind="playbook", target_ref=ref,
                            summary=f"v{number} drafted")  # fmt: skip
        result = await _out(tx, ref, number)
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    return result


# -------------------------------------------------------------------- seal --
@router.post("/playbooks/{ref}/seal", response_model=PB.Playbook, responses=E)
async def seal_playbook(
    ref: str, body: SealIn | None = None, ctx: Ctx = Depends(owner_ctx)
) -> PB.Playbook:
    """The owner's tap (⟨§45⟩ no step-up): the draft becomes a working group stored in the
    database (eligibility `chosen`: only the companies the owner gives it to) and the session's
    company its first member, the seats resolved to the people the session hired, the empty ones
    filled by automatic hiring inside the envelope; its routines run from their next time.
    `publish`: his standing word for that company (`auto`: each routine's package goes out by
    itself from the next run; left out: each waits for his tap)."""
    async with ctx.tx() as tx:
        row = await PB.seal(tx, ctx.hub, ref)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="playbook.seal", action_class="A3",
                        target_kind="playbook", target_ref=ref,
                        summary=f"group {PB.group_key(ref)}")  # fmt: skip
        src = PB._j(row["source"]) or {}
        first = await ctx.hub.companies.find(str(src.get("company") or ""))
        rule = body.publish if body is not None else None
        if rule is not None and first is not None and first.kind != "holding":
            await _standing(ctx, tx, ref, first, rule)
        await ctx.interaction(tx, company_id=holding.id, kind="decision", action="playbook.seal",
                              target_kind="playbook", target_ref=ref, data={"state": "sealed"})  # fmt: skip
        return await PB.render(tx, row)


# ------------------------------------------------------ ⟨1.37⟩ a member's version --
@router.put(
    "/playbooks/{ref}/members/{code}/version", response_model=PB.PlaybookMember, responses=E
)
async def use_version(
    ref: str, code: str, body: PB.MemberVersionIn, ctx: Ctx = Depends(owner_ctx)
) -> PB.PlaybookMember:
    """«استفاده از این نسخه»: the owner's tap; that company runs this sealed version from its
    flow's next run (its membership and its flow automation). A draft or a retired version:
    409."""
    async with ctx.tx() as tx:
        company = await ctx.hub.companies.find(code)
        before = None
        if company is not None:
            before = await tx.scalar(
                """SELECT m.version FROM growth.memberships m JOIN owner.playbooks p
                       ON p.group_id = m.group_id WHERE p.ref = :r AND m.company_id = :co""",
                r=ref,
                co=company.id,
            )
        member = await PB.set_member_version(tx, ctx.hub, ref, code, body.version)
        assert company is not None
        await ctx.audit(tx, company_id=company.id, action="playbook.version", action_class="A2",
                        target_kind="playbook", target_ref=f"{ref}:{code}",
                        summary=f"v{before or 1} -> v{body.version}")  # fmt: skip
        return member


# -------------------------------------------------------------- ⟨1.37⟩ copy --
@router.post("/playbooks/{ref}/copy", response_model=PB.PlaybookApplied, status_code=201,
             responses=E)  # fmt: skip
async def copy_playbook(
    ref: str,
    body: PB.PlaybookCopyIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """A new playbook in draft (v1) from a version of this one (without: its current body), its
    steps and rules as they were, the platform and the title changed; `parent` this one at that
    version. With `note_fa` the copy also opens a session as `apply` does, for the holding: its
    media lead adapts it there (a YouTube or a Telegram flow from an Instagram one), and the
    draft made in that session is the copy's. Requires `Idempotency-Key`."""
    from hq_api.routes.orders import record_order, secretary

    holding = await ctx.hub.companies.holding()
    if not body.note_fa:
        async with ctx.tx() as tx:
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                return idem.replay
            row = await PB.copy(tx, ctx.hub, holding.id, ref, body)
            await ctx.audit(tx, company_id=holding.id, action="playbook.copy", action_class="A1",
                            target_kind="playbook", target_ref=row["ref"],
                            summary=f"from {ref} v{body.version or 'current'} ({body.platform or 'same'})")  # fmt: skip
            result = PB.PlaybookApplied(playbook=await _out(tx, row["ref"]))
            if idem:
                await idem.store(tx, 201, result.model_dump(mode="json"))
        return result
    async with ctx.tx() as tx:
        idempotency.read_key(request, required=True)  # before the secretary's call
        _, _, number = await PB.body_at(tx, ref, body.version)
        pb = await _out(tx, ref, number)
    text = PB.copy_text(pb, body.platform, body.note_fa)
    s = await secretary(ctx, text, holding.code)
    later: list[Any] = []
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await record_order(ctx, tx, s, text, later, source="text", hint=holding.code,
                                 remember=False)  # fmt: skip
        row = await PB.copy(tx, ctx.hub, holding.id, ref, body, order=out.ref,
                            conversation=out.talk_ref)  # fmt: skip
        await PB.mark_source(tx, out.ref, row["ref"])
        rep = await OR.ensure(tx, out.ref)
        if rep is not None and rep.get("conversation_ref"):
            from hq_api.domain import order_turns as OT

            await OT.to_talk_owner(tx, rep, text)
            await SE.remember(tx, rep["id"], f"این جلسه از کارگروه {row['ref']} باز شد")
        await ctx.audit(tx, company_id=holding.id, action="playbook.copy", action_class="A2",
                        target_kind="playbook", target_ref=row["ref"],
                        summary=f"from {ref} v{number}, session {out.ref} ({body.platform or 'same'})")  # fmt: skip
        result = PB.PlaybookApplied(playbook=await _out(tx, row["ref"]), order=out.ref,
                                    conversation=out.talk_ref)  # fmt: skip
        if idem:
            await idem.store(tx, 201, result.model_dump(mode="json"))
    for job in later:
        if job[0] == "decision":
            background.add_task(workflows_client.decision_created, ctx.hub, job[1])
        else:
            background.add_task(job[0], ctx.hub, *job[1:])
    return result


# ------------------------------------------------------------------- apply --
@router.post("/playbooks/{ref}/apply", response_model=PB.PlaybookApplied, responses=E)
async def apply_playbook(
    ref: str,
    body: PB.PlaybookApplyIn,
    request: Request,
    background: BackgroundTasks,
    ctx: Ctx = Depends(owner_ctx),
) -> Any:
    """Give the playbook to another company or platform. `as_is` (sealed only): the company joins
    the working group at once, no session. Else a new order for that company, held by its CEO
    (or the manager of the matching department), whose first word is the playbook as Markdown
    and the owner's note («این کارگروه را برای … روی … پیاده کن»); the holder adapts it there, and
    sealing the draft made from that session records `parent`. Requires `Idempotency-Key`."""
    from hq_api.routes.orders import record_order, secretary

    company = await ctx.hub.companies.find(body.company)
    if company is None or company.kind == "holding":
        raise ApiError(404, "not_found", "unknown company", message_fa="این شرکت را نمیشناسم.")
    if body.as_is:
        async with ctx.tx() as tx:
            idem = await idempotency.claim(tx, request, ctx.who, required=True)
            if idem and idem.replay:
                return idem.replay
            await PB.apply_as_is(tx, ctx.hub, ref, company)
            if body.publish is not None:  # ⟨§45⟩ his standing word for this company, with the gift
                await _standing(ctx, tx, ref, company, body.publish)
            await LV.playbook_flow(tx, await PB.row_of(tx, ref), company.code, None)
            await ctx.audit(tx, company_id=company.id, action="playbook.apply", action_class="A2",
                            target_kind="playbook", target_ref=ref, summary=f"as is: {company.code}")  # fmt: skip
            pb = await _out(tx, ref)
            member = next((x for x in pb.members if x.company == company.code), None)
            result = PB.PlaybookApplied(playbook=pb, member=member)
            if idem:
                await idem.store(tx, 200, result.model_dump(mode="json"))
        return result
    async with ctx.tx() as tx:
        idempotency.read_key(request, required=True)  # before the secretary's call
        row = await PB.row_of(tx, ref)
        if row["state"] == "retired":
            raise ApiError(409, "validation_failed", "the playbook is retired",
                           message_fa="این کارگروه بازنشسته شده است.")  # fmt: skip
        pb = await PB.render(tx, row)
    text = PB.apply_text(pb, company.name_fa or company.code, body.platform, body.note_fa)
    s = await secretary(ctx, text, company.code)
    later: list[Any] = []
    async with ctx.tx() as tx:
        idem = await idempotency.claim(tx, request, ctx.who, required=True)
        if idem and idem.replay:
            return idem.replay
        out = await record_order(ctx, tx, s, text, later, source="text", hint=company.code,
                                 remember=False)  # fmt: skip
        await PB.mark_source(tx, out.ref, ref)
        await LV.playbook_flow(
            tx, row, company.code, out.routes[0].work_ref if out.routes else None
        )
        rep = await OR.ensure(tx, out.ref)
        if rep is not None and rep.get("conversation_ref"):
            from hq_api.domain import order_turns as OT

            await OT.to_talk_owner(tx, rep, text)
            await SE.remember(tx, rep["id"], f"این جلسه از کارگروه {ref} باز شد")
        await ctx.audit(tx, company_id=company.id, action="playbook.apply", action_class="A2",
                        target_kind="playbook", target_ref=ref,
                        summary=f"session {out.ref} for {company.code} ({body.platform or 'any'})")  # fmt: skip
        result = PB.PlaybookApplied(playbook=await _out(tx, ref), order=out.ref,
                                    conversation=out.talk_ref)  # fmt: skip
        if idem:
            await idem.store(tx, 200, result.model_dump(mode="json"))
    for job in later:
        if job[0] == "decision":
            background.add_task(workflows_client.decision_created, ctx.hub, job[1])
        else:
            background.add_task(job[0], ctx.hub, *job[1:])
    return result


# ------------------------------------------------------------------ retire --
@router.post("/playbooks/{ref}/retire", response_model=PB.Playbook, responses=E)
async def retire_playbook(ref: str, ctx: Ctx = Depends(owner_ctx)) -> PB.Playbook:
    """The owner's tap (⟨§45⟩ no step-up): its routines stop for every member (the group `off`);
    nothing is deleted."""
    async with ctx.tx() as tx:
        row = await PB.retire(tx, ref)
        holding = await ctx.hub.companies.holding()
        await ctx.audit(tx, company_id=holding.id, action="playbook.retire", action_class="A3",
                        target_kind="playbook", target_ref=ref, summary="retired")  # fmt: skip
        return await PB.render(tx, row)
