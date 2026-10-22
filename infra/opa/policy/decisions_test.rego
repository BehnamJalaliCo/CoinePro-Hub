package hq.decisions_test

import data.hq.decisions
import data.hq.fixtures_test as f
import rego.v1

mgr := {"kind": "agent", "code": "TY-SALES-MGR"}

dec(kind, class) := {"kind": kind, "company": "TY", "action_class": class, "payload": {}, "proposer": mgr}

publish := {"kind": "a3_action", "company": "TY", "action_class": "A3", "payload": {"action": "publish"}, "proposer": mgr}

price := {"kind": "a3_action", "company": "TY", "action_class": "A3", "payload": {"action": "price_change"}, "proposer": mgr}

recurring := dec("recurring_approval", "A2")

quota_ok := {"within_quota": true, "in_content_calendar": false}

calendar_ok := {"within_quota": false, "in_content_calendar": true}

reasons(p, d, c) := r if {
	r := decisions.deny_reasons with input as {"principal": p, "decision": d, "context": c}
}

allowed(p, d, c) if decisions.allow with input as {"principal": p, "decision": d, "context": c}

test_owner_decides_every_kind if {
	every kind in decisions.kinds {
		allowed(f.owner, dec(kind, "A3"), {})
	}
}

test_unknown_kind_denied_even_for_owner if {
	not allowed(f.owner, dec("trade", "A3"), {})
	"unknown_kind" in reasons(f.owner, dec("trade", "A3"), {})
}

test_a4_never_in_decisions if {
	not allowed(f.owner, dec("proposal", "A4"), {})
	reasons(f.owner, dec("proposal", "A4"), {}) == {"a4_never_in_decisions"}
}

test_unknown_action_class if {
	reasons(f.owner, dec("proposal", "A9"), {}) == {"unknown_action_class"}
}

test_services_never_decide if {
	not allowed(f.svc, recurring, quota_ok)
	reasons(f.svc, recurring, quota_ok) == {"services_never_decide"}
}

test_unknown_principal if {
	not allowed(f.stranger, recurring, quota_ok)
	"unknown_principal" in reasons(f.stranger, recurring, quota_ok)
}

test_missing_or_malformed_input_is_denied if {
	not decisions.allow with input as {"decision": recurring, "context": quota_ok}
	"unknown_principal" in decisions.deny_reasons with input as {"principal": "TY-CEO", "decision": recurring}
	not decisions.allow with input as "not an object"
}

test_ceo_approves_recurring_within_quota if {
	allowed(f.ty_ceo, recurring, quota_ok)
}

test_ceo_recurring_outside_quota if {
	not allowed(f.ty_ceo, recurring, {"within_quota": false})
	reasons(f.ty_ceo, recurring, {}) == {"outside_quota"}
}

test_ceo_of_other_company if {
	not allowed(f.fx_ceo, recurring, quota_ok)
	reasons(f.fx_ceo, recurring, quota_ok) == {"other_company"}
	"other_company" in reasons(object.union(f.ty_ceo, {"company": null}), recurring, quota_ok)
}

test_inactive_ceo if {
	reasons(f.paused(f.ty_ceo), recurring, quota_ok) == {"agent_inactive"}
	reasons(f.dismissed(f.ty_ceo), recurring, quota_ok) == {"agent_inactive"}
}

test_ceo_approves_calendar_publish if {
	allowed(f.ty_ceo, publish, calendar_ok)
}

test_ceo_publish_outside_calendar if {
	reasons(f.ty_ceo, publish, quota_ok) == {"not_in_content_calendar"}
}

test_price_change_is_owner_only if {
	not allowed(f.ty_ceo, price, calendar_ok)
	reasons(f.ty_ceo, price, calendar_ok) == {"owner_only_action"}
	allowed(f.owner, price, {})
}

test_owner_only_kinds_for_ceo if {
	every kind in decisions.kinds - decisions.ceo_kinds {
		reasons(f.ty_ceo, dec(kind, "A3"), quota_ok) == {"owner_only"}
	}
}

test_managers_never_decide if {
	reasons(f.ty_growth_mgr, recurring, quota_ok) == {"ceo_only"}
	reasons(f.ty_growth_mgr, dec("hire", "A2"), quota_ok) == {"owner_only"}
	reasons(f.ty_growth_01, publish, calendar_ok) == {"ceo_only"}
}

test_nobody_decides_their_own_proposal if {
	own := object.union(recurring, {"proposer": {"kind": "agent", "code": "TY-CEO"}})
	not allowed(f.ty_ceo, own, quota_ok)
	reasons(f.ty_ceo, own, quota_ok) == {"own_proposal"}
	by_owner := object.union(dec("proposal", "A1"), {"proposer": {"kind": "owner", "code": "owner"}})
	reasons(f.owner, by_owner, {}) == {"own_proposal"}
	allowed(f.owner, own, {}) # the owner decides the CEO's own proposal
}

# 8.1 §2.1: a protocol card (proposed by the overseer, sealed with step-up)
# is the owner's alone: no agent decides it, the overseer included.
test_a_protocol_card_is_the_owners_alone if {
	card := {
		"kind": "protocol", "company": "HQ", "action_class": "A1",
		"payload": {"ref": "PR-090"}, "proposer": {"kind": "agent", "code": "HQ-OVR"},
	}
	allowed(f.owner, card, {})
	"owner_only" in reasons(f.hq_ovr, card, {})
	"owner_only" in reasons(f.ty_ceo, object.union(card, {"company": "TY"}), {})
}

test_decision_without_proposer_is_denied if {
	no_proposer := {"kind": "proposal", "company": "TY", "action_class": "A1", "payload": {}}
	reasons(f.owner, no_proposer, {}) == {"unknown_proposer"}
	reasons(f.owner, object.union(no_proposer, {"proposer": {"code": 7}}), {}) == {"unknown_proposer"}
}
