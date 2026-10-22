package hq.support_desk_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

ty_support := {"kind": "agent", "code": "TY-SALES-01", "role": "employee", "company": "TY", "department": "SALES"}

ty_sales_mgr := {"kind": "agent", "code": "TY-SALES-MGR", "role": "manager", "company": "TY", "department": "SALES"}

test_only_the_support_agent_drafts_in_its_own_company if {
	allowed(ty_support, "support.draft", {"company": "TY", "charter": "support_agent"})
	not allowed(ty_support, "support.draft", {"company": "FX", "charter": "support_agent"})
	not allowed(ty_support, "support.draft", {"company": "TY", "charter": "support_lead"})
	not allowed(ty_support, "support.draft", {"company": "TY", "charter": "referral_rescue"})
	not allowed(ty_sales_mgr, "support.draft", {"company": "TY", "charter": "manager"})
	not allowed(f.ty_ceo, "support.draft", {"company": "TY", "charter": "ceo"})
	not allowed(f.owner, "support.draft", {"company": "TY"})
	not allowed(f.svc, "support.draft", {"company": "TY"})
}

test_proposals_and_handoffs_for_the_support_people if {
	every op in ["kb.propose", "support.handoff"] {
		allowed(ty_support, op, {"company": "TY", "charter": "support_lead"})
		allowed(ty_support, op, {"company": "TY", "charter": "support_agent"})
		not allowed(ty_support, op, {"company": "FX", "charter": "support_lead"})
		not allowed(ty_support, op, {"company": "TY", "charter": "referral_rescue"})
		not allowed(f.ty_growth_01, op, {"company": "TY", "charter": "content_writer"})
		not allowed(f.hq_ovr, op, {"company": "TY", "charter": "overseer"})
	}
}

test_the_mystery_customer_is_the_overseers if {
	allowed(f.hq_ovr, "support.mystery", {"company": "TY", "charter": "overseer"})
	allowed(f.hq_ovr, "support.mystery", {"company": "FX", "charter": "overseer"})
	not allowed(f.hq_ovr, "support.mystery", {"company": null, "charter": "overseer"})
	not allowed(f.hq_adv, "support.mystery", {"company": "TY", "charter": "advisor"})
	not allowed(ty_support, "support.mystery", {"company": "TY", "charter": "support_agent"})
	not allowed(f.ty_ceo, "support.mystery", {"company": "TY", "charter": "ceo"})
	not allowed(f.owner, "support.mystery", {"company": "TY"})
}
