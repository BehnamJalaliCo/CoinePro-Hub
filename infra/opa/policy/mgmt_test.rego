package hq.mgmt_test

import data.hq.actions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

acts(p, name) if actions.allow with input as {
	"principal": p,
	"action": {"class": "A2", "name": name, "company": p.company},
	"context": {"escrow_classes": [], "company_locked": false},
}

tts := {"kind": "service", "code": "tts", "role": "service", "company": null, "department": null}

hq_aiops := {"kind": "agent", "code": "HQ-AIOPS-MGR", "role": "manager", "company": "HQ", "department": "AIOPS", "scope": "holding"}

ty_aiops := {"kind": "agent", "code": "TY-AIOPS-MGR", "role": "manager", "company": "TY", "department": "AIOPS"}

test_claims_are_checked_by_the_fact_checker_the_overseer_and_qc if {
	allowed(f.hq_ovs_01, "claim.verdict", {"company": "HQ", "charter": "fact_checker"})
	allowed(f.hq_ovr, "claim.verdict", {"company": "HQ", "charter": "overseer"})
	allowed(f.hq_ovs, "claim.verdict", {"company": "HQ", "charter": "inspector"})
	not allowed(f.hq_ovs_01, "claim.verdict", {"company": "HQ", "charter": "ai_safety"})
	not allowed(f.ty_growth_01, "claim.verdict", {"company": "TY", "charter": "fact_checker"})
	not allowed(f.ty_ceo, "claim.verdict", {"company": "TY", "charter": "ceo"})
	not allowed(f.owner, "claim.verdict", {"company": "TY"})
}

test_claim_verdict_is_an_a2_grant_of_the_checkers if {
	acts(f.hq_ovr, "claim.verdict")
	acts(f.hq_ovs, "claim.verdict")
	acts(f.hq_ovs_01, "claim.verdict")
}

test_only_the_tts_service_claims_and_finishes if {
	allowed(tts, "tts.claim", {})
	allowed(tts, "tts.done", {})
	not allowed(f.svc, "tts.claim", {})
	not allowed(f.hq_ovr, "tts.done", {"company": "HQ"})
}

test_the_holding_ai_ops_head_proposes_evaluations if {
	allowed(hq_aiops, "decision.propose", {"company": "HQ", "kind": "evaluation"})
	not allowed(ty_aiops, "decision.propose", {"company": "TY", "kind": "evaluation"})
}
