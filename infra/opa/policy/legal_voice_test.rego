package hq.legal_voice_test

import data.hq.actions
import data.hq.decisions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

acts(p, name, cls) if actions.allow with input as {
	"principal": p,
	"action": {"class": cls, "name": name, "company": p.company},
	"context": {"escrow_classes": [], "company_locked": false},
}

hq_lgl := {"kind": "agent", "code": "HQ-LGL", "role": "employee", "company": "HQ", "department": "LEGAL", "scope": "holding"}

ty_voice := {"kind": "agent", "code": "TY-MEDIA-01", "role": "employee", "company": "TY", "department": "MEDIA"}

tts := {"kind": "service", "code": "tts", "role": "service", "company": null, "department": null}

test_only_the_holding_counsel_has_the_legal_tools if {
	every op in policy.legal_ops {
		allowed(hq_lgl, op, {"company": "HQ", "charter": "legal_counsel"})
		not allowed(f.ty_growth_01, op, {"company": "TY", "charter": "legal_counsel"})
		not allowed(f.hq_pa, op, {"company": "HQ", "charter": "assistant"})
		not allowed(f.owner, op, {"company": "HQ"})
	}
	acts(hq_lgl, "legal.email_draft", "A1")
}

test_media_voice_is_the_voice_producers_in_its_own_company if {
	allowed(ty_voice, "media.voice", {"company": "TY", "charter": "voice_producer"})
	not allowed(ty_voice, "media.voice", {"company": "FX", "charter": "voice_producer"})
	not allowed(f.ty_growth_01, "media.voice", {"company": "TY", "charter": "sre"})
	acts(ty_voice, "media.voice", "A2")
}

test_only_the_tts_service_takes_voice_jobs if {
	allowed(tts, "voices.claim", {})
	allowed(tts, "voices.done", {})
	not allowed(f.svc, "voices.claim", {})
	not allowed(hq_lgl, "voices.done", {"company": "HQ"})
}

test_thread_l_is_its_counsels if {
	allowed(hq_lgl, "message.post", {"thread_code": "L", "thread_kind": "legal", "thread_company": "HQ", "thread_employee": "HQ-LGL"})
	not allowed(f.hq_pa, "message.post", {"thread_code": "L", "thread_kind": "legal", "thread_company": "HQ", "thread_employee": "HQ-LGL"})
}

test_a_ceo_asks_the_holdings_counsel if {
	allowed(f.ty_ceo, "work.create", {"company": "HQ", "kind": "one_off", "to_role": "employee", "to_department": "LEGAL", "to_holding": true})
	not allowed(f.ty_ceo, "work.create", {"company": "FX", "kind": "one_off", "to_role": "employee", "to_department": "LEGAL", "to_holding": false})
	not allowed(f.ty_growth_mgr, "work.create", {"company": "HQ", "kind": "one_off", "to_role": "employee", "to_department": "LEGAL", "to_holding": true})
}

test_an_email_card_is_the_owners_seal if {
	decisions.allow with input as {"principal": f.owner, "decision": {"kind": "email_send", "company": "TY", "action_class": "A3", "proposer": {"kind": "agent", "code": "HQ-LGL"}}}
	not decisions.allow with input as {"principal": f.ty_ceo, "decision": {"kind": "email_send", "company": "TY", "action_class": "A3", "proposer": {"kind": "agent", "code": "HQ-LGL"}}}
}
