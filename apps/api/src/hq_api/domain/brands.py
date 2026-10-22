"""The company's brand and seal (prompt 9.1, contract §18.14).

A brand version (org.company_brands) is traced by code from the owner's logo
(hq_api.brand_trace, in the worker's sandboxed child) or seeded from the
design files, and is append-only except its state:

  processing -> proposed -> active -> retired     (or processing -> failed)

The owner sees a proposed version and seals it (🔏 `company.brand`, target =
the version's digest, recomputed here from the row): a version that changed
after the owner saw it cannot be sealed. Sealing retires the active one.
Company.brand_version and Founding.brand are read from here. The holding's
own seal is fixed in the clients and is not data.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api import audit, brand, events
from hq_api.db import Tx
from hq_api.domain import files as F
from hq_api.errors import ApiError
from hq_api.principal import Principal

log = logging.getLogger("hq_api.brands")

MEDIA = Principal(kind="service", code="media", role="service")
SEEDER = Principal(kind="service", code="seed", role="service")
DEFAULT_DIR = "/app/design/brand/companies"
LOGO_MIMES = {"image/png": True, "image/webp": False, "image/jpeg": False}  # -> best (transparency)
MAX_ATTEMPTS = 3


# ------------------------------------------------------------------ models --
class BrandLayer(BaseModel):
    role: Literal["ink", "accent"]
    color: str
    d: str


class BrandShape(BaseModel):
    vb: str
    layers: list[BrandLayer]


class BrandSource(BaseModel):
    kind: Literal["upload", "seed"]
    file_id: UUID | None = None
    path: str | None = None
    sha256: str
    width: int
    height: int
    has_alpha: bool


class BrandOptions(BaseModel):
    colors: int | None = Field(default=None, ge=1, le=4)
    detail: int = Field(default=brand.OPTIONS_DEFAULT_DETAIL, ge=1, le=5)


class BrandChecks(BaseModel):
    paths_bytes: int
    min_feature_px_16: float
    iou: float
    contrast_night: float | None = None
    contrast_day: float | None = None
    warnings: list[str] = Field(default_factory=list)


class PaletteShare(BaseModel):
    hex: str
    share: float


class CompanyBrand(BaseModel):
    company: str
    version: int
    state: Literal["processing", "proposed", "active", "failed", "retired"]
    source: BrandSource
    mark: BrandShape | None
    wordmark: BrandShape | None
    ink: str
    accent: str | None
    accent_night: str | None
    accent_day: str | None
    palette: list[PaletteShare]
    options: BrandOptions
    checks: BrandChecks | None
    digest: str
    status_reason: str | None
    created_at: datetime
    activated_at: datetime | None
    # ⟨additive⟩ the part this version traced (the other is carried over)
    part: Literal["mark", "wordmark"] = "mark"


class CompanyBrandView(BaseModel):
    active: CompanyBrand | None
    proposed: CompanyBrand | None


class ActiveBrand(BaseModel):
    version: int
    mark: BrandShape
    wordmark: BrandShape | None
    ink: str
    accent: str | None
    accent_night: str | None
    accent_day: str | None


class Brands(BaseModel):
    etag: str
    companies: dict[str, ActiveBrand]


class FoundingBrand(BaseModel):
    state: Literal["missing", "proposed", "active"]
    version: int | None


# ------------------------------------------------------------------- reads --
BRAND_SQL = """
    SELECT b.*, c.code AS company_code
    FROM org.company_brands b JOIN core.companies c ON c.id = b.company_id
