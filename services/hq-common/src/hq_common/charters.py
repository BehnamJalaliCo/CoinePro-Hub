"""Role charters and the tool catalog (agents/, owned by the consultation session).

The server only READS these files (prompt 05 §0.3):
    agents/roles/_common.md   rules shared by every role (first in every system prompt)
    agents/roles/<role>.md    one charter per role: YAML frontmatter + body
    agents/tools.md           the Tool Gateway catalog (a Markdown table)

Safest reading of a flawed charter: a tool it lists that the catalog does not
know is dropped (never granted) and reported in `Library.problems`; a charter
whose frontmatter does not parse is left out (its role cannot run).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DIR = "/app/agents"
CLASSES = ("A0", "A1", "A2", "A3", "A4")
KINDS = ("ceo", "manager", "employee", "advisor", "inspector")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PRIORITIES = ("P0", "P1", "P2", "P3", "P4")
ROLE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
VAR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
# Template variables the runtime fills (agents/README.md).
VARIABLES = (
    "employee_code",
    "employee_title_fa",
    "company_code",
    "company_name_fa",
    "company_name_en",
    "holding_code",
    "department_code",
    "department_name_fa",
    "manager_code",
    "today_jalali",
    "today_gregorian",
    "owner_timezone",
)
# The runtime ends a run with `done`; it is not a gateway tool.
IMPLICIT_TOOLS = ("done",)


@dataclass(frozen=True)
class Tool:
    """One catalog row. `cls` is the class the gateway assumes when it cannot
    tell better: for a per-call class (`A0/A2`: the HTTP method or browser
    step decides) the highest one; for `per tool` (mcp.call) A2, the real
    class coming from the MCP server's registration at call time."""

    name: str
    cls: str
    input: str
    description: str
    classes: tuple[str, ...] = ()  # `A0/A2`: the classes a call may have
    per_tool: bool = False  # `per tool`: the registration decides


def _classes(cell: str) -> tuple[str, tuple[str, ...], bool] | None:
    """(cls, classes, per_tool) of a catalog class cell, or None if unknown."""
    if cell in CLASSES:
        return cell, (), False
    if cell.lower() == "per tool":
        return "A2", (), True
    parts = tuple(c.strip() for c in cell.split("/"))
    if len(parts) > 1 and all(c in CLASSES for c in parts):
        return max(parts), parts, False
    return None


@dataclass(frozen=True)
class Limits:
    steps_per_run: int
    tokens_per_step: int
    tokens_per_run: int


@dataclass(frozen=True)
class Charter:
    role: str
    title_fa: str
    title_en: str
    kind: str
    scope: str
    department: str | None
    model: str
    effort: str
    priority: str
    tools: tuple[str, ...]
    limits: Limits
    version: int
    body: str

    @property
    def ref(self) -> str:
        return f"{self.role}@{self.version}"


@dataclass
class Library:
    root: Path
    common: str = ""
    common_version: int = 0
    roles: dict[str, Charter] = field(default_factory=dict)
    tools: dict[str, Tool] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def get(self, role: str | None) -> Charter | None:
        return self.roles.get(role or "")

    def allowed(self, role: str | None) -> tuple[str, ...]:
        c = self.get(role)
        return c.tools if c else ()

    def tool_rows(self, role: str) -> list[Tool]:
        """The catalog rows of the tools a role may use, in catalog order."""
        allowed = set(self.allowed(role))
        return [t for name, t in self.tools.items() if name in allowed]

    def system_prompt(self, role: str, values: dict[str, str]) -> str:
        """_common.md + <role>.md with the template variables filled in."""
        c = self.roles[role]
        return fill(self.common, values) + "\n\n" + fill(c.body, values)


def fill(text: str, values: dict[str, str]) -> str:
    """Known variables are replaced; an unknown one becomes empty (never left raw)."""
    return VAR.sub(lambda m: str(values.get(m.group(1), "")), text)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError("no frontmatter")
    _, head, body = text.split("---", 2)
    meta = yaml.safe_load(head)
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a mapping")
    return meta, body.strip()


