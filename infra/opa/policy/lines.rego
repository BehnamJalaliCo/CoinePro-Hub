# ⟨1.12⟩ Prompt 22 (contract §30.5): production lines are the owner's alone.
# The api asks before every change of a line, a run, a test or the library;
# the n8n callback is checked by its signature, not here.
#
#   allow           the owner, a known op, and no deny reason
#   step_up_needed  `line.mode` to auto (🔏 line.auto) and a `line.update` that
#                   raises a cap (🔏 line.caps): the api consumed the step-up
#                   and says so in context.step_up
package hq.lines

import data.hq.lib
import rego.v1

ops := {
	"line.create", "line.update", "line.state", "line.mode", "line.run", "line.test",
	"line.cancel", "library.write",
} | flow_ops

p := lib.principal

op := object.get(lib.doc, "op", "")

target := lib.obj(object.get(lib.doc, "target", {}))

ctx := lib.obj(object.get(lib.doc, "context", {}))

stepped_up if object.get(ctx, "step_up", false) == true

default allow := false

allow if {
	p.kind == "owner"
	count(deny_reasons) == 0
}

deny_reasons contains "owner_only" if p.kind != "owner"

deny_reasons contains "unknown_op" if not op in ops

deny_reasons contains "step_up_required" if {
	op == "line.mode"
	object.get(target, "mode", "") == "auto"
	not stepped_up
}

deny_reasons contains "step_up_required" if {
	op == "line.update"
	object.get(target, "caps_rise", false) == true
	not stepped_up
}

# ⟨1.37⟩ flow (contract §59.4, §59.7): a working group's daily flow runs on a line; the use form
# and the flow's controls are the owner's taps (no step-up), except a budget raised past the
# company's month envelope: 🔏 automation.budget (the api consumed it and says so in step_up).
flow_ops := {"flow.use", "flow.state", "flow.run", "flow.pause", "flow.skip", "flow.update"}

deny_reasons contains "step_up_required" if {
	op == "flow.update"
	object.get(target, "over_envelope", false) == true
	not stepped_up
}
