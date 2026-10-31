"""Filing a deliverable in the archive (prompt 15 §1.4, contract §5.2 ⟨1.7.3⟩):
the owner's "file it" on an output of the cartable. One archive draft of class
`report` (the seeded class; the owner may retire it, and then the record has
no class until the archivist files it), with the deliverable's body as a PDF
the hub draws itself and a link `about` the deliverable. The deliverable keeps
the record's ref in `filed_as`; a second call answers the same record. No
model, no outside call; nothing is deleted."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from hq_api.archive import clearance as CL
from hq_api.archive import pdf, scan
from hq_api.archive import records as R
from hq_api.archive import store as ST
from hq_api.archive import vocab as V
from hq_api.errors import ApiError
from hq_api.principal import Principal

CLASS = "report"


def _body(dl: dict[str, Any]) -> tuple[str, str]:
    title = str(dl["title"])[:300]
    parts = [f"{dl['ref']} · {dl['company']} · {dl['p_code']}", "", str(dl["summary"] or "")]
    if dl["body"]:
        parts += ["", str(dl["body"])]
    return title, "\n".join(parts)


SEARCH_TEXT = 400_000  # the record's search text (the column's cap); the PDF is whole


async def _whole_text(hub: Any, txf: Any, dl: dict[str, Any]) -> str | None:
    """The output's full text when the body is only its head (a
    players.store_text attachment `*-full.md`), else None."""
    for fid in dl.get("attachments") or []:
        async with txf() as tx:
            f = await tx.first(
                "SELECT name, mime, storage_key FROM files.files WHERE id = :id", id=fid
            )
        if f and f["mime"] == "text/markdown" and str(f["name"]).endswith("-full.md"):
            raw: bytes = await hub.storage.get(str(f["storage_key"]))
            return raw.decode("utf-8", "replace")
    return None


async def file(hub: Any, txf: Any, who: Principal, dl: dict[str, Any]) -> str:
    """-> the archive record's ref (the same one on every call)."""
    if dl["filed_as"]:
        return str(dl["filed_as"])
    title, body = _body(dl)
    if scan.kinds(f"{title}\n\n{body}"):
        # the archive never keeps a secret (§23.1): the owner sees why, never what
        raise ApiError(422, "secret_in_document", "the deliverable holds a secret pattern")
    async with txf() as tx:
        await CL.full(tx)
        co = await tx.one(
            "SELECT id, code, kind FROM core.companies WHERE id = :c", c=dl["company_id"]
        )
        cls_row = await tx.first(
            "SELECT 1 FROM archive.classes WHERE key = :k AND status = 'active'", k=CLASS
        )
        cls = await R.resolve_class(tx, CLASS, co["code"]) if cls_row else None
        lv = await R.resolve_level(tx, None, cls, None)
    # ⟨1.10.1⟩ the whole output: its full text when the body is only its head
    whole = await _whole_text(hub, txf, dl) or body
    if whole is not body and scan.kinds(whole):
        raise ApiError(422, "secret_in_document", "the deliverable holds a secret pattern")
    data, pages = await pdf.render(hub, title, whole, footer=f"CoinePro HQ · {dl['ref']}")
    name, mime, text = f"{dl['ref']}.pdf", "application/pdf", f"{title}\n\n{whole}"
    sha = hashlib.sha256(data).hexdigest()
    fid = uuid.uuid4()
    blob, wrapped = data, None
    if lv["encrypt"]:
        v = ST.vault(hub)
        if v is None:
            raise ApiError(503, "not_ready", "the archive's key service is not available")
        dek, wrapped = await v.new_key()
        blob = ST.encrypt(dek, data, str(fid).encode())
    key, stored_sha = await hub.storage.put(blob)
    it = ST.Intake(
        file_id=fid,
        name=name,
        mime=mime,
        size=len(data),
        sha256=sha,
        storage_key=key,
        pages=pages,
        text_state="text_layer",
        text=text[:SEARCH_TEXT],  # the search text (the column's cap); the file is whole
        ocr_confidence=None,
    )
    stored = [ST.Stored(it, key, stored_sha, bool(lv["encrypt"]), wrapped)]
    try:
        async with txf() as tx:
            await CL.full(tx)
            # one filing per deliverable, even with two calls at once
            await tx.exec(
                "SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))", k=f"file:{dl['ref']}"
            )
            again = await tx.scalar(
                "SELECT filed_as FROM cartable.deliverables WHERE id = :id", id=dl["id"]
            )
            if again:
                await hub.storage.destroy(key)
                return str(again)
            co = await tx.one(
                "SELECT id, code, kind FROM core.companies WHERE id = :c", c=dl["company_id"]
            )
            folder = await R.default_folder(tx, co["id"], co["code"], cls)
            fields = list(cls["fields"]) if cls else []
            known = {f["key"] for f in fields}
            values = {"date": dl["created_at"].date().isoformat(), "deliverable": dl["ref"],
                      "producer": dl["p_code"]}  # fmt: skip
            meta, _missing, _errors = V.validate_metadata(
                fields, {k: v for k, v in values.items() if k in known}, complete=False
            )
            r = await R.create(
                tx,
                who,
                scope=co,
                cls=cls,
                title_fa=title,
                metadata=meta,
                lv=lv,
                folder=folder,
                stored=stored,
                parties=None,
                links=[{"kind": "about", "to": {"kind": "deliverable", "ref": dl["ref"]}}],
                file_now=False,
                source_kind="owner",
                source_ref=f"deliverable:{dl['ref']}",
            )
            await tx.exec(
                "UPDATE cartable.deliverables SET filed_as = :r WHERE id = :id",
                r=r["ref"],
                id=dl["id"],
            )
            return str(r["ref"])
    except BaseException:
        await hub.storage.destroy(key)
        raise
