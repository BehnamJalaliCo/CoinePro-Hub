# The meeting room and the knowledge base (prompt 11 §1-§3, §11; contract
# §20.1-§20.3). Part of hq.internal (its ops list names them; classes in the
# api's OP_CLASS: knowledge.review and knowledge.approve A2, the rest A1). The
# api sends the principal's charter (never input) and the target's company.
#
#   meeting.statement  any agent of its own company; the api binds the call to
#                      the speaker's own pending turn (its run, its slot)
#   meeting.challenge  the oversight roles (the devil's advocate)
#   meeting.whisper    the advisor only (its notes go to the owner only)
#   meeting.minutes    the secretary only (a system role of the holding)
#   meeting.item       an agent for its own company; a holding-scope role for any
#   knowledge.propose  an entry of the agent's own company (the holding layer:
#                      the holding's roles)
#   knowledge.review   the overseer and AI safety (holding scope), any company
#   knowledge.approve  a CEO, its own company's company or department entry,
#                      unless the owner took the authority-matrix row
#                      `knowledge.approve.company` back (data.hq.authority)
package hq.internal

import rego.v1

grant if {
	op == "meeting.statement"
	agent
	same_company(tv("company"))
}

grant if {
	op == "meeting.challenge"
	oversight_role
}

grant if {
	op == "meeting.whisper"
	agent
	p.role == "advisor"
}

grant if {
	op == "meeting.minutes"
	agent
	holding_reader
	tv("charter") == "secretary"
}

grant if {
	op == "meeting.item"
	agent
	same_company(tv("company"))
}

grant if {
	op == "meeting.item"
	agent
	holding_reader
	is_string(tv("company"))
}

grant if {
	op == "knowledge.propose"
	agent
	same_company(tv("company"))
}

grant if {
	op == "knowledge.review"
	agent
	holding_reader
	tv("charter") in {"overseer", "ai_safety"}
}

grant if {
	op == "knowledge.approve"
	agent
	p.role == "ceo"
	same_company(tv("company"))
	tv("layer") in {"company", "department"}
	not knowledge_approval_taken_back
}

# The authority matrix (prompt 11 §7) is data: a row `knowledge.approve.company`
# whose actor is the owner takes the CEOs' approval back. Without the data the
# default holds (the CEO approves, §0.7).
knowledge_approval_taken_back if {
	data.hq.authority["knowledge.approve.company"].actor == "owner"
}
