package hq.internal_test

import data.hq.internal
import rego.v1

group_agent(code, company, scope, role, dept) := {
	"kind": "agent", "code": code, "role": role, "company": company,
	"department": dept, "status": "active", "scope": scope,
}

test_the_content_lead_files_its_plan if {
	internal.allow with input as {
		"principal": group_agent("TY-MEDIA-MGR", "TY", "company", "manager", "MEDIA"),
		"op": "group.plan",
		"target": {"company": "TY", "charter": "media_director"},
	}
}

test_the_lead_not_for_another_company if {
	not internal.allow with input as {
		"principal": group_agent("TY-MEDIA-MGR", "TY", "company", "manager", "MEDIA"),
		"op": "group.plan",
		"target": {"company": "FX", "charter": "media_director"},
	}
}

test_a_writer_files_no_plan if {
	not internal.allow with input as {
		"principal": group_agent("TY-MEDIA-01", "TY", "company", "employee", "MEDIA"),
		"op": "group.plan",
		"target": {"company": "TY", "charter": "scriptwriter"},
	}
}

test_the_analyst_writes_the_experiment if {
	internal.allow with input as {
		"principal": group_agent("TY-MEDIA-05", "TY", "company", "employee", "MEDIA"),
		"op": "experiment.write",
		"target": {"company": "TY", "charter": "content_analyst"},
	}
}

test_the_publisher_writes_no_experiment if {
	not internal.allow with input as {
		"principal": group_agent("TY-MEDIA-04", "TY", "company", "employee", "MEDIA"),
		"op": "experiment.write",
		"target": {"company": "TY", "charter": "publisher"},
	}
}

test_an_agent_reads_its_own_connections if {
	internal.allow with input as {
		"principal": group_agent("TY-MEDIA-04", "TY", "company", "employee", "MEDIA"),
		"op": "connection.read",
		"target": {"company": "TY", "charter": "publisher"},
	}
}

test_not_another_companys_connections if {
	not internal.allow with input as {
		"principal": group_agent("TY-MEDIA-04", "TY", "company", "employee", "MEDIA"),
		"op": "connection.read",
		"target": {"company": "FX", "charter": "publisher"},
	}
}

test_the_advisor_reads_any_companys_connections if {
	internal.allow with input as {
		"principal": group_agent("HQ-ADV", "HQ", "holding", "advisor", null),
		"op": "connection.read",
		"target": {"company": "FX", "charter": "advisor"},
	}
}