"""


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def content(r: dict[str, Any]) -> dict[str, Any]:
    """The part of a row the digest covers."""
    return {
        "mark": _j(r.get("mark")),
        "wordmark": _j(r.get("wordmark")),
        "ink": r["ink"],
        "accent": r.get("accent"),
        "accent_night": r.get("accent_night"),
        "accent_day": r.get("accent_day"),
    }


def digest_of(r: dict[str, Any]) -> str:
    return brand.digest(content(r))


def render(r: dict[str, Any]) -> CompanyBrand:
    c = content(r)
    checks = _j(r.get("checks"))
    return CompanyBrand(
        company=r["company_code"],
        version=r["version"],
        state=r["state"],
        source=BrandSource.model_validate(_j(r["source"])),
        mark=BrandShape.model_validate(c["mark"]) if c["mark"] else None,
        wordmark=BrandShape.model_validate(c["wordmark"]) if c["wordmark"] else None,
        ink=c["ink"],
        accent=c["accent"],
        accent_night=c["accent_night"],
        accent_day=c["accent_day"],
        palette=[PaletteShare.model_validate(p) for p in _j(r.get("palette")) or []],
        options=BrandOptions.model_validate(_j(r.get("options")) or {}),
        checks=BrandChecks.model_validate(checks) if checks else None,
        digest=digest_of(r),  # always recomputed: what the owner sees is what a seal binds
        status_reason=r.get("status_reason"),
        created_at=r["created_at"],
        activated_at=r.get("activated_at"),
        part=r["part"],
    )


async def company_row(tx: Tx, code: str) -> dict[str, Any]:
    return await tx.one(
        "SELECT id, code, kind FROM core.companies WHERE code = :c", c=code, not_found="not_found"
    )


async def load(tx: Tx, company_id: UUID, version: int, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec(
            "SELECT 1 FROM org.company_brands WHERE company_id = :co AND version = :v FOR UPDATE",
            co=company_id,
            v=version,
        )
    return await tx.one(
        BRAND_SQL + " WHERE b.company_id = :co AND b.version = :v",
        co=company_id,
        v=version,
        not_found="not_found",
    )


async def load_id(tx: Tx, brand_id: UUID, *, lock: bool = False) -> dict[str, Any] | None:
    if lock:
        await tx.exec("SELECT 1 FROM org.company_brands WHERE id = :id FOR UPDATE", id=brand_id)
    return await tx.first(BRAND_SQL + " WHERE b.id = :id", id=brand_id)


async def active(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        BRAND_SQL + " WHERE b.company_id = :co AND b.state = 'active'", co=company_id
    )


async def newest_proposed(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        BRAND_SQL
        + " WHERE b.company_id = :co AND b.state = 'proposed' ORDER BY b.version DESC LIMIT 1",
        co=company_id,
    )


async def view(tx: Tx, company_id: UUID) -> CompanyBrandView:
    a, p = await active(tx, company_id), await newest_proposed(tx, company_id)
    return CompanyBrandView(active=render(a) if a else None, proposed=render(p) if p else None)


async def founding_brand(tx: Tx, company_id: UUID | None) -> FoundingBrand:
    """Founding.brand (§18.8): the step «مُهر شرکت» of the founding's company."""
    if company_id is None:
        return FoundingBrand(state="missing", version=None)
    a = await tx.scalar(
        "SELECT version FROM org.company_brands WHERE company_id = :co AND state = 'active'",
        co=company_id,
    )
    if a is not None:
        return FoundingBrand(state="active", version=a)
    p = await tx.scalar(
        """SELECT max(version) FROM org.company_brands WHERE company_id = :co AND state = 'proposed'""",
        co=company_id,
    )
    return (
        FoundingBrand(state="proposed", version=p)
        if p
        else FoundingBrand(state="missing", version=None)
    )


async def brands(tx: Tx) -> Brands:
    """Every active brand of a company (never the holding's), keyed by code."""
    rows = await tx.all(
        BRAND_SQL + " WHERE b.state = 'active' AND c.kind = 'company' ORDER BY c.code"
    )
    out: dict[str, ActiveBrand] = {}
    tag = hashlib.sha256()
    for r in rows:
        c = content(r)
        if not c["mark"]:
            continue
        out[r["company_code"]] = ActiveBrand(version=r["version"], **c)
        tag.update(f"{r['company_code']}@{r['version']}:{digest_of(r)};".encode())
    return Brands(etag=f'"b-{tag.hexdigest()[:32]}"', companies=out)


# ------------------------------------------------------------------ writes --
def _ref(code: str, version: int) -> str:
    return f"{code}@{version}"


async def _emit(tx: Tx, code: str, r: dict[str, Any], change: str) -> None:
    await events.emit(
        tx,
        code,
        "brand.updated",
        _ref(code, r["version"]),
        {"version": r["version"], "state": r["state"], "part": r["part"], "change": change},
    )


