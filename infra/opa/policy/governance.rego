# The governance tools of prompt 11 §4-§10 (contract §20.4-§20.10,
# agents/tools.md v1.5). Part of hq.internal (its ops list names them;
# OP_CLASS gives each its class). The api sends the target's company and,
# where the row decides, its owner or proposer (looked up in the agent's own
# scope only, so another company's row is never found).
#
#   kpi.record       the CEO or a manager of the KPI's company (a manual KPI, with a source)
#   okr.draft        the company's CEO
#   okr.checkin      the CEO or a manager of the key result's company
#   outcome.note     the proposer of the reviewed decision, in its own company
#   risk.raise       own company; a holding-scope role (oversight) for any company
#   risk.update      the risk's owner (answerable) in its company, or the keeper (QC) anywhere
#   calendar.read    own company; a holding-scope role any company
#   calendar.add     the CEO or the GROWTH manager of its own company; a holding-scope manager anywhere
#   authority.read   any agent (the api returns the rows of its own company only)
#   governance.read  own company; a holding-scope role any company
package hq.internal

import rego.v1

grant if {
	op in {"kpi.record", "okr.checkin"}
	agent
	same_company(tv("company"))
	p.role in {"ceo", "manager"}
}

grant if {
	op == "okr.draft"
	agent
	same_company(tv("company"))
	p.role == "ceo"
}

grant if {
	op == "outcome.note"
	agent
	same_company(tv("company"))
	tv("proposer") == p.code
}

grant if {
	op in {"risk.raise", "calendar.read", "governance.read"}
	agent
	reads_company(tv("company"))
}

grant if {
	op == "risk.update"
	agent
	same_company(tv("company"))
	tv("owner") == p.code
}

grant if {
	op == "risk.update"
	agent
	p.role == "inspector"
	holding_reader
	is_string(tv("company"))
}

grant if {
	op == "calendar.add"
	agent
	same_company(tv("company"))
	p.role == "ceo"
}

grant if {
	op == "calendar.add"
	agent
	same_company(tv("company"))
	p.role == "manager"
	p.department == "GROWTH"
}

grant if {
	op == "calendar.add"
	agent
	holding_reader
	p.role == "manager"
	is_string(tv("company"))
}

grant if {
	op == "authority.read"
	agent
}
