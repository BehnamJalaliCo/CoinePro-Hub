"""Records, versions, links (prompt 14 §3, contract §23.1, §23.12).

A record (AR-000001) belongs to one scope (the holding or a company), has a
class (null only on an imported draft), a level, a state and its versions.
Drafts: an agent's `archive.file`, an import, the owner's own with
`file: false`. Filed: the owner (or the hub's system sources) files it
complete. Sealed: the owner's seal on the current version's manifest; a
sealed record keeps its title, class, metadata, parties and folder (409
sealed_record), its access level is outside the seal; a new version
supersedes the sealed one and the record is `filed` again. A record under a
legal hold answers 423 held to any change except a new version.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from hq_api import audit, events
from hq_api.archive import automations as AU
from hq_api.archive import clearance as CL
from hq_api.archive import retention as RT
from hq_api.archive import scan
from hq_api.archive import schema as SC
from hq_api.archive import store as ST
from hq_api.archive import vocab as V
from hq_api.archive.common import J, actor_of, dumps, invalid
from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_common import persian

RECORD_SQL = """
    SELECT r.*, co.code AS scope, f.ref AS folder_ref, x.ref AS retention_ref, x.then_do AS retention_then
    FROM archive.records r
    JOIN core.companies co ON co.id = r.company_id
    LEFT JOIN archive.folders f ON f.id = r.folder_id
    LEFT JOIN archive.retention_rules x ON x.id = r.retention_rule_id
