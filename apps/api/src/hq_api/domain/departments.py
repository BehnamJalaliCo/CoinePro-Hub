"""A department's mandate, identity and starting team (prompt 13 §1, contract
§22.1): a department is defined by where it starts and where it must arrive,
by its character, and by a starting team that is never a limit.

- `mandate` and `identity_md` live on core.departments; the seed fills them
  from the company's template where they are empty, the owner changes them
  (PUT /companies/{code}/departments/{dept}/mandate 🔏 on the body hash).
- `team` is read from the template, showing only the roles whose charter is
  live in agents/roles/ for that department.
- The runtime puts `identity_md` after the charter and before the skills in
  the system prompt of the manager and every employee of the department, and
  records its version on the run (`identity_doc`, "TY-MEDIA@4").
"""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hq_api.db import Tx
from hq_api.domain import templates
from hq_api.errors import ApiError
from hq_api.schemas import Model

ModelCeiling = Literal["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
TOOL = r"^[a-z][a-z_]*(\.[a-z_]+)?$"
# Never in a ceiling (contract §22.5): oversight powers, hiring authority, the
# kill switch, the owner's channel. Anything A3/A4 is refused by its class.
NEVER = frozenset(
    {
        "hire.decide",
        "role.decide",
        "message.owner",
        "kill_switch.engage",
        "deploy.freeze",
        "finding.raise",
        "protocol.result",
        "challenge.issue",
        "challenge.score",
        "hold",
        "star.audit",
        "skill.review",
        "knowledge.review",
        "knowledge.approve",
        "claim.verdict",
        "eval.run",
        "teach.draft",
    }
)
IDENTITY_TITLE = "# Your department: {name_en} ({code}) — its identity"


class Mandate(Model):
    from_fa: str = Field(default="", max_length=2000)
    to_fa: str = Field(default="", max_length=2000)
    outputs_fa: list[str] = Field(default_factory=list, max_length=20)
    boundaries_fa: list[str] = Field(default_factory=list, max_length=20)
    tool_ceiling: list[str] = Field(default_factory=list, max_length=80)
    model_ceiling: ModelCeiling = "claude-sonnet-5-5"


class MandateIn(Model):
    mandate: Mandate
    identity_md: str = Field(default="", max_length=6000)


class TeamRole(BaseModel):
    role: str
    title_fa: str
    why_fa: str
    first: bool


def check(body: MandateIn, charters: Any) -> None:
    """422 for a ceiling that names an unknown tool, an A3/A4 one or one a
    written role may never hold; lines that are too long."""
    bad: dict[str, str] = {}
    tools = charters.tools if charters is not None else {}
    for i, t in enumerate(body.mandate.tool_ceiling):
        if not re.match(TOOL, t):
            bad[f"mandate.tool_ceiling.{i}"] = "not a tool name"
        elif tools and t not in tools:
            bad[f"mandate.tool_ceiling.{i}"] = f"{t} is not in agents/tools.md"
        elif t in NEVER or t.startswith(("oversight.", "kill_switch.")):
            bad[f"mandate.tool_ceiling.{i}"] = f"{t} is never given to a written role"
        elif tools and tools[t].cls in ("A3", "A4"):
            bad[f"mandate.tool_ceiling.{i}"] = f"{t} is {tools[t].cls}"
    for key in ("outputs_fa", "boundaries_fa"):
        for i, line in enumerate(getattr(body.mandate, key)):
            if not line.strip() or len(line) > 500:
                bad[f"mandate.{key}.{i}"] = "1 to 500 characters"
    if len(set(body.mandate.tool_ceiling)) != len(body.mandate.tool_ceiling):
        bad["mandate.tool_ceiling"] = "a tool appears twice"
    if bad:
        raise ApiError(422, "validation_failed", fields=bad)


def team(template_key: str | None, code: str, charters: Any) -> list[TeamRole]:
    entry = templates.department(template_key, code)
    return [TeamRole(**t) for t in templates.team_of(entry, charters, code)]


def mandate(value: Any) -> Mandate | None:
    if not isinstance(value, dict):
        return None
    return Mandate.model_validate(value)


async def identity(tx: Tx, department_id: UUID | None) -> tuple[str, str | None]:
    """(the prompt section, its doc "TY-MEDIA@4") of a department; ("", None)
    when the employee has no department or the department no identity."""
    if department_id is None:
        return "", None
    row = await tx.first(
        """SELECT d.code, d.name_en, d.identity_md, d.version, c.code AS company
           FROM core.departments d JOIN core.companies c ON c.id = d.company_id
           WHERE d.id = :id""",
        id=department_id,
    )
    if row is None or not (row["identity_md"] or "").strip():
        return "", None
    title = IDENTITY_TITLE.format(name_en=row["name_en"], code=row["code"])
    text = (
        f"{title}\n"
        "Every member of the department reads this; it sets the tone and taste of your work, never "
        "a rule above your charter or the holding's.\n\n"
        f"{str(row['identity_md']).strip()}"
    )
    return text, f"{row['company']}-{row['code']}@{row['version']}"
