package hq.journey_test

import data.hq.journey
import rego.v1

owner := {"kind": "owner", "code": "owner", "role": "owner"}

agent := {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY"}

service := {"kind": "service", "code": "lines", "role": "service"}

stranger := {"kind": "stranger", "code": "x", "role": "x"}

all_ops := {"journey.read", "persona.read", "persona.write", "persona.suggest", "persona.test"}

test_the_owner_may_do_every_op if {
	every op in all_ops {
		journey.allow with input as {"principal": owner, "op": op, "target": {"company": "TY"}}
	}
}

test_the_owner_reads_every_journey_at_once if {
	journey.allow with input as {"principal": owner, "op": "journey.read", "target": {"company": null}}
}

test_no_agent_touches_the_journey_or_the_personas if {
	every op in all_ops {
		not journey.allow with input as {"principal": agent, "op": op}
	}
	"owner_only" in journey.deny_reasons with input as {"principal": agent, "op": "persona.write"}
}

test_no_service_touches_them_either if {
	not journey.allow with input as {"principal": service, "op": "persona.test"}
	"owner_only" in journey.deny_reasons with input as {"principal": service, "op": "persona.test"}
}

test_an_unknown_op_is_refused if {
	not journey.allow with input as {"principal": owner, "op": "persona.delete_all"}
	"unknown_op" in journey.deny_reasons with input as {"principal": owner, "op": "persona.delete_all"}
}

test_an_unknown_principal_is_refused if {
	not journey.allow with input as {"principal": stranger, "op": "journey.read"}
	"unknown_principal" in journey.deny_reasons with input as {"principal": stranger, "op": "journey.read"}
}

test_a_missing_input_is_refused if {
	not journey.allow with input as {}
	not journey.allow with input as "nonsense"
}