def _cell(text: str) -> str:
    return text.strip().strip("`").strip()


def parse_tools(text: str) -> dict[str, Tool]:
    """Rows of the catalog table: | `tool` [· `tool`...] | class | `input` [· ...] | what |."""
    out: dict[str, Tool] = {}
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        names = [_cell(n) for n in cells[0].split("·")]
        parsed = _classes(cells[1].strip())
        inputs = [_cell(i) for i in cells[2].split("·")]
        if parsed is None:
            continue
        cls, classes, per_tool = parsed
        for i, name in enumerate(names):
            if re.match(r"^[a-z][a-z_]*\.[a-z_]+$|^[a-z]+$", name):
                out[name] = Tool(
                    name=name,
                    cls=cls,
                    input=inputs[i] if i < len(inputs) else inputs[-1],
                    description=cells[3].strip(),
                    classes=classes,
                    per_tool=per_tool,
                )
    return out


def _charter(
    meta: dict[str, Any], body: str, catalog: dict[str, Tool], problems: list[str]
) -> Charter:
    role = str(meta["role"])
    if not ROLE.match(role):
        raise ValueError(f"bad role {role!r}")
    kind = str(meta["kind"])
    if kind not in KINDS:
        raise ValueError(f"{role}: unknown kind {kind!r}")
    effort = str(meta["effort"])
    priority = str(meta["priority"])
    if effort not in EFFORTS or priority not in PRIORITIES:
        raise ValueError(f"{role}: bad effort or priority")
    tools: list[str] = []
    for t in meta.get("tools") or []:
        name = str(t)
        if name not in catalog:
            problems.append(f"{role}: tool {name!r} is not in agents/tools.md (not granted)")
            continue
        if catalog[name].cls in ("A3", "A4"):
            problems.append(f"{role}: tool {name!r} is {catalog[name].cls} (never granted)")
            continue
        tools.append(name)
    lim = meta.get("limits") or {}
    limits = Limits(
        steps_per_run=int(lim["steps_per_run"]),
        tokens_per_step=int(lim["tokens_per_step"]),
        tokens_per_run=int(lim["tokens_per_run"]),
    )
    if min(limits.steps_per_run, limits.tokens_per_step, limits.tokens_per_run) <= 0:
        raise ValueError(f"{role}: limits must be positive")
    dept = meta.get("department")
    return Charter(
        role=role,
        title_fa=str(meta["title_fa"]),
        title_en=str(meta["title_en"]),
        kind=kind,
        scope=str(meta.get("scope", "company")),
        department=str(dept) if dept else None,
        model=str(meta["model"]),
        effort=effort,
        priority=priority,
        tools=tuple(tools),
        limits=limits,
        version=int(meta["version"]),
        body=body,
    )


def load(root: str | Path | None = None) -> Library:
    base = Path(root or os.environ.get("HQ_AGENTS_DIR", DEFAULT_DIR))
    lib = Library(root=base)
    tools_file = base / "tools.md"
    if tools_file.exists():
        lib.tools = parse_tools(tools_file.read_text(encoding="utf-8"))
    else:
        lib.problems.append("agents/tools.md is missing: no tool is granted")
    roles = base / "roles"
    common = roles / "_common.md"
    if common.exists():
        meta, body = split_frontmatter(common.read_text(encoding="utf-8"))
        lib.common, lib.common_version = body, int(meta.get("version", 1))
    else:
        lib.problems.append("agents/roles/_common.md is missing")
    for path in sorted(roles.glob("*.md")) if roles.exists() else []:
        if path.name.startswith("_"):
            continue
        try:
            meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
            c = _charter(meta, body, lib.tools, lib.problems)
        except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            lib.problems.append(f"{path.name}: not loaded ({type(exc).__name__}: {exc})")
            continue
        if c.role != path.stem:
            lib.problems.append(f"{path.name}: role {c.role!r} does not match the file name")
            continue
        lib.roles[c.role] = c
    return lib
