"""Company founding and server provisioning (prompt 09, contract §18.8).

A founding (C-0001) belongs to the holding:
  auditing   the repository is audited read-only (a workshop session under an
             automatic read-only grant while a runtime exists; otherwise
             github.read and reading, nothing is executed) by the platform
             SRE or, without one, the AI Ops head: a deliverable with the
             report and five scores
  proposed   the AI Ops head proposes the company (one company_found card,
             with the default or proposed server plan beside it)
  sealed     the owner sealed it: the company exists as DATA (§0, no code
             change; paused until activation), its workshop workspace, and
             the server plan waits for its own seal (server_plan, A3)
  provisioning -> ready_for_login (the provisioner built the server) ->
  active     the owner logged in and activated it (🔏): its CEO starts.

A server plan (PV-0001) is sealed on its digest (hq_common.provisioning):
the step-up target is the digest, the api recomputes it, so a plan changed
after the owner saw it cannot be sealed, and the provisioner refuses a plan
whose digest differs from its seal. The provisioner is code: it executes the
sealed plan only; this module hands runs out and records what it reports.

Review 9.2 (contract §18.16): cancel closes everything (its cards are
withdrawn, a sealed but unrun plan is proposed again, its audit and proposal
work is cancelled, its workshop session stops) and nothing of a cancelled
founding is ever sealed, created or built; a failed run returns the
founding to `sealed` (resume or cancel); a run the provisioner went quiet on
is failed by the reaper; SSH comes only from the owner's own addresses.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, Field

from hq_api import audit, events
from hq_api.db import Tx
from hq_api.domain import brands, notify, templates
from hq_api.domain import work as W
from hq_api.domain.brands import FoundingBrand
from hq_api.errors import ApiError
from hq_api.principal import Principal
from hq_api.schemas import Actor, actor
from hq_common import provisioning as P
from hq_common.redact import scrub

log = logging.getLogger("hq_api.founding")

SERVICE = Principal(kind="service", code="founding", role="service")
STEPS: tuple[tuple[str, str], ...] = (
    ("ssh-key", "کلید SSH مالک"),
    ("firewall", "فایروال هتزنر"),
    ("server", "ساخت سرور"),
    ("boot", "روشن شدن"),
    ("cloud-init", "نصب‌ها روی سرور"),
    ("verify", "بررسی نسخه‌ها و سخت‌سازی"),
    ("login", "آماده‌ی ورود مالک"),
)
STEP_KEYS = tuple(k for k, _ in STEPS)
AXES = ("architecture", "quality", "security", "tests", "debt")
OPEN_STATES = ("auditing", "proposed", "sealed", "provisioning", "ready_for_login")
CALLBACK_TTL = timedelta(minutes=60)
TEMPLATE = "standard"
# A new company's first server, when nobody planned one (rule before AI):
# small, the default location, every reviewed software key the plan allows.
DEFAULT_TYPE = "cpx22"
DEFAULT_LOCATION = "fsn1"
AUDITOR_ROLES = ("hub_platform_sre", "aiops_head")  # the first active one audits
PROPOSER_ROLE = "aiops_head"
_SCORE = re.compile(r"^\s*([0-9]{1,2}(?:\.[0-9])?)\s*(?:/\s*10)?")
CANCEL_NOTE = "تأسیس لغو شد؛ این کارت دیگر معتبر نیست."
# The reaper (review 9.2 §2.3): a run the provisioner has said nothing about
# for this long is failed (the provisioner's longest silent wait is the
# callback's 60 minutes; the margin covers a slow poll).
REAP_EVERY_S = 300


# ------------------------------------------------------------------ models --
class FirewallRule(BaseModel):
    direction: Literal["in"] = "in"
    protocol: Literal["tcp", "udp", "icmp"]
    port: str | None = Field(default=None, max_length=11)
    sources: list[str] = Field(min_length=1, max_length=100)
    note_fa: str = Field(default="", max_length=200)


class PlanFields(BaseModel):
    """What server.plan (and a founding's proposal) may set; the rest is ours."""

    name: str = Field(min_length=1, max_length=63)
    type: str = Field(min_length=2, max_length=10)
    location: str = Field(min_length=2, max_length=10)
    private_network: bool = False
    firewall: list[FirewallRule] = Field(default_factory=list, max_length=50)
    software: list[str] = Field(min_length=1, max_length=20)
    work_user: str = Field(min_length=2, max_length=32)
    repo: str | None = Field(default=None, max_length=200)


class PlanPrice(BaseModel):
    """Where `monthly_eur` came from (§18.16): Hetzner's monthly net prices, EUR."""

    server: str | None = None
    ipv4: str | None = None
    network: str | None = None
    source: str = ""
    at: str | None = None


class ServerPlan(BaseModel):
    id: UUID
    ref: str
    founding: str | None
    company: str
    name: str
    type: str
    location: str
    image: str
    private_network: bool
    firewall: list[dict[str, Any]]
    software: list[str]
    work_user: str
    repo: str | None
    monthly_eur: str | None
    digest: str
    state: str
    decision_ref: str | None
    run: UUID | None
    # §18.16: what stops a seal (empty: it may be sealed), the price's source
    problems: list[str] = Field(default_factory=list)
    price: PlanPrice | None = None
    sealed_at: datetime | None = None
    version: int = 1


class Step(BaseModel):
    key: str
    title_fa: str
    state: Literal["pending", "running", "done", "failed"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log_tail: list[str] = Field(default_factory=list)


class HostKey(BaseModel):
    """One of the new server's SSH host keys, as `ssh` shows it on the first
    login (`SHA256:` + base64 of the key blob's sha256)."""

    type: str
    fingerprint_sha256: str


class RunServer(BaseModel):
    name: str
    ipv4: str | None = None
    ipv6: str | None = None
    private_ip: str | None = None
    # §18.16: the owner checks them before the first login
    host_keys: list[HostKey] = Field(default_factory=list)


class ProvisionRun(BaseModel):
    id: UUID
    plan: str
    state: Literal["queued", "running", "done", "failed"]
    steps: list[Step]
    server: RunServer | None
    login: dict[str, Any] | None
    error: dict[str, Any] | None = None
    created_at: datetime
    finished_at: datetime | None = None


class FoundingAudit(BaseModel):
    session_ref: str | None = None
    report_md: str
    scores: dict[str, float | None]
    deliverable: str | None = None


class FoundingSource(BaseModel):
    kind: Literal["repo", "idea"]
    repo: str | None = None
    brief_md: str = ""


class Founding(BaseModel):
    id: UUID
    ref: str
    name_fa: str | None
    name_en: str | None
    code: str | None
    source: FoundingSource
    state: str
    audit: FoundingAudit | None
    proposal: dict[str, Any] | None
    decision_ref: str | None
    # §18.16: the plan is a ref; the plan itself beside it
    plan: str | None
    plan_detail: ServerPlan | None = None
    company: str | None
    created_at: datetime
    updated_at: datetime
    # ⟨additive⟩ who does what next
    created_by: Actor | None = None
    audit_work: str | None = None
    proposal_work: str | None = None
    workspace: str | None = None
    # ⟨1.4.6⟩ the step «مُهر شرکت» (§18.14), open once the company exists
    brand: FoundingBrand = Field(
        default_factory=lambda: FoundingBrand(state="missing", version=None)
    )


# ------------------------------------------------------------------- plans --
PLAN_SQL = """
    SELECT p.*, f.ref AS founding_ref, d.ref AS decision_ref,
           (SELECT r.id FROM provisioning.runs r WHERE r.plan_id = p.id
             ORDER BY r.created_at DESC LIMIT 1) AS run_id
    FROM provisioning.plans p
    LEFT JOIN core.foundings f ON f.id = p.founding_id
    LEFT JOIN cartable.decisions d ON d.id = p.decision_id
"""


def plan_doc(r: dict[str, Any]) -> dict[str, Any]:
    """The plan as both sides hash it (hq_common.provisioning.digest)."""
    eur = r.get("monthly_eur")
    return {
        "id": str(r["id"]),
        "ref": r["ref"],
        "founding": r.get("founding_ref"),
        "company": r["company_code"],
        "name": r["name"],
        "type": r["type"],
        "location": r["location"],
        "image": r["image"],
        "private_network": bool(r["private_network"]),
        "firewall": list(r["firewall"] or []),
        "software": list(r["software"] or []),
        "work_user": r["work_user"],
        "repo": r.get("repo"),
        "monthly_eur": None if eur is None else str(Decimal(eur).quantize(Decimal("0.01"))),
    }


def render_price(src: dict[str, Any] | None) -> PlanPrice | None:
    """The price's source as §18.16 serves it (also from a row priced before 9.2)."""
    if not src:
        return None
    return PlanPrice(
        server=src.get("server") or src.get("server_monthly_net"),
        ipv4=src.get("ipv4") or src.get("ipv4_monthly_net"),
        network=src.get("network") or "0.00",
        source=str(src.get("source") or ""),
        at=src.get("at"),
    )


async def owner_ssh_sources(tx: Tx) -> list[str]:
    """The owner's addresses SSH may come from (owner settings)."""
    return [
        str(s)
        for s in await tx.scalar("SELECT provision_ssh_sources FROM owner.settings WHERE id = 1")
        or []
    ]


def plan_problems(r: dict[str, Any], ssh_sources: list[str]) -> list[str]:
    """What stops this plan's seal: the shared rules (SSH from the owner's
    addresses only) and, here, a price (no price, no seal)."""
    doc = plan_doc(r)
    probs = P.problems(doc, ssh_sources=ssh_sources)
    if doc["monthly_eur"] is None:
        probs.append("monthly_eur: no price yet (the provisioner is off: make hetzner-token)")
    return probs


def render_plan(r: dict[str, Any], ssh_sources: list[str]) -> ServerPlan:
    doc = plan_doc(r)
    return ServerPlan(
        **{k: v for k, v in doc.items() if k != "id"},
        id=r["id"],
        digest=r["digest"],
        state=r["state"],
        decision_ref=r.get("decision_ref"),
        run=r.get("run_id"),
        problems=plan_problems(r, ssh_sources) if r["state"] == "proposed" else [],
        price=render_price(r.get("price")),
        sealed_at=r.get("sealed_at"),
        version=r["version"],
    )


async def load_plan(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec("SELECT 1 FROM provisioning.plans WHERE ref = :r FOR UPDATE", r=ref)
    return await tx.one(PLAN_SQL + " WHERE p.ref = :r", r=ref, not_found="not_found")


def _clean_fields(fields: PlanFields) -> dict[str, Any]:
    rules = [
        {
            "direction": "in",
            "protocol": r.protocol,
            "port": r.port if r.protocol != "icmp" else None,
            "sources": list(r.sources),
            "note_fa": scrub(r.note_fa)[:200],
        }
        for r in fields.firewall
    ]
    return {
        "name": fields.name,
        "type": fields.type,
        "location": fields.location,
        "private_network": fields.private_network,
        "firewall": rules,
        "software": P.ordered(fields.software)
        + [k for k in fields.software if k not in P.SOFTWARE],
        "work_user": fields.work_user,
        "repo": fields.repo,
    }


async def save_plan(
    tx: Tx,
    who: Principal,
    fields: PlanFields,
    *,
    company_id: UUID,
    company_code: str,
    founding_id: UUID | None = None,
    ref: str | None = None,
    price: tuple[Decimal | None, dict[str, Any] | None] = (None, None),
    card: bool = True,
) -> dict[str, Any]:
    """A new plan, or a new version of a proposed or sealed one (a sealed
    plan changed is no longer sealed: its seal was bound to the old digest).
    Unknown software keys are refused before anything is stored."""
    clean = _clean_fields(fields)
    unknown = sorted({k for k in fields.software if k not in P.SOFTWARE})
    if unknown:
        raise ApiError(
            422,
            "validation_failed",
            fields={"software": f"unknown keys: {', '.join(unknown)[:200]}"},
        )
    eur, price_src = price
    row: dict[str, Any] | None = None
    if ref is not None:
        cur = await load_plan(tx, ref, lock=True)
        founding_id = cur["founding_id"]
    if await founding_state(tx, founding_id) == "cancelled":
        # Nothing of a cancelled founding is planned, carded or sealed again.
        raise ApiError(409, "validation_failed", "the founding is cancelled")
    if ref is not None:
        if cur["state"] not in ("proposed", "sealed"):
            raise ApiError(409, "validation_failed", f"{ref} is {cur['state']}: make a new plan")
        if cur["company_id"] != company_id:
            raise ApiError(
                422, "validation_failed", fields={"company": "the plan keeps its company"}
            )
        if (
            eur is None
            and cur["monthly_eur"] is not None
            and ((cur["type"], cur["location"]) == (clean["type"], clean["location"]))
        ):
            eur, price_src = Decimal(cur["monthly_eur"]), cur["price"]
        voided = cur["state"] == "sealed"
        await tx.exec(
            """UPDATE provisioning.plans SET name = :name, type = :type, location = :location,
                   private_network = :pn, firewall = CAST(:fw AS jsonb), software = CAST(:sw AS jsonb),
                   work_user = :wu, repo = :repo, monthly_eur = :eur, price = CAST(:price AS jsonb),
                   state = 'proposed', sealed_digest = NULL, sealed_at = NULL, seal_step_up_id = NULL,
                   decision_id = CASE WHEN :voided OR NOT EXISTS (
                                          SELECT 1 FROM cartable.decisions dd
                                          WHERE dd.id = provisioning.plans.decision_id
                                            AND dd.status = 'pending')
                                      THEN NULL ELSE decision_id END,
                   version = version + 1, updated_at = now()
               WHERE id = :id""",
            id=cur["id"],
            name=clean["name"],
            type=clean["type"],
            location=clean["location"],
            pn=clean["private_network"],
            fw=json.dumps(clean["firewall"], ensure_ascii=False),
            sw=json.dumps(clean["software"]),
            wu=clean["work_user"],
            repo=clean["repo"],
            eur=eur,
            price=json.dumps(price_src) if price_src else None,
            voided=voided,
        )
        row = await load_plan(tx, ref)
        action = "provision.plan_revise" + (" (seal void)" if voided else "")
    else:
        new = await tx.one(
            """INSERT INTO provisioning.plans (company_id, company_code, founding_id, name, type, location,
                   private_network, firewall, software, work_user, repo, monthly_eur, price, digest,
                   created_by_kind, created_by_code)
               VALUES (:co, :cc, :f, :name, :type, :location, :pn, CAST(:fw AS jsonb), CAST(:sw AS jsonb),
                       :wu, :repo, :eur, CAST(:price AS jsonb), repeat('0', 64), :bk, :bc)
               RETURNING ref""",
            co=company_id,
            cc=company_code,
            f=founding_id,
            name=clean["name"],
            type=clean["type"],
            location=clean["location"],
            pn=clean["private_network"],
            fw=json.dumps(clean["firewall"], ensure_ascii=False),
            sw=json.dumps(clean["software"]),
            wu=clean["work_user"],
            repo=clean["repo"],
            eur=eur,
            price=json.dumps(price_src) if price_src else None,
            bk=who.kind,
            bc=who.code,
        )
        row = await load_plan(tx, new["ref"])
        action = "provision.plan_create"
    digest = P.digest(plan_doc(row))
    await tx.exec(
        "UPDATE provisioning.plans SET digest = :d WHERE id = :id", d=digest, id=row["id"]
    )
    row = await load_plan(tx, row["ref"])
    await audit.record(
        tx,
        who,
        company_id=company_id,
        action=action.split(" ")[0],
        action_class="A1",
        target_kind="server_plan",
        target_ref=row["ref"],
        summary=f"{action}: {row['type']} {row['location']}, digest {digest[:12]}",
    )
    if card and row["decision_id"] is None and company_id != await _holding_id(tx, founding_id):
        await plan_card(tx, row)
        row = await load_plan(tx, row["ref"])
    return row


async def _holding_id(tx: Tx, founding_id: UUID | None) -> UUID | None:
    """The holding's id when the plan is a founding's (its company does not
    exist yet: no card until the founding is sealed)."""
    if founding_id is None:
        return None
    holding: UUID = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
    return holding


async def plan_card(tx: Tx, row: dict[str, Any]) -> dict[str, Any]:
    """The plan's server_plan card for the owner's cartable; its seal is the
    digest, at /provisioning/plans/{ref}/seal (never the cartable's approve)."""
    from hq_api.domain import decisions as D

    eur = row["monthly_eur"]
    d = await D.propose(
        tx,
        SERVICE,
        company_id=row["company_id"],
        company_code=row["company_code"],
        body=D.DecisionIn(
            kind="server_plan",
            title=f"سرور {row['name']} برای {row['company_code']} ({row['ref']})"[:300],
            what=(
                f"{row['type']} در {row['location']} · {len(row['software'] or [])} نرم‌افزار"
                f" · هزینه‌ی ماهانه {eur if eur is not None else 'نامعلوم'} یورو"
            ),
            why="ساخت سرور با API هتزنر هزینه‌ی واقعی دارد: مُهر روی digest همین طرح.",
            risk="medium",
            reversible=False,
            payload={"plan": row["ref"], "company": row["company_code"]},
        ),
        thread_code=None,
    )
    await tx.exec(
        "UPDATE provisioning.plans SET decision_id = :d WHERE id = :id", d=d["id"], id=row["id"]
    )
    return d


async def seal(tx: Tx, who: Principal, row: dict[str, Any], *, step_up_id: UUID) -> dict[str, Any]:
    """The owner's seal (the step-up was consumed on this exact digest)."""
    from hq_api.domain import decisions as D

    if row["state"] != "proposed":
        raise ApiError(409, "validation_failed", f"{row['ref']} is {row['state']}")
    if row["founding_id"] is not None:
        # Nothing of a cancelled founding is ever sealed (§18.16).
        fstate = await tx.scalar(
            "SELECT state FROM core.foundings WHERE id = :f FOR SHARE", f=row["founding_id"]
        )
        if fstate != "sealed":
            raise ApiError(
                409, "validation_failed", f"the founding {row['founding_ref']} is {fstate}"
            )
    doc = plan_doc(row)
    if P.digest(doc) != row["digest"]:  # never: every write recomputes it
        raise ApiError(409, "seal_mismatch", "the plan changed: look at it again")
    probs = P.problems(doc, ssh_sources=await owner_ssh_sources(tx))
    if probs:
        raise ApiError(
            422, "plan_invalid", fields={f"plan.{i}": p[:200] for i, p in enumerate(probs[:20])}
        )
    if row["monthly_eur"] is None:
        raise ApiError(409, "price_unknown", "the monthly cost is not known yet")
    if row["company_code"] != await tx.scalar(
        "SELECT code FROM core.companies WHERE id = :id", id=row["company_id"]
    ):
        raise ApiError(409, "validation_failed", "the plan's company does not exist yet")
    if row["decision_id"] is None:
        await plan_card(tx, row)
        row = await load_plan(tx, row["ref"])
    d = await D.load(tx, row["decision_ref"], lock=True)
    if d["status"] not in ("pending", "approved"):
        # The owner declined this plan's card, or it lapsed (§4): a new
        # version of the plan gets a new card.
        raise ApiError(
            409,
            "validation_failed",
            f"the plan's card {d['ref']} is {d['status']}: revise the plan",
        )
    if d["status"] == "pending":
        await D.decide(tx, who, d, "approved", note=f"مُهر طرح {row['ref']}", step_up_id=step_up_id)
    await tx.exec(
        """UPDATE provisioning.plans SET state = 'sealed', sealed_digest = digest, sealed_at = now(),
               seal_step_up_id = :su, updated_at = now()
           WHERE id = :id""",
        id=row["id"],
        su=step_up_id,
    )
    await audit.record(
        tx,
        who,
        company_id=row["company_id"],
        action="provision.seal",
        action_class="A3",
        target_kind="server_plan",
        target_ref=row["ref"],
        summary=f"sealed {row['type']} {row['location']} {row['monthly_eur']} EUR/month on {row['digest'][:12]}",
        step_up=True,
    )
    await events.emit(
        tx,
        row["company_code"],
        "founding.updated",
        row["ref"],
        {"plan": row["ref"], "state": "sealed"},
    )
    return await load_plan(tx, row["ref"])


# ----------------------------------------------------------------- pricing --
async def price_of(
    provisioner_url: str, type_: str, location: str, transport: Any = None
) -> tuple[Decimal | None, dict[str, Any] | None]:
    """The monthly EUR from Hetzner's /pricing through the provisioner; None
    while it is off (no price is made up: a plan without one is not sealed)."""
    if not provisioner_url:
        return None, None
    try:
        async with httpx.AsyncClient(
            base_url=provisioner_url, timeout=15, transport=transport, trust_env=False
        ) as c:
            r = await c.get("/v1/pricing", params={"type": type_, "location": location})
    except httpx.HTTPError:
        return None, None
    if r.status_code != 200:
        return None, None
    data = r.json()
    try:
        eur = Decimal(str(data["monthly_eur"])).quantize(Decimal("0.01"))
    except (KeyError, ArithmeticError, ValueError):
        return None, None
    keep = ("monthly_eur", "monthly_eur_gross", "vat_rate")
    src: dict[str, Any] = {k: str(data[k]) for k in keep if k in data}
    src.update(
        server=str(data["server_monthly_net"]) if "server_monthly_net" in data else None,
        ipv4=str(data["ipv4_monthly_net"]) if "ipv4_monthly_net" in data else None,
        network="0.00",  # a Hetzner private network costs nothing
        source="hetzner /pricing (net, with the primary IPv4)",
        at=datetime.now(UTC).isoformat(),
    )
    return eur, src


# --------------------------------------------------------------- foundings --
FOUNDING_SQL = """
    SELECT f.*, d.ref AS decision_ref, nc.code AS new_company,
           aw.ref AS audit_work_ref, pw.ref AS proposal_work_ref
    FROM core.foundings f
    LEFT JOIN cartable.decisions d ON d.id = f.decision_id
    LEFT JOIN core.companies nc ON nc.id = f.new_company_id
    LEFT JOIN work.work aw ON aw.id = f.audit_work_id
    LEFT JOIN work.work pw ON pw.id = f.proposal_work_id
"""


async def load(tx: Tx, ref: str, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec("SELECT 1 FROM core.foundings WHERE ref = :r FOR UPDATE", r=ref)
    return await tx.one(FOUNDING_SQL + " WHERE f.ref = :r", r=ref, not_found="not_found")


async def plan_of(tx: Tx, founding_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        PLAN_SQL + " WHERE p.founding_id = :f ORDER BY p.created_at DESC LIMIT 1", f=founding_id
    )


async def render(tx: Tx, r: dict[str, Any], ssh_sources: list[str] | None = None) -> Founding:
    plan = await plan_of(tx, r["id"])
    brand = await brands.founding_brand(tx, r.get("new_company_id"))
    if ssh_sources is None:
        ssh_sources = await owner_ssh_sources(tx)
    a = r.get("audit")
    src = r["source"] or {}
    return Founding(
        id=r["id"],
        ref=r["ref"],
        name_fa=r["name_fa"],
        name_en=r["name_en"],
        code=r["code"],
        source=FoundingSource(
            kind=src["kind"], repo=src.get("repo"), brief_md=str(src.get("brief_md") or "")
        ),
        state=r["state"],
        audit=FoundingAudit.model_validate(a) if a else None,
        proposal=r.get("proposal"),
        decision_ref=r.get("decision_ref"),
        plan=plan["ref"] if plan else None,
        plan_detail=render_plan(plan, ssh_sources) if plan else None,
        company=r.get("new_company"),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        created_by=actor(r["created_by_kind"], r["created_by_code"]),
        audit_work=r.get("audit_work_ref"),
        proposal_work=r.get("proposal_work_ref"),
        workspace=r.get("workspace_code"),
        brand=brand,
    )


async def _holding(tx: Tx) -> dict[str, Any]:
    return await tx.one("SELECT id, code FROM core.companies WHERE kind = 'holding'")


async def _role_holder(tx: Tx, holding_id: UUID, roles: tuple[str, ...]) -> str | None:
    for role in roles:
        code: str | None = await tx.scalar(
            """SELECT code FROM core.employees WHERE company_id = :co AND role = :r AND status = 'active'
               ORDER BY hired_at LIMIT 1""",
            co=holding_id,
            r=role,
        )
        if code:
            return code
    return None


async def _emit(tx: Tx, holding: str, f: dict[str, Any], change: str) -> None:
    await events.emit(
        tx, holding, "founding.updated", f["ref"], {"state": f["state"], "change": change}
    )


async def create(
    tx: Tx, who: Principal, source: dict[str, Any], *, runtime_on: bool
) -> dict[str, Any]:
    """POST /foundings: the founding, then its read-only audit (or, for an
    idea, straight to the proposal)."""
    holding = await _holding(tx)
    row = await tx.one(
        """INSERT INTO core.foundings (company_id, source, created_by_kind, created_by_code)
           VALUES (:co, CAST(:src AS jsonb), :k, :c) RETURNING ref""",
        co=holding["id"],
        src=json.dumps(source, ensure_ascii=False),
        k=who.kind,
        c=who.code,
    )
    f = await load(tx, row["ref"])
    await audit.record(
        tx,
        who,
        company_id=holding["id"],
        action="founding.create",
        action_class="A1",
        target_kind="founding",
        target_ref=f["ref"],
        summary=f"from {source['kind']}" + (f" {source['repo']}" if source.get("repo") else ""),
    )
    if source["kind"] == "repo":
        await _start_audit(tx, who, f, holding, runtime_on=runtime_on)
    else:
        await _start_proposal(tx, f, holding, None)
    f = await load(tx, f["ref"])
    await _emit(tx, holding["code"], f, "created")
    return f


async def _start_audit(
    tx: Tx, who: Principal, f: dict[str, Any], holding: dict[str, Any], *, runtime_on: bool
) -> None:
    from hq_api.workshop import domain as workshop

    auditor = await _role_holder(tx, holding["id"], AUDITOR_ROLES)
    if auditor is None:
        raise ApiError(422, "validation_failed", "no platform SRE or AI Ops head to audit it")
    repo = f["source"]["repo"]
    grant_ref = workspace = None
    if runtime_on and who.is_owner:
        # The owner's founding is the read-only grant's seal: read only, no push.
        workspace = f"{holding['code']}-{f['ref'].replace('-', '')}"
        await tx.exec(
            """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
               VALUES (:co, :code, :repo, 'main', :title, CAST(:policy AS jsonb))
               ON CONFLICT (code) DO NOTHING""",
            co=holding["id"],
            code=workspace,
            repo=repo,
            title=f"ممیزی تأسیس {f['ref']}"[:200],
            policy=json.dumps({**workshop.DEFAULT_POLICY, "may_open_pr": False}),
        )
        g = await workshop.create_grant(
            tx,
            who,
            workshop.direct_audit(who),
            workspace_code=workspace,
            actions=["read"],
            driver_code=auditor,
            budget_usd=Decimal("5"),
            expires_at=datetime.now(UTC) + timedelta(days=2),
            sealed=False,
        )
        grant_ref = g["ref"]
        await tx.exec(
            "UPDATE core.foundings SET workspace_code = :w, grant_id = :g WHERE id = :id",
            w=workspace,
            g=g["id"],
            id=f["id"],
        )
    how = (
        f"A read-only Code Workshop grant {grant_ref} on workspace {workspace} is yours (read only, "
        "no push, $5): open a session with `workshop.session` and audit there."
        if grant_ref
        else "The Code Workshop has no runtime yet: audit WITHOUT executing anything, with "
        "`github.read` (if it is configured) and `web.read` of the repository's public pages."
    )
    w = await W.create(
        tx,
        SERVICE,
        company_id=holding["id"],
        company_code=holding["code"],
        title=f"ممیزی ریپو برای تأسیس {f['ref']}: {repo}"[:300],
        brief=(
            f"Founding {f['ref']}: audit the repository {repo} READ-ONLY (prompt 09 §2, contract §18.8).\n"
            f"{how}\n\n"
            "Report: architecture, code quality, security, tests, technical debt and the running cost, "
            "each with evidence. Deliver it with `deliver` on this work item: body_md = the report; "
            "evidence = one item of kind `metric` per axis with ref = the axis "
            f"({', '.join(AXES)}) and note = the score `N/10` and why."
        ),
        kind="one_off",
        priority="P2",
        assignee_code=auditor,
    )
    await W.event(tx, w, "founding", SERVICE, {"founding": f["ref"], "step": "audit"})
    await tx.exec(
        "UPDATE core.foundings SET audit_work_id = :w, updated_at = now() WHERE id = :id",
        w=w["id"],
        id=f["id"],
    )


def scores_of(evidence: list[dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = dict.fromkeys(AXES)
    for e in evidence or []:
        ref = str(e.get("ref") or "").strip().lower()
        if e.get("kind") == "metric" and ref in out:
            m = _SCORE.match(str(e.get("note") or ""))
            if m and 0 <= float(m.group(1)) <= 10:
                out[ref] = float(m.group(1))
    return out


async def on_delivered(
    tx: Tx, w: dict[str, Any], deliverable_ref: str, body_md: str, evidence: list[dict[str, Any]]
) -> None:
    """The deliver route's hook: the audit of a founding arrived."""
    f = await tx.first(
        FOUNDING_SQL + " WHERE f.audit_work_id = :w AND f.state = 'auditing' FOR UPDATE OF f",
        w=w["id"],
    )
    if f is None:
        return
    session = next(
        (str(e.get("ref")) for e in evidence or [] if str(e.get("ref") or "").startswith("S-")),
        None,
    )
    report = {
        "session_ref": session,
        "report_md": scrub(body_md)[:20000],
        "scores": scores_of(evidence),
        "deliverable": deliverable_ref,
    }
    await tx.exec(
        "UPDATE core.foundings SET audit = CAST(:a AS jsonb), updated_at = now() WHERE id = :id",
        a=json.dumps(report, ensure_ascii=False),
        id=f["id"],
    )
    holding = await _holding(tx)
    await _start_proposal(tx, f, holding, report)
    await _emit(tx, holding["code"], await load(tx, f["ref"]), "audited")


async def _start_proposal(
    tx: Tx, f: dict[str, Any], holding: dict[str, Any], report: dict[str, Any] | None
) -> None:
    proposer = await _role_holder(tx, holding["id"], (PROPOSER_ROLE,))
    if proposer is None:
        raise ApiError(422, "validation_failed", "no AI Ops head to propose the company")
    src = f["source"]
    summary = (
        f"Audit {report['deliverable']}: scores "
        + ", ".join(f"{k} {v if v is not None else '?'}" for k, v in report["scores"].items())
        if report
        else f"An idea (no repository):\n{scrub(str(src.get('brief_md') or ''))[:8000]}"
    )
    w = await W.create(
        tx,
        SERVICE,
        company_id=holding["id"],
        company_code=holding["code"],
        title=f"پیشنهاد شرکت تازه برای تأسیس {f['ref']}"[:300],
        brief=(
            f"Founding {f['ref']} ({src.get('repo') or 'an idea'}). {summary}\n\n"
            "Propose the company with `propose` kind `company_found` and payload "
            '{founding: "' + f["ref"] + '", code (2-10 capitals, a new one), name_fa, name_en, '
            "departments: [codes of the standard template: TECH, GROWTH, SALES, PRODUCT, FIN, QUANT, AIOPS, HR], "
            "kpis: [{name_fa, target}], team: [{role, model, monthly_usd, department?, title_fa?}], "
            "roadmap_md (90 days), monthly_usd}. Cite the audit as evidence in what_md/why_md. "
            "The server plan is made beside it (rule-based; the owner seals it apart)."
        ),
        kind="one_off",
        priority="P2",
        assignee_code=proposer,
    )
    await W.event(tx, w, "founding", SERVICE, {"founding": f["ref"], "step": "proposal"})
    await tx.exec(
        "UPDATE core.foundings SET proposal_work_id = :w, updated_at = now() WHERE id = :id",
        w=w["id"],
        id=f["id"],
    )


async def check_proposal(tx: Tx, payload: dict[str, Any], company_id: UUID) -> None:
    """A company_found card: its founding is open and waits for a proposal,
    the code is new, the departments are the template's."""
    f = await tx.first(FOUNDING_SQL + " WHERE f.ref = :r", r=payload["founding"])
    if f is None or f["company_id"] != company_id:
        raise ApiError(422, "validation_failed", fields={"payload.founding": "unknown founding"})
    if f["state"] not in ("auditing", "proposed") or (
        f["state"] == "auditing" and f["audit"] is None and f["source"]["kind"] == "repo"
    ):
        raise ApiError(
            422, "validation_failed", fields={"payload.founding": f"{f['ref']} is {f['state']}"}
        )
    if f["state"] == "proposed" and f["decision_id"] is not None:
        raise ApiError(409, "validation_failed", fields={"payload.founding": "already proposed"})
    if payload.get("plan"):
        # A plan named on the card is this founding's own (else it is refused, never ignored).
        own = await tx.scalar(
            "SELECT 1 FROM provisioning.plans WHERE ref = :r AND founding_id = :f",
            r=payload["plan"],
            f=f["id"],
        )
        if not own:
            raise ApiError(
                422, "validation_failed", fields={"payload.plan": "not a plan of this founding"}
            )
    if await tx.scalar("SELECT 1 FROM core.companies WHERE code = :c", c=payload["code"]) or (
        await tx.scalar(
            "SELECT 1 FROM core.foundings WHERE code = :c AND state <> 'cancelled' AND id <> :id",
            c=payload["code"],
            id=f["id"],
        )
    ):
        raise ApiError(422, "validation_failed", fields={"payload.code": "already taken"})
    known = {d["code"] for d in (templates.template(TEMPLATE) or {}).get("departments") or []}
    bad = sorted(set(payload["departments"]) - known)
    if bad:
        raise ApiError(
            422,
            "validation_failed",
            fields={"payload.departments": f"not in the {TEMPLATE} template: {', '.join(bad)}"},
        )


async def default_plan(tx: Tx, code: str, repo: str | None) -> PlanFields:
    """The rule-based first server of a new company (nobody planned one)."""
    sources = list(
        await tx.scalar("SELECT provision_ssh_sources FROM owner.settings WHERE id = 1") or []
    )
    software = [k for k in P.DEFAULT_SOFTWARE if repo or k != "repo-clone"]
    rules = (
        [FirewallRule(protocol="tcp", port="22", sources=sources, note_fa="SSH از نشانی‌های مالک")]
        if sources
        else []
    )
    # A new account, never one of the system's (MAIL, PROXY, BACKUP ... are codes too).
    user = P.default_work_user(code)
    return PlanFields(
        name=f"{code.lower()}-app-1",
        type=DEFAULT_TYPE,
        location=DEFAULT_LOCATION,
        private_network=True,
        firewall=rules,
        software=software,
        work_user=user,
        repo=repo,
    )


async def proposed(tx: Tx, d: dict[str, Any], payload: dict[str, Any]) -> None:
    """A company_found card exists: the founding waits for the owner; its
    server plan exists beside the card (proposed, sealed apart)."""
    f = await load(tx, payload["founding"], lock=True)
    plan = await plan_of(tx, f["id"])
    if plan is None:
        plan = await save_plan(
            tx,
            SERVICE,
            await default_plan(tx, payload["code"], f["source"].get("repo")),
            company_id=f["company_id"],
            company_code=payload["code"],
            founding_id=f["id"],
            card=False,
        )
    elif plan["company_code"] != payload["code"] and plan["state"] == "proposed":
        await tx.exec(
            "UPDATE provisioning.plans SET company_code = :c, updated_at = now() WHERE id = :id",
            c=payload["code"],
            id=plan["id"],
        )
        await _redigest(tx, plan["ref"])
    proposal = {
        "departments": payload["departments"],
        "kpis": payload.get("kpis", []),
        "team": payload.get("team", []),
        "roadmap_md": payload.get("roadmap_md", ""),
        "monthly_usd": payload.get("monthly_usd", "0"),
    }
    await tx.exec(
        """UPDATE core.foundings SET state = 'proposed', decision_id = :d, code = :code, name_fa = :nfa,
               name_en = :nen, proposal = CAST(:p AS jsonb), updated_at = now()
           WHERE id = :id""",
        d=d["id"],
        code=payload["code"],
        nfa=payload["name_fa"],
        nen=payload["name_en"],
        p=json.dumps(proposal, ensure_ascii=False, default=str),
        id=f["id"],
    )
    holding = await _holding(tx)
    await _emit(tx, holding["code"], await load(tx, f["ref"]), "proposed")


async def _redigest(tx: Tx, ref: str) -> dict[str, Any]:
    row = await load_plan(tx, ref)
    await tx.exec(
        "UPDATE provisioning.plans SET digest = :d WHERE id = :id",
        d=P.digest(plan_doc(row)),
        id=row["id"],
    )
    return await load_plan(tx, ref)


async def proposal_declined(tx: Tx, d: dict[str, Any], verdict: str) -> None:
    """Rejected: the founding ends; returned: it waits for a new proposal."""
    f = await tx.first(
        "SELECT id, ref, state FROM core.foundings WHERE decision_id = :d FOR UPDATE", d=d["id"]
    )
    if f is None or f["state"] != "proposed":
        return
    state = "cancelled" if verdict == "rejected" else "auditing"
    await tx.exec(
        """UPDATE core.foundings SET state = :s, decision_id = NULL, updated_at = now(),
               cancelled_at = CASE WHEN :s = 'cancelled' THEN now() END
           WHERE id = :id""",
        s=state,
        id=f["id"],
    )
    holding = await _holding(tx)
    await _emit(tx, holding["code"], await load(tx, f["ref"]), verdict)


async def found_company(tx: Tx, d: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    """The effect of a sealed company_found card: the company as DATA (the
    standard template's chosen departments, paused until activation), its
    workspace, and the server plan's own card. Idempotent. Only the card the
    founding waits for founds it (§18.16): a cancelled founding, or a card it
    no longer waits for, makes nothing."""
    f = await load(tx, p["founding"], lock=True)
    if f["new_company_id"] is not None and f["decision_id"] == d["id"]:
        return {"founding": f["ref"], "company": f["new_company"]}
    if f["state"] != "proposed" or f["decision_id"] != d["id"]:
        log.warning(
            "founding: card approved for a founding that does not wait for it",
            extra={"founding": f["ref"], "decision": d["ref"], "state": f["state"]},
        )
        return {"founding": f["ref"], "company": None, "skipped": f"the founding is {f['state']}"}
    await tx.exec("SELECT pg_advisory_xact_lock(hashtext('core.companies.color_index'))")
    co = await tx.one(
        """INSERT INTO core.companies (code, name, kind, name_fa, name_en, color_index, template, status)
           VALUES (:code, :name_en, 'company', :name_fa, :name_en,
                   (SELECT min(slot) FROM generate_series(1, 8) AS slot
                     WHERE slot NOT IN (SELECT color_index FROM core.companies WHERE color_index IS NOT NULL)),
                   :tpl, 'paused')
           RETURNING id""",
        code=p["code"],
        name_fa=p["name_fa"],
        name_en=p["name_en"],
        tpl=TEMPLATE,
    )
    ids = [r["id"] for r in await tx.all("SELECT id FROM core.companies")]
    await tx.rescope(ids)
    added = await templates.apply(
        tx, co["id"], p["code"], TEMPLATE, departments=list(p["departments"])
    )
    repo = f["source"].get("repo")
    workspace = None
    if repo:
        workspace = f"{p['code']}-APP"
        from hq_api.workshop import domain as workshop

        await tx.exec(
            """INSERT INTO workshop.workspaces (company_id, code, repo, default_branch, title_fa, policy)
               VALUES (:co, :code, :repo, 'main', :title, CAST(:policy AS jsonb))
               ON CONFLICT (code) DO NOTHING""",
            co=co["id"],
            code=workspace,
            repo=repo,
            title=f"ریپوی {p['name_fa']}"[:200],
            policy=json.dumps(workshop.DEFAULT_POLICY),
        )
    who = Principal(kind="owner", code="owner", role="owner")
    await audit.record(
        tx,
        who,
        company_id=co["id"],
        action="founding.seal",
        action_class="A2",
        target_kind="company",
        target_ref=p["code"],
        summary=f"founded by {f['ref']} ({d['ref']}): {added}",
        step_up=True,
    )
    await tx.exec(
        """UPDATE core.foundings SET state = 'sealed', new_company_id = :co, updated_at = now()
           WHERE id = :id""",
        co=co["id"],
        id=f["id"],
    )
    plan = await plan_of(tx, f["id"])
    if plan is not None and plan["state"] == "proposed":
        await tx.exec(
            """UPDATE provisioning.plans SET company_id = :co, company_code = :cc, updated_at = now()
               WHERE id = :id""",
            co=co["id"],
            cc=p["code"],
            id=plan["id"],
        )
        plan = await _redigest(tx, plan["ref"])
        if plan["decision_id"] is None:
            await plan_card(tx, plan)
    holding = await _holding(tx)
    await events.emit(tx, p["code"], "control.changed", p["code"], {"change": "company.created"})
    await _emit(tx, holding["code"], await load(tx, f["ref"]), "sealed")
    return {"founding": f["ref"], "company": p["code"], "workspace": workspace}


async def activate(
    tx: Tx, who: Principal, f: dict[str, Any], *, step_up_id: UUID, skip_brand: bool = False
) -> dict[str, Any]:
    """After the owner logged in on the new server: the company goes live and
    its CEO starts (the team of the proposal is the CEO's to hire, under the
    hiring rules). ⟨1.4.6⟩ Without an active brand: 409 not_ready (missing
    ["brand"]) unless `skip_brand` (the company then shows its code)."""
    if f["state"] != "ready_for_login":
        raise ApiError(409, "validation_failed", f"{f['ref']} is {f['state']}")
    has_brand = (await brands.founding_brand(tx, f["new_company_id"])).state == "active"
    if not has_brand and not skip_brand:
        raise ApiError(
            409,
            "not_ready",
            "the company has no sealed brand; seal one or send skip_brand",
            message_fa="مُهر شرکت هنوز ساخته نشده است: لوگو را بده و مُهر کن، یا بدون مُهر فعال کن.",
            missing=["brand"],
        )
    await tx.exec(
        "UPDATE core.companies SET status = 'active' WHERE id = :co AND status = 'paused'",
        co=f["new_company_id"],
    )
    await tx.exec(
        """UPDATE core.foundings SET state = 'active', activated_at = now(), updated_at = now()
           WHERE id = :id""",
        id=f["id"],
    )
    code = f["new_company"]
    proposal = f.get("proposal") or {}
    team = proposal.get("team") or []
    ceo = await tx.first(
        "SELECT code FROM core.employees WHERE company_id = :co AND kind = 'ceo' AND status = 'active'",
        co=f["new_company_id"],
    )
    work_ref = None
    if ceo is not None:
        w = await W.create(
            tx,
            SERVICE,
            company_id=f["new_company_id"],
            company_code=code,
            title=f"شروع کار {code}: نقشه‌ی راه ۹۰ روزه"[:300],
            brief=(
                f"The holding founded {code} ({f['ref']}); the owner activated it. Start: the 90-day "
                f"roadmap and the KPIs below; the proposed team is yours to hire under the hiring rules "
                f"(propose kind hire, with your own monthly estimates; only while hiring is open).\n\n"
                f"KPIs: {json.dumps(proposal.get('kpis') or [], ensure_ascii=False)[:3000]}\n"
                f"Team: {json.dumps(team, ensure_ascii=False, default=str)[:3000]}\n\n"
                f"Roadmap:\n{scrub(str(proposal.get('roadmap_md') or ''))[:12000]}"
            ),
            kind="one_off",
            priority="P2",
            assignee_code=ceo["code"],
        )
        work_ref = w["ref"]
    await audit.record(
        tx,
        who,
        company_id=f["company_id"],
        action="founding.activate",
        action_class="A2",
        target_kind="founding",
        target_ref=f["ref"],
        summary=f"{code} active"
        + (f", {work_ref}" if work_ref else "")
        + ("" if has_brand else ", without a sealed brand (skip_brand)"),
        step_up=True,
    )
    holding = await _holding(tx)
    await _emit(tx, holding["code"], await load(tx, f["ref"]), "activated")
    return await load(tx, f["ref"])


async def cancel(
    tx: Tx, who: Principal, f: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Before it is active, cancel closes everything (§18.16): its pending
    company_found and server_plan cards are withdrawn, a sealed but unrun plan
    is proposed again, its audit and proposal work is cancelled, its read-only
    grant is revoked and its workshop sessions stop (returned, for the
    runtime). A company already made stays (paused): nothing is deleted here.
    Not while a build is queued or running (a failed one returns the
    founding to `sealed`)."""
    if f["state"] in ("active", "cancelled"):
        raise ApiError(409, "validation_failed", f"{f['ref']} is {f['state']}")
    building = await tx.scalar(
        """SELECT 1 FROM provisioning.runs r JOIN provisioning.plans p ON p.id = r.plan_id
           WHERE p.founding_id = :f AND r.state IN ('queued', 'running') LIMIT 1""",
        f=f["id"],
    )
    if f["state"] == "provisioning" or building:
        raise ApiError(409, "validation_failed", "a server is being built: wait for it")
    holding = await _holding(tx)
    cards = await tx.all(
        """UPDATE cartable.decisions d
              SET status = 'withdrawn', decided_at = now(), decided_by_kind = 'service',
                  decided_by_code = 'system', note = :note
             FROM core.companies c
            WHERE c.id = d.company_id AND d.status = 'pending'
              AND ((d.kind = 'company_found' AND d.payload ->> 'founding' = :ref)
                OR (d.kind = 'server_plan' AND (
                      d.id IN (SELECT decision_id FROM provisioning.plans
                                WHERE founding_id = :f AND decision_id IS NOT NULL)
                   OR d.payload ->> 'plan' IN (SELECT ref FROM provisioning.plans
                                                WHERE founding_id = :f))))
        RETURNING d.ref, d.kind, c.code AS company""",
        note=CANCEL_NOTE,
        ref=f["ref"],
        f=f["id"],
    )
    unsealed = await tx.all(
        """UPDATE provisioning.plans SET state = 'proposed', sealed_digest = NULL, sealed_at = NULL,
               seal_step_up_id = NULL, decision_id = NULL, updated_at = now()
           WHERE founding_id = :f AND state = 'sealed'
        RETURNING ref, company_id""",
        f=f["id"],
    )
    work = await tx.all(
        """WITH RECURSIVE down AS (
               SELECT id FROM work.work WHERE id = ANY(CAST(:ids AS uuid[]))
               UNION ALL SELECT c.id FROM work.work c JOIN down ON c.parent_id = down.id)
           UPDATE work.work w SET status = 'cancelled', close_reason = :r, closed_at = now()
             FROM core.companies c
            WHERE w.id IN (SELECT id FROM down) AND w.status = ANY(CAST(:open AS text[]))
              AND c.id = w.company_id
        RETURNING w.ref, c.code AS company""",
        ids=[str(i) for i in (f["audit_work_id"], f["proposal_work_id"]) if i],
        r=f"founding {f['ref']} cancelled",
        open=list(W.OPEN),
    )
    stopped: list[dict[str, Any]] = []
    if f["grant_id"]:
        from hq_api.workshop import domain as workshop

        g = await tx.scalar("SELECT ref FROM workshop.grants WHERE id = :g", g=f["grant_id"])
        if g:
            _grant, stopped = await workshop.revoke_grant(tx, who, workshop.direct_audit(who), g)
    await tx.exec(
        """UPDATE core.foundings SET state = 'cancelled', cancelled_at = now(), updated_at = now()
           WHERE id = :id""",
        id=f["id"],
    )
    for p in unsealed:
        await audit.record(
            tx,
            who,
            company_id=p["company_id"],
            action="provision.seal_void",
            action_class="A1",
            target_kind="server_plan",
            target_ref=p["ref"],
            summary=f"the founding {f['ref']} was cancelled: not built, back to proposed",
        )
    await audit.record(
        tx,
        who,
        company_id=f["company_id"],
        action="founding.cancel",
        action_class="A1",
        target_kind="founding",
        target_ref=f["ref"],
        summary=(
            f"cancelled at {f['state']}: {len(cards)} card(s) withdrawn, {len(unsealed)} plan(s) "
            f"unsealed, {len(work)} work item(s) and {len(stopped)} session(s) stopped"
        )[:300],
    )
    for c in cards:
        await events.emit(
            tx,
            c["company"],
            "decision.updated",
            c["ref"],
            {"status": "withdrawn", "kind": c["kind"], "note": CANCEL_NOTE},
        )
    for w in work:
        await events.emit(tx, w["company"], "work.updated", w["ref"], {"status": "cancelled"})
    await _emit(tx, holding["code"], await load(tx, f["ref"]), "cancelled")
    return await load(tx, f["ref"]), stopped


# -------------------------------------------------------------------- runs --
RUN_SQL = """
    SELECT r.*, p.ref AS plan_ref, p.company_code
    FROM provisioning.runs r JOIN provisioning.plans p ON p.id = r.plan_id
"""


def host_key(line: str) -> HostKey | None:
    """`ssh-ed25519 AAAA... root@x` -> its type and OpenSSH SHA256 fingerprint."""
    parts = str(line).split()
    if len(parts) < 2 or not parts[0].startswith(("ssh-", "ecdsa-", "sk-")):
        return None
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        return None
    fp = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return HostKey(type=parts[0][:40], fingerprint_sha256=f"SHA256:{fp}")


def render_server(r: dict[str, Any]) -> RunServer | None:
    s = r.get("server")
    if not s:
        return None
    lines = ((r.get("cloud_init") or {}).get("ssh_host_keys")) or []
    keys = [k for k in (host_key(x) for x in lines) if k is not None]
    return RunServer(
        name=str(s.get("name") or ""),
        ipv4=s.get("ipv4"),
        ipv6=s.get("ipv6"),
        private_ip=s.get("private_ip"),
        host_keys=keys,
    )


def render_run(r: dict[str, Any]) -> ProvisionRun:
    return ProvisionRun(
        id=r["id"],
        plan=r["plan_ref"],
        state=r["state"],
        steps=[Step.model_validate(s) for s in r["steps"] or []],
        server=render_server(r),
        login=r.get("login"),
        error=r.get("error"),
        created_at=r["created_at"],
        finished_at=r.get("finished_at"),
    )


async def load_run(tx: Tx, run_id: UUID, *, lock: bool = False) -> dict[str, Any]:
    if lock:
        await tx.exec("SELECT 1 FROM provisioning.runs WHERE id = :id FOR UPDATE", id=run_id)
    return await tx.one(RUN_SQL + " WHERE r.id = :id", id=run_id, not_found="not_found")


def _handout(run: dict[str, Any], plan: dict[str, Any], ssh_sources: list[str]) -> dict[str, Any]:
    doc = plan_doc(plan)
    return {
        "id": str(run["id"]),
        "state": run["state"],
        "plan": {
            **doc,
            "digest": plan["digest"],
            "state": plan["state"],
            "decision_ref": plan.get("decision_ref"),
            "run": str(run["id"]),
        },
        "sealed_digest": run["sealed_digest"],
        "steps": [{"key": s["key"], "state": s["state"]} for s in run["steps"] or []],
        # The owner's SSH addresses: the provisioner checks the plan against them too.
        "ssh_sources": ssh_sources,
    }


async def founding_state(tx: Tx, founding_id: UUID | None) -> str | None:
    if founding_id is None:
        return None
    state: str | None = await tx.scalar(
        "SELECT state FROM core.foundings WHERE id = :f", f=founding_id
    )
    return state


async def next_run(tx: Tx) -> dict[str, Any] | None:
    """The provisioner's next job: a resumed run, else the oldest sealed plan
    whose digest is still its seal (a changed one loses its seal instead).
    Nothing of a cancelled founding is built; a plan whose SSH is not from
    the owner's addresses (they changed since the seal) is not built either."""
    sources = await owner_ssh_sources(tx)
    while True:
        resumed = await tx.first(
            RUN_SQL
            + " WHERE r.state = 'queued' ORDER BY r.updated_at LIMIT 1 FOR UPDATE OF r SKIP LOCKED"
        )
        if resumed is None:
            break
        plan = await load_plan(tx, resumed["plan_ref"])
        if await founding_state(tx, plan["founding_id"]) == "cancelled":
            await _refuse_run(tx, resumed, "the founding was cancelled")
            continue
        await tx.exec(
            "UPDATE provisioning.runs SET state = 'running', updated_at = now() WHERE id = :id",
            id=resumed["id"],
        )
        return _handout(await load_run(tx, resumed["id"]), plan, sources)
    while True:
        cand = await tx.first(
            PLAN_SQL
            + """ WHERE p.state = 'sealed' ORDER BY p.sealed_at LIMIT 1 FOR UPDATE OF p SKIP LOCKED"""
        )
        if cand is None:
            return None
        if (
            P.digest(plan_doc(cand)) != cand["sealed_digest"]
            or cand["digest"] != cand["sealed_digest"]
        ):
            await _void_seal(tx, cand)
            continue
        if await founding_state(tx, cand["founding_id"]) == "cancelled":
            await _void_seal(tx, cand, "cancelled")
            continue
        if P.problems(plan_doc(cand), ssh_sources=sources):
            await _void_seal(tx, cand, "rules")
            continue
        steps: list[dict[str, Any]] = [
            {"key": k, "title_fa": t, "state": "pending", "started_at": None, "finished_at": None,
             "log_tail": []}
            for k, t in STEPS
        ]  # fmt: skip
        run = await tx.one(
            """INSERT INTO provisioning.runs (plan_id, company_id, sealed_digest, steps)
               VALUES (:p, :co, :d, CAST(:steps AS jsonb)) RETURNING id""",
            p=cand["id"],
            co=cand["company_id"],
            d=cand["sealed_digest"],
            steps=json.dumps(steps),
        )
        await tx.exec(
            "UPDATE provisioning.plans SET state = 'running', updated_at = now() WHERE id = :id",
            id=cand["id"],
        )
        if cand["founding_id"]:
            await tx.exec(
                """UPDATE core.foundings SET state = 'provisioning', updated_at = now()
                   WHERE id = :f AND state = 'sealed'""",
                f=cand["founding_id"],
            )
        await events.emit(
            tx,
            cand["company_code"],
            "provision.step",
            cand["ref"],
            {"run": str(run["id"]), "state": "running"},
        )
        return _handout(await load_run(tx, run["id"]), await load_plan(tx, cand["ref"]), sources)


async def _refuse_run(tx: Tx, run: dict[str, Any], why: str) -> None:
    """A queued run that must not go on (never handed out): failed, `refused`."""
    await tx.exec(
        """UPDATE provisioning.runs SET state = 'failed', finished_at = now(), updated_at = now(),
               error = CAST(:e AS jsonb)
           WHERE id = :id""",
        id=run["id"],
        e=json.dumps({"step": "ssh-key", "code": "refused"}),
    )
    await tx.exec(
        "UPDATE provisioning.plans SET state = 'failed', updated_at = now() WHERE id = :id",
        id=run["plan_id"],
    )
    await _append_event(tx, run, "ssh-key", "failed", [f"refused: {why}"])


VOID_REASONS: dict[str, tuple[str, str]] = {
    "changed": ("the plan's digest is not its seal any more", "طرح بعد از مُهر عوض شده بود"),
    "cancelled": ("the founding was cancelled", "تأسیس این طرح لغو شده است"),
    "rules": (
        "the plan breaks a rule now (the owner's SSH addresses changed?)",
        "طرح دیگر با قاعده‌ها نمیخواند (نشانی‌های SSH مالک عوض شده؟)",
    ),
}


async def _void_seal(tx: Tx, plan: dict[str, Any], reason: str = "changed") -> None:
    why, why_fa = VOID_REASONS[reason]
    await tx.exec(
        """UPDATE provisioning.plans SET state = 'proposed', sealed_digest = NULL, sealed_at = NULL,
               seal_step_up_id = NULL, decision_id = NULL, updated_at = now()
           WHERE id = :id""",
        id=plan["id"],
    )
    await audit.record(
        tx,
        SERVICE,
        company_id=plan["company_id"],
        action="provision.seal_void",
        action_class="A1",
        target_kind="server_plan",
        target_ref=plan["ref"],
        summary=f"{why}: not run, back to proposed"[:300],
    )
    await notify.raise_notification(
        tx,
        company_id=plan["company_id"],
        company_code=plan["company_code"],
        level="decision",
        title_fa=f"مُهر طرح {plan['ref']} باطل شد و سروری ساخته نشد",
        body_fa=f"{why_fa}. طرح را دوباره ببین و اگر درست است مُهر کن.",
        link_kind="server_plan",
        link_ref=plan["ref"],
        source_kind="service",
        source_code="founding",
    )


async def record_callback_token(
    tx: Tx, run: dict[str, Any], token_sha256: str, expires_at: datetime
) -> None:
    latest = datetime.now(UTC) + CALLBACK_TTL
    await tx.exec(
        """UPDATE provisioning.runs SET callback_sha256 = :h, callback_expires_at = :e,
               callback_used_at = NULL, updated_at = now()
           WHERE id = :id""",
        h=token_sha256,
        e=min(expires_at, latest),
        id=run["id"],
    )


async def _append_event(
    tx: Tx, run: dict[str, Any], key: str, state: str, log_tail: list[str]
) -> int:
    seq: int = await tx.scalar(
        """UPDATE provisioning.runs SET last_seq = last_seq + 1, updated_at = now() WHERE id = :id
           RETURNING last_seq""",
        id=run["id"],
    )
    await tx.exec(
        """INSERT INTO provisioning.run_events (run_id, company_id, seq, key, state, log_tail)
           VALUES (:r, :co, :s, :k, :st, CAST(:lt AS jsonb))""",
        r=run["id"],
        co=run["company_id"],
        s=seq,
        k=key,
        st=state,
        lt=json.dumps(log_tail, ensure_ascii=False),
    )
    return seq


def clean_log(lines: Any) -> list[str]:
    items = lines if isinstance(lines, list) else [lines] if lines else []
    return [scrub(str(x))[:300] for x in items][-10:]


def _must_run(run: dict[str, Any]) -> None:
    """The provisioner reports on a running run only (a reaped or finished
    one takes nothing more: its next try is a resume)."""
    if run["state"] != "running":
        raise ApiError(409, "validation_failed", f"the run is {run['state']}")


async def record_step(tx: Tx, run: dict[str, Any], body: dict[str, Any]) -> None:
    _must_run(run)
    key = str(body.get("key") or "")
    if key not in STEP_KEYS:
        raise ApiError(422, "validation_failed", fields={"key": "unknown step"})
    state = body.get("state")
    if state not in ("running", "done", "failed"):
        raise ApiError(422, "validation_failed", fields={"state": "running, done or failed"})
    tail = clean_log(body.get("log_tail"))
    steps = list(run["steps"] or [])
    for s in steps:
        if s["key"] == key:
            s["state"] = state
            s["started_at"] = body.get("started_at") or s.get("started_at")
            if state in ("done", "failed"):
                s["finished_at"] = body.get("finished_at") or datetime.now(UTC).isoformat()
            if tail:
                s["log_tail"] = tail
    await tx.exec(
        "UPDATE provisioning.runs SET steps = CAST(:s AS jsonb), updated_at = now() WHERE id = :id",
        s=json.dumps(steps, ensure_ascii=False),
        id=run["id"],
    )
    seq = await _append_event(tx, run, key, state, tail)
    await events.emit(
        tx,
        run["company_code"],
        "provision.step",
        run["plan_ref"],
        {"run": str(run["id"]), "key": key, "state": state, "seq": seq},
    )


async def record_server(tx: Tx, run: dict[str, Any], body: dict[str, Any]) -> None:
    _must_run(run)
    raw = body.get("labels")
    labels: dict[str, Any] = raw if isinstance(raw, dict) else {}
    if labels.get(P.LABEL_MANAGED) != P.MANAGED_BY:
        raise ApiError(422, "validation_failed", fields={"labels": "not one of ours"})
    server = {
        "name": str(body.get("name") or "")[:63],
        "ipv4": (str(body["ipv4"])[:45] if body.get("ipv4") else None),
        "ipv6": (str(body["ipv6"])[:64] if body.get("ipv6") else None),
        "private_ip": (str(body["private_ip"])[:45] if body.get("private_ip") else None),
    }
    await tx.exec(
        """INSERT INTO infra.servers (company_id, plan_id, run_id, hetzner_id, name, ipv4, ipv6,
               private_ip, labels)
           VALUES (:co, :p, :r, :hid, :name, :v4, :v6, :pip, CAST(:labels AS jsonb))
           ON CONFLICT (hetzner_id) DO UPDATE SET name = EXCLUDED.name, ipv4 = EXCLUDED.ipv4,
               ipv6 = EXCLUDED.ipv6, private_ip = EXCLUDED.private_ip, labels = EXCLUDED.labels,
               run_id = EXCLUDED.run_id, updated_at = now()""",
        co=run["company_id"],
        p=run["plan_id"],
        r=run["id"],
        hid=int(body["hetzner_id"]),
        name=server["name"],
        v4=server["ipv4"],
        v6=server["ipv6"],
        pip=server["private_ip"],
        labels=json.dumps({str(k)[:63]: str(v)[:63] for k, v in labels.items()}),
    )
    await tx.exec(
        "UPDATE provisioning.runs SET server = CAST(:s AS jsonb), updated_at = now() WHERE id = :id",
        s=json.dumps(server),
        id=run["id"],
    )


async def finish(tx: Tx, run: dict[str, Any], body: dict[str, Any]) -> None:
    state = body.get("state")
    if state not in ("done", "failed"):
        raise ApiError(422, "validation_failed", fields={"state": "done or failed"})
    login = body.get("login") if state == "done" and isinstance(body.get("login"), dict) else None
    if login is not None:
        login = {
            "ssh": str(login.get("ssh") or "")[:200],
            "then": [str(c)[:40] for c in (login.get("then") or [])][:5],
        }
    error = body.get("error") if state == "failed" and isinstance(body.get("error"), dict) else None
    if error is not None:
        error = {k: scrub(str(v))[:200] for k, v in error.items() if k in ("step", "code")}
    await tx.exec(
        """UPDATE provisioning.runs SET state = :st, login = CAST(:login AS jsonb),
               error = CAST(:err AS jsonb), finished_at = now(), updated_at = now()
           WHERE id = :id""",
        st=state,
        login=json.dumps(login) if login else None,
        err=json.dumps(error) if error else None,
        id=run["id"],
    )
    plan = await load_plan(tx, run["plan_ref"])
    await tx.exec(
        "UPDATE provisioning.plans SET state = :st, updated_at = now() WHERE id = :id",
        st=state,
        id=plan["id"],
    )
    await _append_event(tx, run, "login" if state == "done" else "verify", state, [])
    f = None
    if plan["founding_id"]:
        # Done: the owner logs in. Failed: back to `sealed` (§18.16), where the
        # owner resumes the run on the same seal or cancels the founding.
        await tx.exec(
            """UPDATE core.foundings SET state = :st, updated_at = now()
               WHERE id = :f AND state = 'provisioning'""",
            f=plan["founding_id"],
            st="ready_for_login" if state == "done" else "sealed",
        )
        f = await tx.scalar("SELECT ref FROM core.foundings WHERE id = :f", f=plan["founding_id"])
    ssh = (login or {}).get("ssh")
    await notify.raise_notification(
        tx,
        company_id=plan["company_id"],
        company_code=plan["company_code"],
        level="decision",
        title_fa=(
            f"سرور {plan['name']} آماده‌ی ورود توست: {ssh}"
            if state == "done"
            else f"ساخت سرور {plan['name']} در گام {(error or {}).get('step')} متوقف شد"
        )[:200],
        body_fa=(
            "وارد شو، `claude` را اجرا کن و با حساب خودت login کن؛ بعد تأسیس را فعال کن."
            if state == "done"
            else "گزارش گام‌ها در اجرای ساخت است؛ ادامه از همان گام با resume."
        ),
        link_kind="founding" if f else "provision_run",
        link_ref=f or str(run["id"]),
        source_kind="service",
        source_code="provisioner",
    )
    await events.emit(
        tx,
        plan["company_code"],
        "provision.step",
        plan["ref"],
        {"run": str(run["id"]), "state": state},
    )
    if f:
        holding = await _holding(tx)
        fstate = await tx.scalar(
            "SELECT state FROM core.foundings WHERE id = :f", f=plan["founding_id"]
        )
        await events.emit(tx, holding["code"], "founding.updated", f, {"state": fstate})


async def resume(tx: Tx, who: Principal, run: dict[str, Any]) -> None:
    """A failed run continues from its first step not done (the same sealed
    plan; the provisioner never makes a resource twice). Never for a
    cancelled founding, and never after a refusal (e.g. Hetzner answered with
    a root password: that server is not used, §4)."""
    if run["state"] != "failed":
        raise ApiError(409, "validation_failed", f"the run is {run['state']}")
    if (run.get("error") or {}).get("code") == "refused":
        raise ApiError(
            409,
            "validation_failed",
            "refused: this build was refused for safety and is not resumed (a new plan is a new build)",
        )
    plan = await load_plan(tx, run["plan_ref"], lock=True)
    if plan["sealed_digest"] != run["sealed_digest"]:
        raise ApiError(409, "seal_mismatch", "the plan is not the sealed one any more")
    if plan["founding_id"] is not None:
        f = await tx.first(
            "SELECT ref, state FROM core.foundings WHERE id = :f FOR UPDATE", f=plan["founding_id"]
        )
        if f is None or f["state"] != "sealed":
            raise ApiError(
                409, "validation_failed", f"the founding is {f['state'] if f else 'gone'}"
            )
        await tx.exec(
            """UPDATE core.foundings SET state = 'provisioning', updated_at = now()
               WHERE id = :f""",
            f=plan["founding_id"],
        )
    await tx.exec(
        """UPDATE provisioning.runs SET state = 'queued', error = NULL, finished_at = NULL,
               updated_at = now()
           WHERE id = :id""",
        id=run["id"],
    )
    await tx.exec(
        "UPDATE provisioning.plans SET state = 'running', updated_at = now() WHERE id = :id",
        id=plan["id"],
    )
    await _append_event(tx, run, "ssh-key", "queued", ["resumed by the owner"])
    await audit.record(
        tx,
        who,
        company_id=run["company_id"],
        action="provision.resume",
        action_class="A2",
        target_kind="provision_run",
        target_ref=str(run["id"]),
        summary=f"plan {plan['ref']}",
    )


def _clean_report(run: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    results = []
    for r in body.get("results") or []:
        if not isinstance(r, dict) or r.get("key") not in P.SOFTWARE:
            continue
        results.append(
            {
                "key": r["key"],
                "ok": bool(r.get("ok")),
                "version": scrub(str(r["version"]))[:80] if r.get("version") else None,
                "note": scrub(str(r["note"]))[:300] if r.get("note") else None,
            }
        )
    deploy = body.get("deploy_key")
    deploy = str(deploy)[:1000] if isinstance(deploy, str) and deploy.startswith("ssh-") else None
    hosts = [str(h)[:1000] for h in (body.get("ssh_host_keys") or []) if isinstance(h, str)][:10]
    return {
        "received_at": datetime.now(UTC).isoformat(),
        "failed": bool(body.get("failed")),
        "results": results[:30],
        "deploy_key": deploy,
        "ssh_host_keys": [h for h in hosts if h.startswith(("ssh-", "ecdsa-"))],
    }


async def callback(tx: Tx, token: str, body: dict[str, Any]) -> bool:
    """The new server's one report (public, its one-time token): stored once,
    within the token's 60 minutes; anything else is refused the same way.
    A run that failed meanwhile (e.g. its boot step timed out) still takes it
    (review 9.2 §2.3): its resume then finds the report instead of waiting
    for one the server can never send again."""
    digest = hashlib.sha256(token.encode()).hexdigest()
    run = await tx.first(
        RUN_SQL
        + """ WHERE r.callback_sha256 = :h AND r.callback_used_at IS NULL
                AND r.callback_expires_at > now() AND r.state IN ('running', 'failed', 'queued')
              FOR UPDATE OF r""",
        h=digest,
    )
    if (
        run is None
        or str(body.get("run") or "") != str(run["id"])
        or (body.get("plan") not in (None, run["plan_ref"]))
    ):
        return False
    report = _clean_report(run, body)
    await tx.exec(
        """UPDATE provisioning.runs SET cloud_init = CAST(:ci AS jsonb), callback_used_at = now(),
               updated_at = now()
           WHERE id = :id""",
        ci=json.dumps(report, ensure_ascii=False),
        id=run["id"],
    )
    await _append_event(
        tx, run, "cloud-init", "done" if not report["failed"] else "failed", ["the server reported"]
    )
    return True


# --------------------------------------------------------------- inventory --
INVENTORY_EVERY_S = 6 * 3600


async def inventory_loop(hub: Any) -> None:
    """The api's background listing of the Hetzner project (PR-063 reads the
    latest; the worker has no route to the provisioner)."""
    import asyncio
    import contextlib

    while True:
        with contextlib.suppress(Exception):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                # An outside call (Hetzner, through the provisioner): never
                # while the holding is locked (its kill switch, a deploy freeze).
                if not await holding_locked(tx):
                    await refresh_inventory(
                        tx,
                        hub.settings.provisioner_url,
                        getattr(hub, "provisioner_transport", None),
                    )
        await asyncio.sleep(INVENTORY_EVERY_S)


async def holding_locked(tx: Tx) -> bool:
    holding = await _holding(tx)
    return await tx.scalar("SELECT control.lock_state(:co)", co=holding["id"]) is not None


# ------------------------------------------------------------------ reaper --
async def reap_stale_runs(tx: Tx, quiet_s: float) -> list[str]:
    """Runs the provisioner has said nothing about for `quiet_s` (it was
    restarted mid-run, or the hub could not be told): failed, on the step
    they stood at, so the owner can resume or cancel (review 9.2 §2.3).
    Rule-only: no model, no outside call."""
    rows = await tx.all(
        RUN_SQL
        + """ WHERE r.state = 'running'
                AND r.updated_at < now() - make_interval(secs => CAST(:q AS double precision))
              ORDER BY r.updated_at LIMIT 50 FOR UPDATE OF r SKIP LOCKED""",
        q=float(quiet_s),
    )
    reaped = []
    for r in rows:
        steps = list(r["steps"] or [])
        at = next((s for s in steps if s.get("state") == "running"), None) or next(
            (s for s in steps if s.get("state") != "done"), None
        )
        key = at["key"] if at else STEP_KEYS[-1]
        minutes = int(quiet_s // 60)
        code = "callback_timeout" if key == "cloud-init" else "error"
        note = f"{code}: no word from the provisioner for {minutes} minutes (reaped)"
        for s in steps:
            if s["key"] == key:
                s["state"] = "failed"
                s["finished_at"] = datetime.now(UTC).isoformat()
                s["log_tail"] = [*(s.get("log_tail") or []), note][-10:]
        await tx.exec(
            "UPDATE provisioning.runs SET steps = CAST(:s AS jsonb) WHERE id = :id",
            s=json.dumps(steps, ensure_ascii=False),
            id=r["id"],
        )
        await _append_event(tx, r, key, "failed", [note])
        await finish(tx, r, {"state": "failed", "error": {"step": key, "code": code}})
        await audit.record(
            tx,
            SERVICE,
            company_id=r["company_id"],
            action="provision.reap",
            action_class="A1",
            target_kind="provision_run",
            target_ref=str(r["id"]),
            summary=f"failed at {key}: quiet for {minutes} minutes",
        )
        reaped.append(str(r["id"]))
    return reaped


async def reaper_loop(hub: Any) -> None:
    """Every few minutes while the provisioner is on: reap_stale_runs."""
    import asyncio
    import contextlib

    while True:
        await asyncio.sleep(REAP_EVERY_S)
        with contextlib.suppress(Exception):
            async with hub.db.tx(await hub.companies.ids()) as tx:
                await reap_stale_runs(tx, hub.settings.provision_quiet_s)


async def refresh_inventory(
    tx: Tx, provisioner_url: str, transport: Any = None
) -> dict[str, Any] | None:
    """The Hetzner project's servers (read-only, through the provisioner) for
    PR-063; None while the provisioner is off."""
    if not provisioner_url:
        return None
    holding = await _holding(tx)
    ok, error, items = False, None, []
    try:
        async with httpx.AsyncClient(
            base_url=provisioner_url, timeout=20, transport=transport, trust_env=False
        ) as c:
            r = await c.get("/v1/servers")
        if r.status_code == 200:
            ok, items = True, list(r.json().get("items") or [])[:500]
        else:
            error = f"provisioner answered {r.status_code}"
    except httpx.HTTPError as exc:
        error = f"provisioner unreachable ({type(exc).__name__})"
    keep = ("id", "name", "status", "ipv4", "labels", "ours", "plan", "created")
    row = await tx.one(
        """INSERT INTO infra.inventory (company_id, ok, error, servers)
           VALUES (:co, :ok, :e, CAST(:s AS jsonb)) RETURNING *""",
        co=holding["id"],
        ok=ok,
        e=error,
        s=json.dumps([{k: s.get(k) for k in keep} for s in items if isinstance(s, dict)]),
    )
    return dict(row)
