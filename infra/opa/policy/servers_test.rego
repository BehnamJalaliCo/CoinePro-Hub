package hq.internal_test

import data.hq.internal
import rego.v1

agent_of(code, company, scope) := {
	"kind": "agent", "code": code, "role": "employee", "company": company,
	"department": "TECH", "status": "active", "scope": scope,
}

test_own_company_server if {
	internal.allow with input as {
		"principal": agent_of("FX-TECH-MGR", "FX", "company"),
		"op": "server.run",
		"target": {"company": "FX", "charter": "cto", "via": "own"},
	}
}

test_other_company_refused if {
	not internal.allow with input as {
		"principal": agent_of("FX-TECH-MGR", "FX", "company"),
		"op": "server.run",
		"target": {"company": "TY", "charter": "cto", "via": null},
	}
}

test_accepted_request_allowed if {
	internal.allow with input as {
		"principal": agent_of("FX-TECH-MGR", "FX", "company"),
		"op": "server.read",
		"target": {"company": "TY", "charter": "cto", "via": "accepted_request"},
	}
}

test_holding_sre_every_server if {
	internal.allow with input as {
		"principal": agent_of("HQ-SRE-1", "HQ", "holding"),
		"op": "server.run",
		"target": {"company": "TY", "charter": "hub_platform_sre", "via": "holding"},
	}
}

test_other_holding_role_refused if {
	not internal.allow with input as {
		"principal": agent_of("HQ-ADV", "HQ", "holding"),
		"op": "server.run",
		"target": {"company": "TY", "charter": "advisor", "via": "holding"},
	}
}

test_services_never if {
	not internal.allow with input as {
		"principal": {"kind": "service", "code": "worker", "role": "service"},
		"op": "server.run",
		"target": {"company": "TY", "charter": null, "via": null},
	}
}
