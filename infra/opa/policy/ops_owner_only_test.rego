package hq.internal_test

import data.hq.internal
import rego.v1

# ⟨1.13⟩ Prompt 22 part 3 (contract §31.6, §31.7): ad budgets and automations are the
# owner's alone. They have owner routes only; no op of /internal/v1 reaches them, so
# no agent or service can compile, seal, switch, resume or loosen anything.
ops_agent(code, company, scope, role) := {
	"kind": "agent", "code": code, "role": role, "company": company,
	"department": null, "status": "active", "scope": scope,
}

owner_only_ops := {
	"automation.compile", "automation.create", "automation.seal", "automation.state",
	"ads.cap", "ads.resume", "ads.rule", "ads.read",
}

test_no_agent_has_an_owner_only_op if {
	every op in owner_only_ops {
		not internal.allow with input as {
			"principal": ops_agent("TY-CEO", "TY", "company", "ceo"),
			"op": op,
			"target": {"company": "TY"},
		}
	}
}

test_not_even_a_holding_role_has_one if {
	every op in owner_only_ops {
		not internal.allow with input as {
			"principal": ops_agent("HQ-ADV", "HQ", "holding", "advisor"),
			"op": op,
			"target": {"company": "TY"},
		}
	}
}

test_the_op_list_names_none_of_them if {
	count(owner_only_ops & internal.ops) == 0
}
