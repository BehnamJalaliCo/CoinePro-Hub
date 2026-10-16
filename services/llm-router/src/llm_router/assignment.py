"""Assignment resolution: which connection, model and effort a call uses.

Inheritance, most general first; every level overrides the one above, field
by field (a level may set only the effort, for example):

    holding -> company -> department -> role -> task_class

Role and task_class accept a global ref ("advisor") and a company-qualified
ref ("TY:advisor"); the qualified one is more specific. Refs:
    holding     the holding company's code, e.g. "HQ"
    company     the company code, e.g. "TY"
    department  "<COMPANY>-<DEPT>", e.g. "TY-TECH"
    role        "<role>" or "<COMPANY>:<role>"
    task_class  "<task_class>" or "<COMPANY>:<task_class>"
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

SCOPE_ORDER = ("holding", "company", "department", "role", "task_class")
EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Assignment:
    connection_id: str | None = None
    model: str | None = None
    effort: str | None = None


@dataclass(frozen=True)
class Resolved:
    connection_id: str
    model: str | None
    effort: str | None
    trail: tuple[str, ...]  # "scope_type:scope_ref" of every level that applied


class AssignmentError(ValueError):
    pass


def scope_chain(
    *,
    holding: str,
    company: str,
    department: str | None,
    role: str | None,
    task_class: str,
) -> list[tuple[str, str]]:
    """(scope_type, scope_ref) pairs from the most general to the most specific."""
    chain: list[tuple[str, str]] = [("holding", holding), ("company", company)]
    if department:
        chain.append(("department", f"{company}-{department}"))
    if role:
        chain += [("role", role), ("role", f"{company}:{role}")]
    chain += [("task_class", task_class), ("task_class", f"{company}:{task_class}")]
    return chain


def resolve(
    assignments: Mapping[tuple[str, str], Assignment], chain: list[tuple[str, str]]
) -> Resolved:
    connection_id: str | None = None
    model: str | None = None
    effort: str | None = None
    trail: list[str] = []
    for key in chain:
        a = assignments.get(key)
        if a is None:
            continue
        trail.append(f"{key[0]}:{key[1]}")
        if a.connection_id is not None:
            if a.connection_id != connection_id:
                model = None  # a model only makes sense on the connection it was chosen for
            connection_id = a.connection_id
        if a.model is not None:
            model = a.model
        if a.effort is not None:
            effort = a.effort
    if connection_id is None:
        raise AssignmentError("no assignment provides a connection (seed the holding assignment)")
    return Resolved(connection_id, model, effort, tuple(trail))


def apply_request(
    resolved: Resolved,
    *,
    requested_model: str | None,
    requested_effort: str | None,
    allowed_models: list[str],
    default_model: str | None,
) -> tuple[str, str | None]:
    """Final (model, effort): the request may pick a model the connection offers."""
    model = requested_model or resolved.model or default_model
    if model is None:
        raise AssignmentError("no model resolved for this call")
    if allowed_models and model not in allowed_models:
        raise AssignmentError(f"model {model!r} is not offered by the assigned connection")
    effort = requested_effort or resolved.effort
    if effort is not None and effort not in EFFORTS:
        raise AssignmentError(f"unknown effort {effort!r}")
    return model, effort