"""
HELD_MESSAGE = "این سند زیر توقیف قانونی است؛ جز نسخه‌ی تازه هیچ تغییری نمی‌پذیرد."


# ================================================================ loading ==
async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    """A record the reader may see (RLS); one it may not is 404, or 403
    clearance where the reader already knows the ref (a link names it)."""
    row = await tx.first(
        RECORD_SQL + " WHERE r.ref = :r" + (" FOR UPDATE OF r" if lock else ""), r=ref
    )
    if row is not None:
        return row
    known = await tx.scalar(
        "SELECT 1 FROM archive.links WHERE to_kind = 'record' AND to_ref = :r AND removed_at IS NULL LIMIT 1",
        r=ref,
    )
    if known:
        raise ApiError(403, "clearance", "the record is above your clearance")
    raise ApiError(404, "not_found", f"no record {ref}")


async def held(tx: Tx, record_id: UUID) -> list[str]:
    refs = await tx.scalar("SELECT archive.held_by(:r)", r=record_id)
    return list(refs or [])


async def require_not_held(tx: Tx, r: dict[str, Any]) -> None:
    if await held(tx, r["id"]):
        raise ApiError(423, "held", f"{r['ref']} is under a legal hold", message_fa=HELD_MESSAGE)


def require_live(r: dict[str, Any]) -> None:
    if r["state"] == "disposed":
        raise ApiError(409, "sealed_record", f"{r['ref']} was disposed")


async def class_fields(tx: Tx, r: dict[str, Any]) -> list[dict[str, Any]]:
    if not r["class_key"]:
        return []
    c = await SC.class_at(tx, r["class_key"], r["class_version"])
    return list(c["fields"])


# ============================================================== rendering ==
def _actor(kind: str, code: str) -> dict[str, Any]:
    if kind == "owner":
        return {"kind": "owner", "code": "owner", "display_fa": "مدیر کل"}
    if kind in ("service", "system"):
        return {"kind": "service", "code": code, "display_fa": "سامانه"}
    return {"kind": "agent", "code": code, "display_fa": None}


async def render_links(tx: Tx, r: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    rows = await tx.all(
        """SELECT l.*, k.title_fa AS kind_title, k.inverse_fa FROM archive.links l
           JOIN archive.link_kinds k ON k.key = l.kind
           WHERE l.record_id = :r AND l.removed_at IS NULL ORDER BY l.created_at""",
        r=r["id"],
    )
    for x in rows:
        out.append(
            {
                "kind": x["kind"],
                "to_kind": x["to_kind"],
                "to_ref": x["to_ref"],
                "to": {"kind": x["to_kind"], "ref": x["to_ref"]},
                "title_fa": x["title_fa"],
                "at": x["created_at"],
                "by": _actor(x["by_kind"], x["by_code"]),
                "sealed": x["sealed"],
                "inverse": False,
            }
        )
    # Links of other (visible) records to this one, with the inverse name.
    for x in await tx.all(
        """SELECT l.kind, l.created_at, l.by_kind, l.by_code, l.sealed, k.inverse_fa, s.ref, s.title_fa
           FROM archive.links l JOIN archive.records s ON s.id = l.record_id
           JOIN archive.link_kinds k ON k.key = l.kind
           WHERE l.to_kind = 'record' AND l.to_ref = :ref AND l.removed_at IS NULL ORDER BY l.created_at""",
        ref=r["ref"],
    ):
        out.append(
            {
                "kind": x["kind"],
                "to_kind": "record",
                "to_ref": x["ref"],
                "to": {"kind": "record", "ref": x["ref"]},
                "title_fa": x["title_fa"],
                "at": x["created_at"],
                "by": _actor(x["by_kind"], x["by_code"]),
                "sealed": x["sealed"],
                "inverse": True,
                "inverse_fa": x["inverse_fa"],
            }
        )
    return out


async def render_versions(tx: Tx, r: dict[str, Any], *, content: bool) -> list[dict[str, Any]]:
    versions = await tx.all(
        "SELECT * FROM archive.record_versions WHERE record_id = :r ORDER BY n", r=r["id"]
    )
    files = (
        await tx.all(
            """SELECT file_id, version_n, name, mime, size_bytes, sha256, pages, text_state, ocr_confidence,
                      low_conf_pages, quarantined, destroyed_at
               FROM archive.record_files WHERE record_id = :r ORDER BY version_n, name""",
            r=r["id"],
        )
        if content
        else []
    )
    out = []
    for v in versions:
        out.append(
            {
                "n": v["n"],
                "files": [
                    {
                        "file_id": f["file_id"],
                        "name": f["name"],
                        "mime": f["mime"],
                        "size_bytes": int(f["size_bytes"]),
                        "sha256": f["sha256"],
                        "pages": f["pages"],
                        "text_state": f["text_state"],
                        "ocr_confidence": float(f["ocr_confidence"])
                        if f["ocr_confidence"] is not None
                        else None,
                        "low_confidence_pages": list(f["low_conf_pages"] or []),
                        "quarantined": f["quarantined"],
                        "destroyed": f["destroyed_at"] is not None,
                    }
                    for f in files
                    if f["version_n"] == v["n"]
                ],
                "manifest_sha256": v["manifest_sha256"],
                "note_fa": v["note_fa"],
                "created_by": _actor(v["created_by_kind"], v["created_by_code"]),
                "created_at": v["created_at"],
                "sealed": v["sealed"],
                "sealed_at": v["sealed_at"],
                "state": v["state"],
            }
        )
    return out


async def render(
    tx: Tx, r: dict[str, Any], c: CL.Clearance, *, full: bool = True
) -> dict[str, Any]:
    """The Record of §23.1/§23.12 as this reader may see it."""
    fields = await class_fields(tx, r)
    content = c.sees(r["level_rank"], r["company_id"])
    conf = await tx.scalar("SELECT rank FROM archive.levels WHERE key = 'confidential'")
    full_view = c.rank_in(r["company_id"]) >= (int(conf) if conf is not None else 20)
    meta, hidden = V.mask_metadata(fields, J(r["metadata"], {}), agent=c.agent, full=full_view)
    holds = await held(tx, r["id"])
    out: dict[str, Any] = {
        "id": r["id"],
        "ref": r["ref"],
        "scope": r["scope"],
        "class": r["class_key"],
        "class_version": r["class_version"],
        "title_fa": r["title_fa"],
        "folder": r["folder_ref"],
        "level": r["level"],
        "state": r["state"],
        "metadata": meta,
        "masked": hidden,
        "doc_date": r["doc_date"],
        "parties": J(r["parties"], []),
        "holds": holds,
        "retention": {
            "rule": r["retention_ref"],
            "trigger_at": r["trigger_at"],
            "review_at": r["due_at"],
            "disposable": r["disposable"],
        },
        "current_version": r["current_version"],
        "source": {"kind": r["source_kind"], "ref": r["source_ref"]},
        "created_by": _actor(r["created_by_kind"], r["created_by_code"]),
        "created_at": r["created_at"],
        "filed_at": r["filed_at"],
        "sealed_at": r["sealed_at"],
        "suggestion": J(r["suggestion"]) if r["state"] == "draft" else None,
        "tombstone": None,
        "content_visible": content,
        "version": r["version"],
    }
    if full:
        out["versions"] = await render_versions(tx, r, content=content)
        out["links"] = await render_links(tx, r)
        out["reminders"] = [
            {
                "id": x["id"],
                "field": x["field"],
                "at": x["at"],
                "lead_days": x["lead_days"],
                "state": x["state"],
                "due_at": x["due_at"],
            }
            for x in await tx.all(
                "SELECT * FROM archive.reminders WHERE record_id = :r ORDER BY at, lead_days DESC",
                r=r["id"],
            )
        ]
    if r["state"] == "disposed":
        t = await tx.first("SELECT * FROM archive.tombstones WHERE record_id = :r", r=r["id"])
        if t is not None:
            out["tombstone"] = {
                "decision": t["decision_ref"],
                "at": t["at"],
                "hashes": J(t["hashes"], []),
                "dates": J(t["dates"], {}),
            }
    return out


# ============================================================ preparation ==
async def resolve_class(tx: Tx, key: str | None, scope_code: str) -> dict[str, Any] | None:
    if key is None:
        return None
    row = await SC.class_row(tx, key)
    if row is None or row["status"] != "active":
        raise invalid({"class": "an active class of the schema"})
    c = SC.render_class(row)
    if c["scopes"] != "all" and scope_code not in c["scopes"]:
        raise invalid({"class": f"not used in {scope_code}"})
    return c


async def resolve_level(
    tx: Tx, key: str | None, cls: dict[str, Any] | None, folder: dict[str, Any] | None
) -> dict[str, Any]:
    chosen = (
        key or (folder or {}).get("default_level") or (cls or {}).get("default_level") or "internal"
    )
    lv = await SC.level(tx, chosen)
    if lv is None or lv["status"] != "active":
        raise invalid({"level": "an active level"})
    return lv


async def default_folder(
    tx: Tx, company_id: UUID, scope_code: str, cls: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The first folder of the scope whose classes include the class; else the
    class's default folder if it lies in that scope (contract §23.12)."""
    if not await tx.scalar(
        "SELECT 1 FROM archive.folders WHERE company_id = :c LIMIT 1", c=company_id
    ):
        await SC.seed_folders(tx, company_id, scope_code)
    if cls is None:
        return None
    row = await tx.first(
        """SELECT * FROM archive.folders WHERE company_id = :c AND status = 'active' AND :k = ANY (classes)
           ORDER BY sort, ref LIMIT 1""",
        c=company_id,
        k=cls["key"],
    )
    if row is None and cls.get("default_folder"):
        row = await tx.first(
            "SELECT * FROM archive.folders WHERE ref = :r AND company_id = :c AND status = 'active'",
            r=cls["default_folder"],
            c=company_id,
        )
    return row


