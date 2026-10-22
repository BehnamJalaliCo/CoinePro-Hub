package hq.actions_test

import data.hq.actions
import data.hq.fixtures_test as f
import rego.v1

act(class, company) := {"class": class, "name": "test", "company": company}

named(class, name, company) := {"class": class, "name": name, "company": company}

ctx(escrow, locked) := {"escrow_classes": escrow, "company_locked": locked}

open := ctx([], false)

reasons(p, a, c) := r if {
	r := actions.deny_reasons with input as {"principal": p, "action": a, "context": c}
}

allowed(p, a, c) if actions.allow with input as {"principal": p, "action": a, "context": c}

test_owner_may_do_everything_even_when_locked if {
	every class in actions.classes {
		allowed(f.owner, act(class, "TY"), ctx([], true))
	}
}

test_agent_observes_and_proposes if {
	allowed(f.ty_growth_01, act("A0", "TY"), open)
	allowed(f.ty_growth_01, act("A1", "TY"), open)
}

test_agent_a2_by_role_or_inside_escrow if {
	allowed(f.ty_growth_01, act("A2", "TY"), ctx(["A0", "A1", "A2"], false))
	not allowed(f.ty_growth_01, act("A2", "TY"), open)
	reasons(f.ty_growth_01, act("A2", "TY"), open) == {"a2_needs_role_or_escrow"}
	allowed(f.ty_ceo, named("A2", "kill_switch.set", "TY"), open)
	allowed(f.ty_ceo, named("A2", "decision.approve", "TY"), open)
	allowed(f.ty_growth_mgr, named("A2", "work.delegate", "TY"), open)
	reasons(f.ty_growth_mgr, named("A2", "kill_switch.set", "TY"), open) == {"a2_needs_role_or_escrow"}
	reasons(f.ty_growth_01, named("A2", "work.delegate", "TY"), open) == {"a2_needs_role_or_escrow"}
}

test_agent_a3_needs_a_decision if {
	reasons(f.ty_ceo, act("A3", "TY"), ctx(["A3"], false)) == {"a3_requires_decision"}
}

test_a4_forbidden_for_every_non_owner if {
	reasons(f.ty_ceo, act("A4", "TY"), ctx(["A4"], false)) == {"a4_forbidden_for_ai"}
	reasons(f.svc, act("A4", "TY"), open) == {"a4_forbidden_for_ai"}
	not allowed(f.hq_adv, act("A4", "HQ"), open)
}

test_service_classes if {
	allowed(f.svc, act("A0", "TY"), open)
	allowed(f.svc, act("A1", "FX"), open)
	allowed(f.svc, act("A2", "PC"), open)
	reasons(f.svc, act("A3", "TY"), open) == {"a3_not_for_services"}
}

test_agent_other_company if {
	reasons(f.ty_ceo, act("A0", "FX"), open) == {"other_company"}
	"other_company" in reasons(object.union(f.ty_ceo, {"company": null}), act("A0", null), open)
}

test_company_locked if {
	reasons(f.ty_growth_01, act("A1", "TY"), ctx([], true)) == {"company_locked"}
	allowed(f.ty_ceo, named("A1", "notification.raise", "TY"), {"escrow_classes": [], "company_locked": true, "incident": true})
	reasons(f.ty_ceo, named("A1", "notification.raise", "TY"), ctx([], true)) == {"company_locked"}
	reasons(f.ty_ceo, named("A1", "work.deliver", "TY"), {"escrow_classes": [], "company_locked": true, "incident": true}) == {"company_locked"}
	allowed(f.ty_ceo, named("A2", "kill_switch.set", "TY"), ctx([], true))
	allowed(f.ty_ceo, named("A2", "deploy_freeze.set", "TY"), ctx([], true))
	allowed(f.ty_growth_01, act("A0", "TY"), ctx([], true))
	reasons(f.svc, act("A2", "TY"), ctx([], true)) == {"company_locked"}
}

