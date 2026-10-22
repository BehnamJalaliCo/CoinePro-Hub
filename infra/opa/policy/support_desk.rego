# The support desk's agent writes (prompt 10 §12, contract §19.10). Part of
# hq.internal (its ops list names them; classes in the api's OP_CLASS:
# kb.propose A1, support.draft / support.handoff / support.mystery A2). The
# api sends the target's company and the authenticated principal's charter
# (never input). No tool sends free text to a customer: support.draft is a
# draft the api's code decides on.
#
#   kb.propose       the company's support lead and support agent
#   support.draft    the company's support agent only
#   support.handoff  the company's support lead and support agent
#   support.mystery  the holding's overseer only (PR-043), for any company
package hq.internal

import rego.v1

desk_drafters := {"support_agent"}

desk_people := {"support_lead", "support_agent"}

desk_writer(charters) if {
	agent
	same_company(tv("company"))
	tv("charter") in charters
}

grant if {
	op == "kb.propose"
	desk_writer(desk_people)
}

grant if {
	op == "support.draft"
	desk_writer(desk_drafters)
}

grant if {
	op == "support.handoff"
	desk_writer(desk_people)
}

grant if {
	op == "support.mystery"
	agent
	holding_reader
	p.role == "overseer"
	is_string(tv("company"))
}
