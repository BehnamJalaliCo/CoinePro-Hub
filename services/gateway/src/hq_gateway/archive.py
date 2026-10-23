"""The archive's agent tools (agents/tools.md v1.7, contract §23.11; prompt 14 §9).

    archive.search  A0  records within the role's clearance: refs, titles,
                        snippets (a record above it is never returned, not even
                        its title; the api filters before it ranks)
    archive.read    A0  one record's metadata, its versions' files and their
                        text, within clearance
    archive.file    A1  a DRAFT record from files already uploaded, with the
                        class and metadata it proposes; the owner files it and
                        only the owner seals it (a secret pattern in a file
                        refuses it: secret_in_document)
    archive.link    A1  a link of the schema's kinds to a decision, resolution,
                        case, work item, employee, revenue account or record
    archive.hold    A2  the legal counsel's legal hold for one of its cases;
                        only the owner releases it

The api decides who may (OPA hq.internal, archive.rego: the archivist and the
legal counsel; a hold the counsel's alone, with its case) and re-checks the
caller's clearance under RLS. Free text (titles, notes, the hold's reason)
leaves redacted; metadata values leave with credentials masked only, so an
IBAN, an id code, an e-mail or a phone the class asks for reaches the api as
written (the api masks it for every reader below its level).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from hq_common.redact import mask_secrets
from hq_gateway import tools as T

AR = r"^AR-[0-9]{6,}$"
FP = r"^FP-[0-9]{4,}$"
PT = r"^PT-[0-9]{4,}$"
LC = r"^LC-[0-9]{4,}$"
KEY = r"^[a-z][a-z0-9_]{1,40}$"
# A link's target: a hub ref (D-000123, M-0001, LC-0001, W-000123, AR-000123),
# an employee code (TY-GROWTH-01) or a revenue account's id; the api checks it.
TARGET = r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$"
RefKind = Literal[
    "decision",
    "resolution",
    "case",
    "work",
    "record",
    "employee",
    "revenue_account",
]
TEXT_CHARS = 12_000  # a record's text as archive.read returns it (the rest stays in the hub)
METADATA_KEYS = 80
FIELD_KEYS = (
    "ref",
    "scope",
    "class",
    "class_version",
    "title_fa",
    "folder",
    "level",
    "state",
    "metadata",
    "masked",
    "parties",
    "links",
    "holds",
    "retention",
    "reminders",
    "current_version",
    "doc_date",
    "source",
    "filed_at",
    "sealed_at",
)


class _Aliased(T.In):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TargetIn(T.In):
    kind: RefKind
    ref: str = Field(pattern=TARGET)


class LinkSpecIn(T.In):
    kind: str = Field(pattern=KEY)
    to: TargetIn


class PartyIn(T.In):
    party: str = Field(pattern=PT)
    role_fa: str = Field(default="", max_length=120)


class SearchIn(_Aliased):
    q: str | None = Field(default=None, min_length=2, max_length=200)
    scope: str | None = Field(default=None, pattern=T.CODE)
    cls: str | None = Field(default=None, alias="class", pattern=KEY)
    party: str | None = Field(default=None, pattern=PT)
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None
    limit: int = Field(default=20, ge=1, le=50)


class ReadIn(T.In):
    ref: str = Field(pattern=AR)
    version: int | None = Field(default=None, ge=1, le=10_000)


class FileIn(_Aliased):
    scope: str = Field(pattern=T.CODE)
    cls: str = Field(alias="class", pattern=KEY)
    title_fa: str = Field(min_length=1, max_length=300)
    file_ids: list[str] = Field(min_length=1, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)
    level: str | None = Field(default=None, pattern=KEY)
    folder: str | None = Field(default=None, pattern=FP)
    parties: list[PartyIn] = Field(default_factory=list, max_length=20)
    links: list[LinkSpecIn] = Field(default_factory=list, max_length=20)
    note_fa: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def _shape(self) -> FileIn:
        bad = [f for f in self.file_ids if not re.fullmatch(T.UUID_RE, f)]
        if bad:
            raise ValueError("file_ids: each a file id (uuid)")
        if len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("file_ids: each file once")
        if len(self.metadata) > METADATA_KEYS:
            raise ValueError(f"metadata: at most {METADATA_KEYS} fields")
        if any(not re.fullmatch(KEY, str(k)) for k in self.metadata):
            raise ValueError("metadata: field keys are the class's keys (a-z, 0-9, _)")
        if T._depth(self.metadata) > 4:
            raise ValueError("metadata: too deeply nested")
        return self


class LinkIn(T.In):
    ref: str = Field(pattern=AR)
    kind: str = Field(pattern=KEY)
    to: TargetIn


class HoldScopeIn(_Aliased):
    records: list[str] | None = Field(default=None, max_length=200)
    folders: list[str] | None = Field(default=None, max_length=50)
    classes: list[str] | None = Field(default=None, max_length=50)
    parties: list[str] | None = Field(default=None, max_length=50)
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None

    @model_validator(mode="after")
    def _facets(self) -> HoldScopeIn:
        for name, pattern in (("records", AR), ("folders", FP), ("classes", KEY), ("parties", PT)):
            values = getattr(self, name) or []
            if any(not re.fullmatch(pattern, v) for v in values):
                raise ValueError(f"{name}: not a valid {name[:-1]} reference")
        if not any((self.records, self.folders, self.classes, self.parties)):
            # A hold names what it covers: never "everything" by omission.
            raise ValueError("scope: at least one of records, folders, classes or parties")
        if self.from_ and self.to and self.from_ > self.to:
            raise ValueError("scope: from is after to")
        return self


class HoldIn(T.In):
    title_fa: str = Field(min_length=1, max_length=300)
    case: str = Field(pattern=LC)
    reason_md: str = Field(min_length=1, max_length=20000)
    scope: HoldScopeIn


# ------------------------------------------------------------- handlers --
def _record(data: Any) -> Any:
    """What the agent needs of a record (archive.read): its fields, the files of
    each version without storage details, and its text capped."""
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {k: data.get(k) for k in FIELD_KEYS if k in data}
    versions = []
    for v in data.get("versions") or []:
        if not isinstance(v, dict):
            continue
        versions.append(
            {
                "n": v.get("n"),
                "state": v.get("state"),
                "sealed": v.get("sealed"),
                "manifest_sha256": v.get("manifest_sha256"),
                "note_fa": v.get("note_fa"),
                "files": [
                    {
                        k: f.get(k)
                        for k in (
                            "file_id",
                            "name",
                            "mime",
                            "sha256",
                            "pages",
                            "text_state",
                            "ocr_confidence",
                        )
                    }
                    for f in v.get("files") or []
                    if isinstance(f, dict)
                ],
            }
        )
    out["versions"] = versions
    text = data.get("text")
    if isinstance(text, str):
        out["text"] = text[:TEXT_CHARS]
        out["text_truncated"] = len(text) > TEXT_CHARS
    return out


async def archive_search(api: T.Api, call: T.Call, a: SearchIn) -> T.Result:
    params = a.model_dump(mode="json", by_alias=True, exclude_none=True)
    resp = await api.request("GET", "/internal/v1/archive/search", call.token, params=params)
    return T.from_response(resp, None)


async def archive_read(api: T.Api, call: T.Call, a: ReadIn) -> T.Result:
    resp = await api.request(
        "GET",
        f"/internal/v1/archive/records/{a.ref}",
        call.token,
        params={"version": a.version},
    )
    r = T.from_response(resp)
    if r.outcome == "ok":
        r.data = _record(r.data)
    return r


async def archive_file(api: T.Api, call: T.Call, a: FileIn) -> T.Result:
    body: dict[str, Any] = {
        "scope": a.scope,
        "class": a.cls,
        "title_fa": await T._text(a.title_fa),
        "file_ids": a.file_ids,
        # credentials masked, the class's identifiers kept (the api masks them)
        "metadata": mask_secrets(a.metadata),
        "parties": [{"party": p.party, "role_fa": await T._text(p.role_fa)} for p in a.parties],
        "links": [link.model_dump(mode="json") for link in a.links],
        "note_fa": await T._text(a.note_fa),
    }
    if a.level:
        body["level"] = a.level
    if a.folder:
        body["folder"] = a.folder
    resp = await api.request(
        "POST",
        "/internal/v1/archive/records",
        call.token,
        json=body,
        idem=call.idem(f"archive.file:{a.scope}:{a.cls}"),
    )
    r = T.from_response(resp)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {
            k: r.data.get(k) for k in ("ref", "state", "class", "level", "missing", "suggestion")
        } | {"note": "a draft: the owner files it and only the owner seals it"}
    return r


async def archive_link(api: T.Api, call: T.Call, a: LinkIn) -> T.Result:
    resp = await api.request(
        "POST",
        f"/internal/v1/archive/records/{a.ref}/links",
        call.token,
        json={"kind": a.kind, "to": a.to.model_dump(mode="json")},
        idem=call.idem(f"archive.link:{a.ref}:{a.kind}:{a.to.kind}:{a.to.ref}"),
    )
    r = T.from_response(resp, None)
    if r.outcome == "ok":
        r.ref = a.ref
    return r


async def archive_hold(api: T.Api, call: T.Call, a: HoldIn) -> T.Result:
    body = {
        "title_fa": await T._text(a.title_fa),
        "case": a.case,
        "reason_md": await T._text(a.reason_md),
        "scope": a.scope.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    resp = await api.request(
        "POST",
        "/internal/v1/archive/holds",
        call.token,
        json=body,
        idem=call.idem(f"archive.hold:{a.case}"),
    )
    r = T.from_response(resp)
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.data = {
            k: r.data.get(k)
            for k in ("ref", "title_fa", "case", "state", "scope", "records", "placed_at")
        } | {"note": "only the owner releases a hold"}
    return r


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "archive.search": (SearchIn, archive_search),
    "archive.read": (ReadIn, archive_read),
    "archive.file": (FileIn, archive_file),
    "archive.link": (LinkIn, archive_link),
    "archive.hold": (HoldIn, archive_hold),
}
T.TOOLS.update(TOOLS)
