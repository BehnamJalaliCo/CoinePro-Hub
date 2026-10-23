# Prompt 13 §1.1 (contract §22.5): roles written on demand. Part of
# hq.internal (its ops list names them; classes in the api's OP_CLASS:
# role.draft A1, role.decide A2). The ceiling itself (tools, model, limits,
# eval cases) is checked by the api's code (422), never here.
#
#   role.draft   a department's head (a manager; the OVS head is an
#                inspector) writes a role for its own company and department
#   role.decide  a company's CEO decides a draft of its own company (the api
#                also asks that hiring is delegated and the draft passed)
#
# The overseer's review of a draft is `skill.review` with an RD- ref.
package hq.internal

import rego.v1

draft_writers := {"manager", "inspector"}

grant if {
	op == "role.draft"
	agent
	p.role in draft_writers
	same_company(tv("company"))
	tv("department") == p.department
}

grant if {
	op == "role.decide"
	agent
	p.role == "ceo"
	same_company(tv("company"))
}
