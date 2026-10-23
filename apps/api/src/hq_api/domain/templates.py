"""Company templates (seed/templates/*.yaml): departments and leadership.

Applying a template is idempotent: it only adds what is missing, so the
seed can run on every start and never overwrites later edits. A company is
one row plus a template (OPERATING_MODEL §0); nothing here knows a code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from hq_api.db import Tx

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")  # cheapest first
# ⟨1.6⟩ never in a written role's ceiling, whatever a template says (§22.5)
NEVER_IN_CEILING = ("hire.decide", "role.decide", "message.owner", "kill_switch.engage")


@lru_cache(maxsize=1)
def templates() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((SEED_DIR / "templates").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        out[str(data["key"])] = data
    return out


def template(key: str) -> dict[str, Any] | None:
    return templates().get(key)


def _flat(items: Any) -> list[str]:
    """A YAML list that may hold the template's `base_tools` anchor as one item."""
    out: list[str] = []
    for x in items or []:
        if isinstance(x, list):
            out += [t for t in _flat(x) if t not in out]
        elif str(x) not in out:
            out.append(str(x))
    return out


def department(key: str | None, code: str) -> dict[str, Any] | None:
    """The template's entry of one department (None: not a template department)."""
    t = template(key) if key else None
    for d in (t or {}).get("departments") or []:
        if d["code"] == code:
            return dict(d)
    return None


def mandate_of(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    """⟨1.6⟩ A department's mandate as stored (contract §22.1)."""
    if not entry or not entry.get("mandate"):
        return None
    m = entry["mandate"]
    model = str(entry.get("model_ceiling") or "claude-sonnet-5-5")
    return {
        "from_fa": str(m.get("from_fa") or ""),
        "to_fa": str(m.get("to_fa") or ""),
        "outputs_fa": [str(x) for x in m.get("outputs_fa") or []],
        "boundaries_fa": [str(x) for x in m.get("boundaries_fa") or []],
        "tool_ceiling": [t for t in _flat(entry.get("tool_ceiling")) if t not in NEVER_IN_CEILING],
        "model_ceiling": model if model in MODELS else "claude-sonnet-5-5",
    }


def team_of(entry: dict[str, Any] | None, charters: Any, code: str) -> list[dict[str, Any]]:
    """⟨1.6⟩ The starting team: only roles whose charter is live in agents/roles/
    and works in this department (a staged one appears the day it goes live)."""
    out: list[dict[str, Any]] = []
    for t in (entry or {}).get("team") or []:
        c = charters.get(t.get("role")) if charters is not None else None
        if c is None or c.kind != "employee" or (c.department and c.department != code):
            continue
        out.append(
            {
                "role": c.role,
                "title_fa": c.title_fa,
                "why_fa": str(t.get("why_fa") or ""),
                "first": bool(t.get("first")),
            }
        )
    return out


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
            if d.get("manager", True) is False:
                continue
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
        # ⟨1.6⟩ mandate and identity, only where empty (the owner's edits stay)
        mandate = mandate_of(d)
        identity = str(d["identity_md"]).strip() if d.get("identity_md") else None
        if mandate is not None or identity is not None:
            await tx.exec(
                """UPDATE core.departments
                   SET mandate = COALESCE(mandate, CAST(:m AS jsonb)),
                       identity_md = COALESCE(identity_md, CAST(:i AS text))
                   WHERE company_id = :co AND code = :code
                     AND ((mandate IS NULL AND CAST(:m AS jsonb) IS NOT NULL)
                          OR (identity_md IS NULL AND CAST(:i AS text) IS NOT NULL))""",
                co=company_id,
                code=d["code"],
                m=json.dumps(mandate, ensure_ascii=False) if mandate else None,
                i=identity,
            )

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
            if d.get("manager", True) is False:  # ⟨1.6⟩ LEGAL: no manager position
                continue
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
