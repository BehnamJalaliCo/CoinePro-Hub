package hq.kits_test

import data.hq.kits
import rego.v1

test_the_owner_makes_a_company_from_a_kit if {
	kits.allow with input as {
		"principal": {"kind": "owner", "code": "owner", "role": "owner"},
		"op": "company.from_kit",
		"target": {"kit": "content_brand"},
	}
}

test_no_agent_makes_a_company if {
	not kits.allow with input as {
		"principal": {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY"},
		"op": "company.from_kit",
		"target": {"kit": "content_brand"},
	}
	"owner_only" in kits.deny_reasons with input as {
		"principal": {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY"},
		"op": "company.from_kit",
	}
}

test_no_service_makes_a_company if {
	not kits.allow with input as {
		"principal": {"kind": "service", "code": "groups", "role": "service"},
		"op": "company.from_kit",
	}
}

test_an_unknown_op_is_refused if {
	not kits.allow with input as {
		"principal": {"kind": "owner", "code": "owner", "role": "owner"},
		"op": "company.delete_everything",
	}
}

test_a_missing_input_is_refused if {
	not kits.allow with input as {}
}
