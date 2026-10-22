package hq.governance_meetings_test

import data.hq.actions
import data.hq.decisions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

hq_sec := {"kind": "agent", "code": "HQ-SEC", "role": "system", "company": "HQ", "department": "AIOPS", "scope": "holding"}

hq_ai_safety := {"kind": "agent", "code": "HQ-OVS-02", "role": "employee", "company": "HQ", "department": "OVS", "scope": "holding"}

ty_sales := {"kind": "agent", "code": "TY-SALES-01", "role": "employee", "company": "TY", "department": "SALES"}

test_a_speaker_states_in_its_own_company_only if {
	allowed(f.ty_ceo, "meeting.statement", {"company": "TY", "charter": "ceo"})
	not allowed(f.ty_ceo, "meeting.statement", {"company": "FX", "charter": "ceo"})
	not allowed(f.svc, "meeting.statement", {"company": "TY"})
	not allowed(f.owner, "meeting.statement", {"company": "TY"})
}

test_the_devil_is_from_oversight if {
	allowed(f.hq_ovs, "meeting.challenge", {"company": "HQ", "charter": "inspector"})
	allowed(f.hq_ovr, "meeting.challenge", {"company": "HQ", "charter": "overseer"})
	not allowed(f.ty_ceo, "meeting.challenge", {"company": "TY", "charter": "ceo"})
	not allowed(f.hq_adv, "meeting.challenge", {"company": "HQ", "charter": "advisor"})
}

test_only_the_advisor_whispers if {
	allowed(f.hq_adv, "meeting.whisper", {"company": "HQ", "charter": "advisor"})
	not allowed(f.hq_ovr, "meeting.whisper", {"company": "HQ", "charter": "overseer"})
	not allowed(f.ty_ceo, "meeting.whisper", {"company": "TY", "charter": "ceo"})
}

test_only_the_secretary_writes_the_summary if {
	allowed(hq_sec, "meeting.minutes", {"company": "HQ", "charter": "secretary"})
	not allowed(hq_sec, "meeting.minutes", {"company": "HQ", "charter": "aiops_head"})
	not allowed(f.ty_ceo, "meeting.minutes", {"company": "TY", "charter": "secretary"})
	not allowed(f.hq_adv, "meeting.minutes", {"company": "HQ", "charter": "advisor"})
}

test_an_agenda_item_for_its_own_company if {
	allowed(f.ty_ceo, "meeting.item", {"company": "TY", "type": "company"})
	not allowed(f.ty_ceo, "meeting.item", {"company": "FX", "type": "company"})
	allowed(f.hq_adv, "meeting.item", {"company": "FX", "type": "board"})
}

test_knowledge_is_proposed_in_its_own_company if {
	allowed(f.ty_growth_mgr, "knowledge.propose", {"company": "TY", "layer": "department"})
	not allowed(f.ty_growth_mgr, "knowledge.propose", {"company": "FX", "layer": "company"})
	not allowed(f.ty_growth_mgr, "knowledge.propose", {"company": "HQ", "layer": "holding"})
	allowed(f.hq_ovr, "knowledge.propose", {"company": "HQ", "layer": "holding"})
}

test_the_overseer_and_ai_safety_review if {
	allowed(f.hq_ovr, "knowledge.review", {"company": "HQ", "charter": "overseer"})
	allowed(hq_ai_safety, "knowledge.review", {"company": "HQ", "charter": "ai_safety"})
	not allowed(f.hq_ovs_01, "knowledge.review", {"company": "HQ", "charter": "security_analyst"})
	not allowed(f.ty_ceo, "knowledge.review", {"company": "TY", "charter": "ceo"})
}

test_a_ceo_approves_its_own_company_only if {
	allowed(f.ty_ceo, "knowledge.approve", {"company": "TY", "layer": "company"})
	allowed(f.ty_ceo, "knowledge.approve", {"company": "TY", "layer": "department"})
	not allowed(f.ty_ceo, "knowledge.approve", {"company": "FX", "layer": "company"})
	not allowed(f.fx_ceo, "knowledge.approve", {"company": "TY", "layer": "company"})
	not allowed(f.ty_ceo, "knowledge.approve", {"company": "TY", "layer": "holding"})
	not allowed(f.ty_growth_mgr, "knowledge.approve", {"company": "TY", "layer": "company"})
}

test_the_owner_takes_the_approval_back if {
	not policy.allow with input as {"principal": f.ty_ceo, "op": "knowledge.approve", "target": {"company": "TY", "layer": "company"}}
		with data.hq.authority as {"version": "v-test", "rules": {"knowledge.approve.company": {"actor": "owner"}}}
	policy.allow with input as {"principal": f.ty_ceo, "op": "knowledge.approve", "target": {"company": "TY", "layer": "company"}}
		with data.hq.authority as {"version": "v-test", "rules": {"knowledge.approve.company": {"actor": "ceo"}}}
}

test_review_and_approval_are_a2_by_role if {
	actions.allow with input as {"principal": f.hq_ovr, "action": {"class": "A2", "name": "knowledge.review", "company": "HQ"}, "context": {"company_locked": false}}
	actions.allow with input as {"principal": f.ty_ceo, "action": {"class": "A2", "name": "knowledge.approve", "company": "TY"}, "context": {"company_locked": false}}
	not actions.allow with input as {"principal": f.ty_growth_mgr, "action": {"class": "A2", "name": "knowledge.approve", "company": "TY"}, "context": {"company_locked": false}}
	not actions.allow with input as {"principal": f.ty_ceo, "action": {"class": "A2", "name": "knowledge.approve", "company": "TY"}, "context": {"company_locked": true}}
}

test_charter_amendments_are_proposed_by_the_ceo_the_overseer_and_the_advisor if {
	allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "charter_amendment"})
	allowed(f.hq_ovr, "decision.propose", {"company": "HQ", "kind": "charter_amendment"})
	allowed(f.hq_adv, "decision.propose", {"company": "HQ", "kind": "charter_amendment"})
	not allowed(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "charter_amendment"})
	not allowed(ty_sales, "decision.propose", {"company": "TY", "kind": "charter_amendment"})
	not allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "meeting_resolution"})
	not allowed(f.hq_ovr, "decision.propose", {"company": "HQ", "kind": "knowledge_entry"})
}

test_the_new_cards_are_the_owners if {
	some kind in {"meeting_resolution", "charter_amendment", "knowledge_entry"}
	decisions.allow with input as {"principal": f.owner, "decision": {"kind": kind, "company": "TY", "action_class": "A1", "proposer": {"kind": "agent", "code": "TY-CEO"}}, "context": {}}
	not decisions.allow with input as {"principal": f.ty_ceo, "decision": {"kind": kind, "company": "TY", "action_class": "A1", "proposer": {"kind": "agent", "code": "TY-GROWTH-MGR"}}, "context": {}}
}