# Exactly what the Tool Gateway sends (services/gateway hq_gateway/gateway.py
# _decide, and services/gateway/tests test_the_policy_input): tool name
# "notify", the gate's lock as company_locked, the 🔴 incident flag.
gateway_notify(level_urgent) := {
	"principal": {
		"kind": "agent", "code": "TY-TECH-01", "role": "employee", "company": "TY",
		"department": "TECH", "status": "active", "scope": "company",
	},
	"action": {"class": "A2", "name": "notify", "company": "TY"},
	"context": {"escrow_classes": [], "company_locked": true, "incident": level_urgent},
}

test_locked_company_agent_raises_an_incident_from_the_gateway if {
	actions.allow with input as gateway_notify(true)
	actions.policy_action == "notification.raise" with input as gateway_notify(true)
	actions.deny_reasons == {"company_locked"} with input as gateway_notify(false)
	not actions.allow with input as gateway_notify(false)
}

test_missing_lock_information_counts_as_locked if {
	reasons(f.ty_growth_01, act("A1", "TY"), {"escrow_classes": []}) == {"company_locked"}
	allowed(f.ty_growth_01, act("A0", "TY"), {})
}

test_inactive_agent if {
	reasons(f.paused(f.ty_growth_01), act("A1", "TY"), open) == {"agent_inactive"}
	allowed(f.dismissed(f.ty_growth_01), act("A0", "TY"), open)
}

test_unknown_class_and_principal if {
	not allowed(f.owner, act("A9", "TY"), open)
	reasons(f.owner, act("A9", "TY"), open) == {"unknown_class"}
	reasons(f.stranger, act("A0", "TY"), open) == {"unknown_principal"}
	not actions.allow with input as {"action": act("A0", "TY")}
}

test_tool_level_a2_grants if {
	every name in {"work.accept", "work.progress", "work.fail", "activity.set", "notify"} {
		allowed(f.ty_growth_01, named("A2", name, "TY"), open)
		allowed(f.hq_ovs, named("A2", name, "HQ"), open)
	}
	allowed(f.ty_ceo, named("A2", "work.request", "TY"), open)
	allowed(f.ty_growth_mgr, named("A2", "work.request", "TY"), open)
	allowed(f.hq_ovs, named("A2", "work.delegate", "HQ"), open)
	reasons(f.ty_growth_01, named("A2", "work.delegate", "TY"), open) == {"a2_needs_role_or_escrow"}
	reasons(f.hq_adv, named("A2", "notify", "HQ"), open) == {"a2_needs_role_or_escrow"}
}

# prompt 07 §3: an MCP tool sealed as A2 runs for CEOs and managers; an
# employee or the advisor only reads (A0); A3 is never an agent's.
test_mcp_call_by_sealed_class if {
	allowed(f.ty_ceo, named("A2", "mcp.call", "TY"), open)
	allowed(f.ty_growth_mgr, named("A2", "mcp.call", "TY"), open)
	allowed(f.ty_growth_01, named("A0", "mcp.call", "TY"), open)
	reasons(f.ty_growth_01, named("A2", "mcp.call", "TY"), open) == {"a2_needs_role_or_escrow"}
	reasons(f.hq_adv, named("A2", "mcp.call", "HQ"), open) == {"a2_needs_role_or_escrow"}
	reasons(f.ty_ceo, named("A3", "mcp.call", "TY"), open) == {"a3_requires_decision"}
}

# 7.1 §2.10: the one call an approved A3 card allows (the api consumed the
# card for it) runs; a locked company or another company still refuses it,
# and anything that is not a decision ref is no approval.
test_mcp_call_a3_with_an_approved_card if {
	approved := {"escrow_classes": [], "company_locked": false, "approved_decision": "D-000042"}
	allowed(f.ty_growth_01, named("A3", "mcp.call", "TY"), approved)
	locked := {"escrow_classes": [], "company_locked": true, "approved_decision": "D-000042"}
	reasons(f.ty_growth_01, named("A3", "mcp.call", "TY"), locked) == {"company_locked"}
	reasons(f.ty_growth_01, named("A3", "mcp.call", "FX"), approved) == {"other_company"}
	not_a_ref := {"escrow_classes": [], "company_locked": false, "approved_decision": "yes"}
	reasons(f.ty_ceo, named("A3", "mcp.call", "TY"), not_a_ref) == {"a3_requires_decision"}
	reasons(f.svc, named("A3", "mcp.call", "TY"), approved) == {"a3_not_for_services"}
}
