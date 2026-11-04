# ⟨1.13⟩ Prompt 22 (contract §31.2): a ready company from one order. Owner only:
# only the owner makes a company, from a kit or any other way; no agent and no
# service ever does (a founding is its own sealed card). The api asks this
# before the step-up 🔏 company.create is consumed.
#
#   company.from_kit   the owner
package hq.kits

import data.hq.lib
import rego.v1

p := lib.principal

op := object.get(lib.doc, "op", "")

ops := {"company.from_kit"}

default allow := false

allow if {
	op == "company.from_kit"
	p.kind == "owner"
	count(deny_reasons) == 0
}

deny_reasons contains "unknown_op" if not op in ops

deny_reasons contains "unknown_principal" if not p.kind in lib.principal_kinds

deny_reasons contains "owner_only" if {
	op in ops
	p.kind != "owner"
}