async def resolve_folder(
    tx: Tx, ref: str | None, company_id: UUID, scope_code: str, cls: dict[str, Any] | None
) -> dict[str, Any] | None:
    if ref is None:
        return await default_folder(tx, company_id, scope_code, cls)
    row = await tx.first(
        "SELECT * FROM archive.folders WHERE ref = :r AND status = 'active'", r=ref
    )
    if row is None or row["company_id"] != company_id:
        raise invalid({"folder": "an active folder of this scope"})
    if cls is not None and row["classes"] and cls["key"] not in row["classes"]:
        raise invalid({"folder": f"this folder does not take {cls['key']}"})
    return row


async def check_parties(
    tx: Tx, parties: list[dict[str, Any]] | None
) -> tuple[list[dict[str, Any]], list[str]]:
    out, refs = [], []
    for i, p in enumerate(parties or []):
        ref = p.get("party") if isinstance(p, dict) else None
        if not isinstance(ref, str) or not await tx.scalar(
            "SELECT 1 FROM archive.parties WHERE ref = :r AND status = 'active'", r=ref
        ):
            raise invalid({f"parties.{i}.party": "an active party of the registry"})
        role = str(p.get("role_fa") or "")[:120]
        out.append({"party": ref, "role_fa": role})
        refs.append(ref)
    return out, list(dict.fromkeys(refs))


def doc_date_of(fields: list[dict[str, Any]], metadata: dict[str, Any]) -> date | None:
    for f in fields:
        v = metadata.get(f["key"])
        if v is None:
            continue
        if f["type"] == "date":
            return date.fromisoformat(v)
        if f["type"] == "date_range":
            return date.fromisoformat(v["from"])
    return None


def watch_dates_of(
    cls: dict[str, Any] | None, fields: list[dict[str, Any]], metadata: dict[str, Any]
) -> list[date]:
    if cls is None:
        return []
    by_key = {f["key"]: f for f in fields}
    out = []
    for k in cls.get("reminder_fields") or []:
        d = V.field_dates(by_key.get(k), metadata.get(k))
        if d is not None:
            out.append(d)
    return out


def check_files(cls: dict[str, Any] | None, items: list[ST.Intake], *, complete: bool) -> None:
    if cls is None:
        return
    allowed = set(cls.get("allowed_mime") or V.MIMES)
    for it in items:
        if it.mime not in allowed:
            raise invalid({"file_ids": f"{it.name}: {it.mime} is not taken by {cls['key']}"})
    if complete and len(items) < int(cls.get("required_files") or 0):
        raise invalid({"file_ids": f"{cls['key']} needs at least {cls['required_files']} file(s)"})


