package hq.lines_test

import data.hq.lines
import rego.v1

owner := {"kind": "owner", "code": "owner", "role": "owner"}

agent := {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY", "status": "active"}

test_the_owner_makes_a_line if {
	lines.allow with input as {"principal": owner, "op": "line.create", "target": {"company": "TY"}}
}

test_the_owner_runs_and_tests_a_line if {
	lines.allow with input as {"principal": owner, "op": "line.run", "target": {"line": "LN-0001"}}
	lines.allow with input as {"principal": owner, "op": "line.test", "target": {"line": "LN-0001"}}
}

test_an_agent_touches_no_line if {
	not lines.allow with input as {"principal": agent, "op": "line.run", "target": {"line": "LN-0001"}}
	"owner_only" in lines.deny_reasons with input as {"principal": agent, "op": "line.run"}
}

test_a_service_touches_no_line if {
	not lines.allow with input as {"principal": {"kind": "service", "code": "x"}, "op": "library.write"}
}

test_an_unknown_op_is_refused if {
	not lines.allow with input as {"principal": owner, "op": "line.delete"}
	"unknown_op" in lines.deny_reasons with input as {"principal": owner, "op": "line.delete"}
}

test_auto_needs_the_step_up if {
	not lines.allow with input as {"principal": owner, "op": "line.mode", "target": {"mode": "auto"}}
	lines.allow with input as {
		"principal": owner, "op": "line.mode", "target": {"mode": "auto"},
		"context": {"step_up": true},
	}
	lines.allow with input as {"principal": owner, "op": "line.mode", "target": {"mode": "draft"}}
}

test_a_higher_cap_needs_the_step_up if {
	not lines.allow with input as {"principal": owner, "op": "line.update", "target": {"caps_rise": true}}
	lines.allow with input as {
		"principal": owner, "op": "line.update", "target": {"caps_rise": true},
		"context": {"step_up": true},
	}
	lines.allow with input as {"principal": owner, "op": "line.update", "target": {"caps_rise": false}}
}

test_a_missing_input_never_allows if {
	not lines.allow with input as {}
	not lines.allow with input as "x"
}

# ⟨1.37⟩ flow
test_the_flows_controls_are_the_owners_taps if {
	every op in {"flow.use", "flow.state", "flow.run", "flow.pause", "flow.skip", "flow.update"} {
		lines.allow with input as {"principal": owner, "op": op, "target": {"automation": "AT-0001"}}
	}
	not lines.allow with input as {"principal": agent, "op": "flow.run", "target": {"automation": "AT-0001"}}
}

test_a_budget_past_the_envelope_needs_the_step_up if {
	lines.allow with input as {
		"principal": owner, "op": "flow.update",
		"target": {"automation": "AT-0001", "budget_rise": true, "over_envelope": false},
	}
	not lines.allow with input as {
		"principal": owner, "op": "flow.update",
		"target": {"automation": "AT-0001", "budget_rise": true, "over_envelope": true},
	}
	lines.allow with input as {
		"principal": owner, "op": "flow.update",
		"target": {"automation": "AT-0001", "budget_rise": true, "over_envelope": true},
		"context": {"step_up": true},
	}
}
