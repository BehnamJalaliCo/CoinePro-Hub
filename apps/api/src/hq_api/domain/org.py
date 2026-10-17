"""Organisation: employees as API objects, model resolution, hiring and
dismissal (contract §3, OPERATING_MODEL §1.1–§1.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from hq_api.db import Tx
from hq_api.errors import ApiError
from hq_api.schemas import EmployeeRef, ModelChoice, Score, employee_ref

EMPLOYEE_SQL = """
    SELECT e.id, e.code, e.kind, e.title_fa, e.title_en, e.display_name, e.status, e.activity,
           e.activity_note, e.activity_at, e.score, e.score_owner_avg, e.rank_in_department,
           e.hired_at, e.dismissed_at, e.version, e.company_id, e.department_id, e.reports_to,
           e.duties, e.permissions, e.role,
           c.code AS company, d.code AS department,
           r.code AS rt_code, r.title_fa AS rt_title_fa, r.kind AS rt_kind, rc.code AS rt_company,
           rd.code AS rt_department, hd.ref AS hired_by_decision
    FROM core.employees e
    JOIN core.companies c ON c.id = e.company_id
    LEFT JOIN core.departments d ON d.id = e.department_id
    LEFT JOIN core.employees r ON r.id = e.reports_to
    LEFT JOIN core.companies rc ON rc.id = r.company_id
    LEFT JOIN core.departments rd ON rd.id = r.department_id
    LEFT JOIN cartable.decisions hd ON hd.id = e.hired_by_decision_id
