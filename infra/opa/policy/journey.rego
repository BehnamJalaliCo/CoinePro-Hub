# ⟨1.15⟩ Prompt 24 (contract §33.8-§33.9): the company journey, the personas and the message test.
# Owner only: a persona is the owner's data, the journey is his view across companies, and the two
# model calls (the suggestion, the test) are his to ask. No agent and no service reads or changes
# them through the api. The api asks this before every route.
#
#   journey.read      the journey of one company, or of all (target.company null)
#   persona.read      the personas of a company
#   persona.write     add, edit or archive a persona
#   persona.suggest   one model call proposing personas from the company's knowledge
#   persona.test      one model call testing a message against the personas
package hq.journey

import data.hq.lib
import rego.v1

p := lib.principal

op := object.get(lib.doc, "op", "")

ops := {"journey.read", "persona.read", "persona.write", "persona.suggest", "persona.test"}

default allow := false

allow if {
	op in ops
	p.kind == "owner"
	count(deny_reasons) == 0
}

deny_reasons contains "unknown_op" if not op in ops

deny_reasons contains "unknown_principal" if not p.kind in lib.principal_kinds

deny_reasons contains "owner_only" if {
	op in ops
	p.kind != "owner"
}