def no_holding(co: dict[str, Any]) -> None:
    if co["kind"] == "holding":
        raise ApiError(
            422,
            "validation_failed",
            "the holding's seal is fixed, not data",
            message_fa="مُهر هلدینگ ثابت است و از لوگو ساخته نمیشود.",
        )


async def _logo_file(tx: Tx, file_id: UUID, co: dict[str, Any]) -> dict[str, Any]:
    """The owner's own image upload, in the holding (then it moves to this
    company, like a first attachment) or already this company's."""
    f = await tx.first(
        """SELECT f.id, f.mime, f.kind, f.sha256, f.width, f.height, f.variant, f.company_id,
                  f.created_by_kind, f.storage_key, COALESCE(p.status, 'ready') AS status
           FROM files.files f LEFT JOIN files.processing p ON p.file_id = f.id WHERE f.id = :id""",
        id=file_id,
    )
    if f is None or f["variant"] != "original" or f["created_by_kind"] != "owner":
        raise ApiError(422, "validation_failed", fields={"file_id": "not one of your uploads"})
    if f["mime"] not in LOGO_MIMES:
        raise ApiError(
            422,
            "validation_failed",
            fields={"file_id": "a logo is PNG (best, with transparency), WebP or JPEG"},
            message_fa="لوگو باید PNG (بهتر با زمینه‌ی شفاف)، WebP یا JPEG باشد.",
        )
    if f["status"] != "ready":
        raise ApiError(409, "validation_failed", fields={"file_id": "still processing"})
    holding = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
    await F.attach(tx, [file_id], co["id"], holding)  # refuses another company's file
    return dict(f)


async def _next_version(tx: Tx, company_id: UUID) -> int:
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtext('org.company_brands:' || :co))", co=str(company_id)
    )
    n = await tx.scalar(
        "SELECT COALESCE(max(version), 0) + 1 FROM org.company_brands WHERE company_id = :co",
        co=company_id,
    )
    return int(n)


async def _insert(
    tx: Tx,
    who: Principal,
    co: dict[str, Any],
    *,
    part: str,
    source: dict[str, Any],
    file_id: UUID | None,
    options: dict[str, Any],
) -> dict[str, Any]:
    """A new `processing` version that carries the other part (and, for a
    wordmark, the colours) over from the active one."""
    cur = await active(tx, co["id"])
    carried: dict[str, Any] = {"mark": None, "wordmark": None}
    colours: dict[str, Any] = {
        "ink": "#111216",
        "accent": None,
        "accent_night": None,
        "accent_day": None,
    }
    palette: Any = []
    if cur is not None:
        c = content(cur)
        if part == "mark":
            carried["wordmark"] = c["wordmark"]
        else:
            carried["mark"] = c["mark"]
            colours = {k: c[k] for k in colours}
            palette = _j(cur["palette"]) or []
    version = await _next_version(tx, co["id"])
    row = await tx.one(
        """INSERT INTO org.company_brands (company_id, version, part, source, file_id, mark, wordmark,
               ink, accent, accent_night, accent_day, palette, options, created_by_kind, created_by_code)
           VALUES (:co, :v, :part, CAST(:src AS jsonb), :file, CAST(:mark AS jsonb), CAST(:word AS jsonb),
                   :ink, :acc, :an, :ad, CAST(:pal AS jsonb), CAST(:opt AS jsonb), :bk, :bc)
           RETURNING id""",
        co=co["id"],
        v=version,
        part=part,
        src=json.dumps(source, default=str),
        file=file_id,
        mark=json.dumps(carried["mark"]) if carried["mark"] else None,
        word=json.dumps(carried["wordmark"]) if carried["wordmark"] else None,
        ink=colours["ink"],
        acc=colours["accent"],
        an=colours["accent_night"],
        ad=colours["accent_day"],
        pal=json.dumps(palette),
        opt=json.dumps(options),
        bk=who.kind if who.kind in ("owner", "service") else "service",
        bc=who.code,
    )
    r = await load_id(tx, row["id"])
    assert r is not None
    await _emit(tx, co["code"], r, "created")
    return r


