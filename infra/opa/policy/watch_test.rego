package hq.internal_test

import data.hq.internal
import rego.v1

watch_agent(code, company, scope, role, dept) := {
	"kind": "agent", "code": code, "role": role, "company": company,
	"department": dept, "status": "active", "scope": scope,
}

test_ceo_starts_its_own_catalogue if {
	internal.allow with input as {
		"principal": watch_agent("TY-CEO", "TY", "company", "ceo", null),
		"op": "catalogue.start",
		"target": {"company": "TY", "charter": "ceo"},
	}
}

test_ceo_not_another_company if {
	not internal.allow with input as {
		"principal": watch_agent("TY-CEO", "TY", "company", "ceo", null),
		"op": "catalogue.start",
		"target": {"company": "FX", "charter": "ceo"},
	}
}

test_a_manager_does_not_start_it if {
	not internal.allow with input as {
		"principal": watch_agent("TY-TECH-MGR", "TY", "company", "manager", "TECH"),
		"op": "catalogue.start",
		"target": {"company": "TY", "charter": "cto"},
	}
}

test_holding_watch_roles_start_any if {
	internal.allow with input as {
		"principal": watch_agent("HQ-OVR", "HQ", "holding", "overseer", "OVS"),
		"op": "catalogue.start",
		"target": {"company": "TY", "charter": "overseer"},
	}
}

test_other_holding_roles_do_not_start_it if {
	not internal.allow with input as {
		"principal": watch_agent("HQ-LGL", "HQ", "holding", "employee", "LEGAL"),
		"op": "catalogue.start",
		"target": {"company": "TY", "charter": "legal_counsel"},
	}
}

test_oversight_reads_client_errors if {
	internal.allow with input as {
		"principal": watch_agent("HQ-OVR", "HQ", "holding", "overseer", "OVS"),
		"op": "client_errors.read",
		"target": {"company": "HQ", "charter": "overseer"},
	}
}

test_platform_sre_reads_client_errors if {
	internal.allow with input as {
		"principal": watch_agent("HQ-SRE-1", "HQ", "holding", "employee", "AIOPS"),
		"op": "client_errors.read",
		"target": {"company": "HQ", "charter": "hub_platform_sre"},
	}
}

test_a_ceo_does_not_read_client_errors if {
	not internal.allow with input as {
		"principal": watch_agent("TY-CEO", "TY", "company", "ceo", null),
		"op": "client_errors.read",
		"target": {"company": "HQ", "charter": "ceo"},
	}
}
