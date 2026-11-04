"""Routing by domain (contract §29.1, the owner's decisions 1-3 of 2026-11-02).

Every notification, finding and decision card carries a `domain`, set by the
code that raises it (rules here, no model):

    business, media, revenue, product   the company's CEO (media: its media
                                        director); they reach the owner,
                                        written for the owner (§29.7)
    tech, infra                         the company's CTO (its SRE second);
                                        the hub itself: hub_platform_sre
    security                            the company's CTO; the holding's
                                        security_analyst

A technical item reaches the owner (`owner_visible`) only when it is critical
by the fixed list `critical_reason` (data_leak, product_down: a product
unreachable more than 15 minutes, money, legal), or when only the owner can
act on it (a card the owner decides, a hold only the owner releases): then it
is the owner's whatever its domain. Everything else technical goes to its
handler's queue (`routed_to`), and once a week into the technical summary.

The same rules are written once in SQL in migration 0037 for the data
already there; the tests keep both in step.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from hq_api.db import Tx

DOMAINS = ("business", "media", "revenue", "product", "tech", "security", "infra")
BUSINESS = ("business", "media", "revenue", "product")
TECHNICAL = ("tech", "security", "infra")
CRITICAL_REASONS = ("data_leak", "product_down", "money", "legal")
DOMAIN_FA = {
    "business": "کسب‌وکار",
    "media": "رسانه",
    "revenue": "درآمد",
    "product": "محصول",
    "tech": "فنی",
    "security": "امنیت",
    "infra": "زیرساخت",
}
CRITICAL_FA = {
    "data_leak": "نشت داده",
    "product_down": "از کار افتادن محصول",
    "money": "پول",
    "legal": "حقوقی",
}

# A protocol's area (oversight.protocols.area) -> its domain.
AREA_DOMAIN = {
    "truth": "business",
    "authority": "business",
    "money": "business",
    "safety": "security",
    "quality": "business",
    "delivery": "business",
    "security": "security",
    "data": "infra",
    "people": "business",
    "product": "product",
    "owner": "business",
}
# The protocol's answering role decides a technical domain (its area alone
# would call a CTO's deploy check "product").
ROLE_DOMAIN = {
    "sre": "infra",
    "hub_platform_sre": "infra",
    "cto": "tech",
    "lead_developer": "tech",
    "devops_engineer": "tech",
    "security_analyst": "security",
    "ai_safety": "security",
}
# The few seeded protocols whose area and role both mislead.
PROTOCOL_DOMAIN = {
    "PR-060": "infra",  # the sites' health
    "PR-062": "infra",  # the hub's health
    "PR-013": "tech",  # tools within each role's list
    "PR-034": "tech",  # skills and charters reviewed
    "PR-142": "tech",  # the monthly code review
    "PR-141": "product",  # the apps' health from their own error log
    "PR-043": "product",  # the mystery customer
    "PR-101": "product",  # customer messages
    "PR-102": "product",  # automatic answers
    "PR-104": "product",  # expired articles in answers
    "PR-103": "revenue",  # the revenue radar
}
# A critical finding of these protocols is critical for the owner too.
PROTOCOL_CRITICAL = {"PR-030": "data_leak", "PR-031": "data_leak"}
# The watch's kind of finding (§28.3).
KIND_DOMAIN = {
    "security": "security",
    "app_health": "product",
    "code": "tech",
    "growth": "business",
    "holding": "business",
}
DECISION_DOMAIN = {
    "server_destructive": "infra",
    "server_plan": "infra",
    "deploy": "tech",
    "code_session": "tech",
    "tool_enable": "tech",
    "media_series": "media",
    "media_publish": "media",
    "line_publish": "media",
    "message_template": "product",
    "lifecycle_rule": "product",
    "support_go_live": "product",
}
# A notification's link kind (or, failing that, its source).
LINK_DOMAIN = {
    # founding a company is the owner's own business (its server plan's seal)
    "server_plan": "business",
    "founding": "business",
    "backup": "infra",
    "audit": "infra",
    "treasury": "infra",
    "code_session": "tech",
    "device": "security",
    "archive_fixity": "security",
    "support_queue": "product",
    "support_conversation": "product",
    "feedback": "product",
    "revenue_alert": "revenue",
}
SOURCE_DOMAIN = {
    "backup": "infra",
    "llm-router": "infra",
    "site-checks": "infra",
    "archive-fixity": "security",
}
# An agent's incident category (notify) or a code word (§29.1's list).
CATEGORY_DOMAIN = {
    "service_down": "infra",
    "security": "security",
    "data_loss": "infra",
    "budget_hard_stop": "business",
}
CATEGORY_CRITICAL = {"service_down": "product_down", "budget_hard_stop": "money"}
WORD_DOMAIN = (
    (("server_", "deploy", "backup", "incident", "catalogue"), "infra"),
    (("security", "secret", "egress"), "security"),
    (("media_",), "media"),
    (("revenue", "funnel", "referral"), "revenue"),
    (("feedback", "app_health"), "product"),
)


def domain_of_word(word: str | None) -> str | None:
    """§29.1's list of code words (`server_*`, `deploy`, `backup`, ...)."""
    if not word:
        return None
    for words, domain in WORD_DOMAIN:
        if any(word.startswith(w) if w.endswith("_") else word == w for w in words):
            return "tech" if word == "deploy" else domain
    return None


