# ⟨1.14⟩ Prompt 23 (contract §32.5, §32.9): the voice engines, the key, the meter and the price are
# the owner's alone. The api asks before every route of /voice/*; no agent and no service has an op
# here. The provider's key goes in and out only with the owner's step-up `voice.secret`.
#
#   allow           the owner, a known op, and no deny reason
#   step_up_needed  `voice.secret`, set or delete (🔏 voice.secret, target = provider): the api
#                   consumed the step-up and says so in context.step_up
# The op names are the ones talk.rego declares for the same routes.
package hq.voice_engines

import data.hq.lib
import rego.v1

ops := {"voice.read", "voice.secret", "voice.check", "voice.sample", "voice.price"}

step_up_ops := {"voice.secret"}

p := lib.principal

op := object.get(lib.doc, "op", "")

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
	op in step_up_ops
	not stepped_up
}