async def upload(
    tx: Tx, who: Principal, code: str, file_id: UUID, part: str, options: dict[str, Any]
) -> dict[str, Any]:
    """POST /companies/{code}/brand: a new version from the owner's logo."""
    co = await company_row(tx, code)
    no_holding(co)
    f = await _logo_file(tx, file_id, co)
    source = {
        "kind": "upload",
        "file_id": str(file_id),
        "path": None,
        "sha256": f["sha256"],
        "width": int(f["width"] or 0),
        "height": int(f["height"] or 0),
        "has_alpha": False,  # known once traced
    }
    return await _insert(tx, who, co, part=part, source=source, file_id=file_id, options=options)


async def retrace(
    tx: Tx, who: Principal, code: str, version: int, options: dict[str, Any]
) -> dict[str, Any]:
    """POST /companies/{code}/brand/{version}/retrace: the same file again."""
    co = await company_row(tx, code)
    no_holding(co)
    old = await load(tx, co["id"], version)
    if old["file_id"] is None:
        raise ApiError(
            409,
            "validation_failed",
            "a seeded version has no logo file; upload the logo",
            message_fa="این نسخه از فایل‌های طراحی آمده و لوگوی PNG ندارد؛ لوگو را بارگذاری کن.",
        )
    source = {**_j(old["source"]), "has_alpha": False}
    return await _insert(
        tx, who, co, part=old["part"], source=source, file_id=old["file_id"], options=options
    )


async def activate(
    tx: Tx, who: Principal, co: dict[str, Any], r: dict[str, Any], *, step_up_id: UUID
) -> tuple[dict[str, Any], int | None]:
    """The owner's seal (the route consumed the step-up on the recomputed
    digest): this version active, the previous one retired."""
    if r["state"] not in ("proposed", "retired"):
        raise ApiError(
            409,
            "validation_failed",
            f"version {r['version']} is {r['state']}",
            message_fa="این نسخه آماده‌ی مُهر نیست.",
        )
    if not content(r)["mark"]:
        raise ApiError(
            409,
            "not_ready",
            "a brand needs its mark before it is sealed",
            message_fa="اول نشان (mark) شرکت را بساز؛ مُهر بدون نشان ممکن نیست.",
            missing=["mark"],
        )
    # One seal at a time per company (the same lock as a new version's number).
    await tx.exec(
        "SELECT pg_advisory_xact_lock(hashtext('org.company_brands:' || :co))", co=str(co["id"])
    )
    prev = await active(tx, co["id"])
    if prev is not None:
        await tx.exec(
            """UPDATE org.company_brands SET state = 'retired', retired_at = now(), updated_at = now()
               WHERE id = :id""",
            id=prev["id"],
        )
    await tx.exec(
        """UPDATE org.company_brands SET state = 'active', activated_at = now(), retired_at = NULL,
               step_up_id = :su, updated_at = now()
           WHERE id = :id""",
        id=r["id"],
        su=step_up_id,
    )
    out = await load_id(tx, r["id"])
    assert out is not None
    await _emit(tx, co["code"], out, "activated")
    return out, prev["version"] if prev else None


# --------------------------------------------------------- the worker side --
def job_kwargs(r: dict[str, Any], path: Path) -> dict[str, Any]:
    """The child's arguments for one version (hq_api.brand_trace.trace_job)."""
    opts = _j(r["options"]) or {}
    other = content(r)["wordmark" if r["part"] == "mark" else "mark"]
    return {
        "path": str(path),
        "colors": opts.get("colors"),
        "detail": int(opts.get("detail") or brand.OPTIONS_DEFAULT_DETAIL),
        "extra_bytes": brand.paths_bytes(other),
    }


