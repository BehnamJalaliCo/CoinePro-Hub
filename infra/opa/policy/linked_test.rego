package hq.linked_test

import data.hq.internal
import rego.v1

linked_agent(code, company, scope, role, dept) := {
	"kind": "agent", "code": code, "role": role, "company": company,
	"department": dept, "status": "active", "scope": scope,
}

ty_writer := linked_agent("TY-MEDIA-01", "TY", "company", "employee", "MEDIA")

# The facts the api sends about an active company, links enforced (the strict mode).
fx(over) := object.union(
	{
		"company": "FX", "company_kind": "company", "company_active": true,
		"linked": false, "links_enforced": true, "what": "kpis", "charter": "scriptwriter",
	},
	over,
)

read(principal, target) if {
	internal.allow with input as {"principal": principal, "op": "linked.read", "target": target}
}

test_any_agent_reads_its_own_company if {
	read(ty_writer, {"company": "TY", "linked": false, "what": "kpis", "charter": "scriptwriter"})
}

test_while_links_are_not_enforced_any_active_company_is_read if {
	read(ty_writer, fx({"links_enforced": false}))
	read(ty_writer, fx({"links_enforced": false, "what": "profile"}))
	pc_media := linked_agent("PC-MEDIA-MGR", "PC", "company", "manager", "MEDIA")
	read(pc_media, fx({"company": "IG", "links_enforced": false, "what": "connections"}))
}

test_never_the_holding_an_inactive_or_unknown_company_without_enforcement if {
	not read(ty_writer, fx({"company": "HQ", "company_kind": "holding", "links_enforced": false}))
	not read(ty_writer, fx({"company_active": false, "links_enforced": false}))
	not read(ty_writer, fx({"company": "NOPE", "company_kind": null, "company_active": false, "links_enforced": false}))
}

test_a_missing_or_odd_setting_counts_as_enforced if {
	not read(ty_writer, object.remove(fx({}), ["links_enforced"]))
	not read(ty_writer, fx({"links_enforced": "false"}))
	not read(ty_writer, fx({"links_enforced": null}))
}

test_while_links_are_enforced_only_along_an_on_link_either_end if {
	read(ty_writer, fx({"linked": true, "what": "outputs"}))
	fx_ceo := linked_agent("FX-CEO", "FX", "company", "ceo", null)
	read(fx_ceo, fx({"company": "TY", "linked": true, "what": "catalogue", "charter": "ceo"}))
	not read(ty_writer, fx({}))
	not read(ty_writer, fx({"linked": "true"}))
	not read(ty_writer, fx({"linked": true, "company_active": false}))
	not read(ty_writer, {"linked": true, "links_enforced": false, "what": "kpis"})
}

test_the_refusal_names_the_operation if {
	reasons := internal.deny_reasons with input as {
		"principal": ty_writer, "op": "linked.read",
		"target": fx({}),
	}
	reasons == {"linked.read_not_permitted"}
}

test_a_holding_reader_reads_any_company if {
	adv := linked_agent("HQ-ADV", "HQ", "holding", "advisor", null)
	read(adv, fx({"what": "connections", "charter": "advisor"}))
	ovs := linked_agent("HQ-OVS", "HQ", "holding", "overseer", null)
	read(ovs, {"company": "TY", "linked": false, "what": "links", "charter": "overseer"})
}

test_a_company_reader_is_no_holding_reader if {
	ceo := linked_agent("TY-CEO", "TY", "company", "ceo", null)
	not read(ceo, fx({"company": "HQ", "company_kind": "holding", "what": "outputs", "charter": "ceo"}))
}

test_services_paused_agents_and_the_owner_never_read if {
	svc := {"kind": "service", "code": "worker", "role": "service", "company": null, "department": null}
	not read(svc, fx({"links_enforced": false, "linked": true}))
	paused := object.union(ty_writer, {"status": "paused"})
	not read(paused, {"company": "TY", "linked": false, "what": "kpis"})
	owner := {"kind": "owner", "code": "owner", "role": "owner", "company": null, "department": null}
	not read(owner, fx({"links_enforced": false}))
}
