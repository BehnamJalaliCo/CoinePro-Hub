package hq.roles_test

import data.hq.actions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

acts(p, cls, name) if actions.allow with input as {
	"principal": p,
	"action": {"class": cls, "name": name, "company": p.company},
	"context": {"escrow_classes": [], "company_locked": false},
}

test_a_department_head_writes_roles_of_its_own_department_only if {
	allowed(f.ty_growth_mgr, "role.draft", {"company": "TY", "department": "GROWTH"})
	allowed(f.hq_ovs, "role.draft", {"company": "HQ", "department": "OVS"})
	not allowed(f.ty_growth_mgr, "role.draft", {"company": "TY", "department": "HR"})
	not allowed(f.ty_growth_mgr, "role.draft", {"company": "FX", "department": "GROWTH"})
	not allowed(f.ty_growth_01, "role.draft", {"company": "TY", "department": "GROWTH"})
	not allowed(f.ty_ceo, "role.draft", {"company": "TY", "department": "GROWTH"})
	not allowed(f.owner, "role.draft", {"company": "TY", "department": "GROWTH"})
	not allowed(f.svc, "role.draft", {"company": "TY", "department": "GROWTH"})
}

test_a_ceo_decides_drafts_of_its_own_company_only if {
	allowed(f.ty_ceo, "role.decide", {"company": "TY"})
	not allowed(f.ty_ceo, "role.decide", {"company": "FX"})
	not allowed(f.fx_ceo, "role.decide", {"company": "TY"})
	not allowed(f.ty_growth_mgr, "role.decide", {"company": "TY"})
	not allowed(f.hq_ovr, "role.decide", {"company": "HQ"})
}

test_role_decide_is_a_ceos_a2_grant_and_role_draft_is_a1 if {
	acts(f.ty_ceo, "A2", "role.decide")
	not acts(f.ty_growth_mgr, "A2", "role.decide")
	acts(f.ty_growth_mgr, "A1", "role.draft")
}