"""

REF_COLS = """{a}.code AS {p}code, {a}.title_fa AS {p}title_fa, {a}.kind AS {p}kind,
              (SELECT code FROM core.companies WHERE id = {a}.company_id) AS {p}company,
              (SELECT code FROM core.departments WHERE id = {a}.department_id) AS {p}department"""


def ref_cols(alias: str, prefix: str) -> str:
    return REF_COLS.format(a=alias, p=prefix)


# Depth of a root work item by who receives it (contract §4: owner -> CEO is 0).
DEPTH_OF_KIND = {"ceo": 0, "advisor": 0, "system": 0, "manager": 1, "inspector": 1, "employee": 2}


class CharterRef(BaseModel):
    """The charter an employee runs with (contract §16.1)."""

    role: str
    version: int | None


class Employee(BaseModel):
    id: UUID
    code: str
    company: str
    department: str | None
    kind: str
    title_fa: str
    title_en: str
    display_name: str | None
    reports_to: EmployeeRef | None
    status: str
    activity: str
    activity_note: str | None
    activity_at: datetime | None
    model: ModelChoice | None
    score: Score
    duties: list[Any]
    permissions: list[Any]
    hired_at: datetime
    dismissed_at: datetime | None
    hired_by_decision: str | None
    charter: CharterRef | None = None
    version: int


class Assignments:
    """Read-only mirror of llm-router's resolution (services/llm-router/src/
    llm_router/assignment.py): holding -> company -> department -> role; each
    level overrides field by field; a new connection resets the model."""

    def __init__(self, rows: list[dict[str, Any]], holding_code: str) -> None:
        self._by = {(r["scope_type"], r["scope_ref"]): r for r in rows}
        self._holding = holding_code

    @classmethod
    async def load(cls, tx: Tx, holding_code: str) -> Assignments:
        rows = await tx.all(
            """SELECT a.scope_type, a.scope_ref, cn.key AS connection, a.model, a.effort
               FROM llm.assignments a LEFT JOIN llm.connections cn ON cn.id = a.connection_id"""
        )
        return cls(rows, holding_code)

    def resolve(
        self, company: str, department: str | None, kind: str, code: str
    ) -> ModelChoice | None:
        """`kind` is the employee's charter role when it has one (else its kind),
        exactly what the runtime sends the router as `role`."""
        chain = [("holding", self._holding), ("company", company)]
        if department:
            chain.append(("department", f"{company}-{department}"))
        chain += [
            ("role", kind),
            ("role", f"{company}:{kind}"),
            ("role", code),
            ("role", f"{company}:{code}"),
        ]
        connection = model = effort = None
        hit = False
        for key in chain:
            a = self._by.get(key)
            if a is None:
                continue
            hit = True
            if a["connection"] is not None:
                if a["connection"] != connection:
                    model = None
                connection = a["connection"]
            if a["model"] is not None:
                model = a["model"]
            if a["effort"] is not None:
                effort = a["effort"]
        return ModelChoice(connection=connection, model=model, effort=effort) if hit else None


async def trends(tx: Tx, ids: list[UUID]) -> dict[UUID, list[float | None]]:
    if not ids:
        return {}
    rows = await tx.all(
        """SELECT employee_id, month, value FROM core.employee_scores
           WHERE employee_id = ANY(:ids) AND month > date_trunc('month', now()) - interval '12 months'""",
        ids=ids,
    )
    now = datetime.now(UTC)
    months = [(now.year * 12 + now.month - 1 - i) for i in range(11, -1, -1)]
    out: dict[UUID, list[float | None]] = {i: [None] * 12 for i in ids}
    for r in rows:
        idx = r["month"].year * 12 + r["month"].month - 1
        if idx in months and r["value"] is not None:
            out[r["employee_id"]][months.index(idx)] = float(r["value"])
    return out


def render(
    row: dict[str, Any],
    assignments: Assignments | None,
    trend: list[float | None],
    charters: Any = None,
) -> Employee:
    role = row.get("role")
    model = (
        assignments.resolve(row["company"], row["department"], role or row["kind"], row["code"])
        if assignments
        else None
    )
    charter = charters.get(role) if charters is not None and role else None
    return Employee(
        id=row["id"],
        code=row["code"],
        company=row["company"],
        department=row["department"],
        kind=row["kind"],
        title_fa=row["title_fa"],
        title_en=row["title_en"],
        display_name=row["display_name"],
        reports_to=employee_ref(row, "rt_"),
        status=row["status"],
        activity=row["activity"],
        activity_note=row["activity_note"],
        activity_at=row["activity_at"],
        model=model,
        score=Score(
            value=float(row["score"]) if row["score"] is not None else None,
            owner_avg=float(row["score_owner_avg"]) if row["score_owner_avg"] is not None else None,
            rank_in_department=row["rank_in_department"],
            trend=trend,
        ),
        duties=list(row["duties"] or []),
        permissions=list(row["permissions"] or []),
        hired_at=row["hired_at"],
        dismissed_at=row["dismissed_at"],
        hired_by_decision=row["hired_by_decision"],
        charter=CharterRef(role=role, version=charter.version if charter else None)
        if role
        else None,
        version=row["version"],
    )


async def load_employee(tx: Tx, code: str) -> dict[str, Any]:
    return await tx.one(EMPLOYEE_SQL + " WHERE e.code = :code", code=code, not_found="not_found")


async def manager_of(tx: Tx, department_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT id, code, kind FROM core.employees
           WHERE department_id = :d AND kind IN ('manager', 'inspector') AND status <> 'dismissed'""",
        d=department_id,
    )


async def ceo_of(tx: Tx, company_id: UUID) -> dict[str, Any] | None:
    return await tx.first(
        """SELECT id, code, kind FROM core.employees
           WHERE company_id = :co AND kind = 'ceo' AND status <> 'dismissed'""",
        co=company_id,
    )


