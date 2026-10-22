"""The template send entry point for the rest of prompt 10 (§3 referral
rescue, §8 feedback, §7 lifecycle): every message a rule sends to a customer
goes through `send_template`, nowhere else.

    from hq_api.domain import growth
    out = await growth.send_template(
        tx, hub,
        company_id=co_id,
        purpose="rescue",                      # welcome | reactivation | rescue | nps | csat
        dedupe_key=f"rescue:{case_ref}:{n}",   # one send per occurrence (UNIQUE per company)
        conversation_id=case["conversation_id"],   # or subject=<the customer's support subject>
        rescue_case_id=case["id"], follow_up=n,
        variables={"name": "..."},             # only the template's declared variables are used
    )
    out["status"]  # queued | sent | blocked | skipped | no_channel | failed
    out["reason"]  # e.g. holding_locked, no_active_rule, template_not_sealed, opted_out,
                   # per_customer_days, quiet_hours (retried), daily_cap (retried),
                   # channel_not_live, telegram_rules, guard, no_conversation

It checks, in this order: the launch gate (holding or company locked ->
skipped, nothing recorded, so the same dedupe_key can run later), the
company's ACTIVE rule of that kind (sealed by the owner) and its template
version (sealed and current, else the rule is paused), opt-out, the rule's
per-customer days, quiet hours (Tehran), the daily cap, a live channel and
Telegram's own rules, then the outbound guard (with the safety line); only
then a message is queued for the worker. There is no way to send free text.
"""

from __future__ import annotations

from hq_api.domain.lifecycle import RULE_KINDS, nps_score, send_template

__all__ = ["RULE_KINDS", "nps_score", "send_template"]