def no_secret(values: dict[str, Any]) -> None:
    if scan.values_kinds(values):
        raise ApiError(
            422,
            "secret_in_document",
            "a secret pattern was found in what was written; nothing was stored",
            fields={"metadata": "secret pattern"},
        )


# ================================================================ writing ==
async def search_vectors(tx: Tx, r: dict[str, Any], fields: list[dict[str, Any]]) -> None:
    """meta_tsv (title, ref, searchable values, party names), sens_tsv (the
    sensitive searchable values), text_tsv (the current version's text)."""
    metadata = J(r["metadata"], {})
    plain, sens = V.search_words(fields, metadata)
    party_names = await tx.scalar(
        "SELECT string_agg(name_fa || ' ' || COALESCE(name_en, ''), ' ') FROM archive.parties WHERE ref = ANY(:p)",
        p=list(r["party_refs"] or []),
    )
    meta_doc = persian.normalise(f"{r['title_fa']} {r['ref']} {plain} {party_names or ''}")
    await tx.exec(
        """UPDATE archive.records SET
               meta_tsv = to_tsvector('simple', core.fa_normalize(:m)),
               sens_tsv = to_tsvector('simple', core.fa_normalize(:s)),
               text_tsv = (SELECT to_tsvector('simple', core.fa_normalize(
                                      left(COALESCE(string_agg(f.text, ' '), ''), 400000)))
                           FROM archive.record_files f
                           WHERE f.record_id = :id AND f.version_n = :v AND f.destroyed_at IS NULL
                             AND NOT f.quarantined)
           WHERE id = :id""",
        id=r["id"],
        m=meta_doc,
        s=persian.normalise(sens),
        v=r["current_version"],
    )


async def insert_files(
    tx: Tx, r: dict[str, Any], n: int, stored: list[ST.Stored], ocr_on: bool
) -> str:
    rows = []
    for s in stored:
        it = s.intake
        await tx.exec(
            """INSERT INTO archive.record_files (company_id, record_id, version_n, file_id, name, mime, size_bytes,
                   sha256, stored_sha256, storage_key, encrypted, wrapped_dek, pages, text_state, ocr_wanted,
                   ocr_confidence, low_conf_pages, text)
               VALUES (:co, :r, :n, :f, :name, :mime, :size, :sha, :ssha, :key, :enc, :dek, :pages, :ts, :ow,
                       :oc, :lp, :text)""",
            co=r["company_id"],
            r=r["id"],
            n=n,
            f=it.file_id,
            name=it.name[:255],
            mime=it.mime,
            size=it.size,
            sha=it.sha256,
            ssha=s.stored_sha256,
            key=s.storage_key,
            enc=s.encrypted,
            dek=s.wrapped_dek,
            pages=it.pages,
            ts=it.text_state,
            ow=bool(ocr_on and it.ocr_wanted),
            oc=it.ocr_confidence,
            lp=it.low_pages,
            text=it.text,
        )
        rows.append({"sha256": it.sha256, "name": it.name})
    return ST.manifest(rows)