async def hire(
    tx: Tx,
    *,
    company_id: UUID,
    company_code: str,
    department_code: str,
    title_fa: str,
    title_en: str,
    duties: list[Any],
    permissions: list[Any],
    decision_id: UUID | None,
    role: str | None = None,
) -> dict[str, Any]:
    """A new numbered employee: next code (never reused), reports to the
    department's manager, gets a direct thread, runs with its charter `role`.
    Model assignment is the caller's (it belongs to llm.assignments)."""
    dept = await tx.one(
        "SELECT id, code FROM core.departments WHERE company_id = :co AND code = :d",
        co=company_id,
        d=department_code,
        not_found="not_found",
    )
    code = await tx.scalar("SELECT core.issue_employee_code(:co, :d)", co=company_id, d=dept["id"])
    mgr = await manager_of(tx, dept["id"])
    row = await tx.one(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en,
               reports_to, duties, permissions, hired_by_decision_id, role)
           VALUES (:co, :d, :code, 'employee', :tfa, :ten, :rt, CAST(:duties AS jsonb),
                   CAST(:perms AS jsonb), :dec, :role)
           RETURNING id, code""",
        co=company_id,
        d=dept["id"],
        code=code,
        tfa=title_fa,
        ten=title_en,
        rt=mgr["id"] if mgr else None,
        duties=_json(duties),
        perms=_json(permissions),
        dec=decision_id,
        role=role,
    )
    await tx.exec(
        """INSERT INTO msg.threads (code, kind, company_id, employee_id, title_fa)
           VALUES (:code, 'employee', :co, :e, :title) ON CONFLICT (code) DO NOTHING""",
        code=code,
        co=company_id,
        e=row["id"],
        title=title_fa,
    )
    return row


async def dismiss(
    tx: Tx, employee: dict[str, Any], *, reason: str, transfer_to: str | None
) -> dict[str, Any]:
    """Status dismissed (final), open work back to the manager, and a
    knowledge-transfer work item for the runtime (§1.3)."""
    if employee["status"] == "dismissed":
        raise ApiError(409, "validation_failed", "already dismissed")
    if employee["kind"] in ("ceo", "advisor", "system"):
        raise ApiError(422, "validation_failed", "leadership positions are not dismissed this way")
    target = None
    if transfer_to:
        target = await tx.one(
            "SELECT id, code, kind, company_id, status FROM core.employees WHERE code = :c",
            c=transfer_to,
            not_found="not_found",
        )
        if target["company_id"] != employee["company_id"] or target["status"] == "dismissed":
            raise ApiError(
                422, "validation_failed", fields={"transfer_to": "same company, not dismissed"}
            )
    manager = await manager_of(tx, employee["department_id"]) if employee["department_id"] else None
    if manager and manager["id"] == employee["id"]:
        manager = await ceo_of(tx, employee["company_id"])
    receiver = target or manager
    await tx.exec(
        """UPDATE core.employees SET status = 'dismissed', dismissed_at = now(), dismissal_reason = :r,
               activity = 'sleeping', activity_note = NULL
           WHERE id = :id""",
        id=employee["id"],
        r=reason,
    )
    moved = await tx.exec(
        """UPDATE work.work SET assignee_id = :to, status = 'queued'
           WHERE assignee_id = :id AND status IN ('queued', 'in_progress', 'waiting')""",
        id=employee["id"],
        to=manager["id"] if manager else None,
    )
    # Knowledge transfer (§1.3): the memory notes go to the receiver, marked
    # with their source (append-only; the dismissed employee keeps its own).
    transferred = 0
    if receiver is not None:
        transferred = await tx.exec(
            """INSERT INTO core.employee_memory (company_id, employee_id, note, tags, source_employee_id)
               SELECT company_id, :to, note, tags || ARRAY['transfer'], employee_id
               FROM core.employee_memory WHERE employee_id = :id ORDER BY id""",
            id=employee["id"],
            to=receiver["id"],
        )
    kt = await tx.one(
        """INSERT INTO work.work (company_id, department_id, kind, title, brief, priority,
               created_by_kind, created_by_code, assignee_id, depth)
           VALUES (:co, :d, 'one_off', :title, :brief, 'P3', 'service', 'system', :to, :depth)
           RETURNING id, ref""",
        co=employee["company_id"],
        d=employee["department_id"],
        title=f"Knowledge transfer from {employee['code']}",
        brief=(
            f"Transfer the knowledge, memory and playbooks of {employee['code']} "
            "and write the positive and negative lessons of their work (OPERATING_MODEL §1.3). "
            f"{transferred} memory note(s) of {employee['code']} are now in your memory (tag transfer)."
        ),
        to=receiver["id"] if receiver else None,
        depth=DEPTH_OF_KIND.get(receiver["kind"], 2) if receiver else 0,
    )
    return {
        "moved_work": moved,
        "knowledge_transfer_work": kt["ref"],
        "memory_transferred": transferred,
    }


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, default=str)
