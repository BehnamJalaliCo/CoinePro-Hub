package hq.owner_tools_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

reasons(p, op, t) := r if {
	r := policy.deny_reasons with input as {"principal": p, "op": op, "target": t}
}

hq_lib := {"kind": "agent", "code": "HQ-LIB", "role": "system", "company": "HQ", "department": null, "scope": "holding"}

hq_sec := {"kind": "agent", "code": "HQ-SEC", "role": "system", "company": "HQ", "department": "AIOPS", "scope": "holding"}

ty_cto := {"kind": "agent", "code": "TY-TECH-MGR", "role": "manager", "company": "TY", "department": "TECH"}

dceo := {"kind": "service", "code": "dceo", "role": "service", "company": null, "department": null}

test_only_the_librarian_answers_an_ask if {
	allowed(hq_lib, "ask.answer", {"ask": "AK-0001", "charter": "librarian"})
	not allowed(hq_sec, "ask.answer", {"ask": "AK-0001", "charter": "secretary"})
	not allowed(f.hq_adv, "ask.answer", {"ask": "AK-0001", "charter": "advisor"})
	not allowed(f.ty_ceo, "ask.answer", {"ask": "AK-0001", "charter": "librarian"})
	not allowed(f.svc, "ask.answer", {"ask": "AK-0001"})
}

test_the_digital_ceo_writes_only_its_own_rows if {
	allowed(dceo, "dceo.predict", {"decision": "D-000001", "method": "model"})
	allowed(dceo, "dceo.principles", {"week": "2026-10-24"})
	not allowed(f.svc, "dceo.predict", {"decision": "D-000001"})
	not allowed(f.hq_adv, "dceo.predict", {"decision": "D-000001"})
}

test_the_digital_ceo_never_acts if {
	"dceo_never_acts" in reasons(dceo, "decision.approve", {"company": "TY"})
	not allowed(dceo, "decision.approve", {"company": "TY"})
	"dceo_never_acts" in reasons(dceo, "notification.raise", {"company": "HQ", "level": "report"})
	not allowed(dceo, "notification.raise", {"company": "HQ", "level": "report"})
	not allowed(dceo, "context.read", {"employee": "HQ-ADV"})
	not allowed(dceo, "message.post", {"company": "HQ"})
	not "dceo_never_acts" in reasons(dceo, "dceo.predict", {"decision": "D-000001"})
}

test_docs_and_code_are_for_the_advisor_the_overseer_the_librarian_and_a_cto if {
	allowed(f.hq_adv, "knowledge.read", {"company": "HQ", "kinds": ["docs", "code"], "charter": "advisor"})
	allowed(f.hq_ovr, "knowledge.read", {"company": "TY", "kinds": ["code"], "charter": "overseer"})
	allowed(hq_lib, "knowledge.read", {"company": "HQ", "kinds": ["docs", "code"], "charter": "librarian"})
	allowed(ty_cto, "knowledge.read", {"company": "TY", "kinds": ["code"], "charter": "cto"})
	not allowed(ty_cto, "knowledge.read", {"company": "FX", "kinds": ["code"], "charter": "cto"})
	not allowed(f.ty_ceo, "knowledge.read", {"company": "TY", "kinds": ["code"], "charter": "ceo"})
	not allowed(f.ty_growth_01, "knowledge.read", {"company": "TY", "kinds": ["docs"], "charter": "marketer"})
}

test_notes_and_messages_are_the_advisors_only if {
	allowed(f.hq_adv, "knowledge.read", {"company": "HQ", "kinds": ["notes", "messages"], "charter": "advisor"})
	not allowed(hq_lib, "knowledge.read", {"company": "HQ", "kinds": ["notes"], "charter": "librarian"})
	not allowed(hq_lib, "knowledge.read", {"company": "HQ", "kinds": ["messages"], "charter": "librarian"})
	not allowed(f.hq_ovr, "knowledge.read", {"company": "HQ", "kinds": ["notes"], "charter": "overseer"})
	allowed(f.ty_ceo, "knowledge.read", {"company": "TY", "kinds": ["decisions", "work"], "charter": "ceo"})
}