async def create(
    tx: Tx,
    who: Principal,
    *,
    scope: dict[str, Any],
    cls: dict[str, Any] | None,
    title_fa: str,
    metadata: dict[str, Any],
    lv: dict[str, Any],
    folder: dict[str, Any] | None,
    stored: list[ST.Stored],
    parties: list[dict[str, Any]] | None,
    links: list[dict[str, Any]] | None,
    file_now: bool,
    source_kind: str,
    source_ref: str | None = None,
    suggestion: dict[str, Any] | None = None,
    note_fa: str | None = None,
) -> dict[str, Any]:
    """A record and its first version, in the caller's transaction (the files
    are already stored: ST.ingest)."""
    fields = list(cls["fields"]) if cls else []
    clean, _missing, errors = V.validate_metadata(fields, metadata, complete=file_now)
    if errors:
        raise invalid(errors)
    no_secret({"title_fa": title_fa, "metadata": clean, "note_fa": note_fa or ""})
    check_files(cls, [s.intake for s in stored], complete=file_now)
    party_rows, party_refs = await check_parties(tx, parties)
    kind, code = actor_of(who)
    dd = doc_date_of(fields, clean)
    row = await tx.one(
        """INSERT INTO archive.records (company_id, class_key, class_version, title_fa, folder_id, level, level_rank,
               state, metadata, doc_date, parties, party_refs, watch_dates, source_kind, source_ref, suggestion,
               created_by_kind, created_by_code, filed_at)
           VALUES (:co, :ck, :cv, :t, :fo, :lv, :lr, :st, CAST(:m AS jsonb), :dd, CAST(:p AS jsonb), :pr, :wd,
                   :sk, :sr, CAST(:sg AS jsonb), :bk, :bc, CASE WHEN :st = 'filed' THEN now() END)
           RETURNING ref""",
        co=scope["id"],
        ck=cls["key"] if cls else None,
        cv=cls["version"] if cls else None,
        t=title_fa,
        fo=folder["id"] if folder else None,
        lv=lv["key"],
        lr=lv["rank"],
        st="filed" if file_now else "draft",
        m=dumps(clean),
        dd=dd,
        p=dumps(party_rows),
        pr=party_refs,
        wd=watch_dates_of(cls, fields, clean),
        sk=source_kind,
        sr=source_ref,
        sg=dumps(suggestion) if suggestion is not None and not file_now else None,
        bk=kind,
        bc=code,
    )
    r = await load(tx, row["ref"])
    manifest = await insert_files(tx, r, 1, stored, bool(cls is None or cls.get("ocr", True)))
    await tx.exec(
        """INSERT INTO archive.record_versions (company_id, record_id, n, manifest_sha256, note_fa,
               created_by_kind, created_by_code)
           VALUES (:co, :r, 1, :m, :note, :bk, :bc)""",
        co=r["company_id"],
        r=r["id"],
        m=manifest,
        note=(note_fa or None) and note_fa[:2000],
        bk=kind,
        bc=code,
    )
    for i, link in enumerate(links or []):
        await add_link(tx, who, r, link.get("kind"), link.get("to") or {}, path=f"links.{i}")
    if cls is not None:
        for al in cls.get("auto_link") or []:
            v = clean.get(al["field"])
            to = _auto_target(fields, al["field"], v)
            if to is not None:
                await add_link(tx, who, r, al["link_kind"], to, quiet=True)
    if file_now:
        await RT.compute(tx, r, cls, fields)
    r = await load(tx, row["ref"])
    await search_vectors(tx, r, fields)
    await audit.record(
        tx,
        who,
        company_id=r["company_id"],
        action="archive.record_create",
        action_class="A1",
        target_kind="archive_record",
        target_ref=r["ref"],
        summary=f"{r['class_key'] or 'unclassified'} {r['state']} {r['level']}",
    )
    await emit(tx, r, "record.filed" if file_now else "record.updated", change="created")
    if file_now:
        await AU.fire(tx, "filed", r)
    return await load(tx, row["ref"])


def _auto_target(fields: list[dict[str, Any]], key: str, v: Any) -> dict[str, Any] | None:
    f = next((x for x in fields if x["key"] == key), None)
    if f is None or v is None:
        return None
    if f["type"] == "ref" and isinstance(v, dict):
        return {"kind": v["kind"], "ref": v["ref"]}
    if f["type"] == "party":
        return {"kind": "party", "ref": v}
    if f["type"] == "company":
        return {"kind": "company", "ref": v}
    return None


async def emit(tx: Tx, r: dict[str, Any], type_: str, **data: Any) -> None:
    """Stream topic `archive` (owner only): metadata only, never a title or a
    value (red line 3)."""
    await events.emit(
        tx,
        r["scope"],
        type_,
        r["ref"],
        {"state": r["state"], "level": r["level"], "class": r["class_key"], **data},
    )


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


async def link_title(tx: Tx, kind: str, ref: str) -> str | None:
    if kind == "record":
        return _s(await tx.scalar("SELECT title_fa FROM archive.records WHERE ref = :r", r=ref))
    if kind == "decision":
        return _s(await tx.scalar("SELECT title FROM cartable.decisions WHERE ref = :r", r=ref))
    if kind == "resolution":
        return _s(await tx.scalar("SELECT title FROM cartable.resolutions WHERE ref = :r", r=ref))
    if kind == "case":
        return _s(await tx.scalar("SELECT title_fa FROM legal.cases WHERE ref = :r", r=ref))
    if kind == "work":
        return _s(await tx.scalar("SELECT title FROM work.work WHERE ref = :r", r=ref))
    if kind == "employee":
        return _s(await tx.scalar("SELECT title_fa FROM core.employees WHERE code = :r", r=ref))
    if kind == "party":
        return _s(await tx.scalar("SELECT name_fa FROM archive.parties WHERE ref = :r", r=ref))
    if kind == "company":
        return _s(await tx.scalar("SELECT name_fa FROM core.companies WHERE code = :r", r=ref))
    return None


