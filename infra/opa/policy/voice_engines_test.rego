package hq.voice_engines_test

import data.hq.voice_engines
import rego.v1

owner := {"kind": "owner", "code": "owner", "role": "owner"}

agent := {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY", "status": "active"}

service := {"kind": "service", "code": "tts", "role": "service"}

reads := {"voice.read"}

spends := {"voice.check", "voice.sample", "voice.price"}

secrets := {"voice.secret"}

test_the_owner_reads_the_engines_the_voices_and_the_meter if {
	every op in reads {
		voice_engines.allow with input as {"principal": owner, "op": op}
	}
}

test_the_owner_checks_samples_and_prices if {
	every op in spends {
		voice_engines.allow with input as {"principal": owner, "op": op}
	}
}

test_the_key_needs_the_step_up if {
	every op in secrets {
		not voice_engines.allow with input as {"principal": owner, "op": op}
		"step_up_required" in voice_engines.deny_reasons with input as {"principal": owner, "op": op}
		voice_engines.allow with input as {
			"principal": owner, "op": op,
			"context": {"step_up": true},
		}
	}
}

test_a_step_up_flag_that_is_not_true_is_no_step_up if {
	not voice_engines.allow with input as {
		"principal": owner, "op": "voice.secret",
		"context": {"step_up": "yes"},
	}
}

test_nothing_else_needs_a_step_up if {
	every op in reads | spends {
		not "step_up_required" in voice_engines.deny_reasons with input as {"principal": owner, "op": op}
	}
}

test_an_agent_has_no_op_here if {
	every op in (reads | spends) | secrets {
		not voice_engines.allow with input as {
			"principal": agent, "op": op,
			"context": {"step_up": true},
		}
		"owner_only" in voice_engines.deny_reasons with input as {"principal": agent, "op": op}
	}
}

test_a_service_has_no_op_here if {
	not voice_engines.allow with input as {"principal": service, "op": "voice.read"}
	"owner_only" in voice_engines.deny_reasons with input as {"principal": service, "op": "voice.read"}
}

test_an_unknown_op_is_refused if {
	not voice_engines.allow with input as {"principal": owner, "op": "voice.cap.raise"}
	"unknown_op" in voice_engines.deny_reasons with input as {"principal": owner, "op": "voice.cap.raise"}
}

test_no_input_is_refused if {
	not voice_engines.allow with input as {}
}