def compose(
    r: dict[str, Any], got: dict[str, Any], mark_checks: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The traced part with what this version carried over -> the columns of
    a proposed version (a traced wordmark keeps the carried mark's small-size
    check, `mark_checks`). ValueError when anything is not our own path."""
    c = content(r)
    shape = got["shape"]
    if not brand.shape_ok(shape):
        raise ValueError("invalid_path")
    mark, wordmark = (shape, c["wordmark"]) if r["part"] == "mark" else (c["mark"], shape)
    for s in (mark, wordmark):
        if s is not None and not brand.shape_ok(s):
            raise ValueError("invalid_path")
    total = brand.paths_bytes(mark, wordmark)
    if total > brand.PATHS_BUDGET:
        raise ValueError("too_complex")
    if r["part"] == "mark" or c["mark"] is None:
        ink, accent = got["ink"], got["accent"]
        palette = got["palette"]
    else:
        ink, accent = c["ink"], c["accent"]
        palette = _j(r["palette"]) or got["palette"]
    for hx in (ink, accent):
        if hx is not None and not brand.hex_ok(hx):
            raise ValueError("invalid_path")
    themed = brand.theme_accents(accent)
    checks = dict(got["checks"])
    if r["part"] == "wordmark" and c["mark"] is not None and mark_checks:
        checks["min_feature_px_16"] = mark_checks.get(
            "min_feature_px_16", checks["min_feature_px_16"]
        )
    checks.update(
        paths_bytes=total,
        contrast_night=themed["contrast_night"],
        contrast_day=themed["contrast_day"],
        warnings=list(checks.get("warnings") or []) + themed["warnings"],
    )
    source = {**_j(r["source"]), "has_alpha": bool(got["has_alpha"]),
              "width": int(got["width"]), "height": int(got["height"])}  # fmt: skip
    out = {
        "mark": mark,
        "wordmark": wordmark,
        "ink": ink,
        "accent": accent,
        "accent_night": themed["accent_night"],
        "accent_day": themed["accent_day"],
        "palette": palette[:6],
        "options": {"colors": got["options"]["colors"], "detail": got["options"]["detail"]},
        "checks": checks,
        "source": source,
    }
    out["digest"] = brand.digest(out)
    return out


async def mark_checks(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    """The active version's checks (a wordmark keeps the mark's small-size check)."""
    cur = await active(tx, company_id)
    return _j(cur["checks"]) if cur is not None else None


async def proposed(tx: Tx, r: dict[str, Any], cols: dict[str, Any]) -> dict[str, Any]:
    await tx.exec(
        """UPDATE org.company_brands SET state = 'proposed', mark = CAST(:mark AS jsonb),
               wordmark = CAST(:word AS jsonb), ink = :ink, accent = :acc, accent_night = :an,
               accent_day = :ad, palette = CAST(:pal AS jsonb), options = CAST(:opt AS jsonb),
               checks = CAST(:chk AS jsonb), digest = :dg, source = CAST(:src AS jsonb),
               updated_at = now()
           WHERE id = :id AND state = 'processing'""",
        id=r["id"],
        mark=json.dumps(cols["mark"]) if cols["mark"] else None,
        word=json.dumps(cols["wordmark"]) if cols["wordmark"] else None,
        ink=cols["ink"],
        acc=cols["accent"],
        an=cols["accent_night"],
        ad=cols["accent_day"],
        pal=json.dumps(cols["palette"]),
        opt=json.dumps(cols["options"]),
        chk=json.dumps(cols["checks"], ensure_ascii=False),
        dg=cols["digest"],
        src=json.dumps(cols["source"]),
    )
    out = await load_id(tx, r["id"])
    assert out is not None
    code = out["company_code"]
    await audit.record(
        tx,
        MEDIA,
        company_id=out["company_id"],
        action="brand.traced",
        action_class="A0",
        target_kind="brand",
        target_ref=_ref(code, out["version"]),
        summary=f"proposed: {len((cols['mark'] or {}).get('layers', []))} mark layer(s), "
        f"detail {cols['options']['detail']}, iou {cols['checks'].get('iou')}",
    )
    await _emit(tx, code, out, "proposed")
    return out


async def failed(tx: Tx, r: dict[str, Any], reason: str) -> dict[str, Any]:
    reason = reason if reason in brand.REASONS else "unreadable"
    await tx.exec(
        """UPDATE org.company_brands SET state = 'failed', status_reason = :why, updated_at = now()
           WHERE id = :id AND state = 'processing'""",
        id=r["id"],
        why=reason,
    )
    out = await load_id(tx, r["id"])
    assert out is not None
    code = out["company_code"]
    await audit.record(
        tx,
        MEDIA,
        company_id=out["company_id"],
        action="brand.failed",
        action_class="A0",
        target_kind="brand",
        target_ref=_ref(code, out["version"]),
        summary=reason,
    )
    await _emit(tx, code, out, "failed")
    return out


# --------------------------------------------------------------------- seed --
def brands_dir() -> Path:
    return Path(os.environ.get("HQ_BRANDS_DIR", DEFAULT_DIR))


async def seed(tx: Tx, root: Path | None = None) -> int:
    """Version 1, active, for every folder of design/brand/companies/<code>/
    whose company exists and has no brand version yet (an upload is never
    touched; idempotent). No company code is written anywhere: folders are
    read. Returns how many companies were seeded."""
    root = root or brands_dir()
    if not root.is_dir():
        return 0
    from hq_api import brand_trace

    added = 0
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        code = folder.name.upper()
        co = await tx.first(
            "SELECT id, code, kind FROM core.companies WHERE code = :c AND kind = 'company'", c=code
        )
        if co is None:
            continue
        if await tx.scalar(
            "SELECT 1 FROM org.company_brands WHERE company_id = :co LIMIT 1", co=co["id"]
        ):
            continue
        try:
            got = brand.seed_folder(folder)
        except (OSError, ValueError, UnicodeDecodeError):
            log.warning("brand seed: unreadable folder", extra={"company": code})
            continue
        if got is None:
            continue
        mark, wordmark = got["mark"], got["wordmark"]
        ink, accent = brand.colours_of(mark)
        themed = brand.theme_accents(accent)
        try:
            measured = brand_trace.shape_checks(mark)
        except Exception:  # noqa: BLE001 - a seed never fails the migration
            log.warning("brand seed: could not rasterise", extra={"company": code})
            measured = {"min_feature_px_16": 0.0, "palette": [{"hex": ink, "share": 1.0}]}
        small = measured["min_feature_px_16"]
        _, _, vw, vh = (float(v) for v in mark["vb"].split())
        cols = {
            "mark": mark,
            "wordmark": wordmark,
            "ink": ink,
            "accent": accent,
            "accent_night": themed["accent_night"],
            "accent_day": themed["accent_day"],
        }
        checks = {
            "paths_bytes": brand.paths_bytes(mark, wordmark),
            "min_feature_px_16": small,
            "iou": 1.0,
            "contrast_night": themed["contrast_night"],
            "contrast_day": themed["contrast_day"],
            "warnings": ([brand.WARN_SMALL] if small < 1 else []) + themed["warnings"],
        }
        source = {
            "kind": "seed",
            "file_id": None,
            "path": f"design/brand/companies/{folder.name}/",
            "sha256": got["sha256"],
            "width": round(vw),
            "height": round(vh),
            "has_alpha": True,
        }
        colours = {x["color"] for x in mark["layers"]}
        await tx.exec(
            """INSERT INTO org.company_brands (company_id, version, state, part, source, mark, wordmark,
                   ink, accent, accent_night, accent_day, palette, options, checks, digest,
                   created_by_kind, created_by_code, activated_at)
               VALUES (:co, 1, 'active', 'mark', CAST(:src AS jsonb), CAST(:mark AS jsonb),
                       CAST(:word AS jsonb), :ink, :acc, :an, :ad, CAST(:pal AS jsonb),
                       CAST(:opt AS jsonb), CAST(:chk AS jsonb), :dg, 'service', 'seed', now())""",
            co=co["id"],
            src=json.dumps(source),
            mark=json.dumps(mark),
            word=json.dumps(wordmark) if wordmark else None,
            ink=ink,
            acc=accent,
            an=themed["accent_night"],
            ad=themed["accent_day"],
            pal=json.dumps(measured["palette"]),
            opt=json.dumps(
                {"colors": min(4, len(colours)), "detail": brand.OPTIONS_DEFAULT_DETAIL}
            ),
            chk=json.dumps(checks, ensure_ascii=False),
            dg=brand.digest(cols),
        )
        await audit.record(
            tx,
            SEEDER,
            company_id=co["id"],
            action="brand.seed",
            action_class="A0",
            target_kind="brand",
            target_ref=_ref(code, 1),
            summary=f"from {source['path']} ({', '.join(got['files'])})"[:300],
        )
        added += 1
    return added