async def add_link(
    tx: Tx,
    who: Principal,
    r: dict[str, Any],
    kind: Any,
    to: dict[str, Any],
    *,
    path: str = "link",
    quiet: bool = False,
) -> dict[str, Any] | None:
    k = (
        await tx.first(
            "SELECT * FROM archive.link_kinds WHERE key = :k AND status = 'active'", k=kind
        )
        if isinstance(kind, str)
        else None
    )
    to_kind, to_ref = to.get("kind"), to.get("ref")
    errors: dict[str, str] = {}
    if k is None:
        errors[f"{path}.kind"] = "an active link kind"
    elif to_kind not in list(k["to_kinds"]):
        errors[f"{path}.to.kind"] = f"{kind} links to {', '.join(k['to_kinds'])}"
    pat = V.REF_PATTERNS.get(str(to_kind))
    if pat is None or not isinstance(to_ref, str) or not pat.fullmatch(to_ref):
        errors[f"{path}.to.ref"] = "not a ref of that kind"
    if not errors and to_kind == "record" and to_ref == r["ref"]:
        errors[f"{path}.to.ref"] = "not the record itself"
    title = None
    if not errors:
        title = await link_title(tx, str(to_kind), str(to_ref))
        if title is None and to_kind in (
            "record",
            "decision",
            "resolution",
            "case",
            "party",
            "company",
        ):
            errors[f"{path}.to.ref"] = f"unknown {to_kind}"
    if errors:
        if quiet:
            return None
        raise invalid(errors)
    kind_, code = actor_of(who)
    got = await tx.first(
        """INSERT INTO archive.links (company_id, record_id, kind, to_kind, to_ref, title_fa, by_kind, by_code)
           VALUES (:co, :r, :k, :tk, :tr, :t, :bk, :bc)
           ON CONFLICT (record_id, kind, to_kind, to_ref) WHERE removed_at IS NULL DO NOTHING RETURNING *""",
        co=r["company_id"],
        r=r["id"],
        k=kind,
        tk=to_kind,
        tr=to_ref,
        t=(title or "")[:300] or None,
        bk=kind_,
        bc=code,
    )
    if got is None:
        got = await tx.one(
            """SELECT * FROM archive.links WHERE record_id = :r AND kind = :k AND to_kind = :tk AND to_ref = :tr
                 AND removed_at IS NULL""",
            r=r["id"],
            k=kind,
            tk=to_kind,
            tr=to_ref,
        )
        existing: dict[str, Any] = got
        return existing
    if kind == "supersedes" and to_kind == "record":
        await RT.superseded(tx, str(to_ref))
    return got


async def remove_link(
    tx: Tx, who: Principal, r: dict[str, Any], kind: str, to_kind: str, to_ref: str
) -> None:
    link = await tx.first(
        """SELECT * FROM archive.links WHERE record_id = :r AND kind = :k AND to_kind = :tk AND to_ref = :tr
             AND removed_at IS NULL FOR UPDATE""",
        r=r["id"],
        k=kind,
        tk=to_kind,
        tr=to_ref,
    )
    if link is None:
        raise ApiError(404, "not_found", "no such link")
    if link["sealed"]:
        raise ApiError(409, "sealed_record", "a sealed link is never removed")
    await tx.exec(
        "UPDATE archive.links SET removed_at = now(), removed_by = :b WHERE id = :id",
        id=link["id"],
        b=who.code[:64],
    )


