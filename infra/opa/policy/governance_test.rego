package hq.governance_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

ty := {"company": "TY"}

fx := {"company": "FX"}

ty_tech_mgr := {"kind": "agent", "code": "TY-TECH-MGR", "role": "manager", "company": "TY", "department": "TECH"}

hq_aiops := {"kind": "agent", "code": "HQ-AIOPS-MGR", "role": "manager", "company": "HQ", "department": "AIOPS", "scope": "holding"}

test_kpi_record_and_checkins_are_the_companys_leaders if {
	every op in {"kpi.record", "okr.checkin"} {
		allowed(f.ty_ceo, op, ty)
		allowed(f.ty_growth_mgr, op, ty)
		not allowed(f.fx_ceo, op, ty)
		not allowed(f.ty_growth_01, op, ty)
		not allowed(f.owner, op, ty)
	}
}

test_only_the_ceo_drafts_its_okrs if {
	allowed(f.ty_ceo, "okr.draft", ty)
	not allowed(f.fx_ceo, "okr.draft", ty)
	not allowed(f.ty_growth_mgr, "okr.draft", ty)
}

test_the_proposer_notes_its_outcome if {
	allowed(f.ty_ceo, "outcome.note", {"company": "TY", "proposer": "TY-CEO"})
	not allowed(f.ty_ceo, "outcome.note", {"company": "TY", "proposer": "TY-GROWTH-MGR"})
	not allowed(f.fx_ceo, "outcome.note", {"company": "TY", "proposer": "FX-CEO"})
}

test_reads_and_risks_of_ones_own_company_or_a_holding_role if {
	every op in {"risk.raise", "calendar.read", "governance.read"} {
		allowed(f.ty_ceo, op, ty)
		not allowed(f.fx_ceo, op, ty)
		allowed(f.hq_ovs, op, fx)
		allowed(f.hq_ovr, op, ty)
	}
}

test_risk_update_is_the_owners_or_the_keepers if {
	allowed(f.ty_growth_mgr, "risk.update", {"company": "TY", "owner": "TY-GROWTH-MGR"})
	not allowed(f.ty_ceo, "risk.update", {"company": "TY", "owner": "TY-GROWTH-MGR"})
	not allowed(f.fx_ceo, "risk.update", {"company": "TY", "owner": "FX-CEO"})
	allowed(f.hq_ovs, "risk.update", {"company": "FX", "owner": "FX-CEO"})
	not allowed(f.hq_ovr, "risk.update", {"company": "FX", "owner": "FX-CEO"})
}

test_calendar_add_for_ones_own_company if {
	allowed(f.ty_ceo, "calendar.add", ty)
	allowed(f.ty_growth_mgr, "calendar.add", ty)
	not allowed(ty_tech_mgr, "calendar.add", ty)
	not allowed(f.ty_ceo, "calendar.add", fx)
	not allowed(f.ty_growth_mgr, "calendar.add", fx)
	allowed(hq_aiops, "calendar.add", fx)
	not allowed(f.hq_ovr, "calendar.add", fx)
}

test_authority_read_for_agents_only if {
	allowed(f.ty_growth_01, "authority.read", ty)
	not allowed(f.svc, "authority.read", ty)
	not allowed(f.owner, "authority.read", {})
}
