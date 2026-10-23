# The numbers of the authority matrix (prompt 11 §7, contract §20.7).
#
# The api pushes the owner's rows to data.hq.authority (PUT
# /v1/data/hq/authority: the one data write system.authz allows) at its first
# use and after every change. The bounds come from the files
# (data.hq.config.authority_bounds, authority_lists): a forged push can move a
# number only inside the owner's bounds and shorten a list only inside its
# seeded list; without a push the files' defaults apply. The locked invariants
# (A4 never, A3 only the owner's, proposer != approver, releasing a switch or
# a hold, no agent edits the matrix) live in hq.actions, hq.decisions and
# hq.internal and never read this data.
#
#   {rule, count}                         allow while count < the rule's number
#   {rule: "deploy.blackout_days", day}   deny "blackout_day" on such a day
#   {rule: "batch.kinds", kind}           allow when the kind may be sealed in a batch
package hq.limits

import data.hq.lib
import rego.v1

config := x if {
	x := data.hq.config
	is_object(x)
} else := {}

bounds := lib.obj(object.get(config, "authority_bounds", {}))

lists := lib.obj(object.get(config, "authority_lists", {}))

never := {k | some k in object.get(config, "never_batch", [])}

pushed := x if {
	x := data.hq.authority
	is_object(x)
} else := {}

# The digest of the pushed rows: the api pushes again when it differs from its own.
version := object.get(pushed, "version", "")

rule := object.get(lib.doc, "rule", "")

pushed_limit := lib.obj(object.get(lib.obj(object.get(lib.obj(object.get(pushed, "rules", {})), rule, {})), "limit", {}))

b := lib.obj(object.get(bounds, rule, {}))

# The number in force: the pushed one clamped into the file's bounds, else the file's default.
limit := min([max([n, b.min]), b.max]) if {
	n := object.get(pushed_limit, b.field, null)
	is_number(n)
} else := object.get(b, "default", 0)

l := lib.obj(object.get(lists, rule, {}))

allowed_items := {x | some x in object.get(l, "allowed", [])}

# A list in force: the pushed one, only what the seeded list holds.
items := {x | some x in object.get(pushed_limit, l.field, []); x in allowed_items} if {
	is_array(object.get(pushed_limit, l.field, null))
} else := {x | some x in object.get(l, "default", []); x in allowed_items}

count_in := object.get(lib.doc, "count", null)

known if bounds[rule]

known if lists[rule]

default allow := false

allow if {
	known
	count(deny_reasons) == 0
}

deny_reasons contains "unknown_rule" if not known

deny_reasons contains "over_limit" if {
	bounds[rule]
	not is_number(count_in)
}

deny_reasons contains "over_limit" if {
	bounds[rule]
	is_number(count_in)
	count_in >= limit
}

deny_reasons contains "blackout_day" if {
	rule == "deploy.blackout_days"
	object.get(lib.doc, "day", "") in items
}

deny_reasons contains "not_batchable" if {
	rule == "batch.kinds"
	not object.get(lib.doc, "kind", "") in items
}

deny_reasons contains "never_batched" if {
	rule == "batch.kinds"
	object.get(lib.doc, "kind", "") in never
}