async def patch(
    tx: Tx, who: Principal, r: dict[str, Any], body: dict[str, Any], c: CL.Clearance
) -> dict[str, Any]:
    """title_fa, metadata, folder, parties, class (a draft only); `level` is
    the route's (raise or declassify, with its re-store)."""
    require_live(r)
    if r["state"] == "sealed" and set(body) - {"level"}:
        raise ApiError(409, "sealed_record", f"{r['ref']} is sealed; a correction is a new version")
    await require_not_held(tx, r)
    sets: dict[str, Any] = {}
    cls = None
    if "class" in body:
        if r["state"] != "draft":
            raise invalid({"class": "only a draft takes a class"})
        cls = await resolve_class(tx, body["class"], r["scope"])
        sets["class_key"], sets["class_version"] = (
            (cls["key"], cls["version"]) if cls else (None, None)
        )
    elif r["class_key"]:  # the record keeps the class version it was filed under
        cls = await SC.class_at(tx, r["class_key"], r["class_version"])
    fields = list(cls["fields"]) if cls else []
    meta = J(r["metadata"], {})
    if "metadata" in body:
        merged = {**meta, **(body["metadata"] or {})}
        merged = {k: v for k, v in merged.items() if v is not None}
        clean, _missing, errors = V.validate_metadata(
            fields, merged, complete=r["state"] != "draft", keep=meta
        )
        if errors:
            raise invalid(errors)
        no_secret({"metadata": clean})
        sets["metadata"] = clean
        meta = clean
    if "title_fa" in body:
        t = body["title_fa"]
        if not isinstance(t, str) or not 1 <= len(t.strip()) <= 300:
            raise invalid({"title_fa": "text of 1-300 characters"})
        no_secret({"title_fa": t})
        sets["title_fa"] = t.strip()
    if "folder" in body:
        f = (
            await resolve_folder(tx, body["folder"], r["company_id"], r["scope"], cls)
            if body["folder"]
            else None
        )
        sets["folder_id"] = f["id"] if f else None
    if "parties" in body:
        rows, refs = await check_parties(tx, body["parties"])
        sets["parties"], sets["party_refs"] = rows, refs
    if not sets:
        return r
    if cls is not None:
        sets["doc_date"] = doc_date_of(fields, meta)
        sets["watch_dates"] = watch_dates_of(cls, fields, meta)
    assigns = []
    params: dict[str, Any] = {"id": r["id"]}
    for k, v in sets.items():
        if k in ("metadata", "parties"):
            assigns.append(f"{k} = CAST(:{k} AS jsonb)")
            params[k] = dumps(v)
        else:
            assigns.append(f"{k} = :{k}")
            params[k] = v
    await tx.exec(f"UPDATE archive.records SET {', '.join(assigns)} WHERE id = :id", **params)  # noqa: S608
    r = await load(tx, r["ref"])
    if r["state"] != "draft":
        await RT.compute(tx, r, cls, fields)
    await search_vectors(tx, r, fields)
    await audit.record(
        tx,
        who,
        company_id=r["company_id"],
        action="archive.record_update",
        action_class="A1",
        target_kind="archive_record",
        target_ref=r["ref"],
        summary=",".join(sorted(sets))[:300],
    )
    await emit(tx, r, "record.updated", change="metadata", fields=sorted(sets))
    return await load(tx, r["ref"])


async def file_draft(tx: Tx, who: Principal, r: dict[str, Any]) -> dict[str, Any]:
    """POST /archive/records/{ref}/file: a completed draft becomes filed."""
    if r["state"] != "draft":
        raise ApiError(409, "validation_failed", f"{r['ref']} is {r['state']}, not a draft")
    await require_not_held(tx, r)
    if not r["class_key"]:
        raise invalid({"class": "a draft needs its class before it is filed"})
    fields = await class_fields(tx, r)
    meta = J(r["metadata"], {})
    _clean, _missing, errors = V.validate_metadata(fields, meta, complete=True, keep=meta)
    if errors:
        raise invalid(errors)
    cls = await SC.class_at(tx, r["class_key"], r["class_version"])
    n = await tx.scalar(
        "SELECT count(*) FROM archive.record_files WHERE record_id = :r AND version_n = :v",
        r=r["id"],
        v=r["current_version"],
    )
    if int(n or 0) < int(cls.get("required_files") or 0):
        raise invalid({"file_ids": f"{cls['key']} needs at least {cls['required_files']} file(s)"})
    await tx.exec(
        "UPDATE archive.records SET state = 'filed', filed_at = now(), suggestion = NULL WHERE id = :id",
        id=r["id"],
    )
    r = await load(tx, r["ref"])
    await RT.compute(tx, r, cls, fields)
    r = await load(tx, r["ref"])
    await audit.record(
        tx,
        who,
        company_id=r["company_id"],
        action="archive.record_file",
        action_class="A1",
        target_kind="archive_record",
        target_ref=r["ref"],
        summary=f"{r['class_key']} filed",
    )
    await emit(tx, r, "record.filed", change="filed")
    await AU.fire(tx, "filed", r)
    return r


