package hq.limits_test

import data.hq.actions
import data.hq.decisions
import data.hq.fixtures_test as f
import data.hq.limits
import rego.v1

q(i) if limits.allow with input as i

reasons(i) := r if {
	r := limits.deny_reasons with input as i
}

pushed(rules) := {"version": "v-test", "rules": rules}

test_the_files_defaults_without_a_push if {
	q({"rule": "hire.per_day", "count": 4})
	not q({"rule": "hire.per_day", "count": 5})
	reasons({"rule": "hire.per_day", "count": 5}) == {"over_limit"}
	limits.limit == 5 with input as {"rule": "hire.per_day"}
	limits.version == ""
}

test_the_owners_number_is_enforced_at_once if {
	not q({"rule": "hire.per_day", "count": 1}) with data.hq.authority as pushed({"hire.per_day": {"limit": {"count_day": 1}}})
	q({"rule": "hire.per_day", "count": 0}) with data.hq.authority as pushed({"hire.per_day": {"limit": {"count_day": 1}}})
	limits.version == "v-test" with data.hq.authority as pushed({})
}

test_a_forged_push_stays_inside_the_bounds if {
	# 1000 hires a day is clamped to the file's maximum (20); a negative cap to its minimum.
	not q({"rule": "hire.per_day", "count": 20}) with data.hq.authority as pushed({"hire.per_day": {"limit": {"count_day": 1000}}})
	q({"rule": "hire.per_day", "count": 19}) with data.hq.authority as pushed({"hire.per_day": {"limit": {"count_day": 1000}}})
	not q({"rule": "notify.urgent_per_hour", "count": 0}) with data.hq.authority as pushed({"notify.urgent_per_hour": {"limit": {"count_hour": -5}}}) with data.hq.config.authority_bounds as {"notify.urgent_per_hour": {"field": "count_hour", "min": 0, "max": 30, "default": 5}}

	# a string is not a number: the default applies
	limits.limit == 5 with input as {"rule": "hire.per_day"} with data.hq.authority as pushed({"hire.per_day": {"limit": {"count_day": "999"}}})
}

test_a_count_must_be_a_number_and_a_rule_known if {
	reasons({"rule": "hire.per_day", "count": "3"}) == {"over_limit"}
	reasons({"rule": "hire.per_day"}) == {"over_limit"}
	reasons({"rule": "hire.per_month", "count": 0}) == {"unknown_rule"}

	# without the files' data nothing is known, so nothing is allowed
	reasons({"rule": "hire.per_day", "count": 0}) == {"unknown_rule"} with data.hq.config as []
	not limits.allow with input as "not an object"
}

test_blackout_days if {
	reasons({"rule": "deploy.blackout_days", "day": "fri"}) == {"blackout_day"}
	q({"rule": "deploy.blackout_days", "day": "sat"})
	q({"rule": "deploy.blackout_days", "day": "fri"}) with data.hq.authority as pushed({"deploy.blackout_days": {"limit": {"days": []}}})
	not q({"rule": "deploy.blackout_days", "day": "mon"}) with data.hq.authority as pushed({"deploy.blackout_days": {"limit": {"days": ["mon", "funday"]}}})
}

test_batch_kinds_only_shorten if {
	q({"rule": "batch.kinds", "kind": "proposal"})
	reasons({"rule": "batch.kinds", "kind": "hire"}) == {"not_batchable", "never_batched"}
	not q({"rule": "batch.kinds", "kind": "proposal"}) with data.hq.authority as pushed({"batch.kinds": {"limit": {"kinds": ["knowledge_entry"]}}})

	# a forged push cannot add a kind the file does not allow
	reasons({"rule": "batch.kinds", "kind": "deploy"}) == {"not_batchable", "never_batched"} with data.hq.authority as pushed({"batch.kinds": {"limit": {"kinds": ["deploy", "hire"]}}})
}

# The locked invariants never read the matrix: tampered data gives no agent A3.
tampered := pushed({
	"a3.owner_only": {"actor": "ceo", "locked": false, "limit": {"count_day": 1000}},
	"a4.never": {"actor": "agent", "locked": false},
	"decision.proposer_not_approver": {"actor": "agent"},
	"decision.recurring_approval.ceo": {"actor": "ceo"},
})

test_tampered_data_gives_no_agent_a3 if {
	a3 := {"principal": f.ty_ceo, "action": {"class": "A3", "name": "deploy", "company": "TY"}, "context": {"company_locked": false}}
	not actions.allow with input as a3 with data.hq.authority as tampered
	a4 := {"principal": f.ty_ceo, "action": {"class": "A4", "name": "x", "company": "TY"}, "context": {"company_locked": false}}
	not actions.allow with input as a4 with data.hq.authority as tampered
	deploy := {"kind": "deploy", "company": "TY", "action_class": "A3", "payload": {}, "proposer": {"kind": "agent", "code": "TY-TECH-MGR"}}
	not decisions.allow with input as {"principal": f.ty_ceo, "decision": deploy, "context": {}} with data.hq.authority as tampered
	own := {"kind": "recurring_approval", "company": "TY", "action_class": "A2", "payload": {}, "proposer": {"kind": "agent", "code": "TY-CEO"}}
	not decisions.allow with input as {"principal": f.ty_ceo, "decision": own, "context": {"within_quota": true}} with data.hq.authority as tampered
}

test_the_owner_takes_recurring_approval_back if {
	rec := {"kind": "recurring_approval", "company": "TY", "action_class": "A2", "payload": {}, "proposer": {"kind": "agent", "code": "TY-GROWTH-MGR"}}
	i := {"principal": f.ty_ceo, "decision": rec, "context": {"within_quota": true}}
	decisions.allow with input as i
	not decisions.allow with input as i with data.hq.authority as pushed({"decision.recurring_approval.ceo": {"actor": "owner"}})
	"owner_only" in decisions.deny_reasons with input as i with data.hq.authority as pushed({"decision.recurring_approval.ceo": {"actor": "owner"}})
	decisions.allow with input as object.union(i, {"principal": f.owner}) with data.hq.authority as pushed({"decision.recurring_approval.ceo": {"actor": "owner"}})
}
