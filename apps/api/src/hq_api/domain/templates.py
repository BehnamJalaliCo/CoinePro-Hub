"""Company templates (seed/templates/*.yaml): departments and leadership.

Applying a template is idempotent: it only adds what is missing, so the
seed can run on every start and never overwrites later edits. A company is
one row plus a template (OPERATING_MODEL §0); nothing here knows a code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from hq_api.db import Tx

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"


@lru_cache(maxsize=1)
def templates() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((SEED_DIR / "templates").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        out[str(data["key"])] = data
    return out


def template(key: str) -> dict[str, Any] | None:
    return templates().get(key)


def leadership_roles(company_code: str, key: str) -> dict[str, str | None]:
    """Employee code -> charter role of every leadership position of a template."""
    t = template(key)
    if t is None:
        raise ValueError(f"unknown template {key}")
    lead = t.get("leadership") or {}
    roles: dict[str, str | None] = {}
    if lead.get("ceo"):
        roles[f"{company_code}-CEO"] = lead["ceo"].get("role")
    if lead.get("managers"):
        for d in t.get("departments") or []:
            roles[f"{company_code}-{d['code']}-MGR"] = d.get("head_role")
    for x in lead.get("extra") or []:
        roles[f"{company_code}-{x['code_suffix']}"] = x.get("role")
    return roles


async def apply(
    tx: Tx,
    company_id: UUID,
    company_code: str,
    key: str,
    departments: list[str] | None = None,
) -> dict[str, int]:
    """Create the template's departments, leadership positions, their threads
    and the company's kill-switch row (released). Returns what was added.
    `departments`: only these of the template's (a founding's proposal)."""
    t = template(key)
    if t is None:
        raise ValueError(f"unknown template {key}")
    if departments is not None:
        t = {
            **t,
            "departments": [d for d in t.get("departments") or [] if d["code"] in departments],
        }
    added = {"departments": 0, "employees": 0, "threads": 0}

    for d in t.get("departments") or []:
        row = await tx.first(
            """INSERT INTO core.departments (company_id, code, name_fa, name_en, manager_title_fa,
                   manager_title_en, sort)
               VALUES (:co, :code, :nfa, :nen, :mfa, :men, :sort)
               ON CONFLICT (company_id, code) DO NOTHING RETURNING id""",
            co=company_id,
            code=d["code"],
            nfa=d["name_fa"],
            nen=d["name_en"],
            mfa=d["manager_title_fa"],
            men=d["manager_title_en"],
            sort=int(d.get("sort", 100)),
        )
        added["departments"] += row is not None

    lead = t.get("leadership") or {}
    ceo_id: UUID | None = None
    if lead.get("ceo"):
        ceo_code = f"{company_code}-CEO"
        ceo_id = await _position(
            tx,
            company_id,
            None,
            ceo_code,
            "ceo",
            lead["ceo"]["title_fa"],
            lead["ceo"]["title_en"],
            None,
            added,
            role=lead["ceo"].get("role"),
        )
        await _thread(tx, company_id, None, ceo_id, ceo_code, "ceo", lead["ceo"]["title_fa"], added)

    if lead.get("managers"):
        for d in t.get("departments") or []:
            dept_id = await tx.scalar(
                "SELECT id FROM core.departments WHERE company_id = :co AND code = :code",
                co=company_id,
                code=d["code"],
            )
            code = f"{company_code}-{d['code']}-MGR"
            mgr_id = await _position(
                tx,
                company_id,
                dept_id,
                code,
                d.get("head_kind", "manager"),
                d["manager_title_fa"],
                d["manager_title_en"],
                ceo_id,
                added,
                role=d.get("head_role"),
            )
            await _thread(
                tx, company_id, None, mgr_id, code, "manager", d["manager_title_fa"], added
            )
            await _thread(
                tx,
                company_id,
                dept_id,
                None,
                f"{company_code}-{d['code']}",
                "department",
                d["name_fa"],
                added,
            )

    for x in lead.get("extra") or []:
        code = f"{company_code}-{x['code_suffix']}"
        x_dept = None
        if x.get("department"):
            x_dept = await tx.scalar(
                "SELECT id FROM core.departments WHERE company_id = :co AND code = :code",
                co=company_id,
                code=x["department"],
            )
        emp_id = await _position(
            tx,
            company_id,
            x_dept,
            code,
            x["kind"],
            x["title_fa"],
            x["title_en"],
            None,
            added,
            role=x.get("role"),
        )
        if x.get("thread"):
            await _thread(
                tx,
                company_id,
                None,
                emp_id,
                x["thread"],
                x["thread_kind"],
                x["thread_title_fa"],
                added,
            )

    if lead.get("managers"):
        for d in t.get("departments") or []:
            if d.get("head_reports_to"):
                await tx.exec(
                    """UPDATE core.employees SET reports_to =
                           (SELECT id FROM core.employees WHERE code = :boss AND company_id = :co)
                       WHERE code = :code AND company_id = :co AND reports_to IS NULL""",
                    boss=f"{company_code}-{d['head_reports_to']}",
                    code=f"{company_code}-{d['code']}-MGR",
                    co=company_id,
                )

    await tx.exec(
        "INSERT INTO control.kill_switches (company_id) VALUES (:co) ON CONFLICT DO NOTHING",
        co=company_id,
    )
    return added


async def _position(
    tx: Tx,
    company_id: UUID,
    department_id: UUID | None,
    code: str,
    kind: str,
    title_fa: str,
    title_en: str,
    reports_to: UUID | None,
    added: dict[str, int],
    *,
    role: str | None = None,
) -> UUID:
    row = await tx.first(
        """INSERT INTO core.employees (company_id, department_id, code, kind, title_fa, title_en,
               reports_to, activity, role)
           VALUES (:co, :dept, :code, :kind, :tfa, :ten, :rt, 'sleeping', :role)
           ON CONFLICT (code) DO NOTHING RETURNING id""",
        co=company_id,
        dept=department_id,
        code=code,
        kind=kind,
        tfa=title_fa,
        ten=title_en,
        rt=reports_to,
        role=role,
    )
    if row is not None:
        added["employees"] += 1
        emp: UUID = row["id"]
        return emp
    existing: UUID = await tx.scalar("SELECT id FROM core.employees WHERE code = :code", code=code)
    return existing


async def _thread(
    tx: Tx,
    company_id: UUID,
    department_id: UUID | None,
    employee_id: UUID | None,
    code: str,
    kind: str,
    title_fa: str,
    added: dict[str, int],
) -> None:
    row = await tx.first(
        """INSERT INTO msg.threads (code, kind, company_id, department_id, employee_id, title_fa)
           VALUES (:code, :kind, :co, :dept, :emp, :title)
           ON CONFLICT (code) DO NOTHING RETURNING id""",
        code=code,
        kind=kind,
        co=company_id,
        dept=department_id,
        emp=employee_id,
        title=title_fa,
    )
    added["threads"] += row is not None
