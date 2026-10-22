package hq.support_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

ty_support := {"kind": "agent", "code": "TY-SALES-01", "role": "employee", "company": "TY", "department": "SALES"}

fx_support := {"kind": "agent", "code": "FX-SALES-01", "role": "employee", "company": "FX", "department": "SALES"}

ty_sales_mgr := {"kind": "agent", "code": "TY-SALES-MGR", "role": "manager", "company": "TY", "department": "SALES"}

ty_fin_mgr := {"kind": "agent", "code": "TY-FIN-MGR", "role": "manager", "company": "TY", "department": "FIN"}

ty_fin_01 := {"kind": "agent", "code": "TY-FIN-01", "role": "employee", "company": "TY", "department": "FIN"}

ty := {"company": "TY"}

fx := {"company": "FX"}

as_charter(t, c) := object.union(t, {"charter": c})

test_conversations_stay_with_the_company_support_people if {
	every c in ["support_lead", "support_agent", "referral_rescue"] {
		allowed(ty_support, "support.read", as_charter(ty, c))
		not allowed(ty_support, "support.read", as_charter(fx, c))
		not allowed(fx_support, "support.read", as_charter(ty, c))
	}
	allowed(ty_sales_mgr, "support.read", as_charter(ty, "manager"))
	not allowed(ty_sales_mgr, "support.read", as_charter(fx, "manager"))
	not allowed(ty_support, "support.read", as_charter(ty, "content_writer"))
	not allowed(f.ty_growth_mgr, "support.read", as_charter(ty, "manager"))
	not allowed(f.ty_ceo, "support.read", as_charter(ty, "ceo"))
	not allowed(f.hq_adv, "support.read", as_charter(ty, "advisor"))
	not allowed(f.hq_ovr, "support.read", as_charter(ty, "overseer"))
	not allowed(f.owner, "support.read", ty)
	not allowed(f.svc, "support.read", ty)
}

test_statistics_for_the_ceo_and_the_holding_readers if {
	allowed(f.ty_ceo, "support.stats", ty)
	not allowed(f.ty_ceo, "support.stats", fx)
	allowed(f.hq_adv, "support.stats", ty)
	allowed(f.hq_ovr, "support.stats", fx)
	not allowed(f.hq_adv, "support.stats", {"company": null})
	allowed(ty_support, "support.stats", as_charter(ty, "support_lead"))
	allowed(ty_sales_mgr, "support.stats", ty)
	not allowed(f.ty_growth_mgr, "support.stats", ty)
	not allowed(f.hq_pa, "support.stats", ty)
	not allowed(f.hq_ovs_01, "support.stats", ty)
}

test_approved_articles_for_the_whole_company_proposed_for_support if {
	allowed(f.ty_growth_01, "kb.read", {"company": "TY", "status": "approved"})
	allowed(f.ty_ceo, "kb.read", {"company": "TY", "status": "approved"})
	not allowed(f.ty_growth_01, "kb.read", {"company": "FX", "status": "approved"})
	not allowed(f.ty_growth_01, "kb.read", {"company": "TY", "status": "proposed"})
	allowed(ty_support, "kb.read", {"company": "TY", "status": "proposed", "charter": "support_lead"})
	allowed(ty_sales_mgr, "kb.read", {"company": "TY", "status": "proposed"})
	not allowed(fx_support, "kb.read", {"company": "TY", "status": "approved", "charter": "support_agent"})
	not allowed(f.hq_adv, "kb.read", {"company": "TY", "status": "approved"})
}

test_the_radar_and_the_funnel if {
	every op in ["revenue.read", "funnel.read"] {
		allowed(f.ty_ceo, op, ty)
		not allowed(f.ty_ceo, op, fx)
		allowed(ty_fin_mgr, op, ty)
		allowed(ty_sales_mgr, op, ty)
		allowed(ty_fin_01, op, as_charter(ty, "revenue_analyst"))
		not allowed(ty_fin_01, op, as_charter(fx, "revenue_analyst"))
		not allowed(ty_fin_01, op, as_charter(ty, "bookkeeper"))
		allowed(f.hq_adv, op, fx)
		allowed(f.hq_ovr, op, ty)
		not allowed(f.ty_growth_mgr, op, ty)
		not allowed(f.hq_pa, op, ty)
	}
	allowed(ty_support, "funnel.read", as_charter(ty, "referral_rescue"))
	not allowed(ty_support, "revenue.read", as_charter(ty, "referral_rescue"))
}

test_an_inactive_support_agent_reads_nothing if {
	not allowed(f.paused(ty_support), "support.read", as_charter(ty, "support_agent"))
	not allowed(f.dismissed(ty_sales_mgr), "kb.read", {"company": "TY", "status": "approved"})
}
