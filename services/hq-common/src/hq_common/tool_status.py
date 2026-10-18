"""Which agents/tools.md tools this build carries out (prompt 07 §3).

The api's `GET /tools/catalog` reports a catalog tool as `live` when the Tool
Gateway has it and `off` when it is only in the catalog so far; the gateway's
own test keeps GATEWAY_TOOLS equal to its tool table, so the two never drift.
"""

from __future__ import annotations

GATEWAY_TOOLS: frozenset[str] = frozenset(
    {
        "work.get",
        "company.state",
        "health.sites",
        "health.hub",
        "treasury.usage",
        "knowledge.search",
        "audit.recent",
        "memory.read",
        "files.read",
        "github.read",
        "deliver",
        "propose",
        "message.owner",
        "message.thread",
        "memory.write",
        "work.accept",
        "work.progress",
        "work.fail",
        "work.delegate",
        "work.request",
        "activity.set",
        "notify",
        "mcp.call",
        "backups.status",
        # the internet tools (prompt 07 §2): live once egress runs
        "web.search",
        "web.read",
        "web.browse",
        "http.request",
        "egress.recent",
        # prompt 08 §3, §5: inquiries, errands, the owner's planner, workshop.read
        "inquiry.ask",
        "inquiry.answer",
        "errand.step",
        "errand.finish",
        "planner.add",
        "workshop.read",
        # prompt 08 §4, §8, §9: stars, lessons, stories, the CEOs' hire decisions
        "star.rubric",
        "star.give",
        "star.audit",
        "lesson.write",
        "story.post",
        "hire.decide",
    }
)
# Tools whose traffic leaves the hub through the egress service (contract §18.7).
WEB_TOOLS: frozenset[str] = frozenset(
    {"web.search", "web.read", "web.browse", "http.request", "egress.recent"}
)
# Built, but waiting for something only the owner provides (github.read: a
# read-only token, prompt 5.1 §3).
NOT_CONFIGURED: frozenset[str] = frozenset({"github.read"})
