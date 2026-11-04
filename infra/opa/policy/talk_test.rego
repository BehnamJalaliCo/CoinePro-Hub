package hq.talk_test

import data.hq.talk
import rego.v1

owner := {"kind": "owner", "code": "owner", "role": "owner"}

agent := {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY", "status": "active"}

test_the_owner_talks if {
	talk.allow with input as {"principal": owner, "op": "turn.create"}
	talk.allow with input as {"principal": owner, "op": "conversation.create"}
	talk.allow with input as {"principal": owner, "op": "card.run"}
	talk.allow with input as {"principal": owner, "op": "turn.stop"}
}

test_an_agent_never_talks_here if {
	not talk.allow with input as {"principal": agent, "op": "conversation.read"}
	"owner_only" in talk.deny_reasons with input as {"principal": agent, "op": "turn.create"}
}

test_a_service_never_talks_here if {
	not talk.allow with input as {"principal": {"kind": "service", "code": "x"}, "op": "card.run"}
}

test_an_unknown_op_is_refused if {
	not talk.allow with input as {"principal": owner, "op": "conversation.delete"}
	"unknown_op" in talk.deny_reasons with input as {"principal": owner, "op": "turn.delete"}
}

test_the_voice_key_needs_the_step_up if {
	not talk.allow with input as {"principal": owner, "op": "voice.secret"}
	"step_up_required" in talk.deny_reasons with input as {"principal": owner, "op": "voice.secret"}
	talk.allow with input as {"principal": owner, "op": "voice.secret", "context": {"step_up": true}}
	talk.allow with input as {"principal": owner, "op": "voice.sample"}
}

test_a_missing_input_never_allows if {
	not talk.allow with input as {}
	not talk.allow with input as "x"
}
