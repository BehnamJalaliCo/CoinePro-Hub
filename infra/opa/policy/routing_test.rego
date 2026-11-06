package hq.internal_test

import data.hq.fixtures_test as f
import data.hq.internal
import rego.v1

ty_cto := {"kind": "agent", "code": "TY-TECH-MGR", "role": "manager", "company": "TY", "department": "TECH", "status": "active"}

r21(p, op, t) if internal.allow with input as {"principal": p, "op": op, "target": t}

test_the_assignee_acks_and_reports_its_order if {
	r21(f.ty_ceo, "order.ack", {"company": "TY", "assigned": true})
	r21(f.ty_growth_mgr, "order.progress", {"company": "TY", "assigned": true})
	r21(f.ty_ceo, "order.ask", {"company": "TY", "assigned": true})
	not r21(f.ty_ceo, "order.ask", {"company": "TY", "assigned": false})
	not r21(f.ty_ceo, "order.ack", {"company": "TY", "assigned": false})
	not r21(f.ty_ceo, "order.ack", {"company": "FX", "assigned": true})
	not r21(f.svc, "order.progress", {"company": "TY", "assigned": true})
}

test_only_a_ceo_adds_budget_in_its_company if {
	r21(f.ty_ceo, "work.budget", {"company": "TY", "role": "ceo"})
	not r21(f.ty_ceo, "work.budget", {"company": "FX", "role": "ceo"})
	not r21(f.ty_growth_mgr, "work.budget", {"company": "TY", "role": "manager"})
}

test_only_the_named_approver_decides_a_card if {
	r21(ty_cto, "card.decide", {"company": "TY", "approver": "TY-TECH-MGR", "kind": "server_destructive"})
	not r21(f.ty_ceo, "card.decide", {"company": "TY", "approver": "TY-TECH-MGR", "kind": "server_destructive"})
	not r21(ty_cto, "card.decide", {"company": "TY", "approver": null, "kind": "server_destructive"})
	not r21(ty_cto, "card.decide", {"company": "FX", "approver": "TY-TECH-MGR", "kind": "server_destructive"})
}

test_a_ceo_or_a_manager_proposes_an_automation if {
	r21(f.ty_ceo, "automation.propose", {"company": "TY"})
	r21(f.ty_growth_mgr, "automation.propose", {"company": "TY"})
	not r21(f.ty_growth_01, "automation.propose", {"company": "TY"})
	not r21(f.ty_ceo, "automation.propose", {"company": "FX"})
	not r21(f.svc, "automation.propose", {"company": "TY"})
}
