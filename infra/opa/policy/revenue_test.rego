package hq.revenue_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

ty_sales := {"kind": "agent", "code": "TY-SALES-01", "role": "employee", "company": "TY", "department": "SALES"}

fx_sales := {"kind": "agent", "code": "FX-SALES-01", "role": "employee", "company": "FX", "department": "SALES"}

ty_product_mgr := {"kind": "agent", "code": "TY-PRODUCT-MGR", "role": "manager", "company": "TY", "department": "PRODUCT"}

worker := {"kind": "service", "code": "worker", "role": "service", "company": null, "department": null}

as_charter(c, charter) := {"company": c, "charter": charter}

test_only_the_workers_token_reaches_a_connector if {
	allowed(worker, "egress.connector", {"company": "TY", "adapter": "lbank-affiliate-v2"})
	not allowed(f.svc, "egress.connector", {"company": "TY"})
	not allowed(f.ty_ceo, "egress.connector", {"company": "TY"})
	not allowed(f.owner, "egress.connector", {"company": "TY"})
	not allowed(ty_sales, "egress.connector", as_charter("TY", "support_agent"))
}

test_referral_check_for_the_support_agent_and_the_rescue_specialist if {
	allowed(ty_sales, "referral.check", as_charter("TY", "support_agent"))
	allowed(ty_sales, "referral.check", as_charter("TY", "referral_rescue"))
	not allowed(ty_sales, "referral.check", as_charter("FX", "support_agent"))
	not allowed(fx_sales, "referral.check", as_charter("TY", "referral_rescue"))
	not allowed(ty_sales, "referral.check", as_charter("TY", "support_lead"))
	not allowed(f.ty_ceo, "referral.check", as_charter("TY", "ceo"))
	not allowed(worker, "referral.check", as_charter("TY", "support_agent"))
}

test_rescue_update_is_the_specialists if {
	allowed(ty_sales, "rescue.update", as_charter("TY", "referral_rescue"))
	not allowed(ty_sales, "rescue.update", as_charter("FX", "referral_rescue"))
	not allowed(ty_sales, "rescue.update", as_charter("TY", "support_agent"))
	not allowed(f.ty_ceo, "rescue.update", as_charter("TY", "ceo"))
}

test_feedback_tag_for_the_support_lead_and_the_product_manager if {
	allowed(ty_sales, "feedback.tag", as_charter("TY", "support_lead"))
	not allowed(ty_sales, "feedback.tag", as_charter("TY", "support_agent"))
	not allowed(ty_sales, "feedback.tag", as_charter("FX", "support_lead"))
	allowed(ty_product_mgr, "feedback.tag", as_charter("TY", "manager"))
	not allowed(ty_product_mgr, "feedback.tag", as_charter("FX", "manager"))
	not allowed(f.ty_growth_mgr, "feedback.tag", as_charter("TY", "manager"))
	not allowed(f.ty_ceo, "feedback.tag", as_charter("TY", "ceo"))
}
