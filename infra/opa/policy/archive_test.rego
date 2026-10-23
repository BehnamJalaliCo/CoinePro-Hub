package hq.archive_test

import data.hq.actions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

acts(p, name, cls) if actions.allow with input as {
	"principal": p,
	"action": {"class": cls, "name": name, "company": p.company},
	"context": {"escrow_classes": [], "company_locked": false},
}

hq_arc := {"kind": "agent", "code": "HQ-ARC", "role": "system", "company": "HQ", "department": null, "scope": "holding"}

hq_lgl := {"kind": "agent", "code": "HQ-LGL", "role": "employee", "company": "HQ", "department": "LEGAL", "scope": "holding"}

arc := {"company": "HQ", "charter": "archivist"}

lgl := {"company": "HQ", "charter": "legal_counsel"}

test_the_archivist_and_the_counsel_search_read_file_and_link if {
	every op in policy.archive_ops {
		allowed(hq_arc, op, object.union(arc, {"scope": "TY", "ref": "AR-000001"}))
		allowed(hq_lgl, op, object.union(lgl, {"scope": "HQ", "ref": "AR-000001"}))
	}
	acts(hq_arc, "archive.search", "A0")
	acts(hq_arc, "archive.file", "A1")
	acts(hq_lgl, "archive.link", "A1")
}

test_nobody_else_reaches_the_archive_tools if {
	every op in policy.archive_ops {
		# a company's CEO, manager or employee, even with a borrowed charter name
		not allowed(f.ty_ceo, op, {"company": "TY", "charter": "ceo"})
		not allowed(f.ty_growth_mgr, op, {"company": "TY", "charter": "manager"})
		not allowed(f.ty_growth_01, op, {"company": "TY", "charter": "archivist"})

		# another holding role
		not allowed(f.hq_pa, op, {"company": "HQ", "charter": "assistant"})
		not allowed(f.hq_ovr, op, {"company": "HQ", "charter": "overseer"})

		# a service, the owner on the internal API
		not allowed(f.svc, op, {"charter": "archivist"})
		not allowed(f.owner, op, {"company": "HQ", "charter": "archivist"})
	}
}

test_only_the_counsel_holds_and_only_with_its_case if {
	allowed(hq_lgl, "archive.hold", object.union(lgl, {"case": "LC-0001"}))
	acts(hq_lgl, "archive.hold", "A2")
	not allowed(hq_lgl, "archive.hold", lgl)
	not allowed(hq_lgl, "archive.hold", object.union(lgl, {"case": "D-000001"}))
	not allowed(hq_lgl, "archive.hold", object.union(lgl, {"case": 7}))

	# the archivist never holds (nor releases: there is no release op at all)
	not allowed(hq_arc, "archive.hold", object.union(arc, {"case": "LC-0001"}))
	not acts(hq_arc, "archive.hold", "A2")
	not allowed(f.ty_ceo, "archive.hold", {"company": "TY", "charter": "legal_counsel", "case": "LC-0001"})
	not allowed(f.svc, "archive.hold", {"charter": "legal_counsel", "case": "LC-0001"})
}

test_a_denial_names_the_archive_op if {
	reasons := policy.deny_reasons with input as {"principal": f.ty_ceo, "op": "archive.file", "target": {"company": "TY", "charter": "ceo"}}
	"archive.file_not_permitted" in reasons
	not "unknown_op" in reasons
}

test_any_agent_may_ask_knowledge_for_records if {
	allowed(f.ty_growth_01, "knowledge.read", {"company": "TY", "kinds": ["records", "work"]})
	allowed(hq_arc, "knowledge.read", {"company": "FX", "kinds": ["records"]})
}