async def add_version(
    tx: Tx, who: Principal, r: dict[str, Any], stored: list[ST.Stored], note_fa: str | None
) -> dict[str, Any]:
    """A new version (allowed under a hold): the current one is superseded; a
    sealed record is `filed` again (its old seal stays on the old version)."""
    require_live(r)
    if not stored:
        raise invalid({"file_ids": "a version needs at least one file"})
    no_secret({"note_fa": note_fa or ""})
    cls = await SC.class_at(tx, r["class_key"], r["class_version"]) if r["class_key"] else None
    check_files(cls, [s.intake for s in stored], complete=r["state"] != "draft")
    n = int(r["current_version"]) + 1
    await tx.exec(
        "UPDATE archive.record_versions SET state = 'superseded' WHERE record_id = :r AND state = 'current'",
        r=r["id"],
    )
    manifest = await insert_files(tx, r, n, stored, bool(cls is None or cls.get("ocr", True)))
    kind, code = actor_of(who)
    await tx.exec(
        """INSERT INTO archive.record_versions (company_id, record_id, n, manifest_sha256, note_fa,
               created_by_kind, created_by_code)
           VALUES (:co, :r, :n, :m, :note, :bk, :bc)""",
        co=r["company_id"],
        r=r["id"],
        n=n,
        m=manifest,
        note=(note_fa or None) and note_fa[:2000],
        bk=kind,
        bc=code,
    )
    await tx.exec(
        """UPDATE archive.records SET current_version = :n,
               state = CASE WHEN state = 'sealed' THEN 'filed' ELSE state END,
               sealed_at = CASE WHEN state = 'sealed' THEN NULL ELSE sealed_at END
           WHERE id = :id""",
        id=r["id"],
        n=n,
    )
    r = await load(tx, r["ref"])
    await search_vectors(tx, r, list(cls["fields"]) if cls else [])
    await audit.record(
        tx,
        who,
        company_id=r["company_id"],
        action="archive.record_version",
        action_class="A1",
        target_kind="archive_record",
        target_ref=r["ref"],
        summary=f"version {n}, manifest {manifest[:12]}",
    )
    await emit(tx, r, "record.updated", change="version", n=n)
    await AU.fire(tx, "version_added", r)
    return r


async def current_manifest(tx: Tx, r: dict[str, Any]) -> str:
    rows = await tx.all(
        """SELECT sha256, name FROM archive.record_files WHERE record_id = :r AND version_n = :v""",
        r=r["id"],
        v=r["current_version"],
    )
    return ST.manifest(rows)


async def seal(
    tx: Tx, who: Principal, r: dict[str, Any], manifest_sha256: str, step_up_id: UUID
) -> dict[str, Any]:
    if r["state"] != "filed":
        raise ApiError(
            409, "validation_failed", f"{r['ref']} is {r['state']}: only a filed record is sealed"
        )
    v = await tx.one(
        "SELECT * FROM archive.record_versions WHERE record_id = :r AND n = :n FOR UPDATE",
        r=r["id"],
        n=r["current_version"],
    )
    again = await current_manifest(tx, r)
    if manifest_sha256 != again or v["manifest_sha256"] != again:
        raise ApiError(409, "seal_mismatch", "the manifest changed since you saw it")
    await tx.exec(
        "UPDATE archive.record_versions SET sealed = true, sealed_at = now(), seal_step_up_id = :s WHERE id = :id",
        id=v["id"],
        s=step_up_id,
    )
    await tx.exec(
        "UPDATE archive.records SET state = 'sealed', sealed_at = now() WHERE id = :id", id=r["id"]
    )
    await tx.exec(
        "UPDATE archive.links SET sealed = true WHERE record_id = :r AND removed_at IS NULL",
        r=r["id"],
    )
    r = await load(tx, r["ref"])
    await audit.record(
        tx,
        who,
        company_id=r["company_id"],
        action="archive.seal",
        action_class="A2",
        target_kind="archive_record",
        target_ref=r["ref"],
        summary=f"manifest {again[:16]}",
        step_up=True,
    )
    await emit(tx, r, "record.sealed", n=r["current_version"])
    await AU.fire(tx, "sealed", r)
    return r


async def log_access(
    tx: Tx,
    who: Principal,
    r: dict[str, Any],
    action: str,
    *,
    file_id: UUID | None = None,
    version_n: int | None = None,
    step_up: bool = False,
    watermarked: bool = False,
    level_from: str | None = None,
    level_to: str | None = None,
) -> None:
    kind, code = actor_of(who)
    await tx.exec(
        """INSERT INTO archive.access_log (company_id, record_id, level_rank, actor_kind, actor_code, action,
               file_id, version_n, step_up, watermarked, level_from, level_to)
           VALUES (:co, :r, :lr, :ak, :ac, :a, :f, :v, :su, :w, :lf, :lt)""",
        co=r["company_id"],
        r=r["id"],
        lr=r["level_rank"],
        ak=kind,
        ac=code,
        a=action,
        f=file_id,
        v=version_n,
        su=step_up,
        w=watermarked,
        lf=level_from,
        lt=level_to,
    )


def watermark_text(who: Principal, ref: str) -> str:
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    viewer = "owner" if who.is_owner else who.code
    return f"{ref} | {viewer} | {at} | CoinePro HQ"


def manifest_of(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{x['sha256']}  {x['name']}" for x in rows)).encode()
    ).hexdigest()
