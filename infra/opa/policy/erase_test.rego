package hq.internal_test

import data.hq.decisions
import data.hq.fixtures_test as f
import data.hq.internal
import rego.v1

hq_arc := {"kind": "agent", "code": "HQ-ARC", "role": "system", "company": "HQ", "department": null, "scope": "holding"}

erase(p, t) if internal.allow with input as {"principal": p, "op": "erase.propose", "target": t}

test_a_working_role_proposes_what_it_can_read if {
	erase(f.ty_ceo, {"company": "TY", "kind": "session", "readable": true})
	erase(f.ty_growth_mgr, {"company": "TY", "kind": "output", "readable": true})
	erase(f.ty_growth_01, {"company": "TY", "kind": "archive_record", "readable": true})
}

test_never_what_it_cannot_read if {
	not erase(f.ty_ceo, {"company": "TY", "kind": "session", "readable": false})
	not erase(f.ty_ceo, {"company": "TY", "kind": "output"})
	not erase(f.ty_ceo, {"company": "FX", "kind": "output", "readable": true})
	not erase(f.ty_ceo, {"company": null, "kind": "session", "readable": true})
}

test_a_holding_scope_role_reads_every_company if {
	erase(f.hq_ovr, {"company": "FX", "kind": "output", "readable": true})
	erase(f.hq_adv, {"company": null, "kind": "session", "readable": true})
	not erase(f.hq_ovr, {"company": "FX", "kind": "output", "readable": false})
}

test_only_the_three_kinds_and_never_a_system_role_or_a_service if {
	not erase(f.ty_ceo, {"company": "TY", "kind": "company", "readable": true})
	not erase(hq_arc, {"company": "HQ", "kind": "archive_record", "readable": true})
	not erase(f.svc, {"company": "TY", "kind": "session", "readable": true})
	not erase(f.owner, {"company": "TY", "kind": "session", "readable": true})
	not erase(f.paused(f.ty_ceo), {"company": "TY", "kind": "session", "readable": true})
}

test_only_the_owner_seals_an_erase_card if {
	card := {"kind": "erase", "company": "TY", "action_class": "A3", "proposer": {"kind": "agent", "code": "TY-CEO"}}
	decisions.allow with input as {"principal": f.owner, "decision": card}
	not decisions.allow with input as {"principal": f.ty_ceo, "decision": card}
	not decisions.allow with input as {"principal": f.fx_ceo, "decision": card}
	not decisions.allow with input as {"principal": f.svc, "decision": card}
}
