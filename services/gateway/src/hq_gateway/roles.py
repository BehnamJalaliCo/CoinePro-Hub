"""Roles written on demand (prompt 13 §1.1, contract §22.5, agents/tools.md):

    role.draft   A1  a department manager writes a role the work needs
    role.decide  A2  a CEO approves a draft of its own company (delegated hiring)
"""

from __future__ import annotations

from hq_gateway import tools as T

TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {}
T.TOOLS.update(TOOLS)
