package hq.advisor_substitutes_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

ty_cto := {"kind": "agent", "code": "TY-TECH-MGR", "role": "manager", "company": "TY", "department": "TECH"}

ty_dev := {"kind": "agent", "code": "TY-TECH-01", "role": "employee", "company": "TY", "department": "TECH"}

dispatcher := {"kind": "service", "code": "substitutes", "role": "service", "company": null, "department": null}

seat(c, s, charter) := {"company": c, "seat": s, "charter": charter}

test_memo_write_is_the_advisors if {
	allowed(f.hq_adv, "memo.write", {"decision": "D-000001", "charter": "advisor"})
	not allowed(f.hq_adv, "memo.write", {"decision": "D-000001", "charter": "assistant"})
	not allowed(f.hq_pa, "memo.write", {"decision": "D-000001", "charter": "assistant"})
	not allowed(f.hq_ovr, "memo.write", {"decision": "D-000001", "charter": "overseer"})
	not allowed(f.ty_ceo, "memo.write", {"decision": "D-000001", "charter": "advisor"})
	not allowed(f.owner, "memo.write", {"decision": "D-000001", "charter": "advisor"})
	not allowed(dispatcher, "memo.write", {"decision": "D-000001"})
}

test_substitute_seats_by_role if {
	allowed(f.hq_adv, "substitute.call", seat("HQ", "quick_search", "advisor"))
	allowed(f.hq_adv, "substitute.call", seat("HQ", "code_review", "advisor"))
	not allowed(f.hq_adv, "substitute.call", seat("HQ", "creative", "advisor"))
	allowed(f.hq_ovr, "substitute.call", seat("HQ", "overseer_cross_check", "overseer"))
	not allowed(f.hq_ovr, "substitute.call", seat("HQ", "assistant_errand", "overseer"))
	allowed(f.hq_pa, "substitute.call", seat("HQ", "assistant_errand", "assistant"))
	allowed(f.hq_pa, "substitute.call", seat("HQ", "creative", "assistant"))
	allowed(f.ty_ceo, "substitute.call", seat("TY", "content_draft", "ceo"))
	allowed(f.ty_ceo, "substitute.call", seat("TY", "creative", "ceo"))
	not allowed(f.ty_ceo, "substitute.call", seat("FX", "content_draft", "ceo"))
	not allowed(f.ty_ceo, "substitute.call", seat("TY", "overseer_cross_check", "ceo"))
}

test_a_cto_and_qc_ask_only_for_a_code_review if {
	allowed(ty_cto, "substitute.call", seat("TY", "code_review", "cto"))
	not allowed(ty_cto, "substitute.call", seat("TY", "content_draft", "cto"))
	not allowed(ty_cto, "substitute.call", seat("FX", "code_review", "cto"))
	allowed(f.hq_ovs, "substitute.call", seat("HQ", "code_review", "inspector"))
	not allowed(f.hq_ovs, "substitute.call", seat("HQ", "long_read", "inspector"))
	not allowed(ty_dev, "substitute.call", seat("TY", "code_review", "sre"))
	not allowed(f.ty_growth_01, "substitute.call", seat("TY", "content_draft", "growth"))
	not allowed(f.owner, "substitute.call", seat("HQ", "quick_search", "advisor"))
}

test_the_job_queue_is_the_dispatchers if {
	allowed(dispatcher, "substitutes.jobs", {})
	not allowed(f.svc, "substitutes.jobs", {})
	not allowed(f.hq_adv, "substitutes.jobs", {})
	not allowed(f.owner, "substitutes.jobs", {})
}
