package hq.people_test

import data.hq.actions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

hq_aiops := {
	"kind": "agent", "code": "HQ-AIOPS-MGR", "role": "manager", "company": "HQ",
	"department": "AIOPS", "scope": "holding",
}

test_ceos_write_rubrics_and_give_stars_in_their_company_only if {
	every op in ["star.rubric", "star.give"] {
		allowed(f.ty_ceo, op, {"company": "TY"})
		not allowed(f.ty_ceo, op, {"company": "FX"})
		not allowed(f.ty_growth_mgr, op, {"company": "TY"})
		not allowed(f.hq_ovr, op, {"company": "HQ"})
	}
}

test_only_the_overseer_audits_stars if {
	allowed(f.hq_ovr, "star.audit", {"company": null})
	not allowed(f.ty_ceo, "star.audit", {"company": "TY"})
	not allowed(f.hq_adv, "star.audit", {"company": null})
}

test_lessons_from_the_overseer_and_the_ai_ops_head if {
	allowed(f.hq_ovr, "lesson.write", {"company": "TY", "charter": "overseer"})
	allowed(hq_aiops, "lesson.write", {"company": "TY", "charter": "aiops_head"})
	not allowed(hq_aiops, "lesson.write", {"company": "TY", "charter": "manager"})
	not allowed(f.ty_ceo, "lesson.write", {"company": "TY", "charter": "ceo"})
}

test_stories_by_ceos_and_holding_heads if {
	allowed(f.ty_ceo, "story.post", {"company": "TY"})
	not allowed(f.ty_ceo, "story.post", {"company": "FX"})
	allowed(f.hq_ovs, "story.post", {"company": "HQ"})
	allowed(f.hq_ovr, "story.post", {"company": "HQ"})
	not allowed(f.ty_growth_mgr, "story.post", {"company": "TY"})
	not allowed(f.hq_pa, "story.post", {"company": "HQ"})
}

test_a_ceo_decides_only_the_cards_it_approves if {
	allowed(f.ty_ceo, "hire.decide", {"company": "TY", "approver": "TY-CEO"})
	not allowed(f.fx_ceo, "hire.decide", {"company": "TY", "approver": "TY-CEO"})
	not allowed(f.ty_ceo, "hire.decide", {"company": "TY", "approver": null})
	not allowed(f.ty_growth_mgr, "hire.decide", {"company": "TY", "approver": "TY-GROWTH-MGR"})
}

test_the_new_a2_actions_are_granted_to_their_roles if {
	every name in ["star.rubric", "star.give", "hire.decide"] {
		actions.allow with input as {
			"principal": f.ty_ceo,
			"action": {"class": "A2", "name": name, "company": "TY"},
			"context": {"company_locked": false},
		}
	}
	actions.allow with input as {
		"principal": f.hq_ovr,
		"action": {"class": "A2", "name": "star.audit", "company": "HQ"},
		"context": {"company_locked": false},
	}
	not actions.allow with input as {
		"principal": f.ty_growth_mgr,
		"action": {"class": "A2", "name": "star.give", "company": "TY"},
		"context": {"company_locked": false},
	}
}
