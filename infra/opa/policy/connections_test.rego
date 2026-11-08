package hq.connections_test

import data.hq.internal
import rego.v1

conn_agent(code, company, role, dept) := {
	"kind": "agent", "code": code, "role": role, "company": company,
	"department": dept, "status": "active", "scope": "company",
}

pc_cto := conn_agent("PC-TECH-MGR", "PC", "manager", "TECH")

pc_media := conn_agent("PC-MEDIA-MGR", "PC", "manager", "MEDIA")

pc_ceo := conn_agent("PC-CEO", "PC", "ceo", null)

pc_writer := conn_agent("PC-MEDIA-01", "PC", "employee", "MEDIA")

ig_devops := conn_agent("IG-TECH-01", "IG", "employee", "TECH")

set(principal, target) if {
	internal.allow with input as {"principal": principal, "op": "connection.set", "target": target}
}

test_the_ceo_the_media_director_and_the_technical_roles_set_their_own_companys_connection if {
	set(pc_ceo, {"company": "PC", "charter": "ceo", "technical": false, "linked": false})
	set(pc_media, {"company": "PC", "charter": "media_director", "technical": false, "linked": false})
	set(pc_cto, {"company": "PC", "charter": "cto", "technical": true, "linked": false})
}

test_a_writer_or_a_service_never if {
	not set(pc_writer, {"company": "PC", "charter": "scriptwriter", "technical": false, "linked": false})
	not set({"kind": "service", "code": "worker", "role": "service"}, {"company": "PC", "charter": null, "technical": false, "linked": false})
}

test_a_technical_role_sets_another_companys_connection_within_reach if {
	set(ig_devops, {"company": "PC", "charter": "devops_engineer", "technical": true, "linked": true})
	set(pc_cto, {"company": "IG", "charter": "cto", "technical": true, "linked": true})
	not set(pc_cto, {"company": "IG", "charter": "cto", "technical": true, "linked": false})
	not set(pc_media, {"company": "IG", "charter": "media_director", "technical": false, "linked": true})
	not set(pc_cto, {"company": null, "charter": "cto", "technical": true, "linked": true})
}

test_the_refusal_names_the_operation if {
	reasons := internal.deny_reasons with input as {
		"principal": pc_writer, "op": "connection.set",
		"target": {"company": "PC", "charter": "scriptwriter", "technical": false, "linked": false},
	}
	reasons == {"connection.set_not_permitted"}
}