def finding_domain(
    *,
    protocol: str | None = None,
    area: str | None = None,
    answerable: str | None = None,
    kind: str | None = None,
) -> str:
    """A finding's domain: the protocol's own (the few that mislead), the
    watch's kind (no protocol), the area when it is security or safety, the
    answering role, the area, the kind, else business."""
    if protocol in PROTOCOL_DOMAIN:
        return PROTOCOL_DOMAIN[protocol]
    if protocol is None and kind in KIND_DOMAIN:
        return KIND_DOMAIN[kind]
    if area in ("security", "safety"):
        return "security"
    if answerable in ROLE_DOMAIN:
        return ROLE_DOMAIN[answerable]
    if area in ("data", "product"):
        return AREA_DOMAIN[area]
    if kind in KIND_DOMAIN:
        return KIND_DOMAIN[kind]
    return "business"


def decision_domain(kind: str) -> str:
    return DECISION_DOMAIN.get(kind, "business")


def notification_domain(
    link_kind: str | None, source_code: str | None = None, category: str | None = None
) -> str:
    if category in CATEGORY_DOMAIN:
        return CATEGORY_DOMAIN[category]
    if link_kind in LINK_DOMAIN:
        return LINK_DOMAIN[link_kind]
    if link_kind and link_kind.startswith("media"):
        return "media"
    if source_code in SOURCE_DOMAIN:
        return SOURCE_DOMAIN[source_code]
    return domain_of_word(link_kind) or "business"


def critical_of(
    *, protocol: str | None = None, severity: str | None = None, category: str | None = None
) -> str | None:
    """The fixed list's reason a rule knows by itself (an agent may name one)."""
    if category in CATEGORY_CRITICAL:
        return CATEGORY_CRITICAL[category]
    if severity == "critical" and protocol in PROTOCOL_CRITICAL:
        return PROTOCOL_CRITICAL[protocol]
    return None


def clean_domain(domain: str | None) -> str | None:
    return domain if domain in DOMAINS else None


def clean_critical(reason: str | None) -> str | None:
    return reason if reason in CRITICAL_REASONS else None


def owner_visible(domain: str, critical_reason: str | None, owner_action: bool = False) -> bool:
    """§29.1: business items always; a technical one only when critical by
    the fixed list, or when only the owner can act on it."""
    return domain in BUSINESS or critical_reason in CRITICAL_REASONS or owner_action


async def _by_role(tx: Tx, company_id: UUID, roles: tuple[str, ...]) -> str | None:
    """The first active employee of these roles (in that order) in a company.
    A SECURITY-DEFINER-free read: under a company-scoped transaction another
    company's employees are not visible, and then nobody is named."""
    code: str | None = await tx.scalar(
        """SELECT code FROM core.employees
           WHERE company_id = :co AND status = 'active' AND (role = ANY(:roles) OR kind = ANY(:roles))
           ORDER BY array_position(CAST(:roles AS text[]), COALESCE(role, kind)), hired_at
           LIMIT 1""",
        co=company_id,
        roles=list(roles),
    )
    return code


async def _holding(tx: Tx) -> UUID | None:
    hid: UUID | None = await tx.scalar("SELECT id FROM core.companies WHERE kind = 'holding'")
    return hid


async def route(tx: Tx, company_id: UUID, domain: str) -> str | None:
    """Who handles an item of this company and domain (an employee code), or
    None: the owner (the holding's business, §29.13's home cards)."""
    kind = await tx.scalar("SELECT kind FROM core.companies WHERE id = :co", co=company_id)
    holding = kind == "holding"
    if domain in ("tech", "infra"):
        if holding:  # the hub's platform SRE, else the head of AI operations
            return await _by_role(tx, company_id, ("hub_platform_sre", "aiops_head"))
        return await _by_role(tx, company_id, ("cto", "sre")) or await _by_role(
            tx, company_id, ("ceo",)
        )
    if domain == "security":
        if holding:
            return await _by_role(
                tx, company_id, ("security_analyst", "hub_platform_sre", "aiops_head")
            )
        found = await _by_role(tx, company_id, ("cto", "sre"))
        if found:
            return found
        hid = await _holding(tx)
        return (await _by_role(tx, hid, ("security_analyst",)) if hid else None) or (
            await _by_role(tx, company_id, ("ceo",))
        )
    if holding:
        return None
    if domain == "media":
        return await _by_role(tx, company_id, ("media_director", "ceo"))
    return await _by_role(tx, company_id, ("ceo",))


async def classify(
    tx: Tx,
    company_id: UUID,
    domain: str,
    critical_reason: str | None = None,
    *,
    owner_action: bool = False,
) -> dict[str, Any]:
    """The four routing fields of a new item: {domain, owner_visible,
    routed_to, critical_reason}."""
    domain = clean_domain(domain) or "business"
    critical_reason = clean_critical(critical_reason)
    return {
        "domain": domain,
        "owner_visible": owner_visible(domain, critical_reason, owner_action),
        "routed_to": await route(tx, company_id, domain),
        "critical_reason": critical_reason,
    }


def fields(row: dict[str, Any]) -> dict[str, Any]:
    """The four fields of a stored row, for an API model."""
    return {
        "domain": row.get("domain") or "business",
        "owner_visible": bool(row.get("owner_visible", True)),
        "routed_to": row.get("routed_to"),
        "critical_reason": row.get("critical_reason"),
    }


# The owner's list filters: `?scope=all` shows every row; `domain` and
# `company` narrow it (the app's «شرکت ← فنی»).
SCOPES = ("owner", "all")


def parse_domains(values: list[str] | None) -> list[str] | None:
    """`?domain=tech&domain=infra`, `?domain=tech,infra` or `?domain=tech|infra`;
    an unknown domain is a 422."""
    if not values:
        return None
    from hq_api.errors import ApiError

    out: list[str] = []
    for v in values:
        for d in v.replace("|", ",").split(","):
            d = d.strip()
            if not d:
                continue
            if d not in DOMAINS:
                raise ApiError(422, "validation_failed", fields={"domain": f"unknown domain {d}"})
            out.append(d)
    return out or None
