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

test_a_technical_role_on_a_linked_companys_server if {
	internal.allow with input as {
		"principal": agent_of("PC-TECH-MGR", "PC", "company"),
		"op": "server.run",
		"target": {"company": "IG", "charter": "cto", "via": "linked"},
	}
	internal.allow with input as {
		"principal": agent_of("PC-TECH-01", "PC", "company"),
		"op": "server.read",
		"target": {"company": "IG", "charter": "devops_engineer", "via": "linked"},
	}
	not internal.allow with input as {
		"principal": agent_of("PC-TECH-MGR", "PC", "company"),
		"op": "server.run",
		"target": {"company": null, "charter": "cto", "via": "linked"},
	}
	not internal.allow with input as {
		"principal": agent_of("PC-TECH-MGR", "PC", "company"),
		"op": "server.run",
		"target": {"company": "IG", "charter": "cto", "via": "maybe"},
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

test_any_working_role_on_the_holdings_workshop if {
	internal.allow with input as {
		"principal": object.union(agent_of("PC-MED-02", "PC", "company"), {"department": "MED"}),
		"op": "server.run",
		"target": {"company": "HQ", "charter": "scriptwriter", "via": "workshop"},
	}
	internal.allow with input as {
		"principal": object.union(agent_of("TY-CEO", "TY", "company"), {"role": "ceo"}),
		"op": "server.run",
		"target": {"company": "HQ", "charter": "ceo", "via": "workshop"},
	}

	# reading the workshop's files by hand is not part of it
	not internal.allow with input as {
		"principal": agent_of("PC-MED-02", "PC", "company"),
		"op": "server.read",
		"target": {"company": "HQ", "charter": "scriptwriter", "via": "workshop"},
	}

	# a system role never, and no company named is no grant
	not internal.allow with input as {
		"principal": object.union(agent_of("PC-SYS", "PC", "company"), {"role": "system"}),
		"op": "server.run",
		"target": {"company": "HQ", "charter": "dispatcher", "via": "workshop"},
	}
	not internal.allow with input as {
		"principal": agent_of("PC-MED-02", "PC", "company"),
		"op": "server.run",
		"target": {"company": null, "charter": "scriptwriter", "via": "workshop"},
	}
}
