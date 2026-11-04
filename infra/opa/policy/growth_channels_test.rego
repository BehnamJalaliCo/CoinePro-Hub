package hq.internal_test

import data.hq.internal
import rego.v1

channel_agent(code, role, dept) := {
	"kind": "agent", "code": code, "role": role, "company": "TY",
	"department": dept, "status": "active", "scope": "company",
}

test_no_agent_reaches_an_owner_only_growth_op if {
	every op in internal.owner_only_growth_ops {
		not internal.allow with input as {
			"principal": channel_agent("TY-GROWTH-MGR", "manager", "GROWTH"),
			"op": op,
			"target": {"company": "TY"},
		}
		not internal.allow with input as {
			"principal": channel_agent("TY-CEO", "ceo", "CEO"),
			"op": op,
			"target": {"company": "TY"},
		}
	}
}

test_the_refusal_names_the_reason if {
	r := internal.deny_reasons with input as {
		"principal": channel_agent("TY-GROWTH-MGR", "manager", "GROWTH"),
		"op": "newsletter.send",
		"target": {"company": "TY"},
	}
	r.owner_only_growth
}

test_a_service_is_refused_too if {
	not internal.allow with input as {
		"principal": {"kind": "service", "code": "seo", "role": "service"},
		"op": "seo.keyword",
		"target": {"company": "TY"},
	}
}

test_the_connection_read_stays_open_to_the_growth_lead if {
	internal.allow with input as {
		"principal": channel_agent("TY-GROWTH-MGR", "manager", "GROWTH"),
		"op": "connection.read",
		"target": {"company": "TY", "charter": "growth_lead"},
	}
}
