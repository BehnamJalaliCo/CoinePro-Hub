# ⟨1.14⟩ Prompt 23 (contract §32.9): the owner's talk is the owner's alone.
# The api asks before every read and change of a conversation, a turn, a card
# and a persona; the voice layer asks before its routes (engines, the key, the
# meter, the prices) with the same package.
#
#   allow           the owner, a known op, and no deny reason
#   step_up_needed  `voice.secret` (🔏 voice.secret, target = provider): the
#                   api consumed the step-up and says so in context.step_up
# A card keeps the step-ups of the route it runs: that route asks its own policy.
package hq.talk

import data.hq.lib
import rego.v1

ops := {
	"persona.read", "persona.update",
	"conversation.read", "conversation.create", "conversation.update",
	"turn.create", "turn.stop", "invite", "minutes",
	"card.run", "card.dismiss",
	"voice.read", "voice.secret", "voice.check", "voice.sample", "voice.price",
}

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
	op == "voice.secret"
	not stepped_up
}
