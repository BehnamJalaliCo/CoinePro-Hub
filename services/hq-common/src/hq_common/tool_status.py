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
        # prompt 09 §3: the agents' server plan
        "server.plan",
        # the skill library and the academy (prompt 08 §6-§7)
        "skill.review",
        "eval.run",
        "teach.draft",
        # the Chief Overseer (prompt 08 §2)
        "finding.raise",
        "finding.update",
        "protocol.result",
        "challenge.issue",
        "challenge.submit",
        "challenge.score",
        "hold",
        "kill_switch.engage",
        "deploy.freeze",
        # prompt 10 §2, §3, §8 (contract §19.10): the radar, the funnel, rescue, feedback
        "revenue.read",
        "funnel.read",
        "rescue.update",
        "feedback.tag",
        "referral.check",
        # prompt 10 §12: the support desk (none sends free text to a customer)
        "kb.search",
        "kb.propose",
        "support.draft",
        "support.handoff",
        "support.mystery",
        # prompt 11 §1-§3 (contract §20.1-§20.3): the meeting room and the knowledge base
        "meeting.statement",
        "meeting.challenge",
        "meeting.whisper",
        "meeting.item",
        "meeting.minutes",
        "knowledge.propose",
        "knowledge.review",
        "knowledge.approve",
        # prompt 11 §4-§10 (contract §20.11): cards, OKRs, outcomes, risks, the calendar, the matrix
        "kpi.record",
        "okr.draft",
        "okr.checkin",
        "outcome.note",
        "risk.raise",
        "risk.update",
        "calendar.read",
        "calendar.add",
        "authority.read",
        "governance.read",
        # prompt 12 part A (contract §21.1, §21.13): the advisor's memo; the
        # substitute players (refused channel_not_configured while signed out)
        "memo.write",
        "substitute.call",
        # prompt 12 §12 (contract §21.9): a fact check of one claim
        "claim.verdict",
        # prompt 12 §2 (contract §21.2): the librarian's answer to the owner's ask
        "ask.answer",
        # prompt 13 §1.1 (contract §22.5): roles written on demand
        "role.draft",
        "role.decide",
        # prompt 13 §2 (contract §22.2): the media studio
        "media.item",
        "media.render",
        "media.voice",  # the narration, in the voice registry's queue (§22.3)
        "media.review",
        "series.propose",
        # prompt 13 (contract §22.3, §22.4): the legal counsel's tools (email.draft
        # only makes a card)
        "case.open",
        "case.note",
        "email.draft",
        "mail.read",
        # prompt 14 (contract §23.11): the archive (archive.file only makes a draft)
        "archive.search",
        "archive.read",
        "archive.file",
        "archive.link",
        "archive.hold",
    }
)
# Tools whose traffic leaves the hub through the egress service (contract §18.7).
WEB_TOOLS: frozenset[str] = frozenset(
    {"web.search", "web.read", "web.browse", "http.request", "egress.recent"}
)
# Built, but waiting for something only the owner provides (github.read: a
# read-only token, prompt 5.1 §3).
NOT_CONFIGURED: frozenset[str] = frozenset({"github.read"})
