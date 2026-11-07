package hq.internal_test

import data.hq.actions
import data.hq.internal
import rego.v1

hub_agent(code, role, scope) := {
	"kind": "agent", "code": code, "role": role, "company": "HQ",
	"department": "AIOPS", "status": "active", "scope": scope,
}

hub_in(principal, op, target) := {"principal": principal, "op": op, "target": target}

sre := hub_agent("HQ-SRE-1", "employee", "holding")

aiops := hub_agent("HQ-AIOPS", "manager", "holding")

hq_cto := hub_agent("HQ-CTO", "manager", "company")

fx_cto := {
	"kind": "agent", "code": "FX-CTO", "role": "manager", "company": "FX",
	"department": "TECH", "status": "active", "scope": "company",
}

media_dir := {
	"kind": "agent", "code": "PC-MED", "role": "manager", "company": "PC",
	"department": "MED", "status": "active", "scope": "company",
}

test_sre_reads_and_operates if {
	internal.allow with input as hub_in(
		sre, "hubops.read",
		{"charter": "hub_platform_sre", "holding": true, "class": "A0", "op": "status", "mode": "read"},
	)
	internal.allow with input as hub_in(
		sre, "hubops.run",
		{"charter": "hub_platform_sre", "holding": true, "class": "A2", "op": "restart", "mode": "run"},
	)
}

test_aiops_proposes_a3 if {
	internal.allow with input as hub_in(
		aiops, "hubops.propose",
		{"charter": "aiops_head", "holding": true, "class": "A3", "op": "n8n.create", "mode": "propose"},
	)
}

test_a3_never_runs_without_a_card if {
	not internal.allow with input as hub_in(
		aiops, "hubops.run",
		{"charter": "aiops_head", "holding": true, "class": "A3", "op": "n8n.create", "mode": "run"},
	)
	not internal.allow with input as hub_in(
		sre, "hubops.read",
		{"charter": "hub_platform_sre", "holding": true, "class": "A3", "op": "n8n.create", "mode": "read"},
	)
}

test_holding_cto_only if {
	internal.allow with input as hub_in(
		hq_cto, "hubops.run",
		{"charter": "cto", "holding": true, "class": "A2", "op": "restart", "mode": "run"},
	)
	not internal.allow with input as hub_in(
		fx_cto, "hubops.run",
		{"charter": "cto", "holding": false, "class": "A2", "op": "restart", "mode": "run"},
	)
}

test_other_roles_refused if {
	not internal.allow with input as hub_in(
		media_dir, "hubops.read",
		{"charter": "media_director", "holding": false, "class": "A0", "op": "status", "mode": "read"},
	)

	# a holding-scope role that is not technical
	not internal.allow with input as hub_in(
		hub_agent("HQ-ADV", "advisor", "holding"), "hubops.read",
		{"charter": "advisor", "holding": true, "class": "A0", "op": "status", "mode": "read"},
	)

	# the charter name alone is not enough without the holding scope
	not internal.allow with input as hub_in(
		hub_agent("FX-SRE", "employee", "company"), "hubops.read",
		{"charter": "hub_platform_sre", "holding": false, "class": "A0", "op": "status", "mode": "read"},
	)
}

test_dispatcher_queue_only_its_token if {
	internal.allow with input as hub_in({"kind": "service", "code": "hubops", "role": "service"}, "hubops.jobs", {})
	not internal.allow with input as hub_in({"kind": "service", "code": "substitutes", "role": "service"}, "hubops.jobs", {})
	not internal.allow with input as hub_in(sre, "hubops.jobs", {})
}

test_hub_ops_tool_is_a2_for_technical_kinds if {
	actions.allow with input as {
		"principal": sre,
		"action": {"class": "A2", "name": "hub.ops", "company": "HQ"},
		"context": {"escrow_classes": [], "company_locked": false},
	}
	actions.allow with input as {
		"principal": aiops,
		"action": {"class": "A2", "name": "hubops.run", "company": "HQ"},
		"context": {"escrow_classes": [], "company_locked": false},
	}
}

# An A3 op asked through read or run is refused with its reason: it needs the owner's sealed decision.
# (set lookups, not `in`: this file imports data.hq.internal, which shadows the `in` builtin)
test_an_a3_op_through_read_or_run_says_it_needs_a_decision if {
	run_a3 := internal.deny_reasons with input as hub_in(
		sre, "hubops.run",
		{"charter": "hub_platform_sre", "holding": true, "class": "A3", "op": "profile_on", "mode": "run"},
	)
	run_a3.a3_requires_decision
	read_a4 := internal.deny_reasons with input as hub_in(
		sre, "hubops.read",
		{"charter": "hub_platform_sre", "holding": true, "class": "A4", "op": "status", "mode": "read"},
	)
	read_a4.a3_requires_decision
	run_a2 := internal.deny_reasons with input as hub_in(
		sre, "hubops.run",
		{"charter": "hub_platform_sre", "holding": true, "class": "A2", "op": "restart", "mode": "run"},
	)
	not run_a2.a3_requires_decision
}
