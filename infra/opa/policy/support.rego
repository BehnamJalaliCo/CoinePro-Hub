# Who reads the support desk, the revenue radar and the funnel (prompt 10
# §1.5; contract §19.0, §19.10). Part of hq.internal (its ops list names them;
# every one is A0 in the api's OP_CLASS). The api sends the target's company
# and, for agents, the charter of the authenticated principal (never input).
#
#   support.read   conversations, customers, messages, proposed articles:
#                  the company's support roles and its SALES manager only
#   support.stats  counts and masked quotes: the above, the company's CEO,
#                  and the holding's advisor and overseer (any company)
#   kb.read        approved articles: every employee of the company;
#                  proposed ones: the support people (as support.read)
#   revenue.read   the radar: CEOs, FIN and SALES managers, the revenue
#                  analyst (own company); the advisor and the overseer
#   funnel.read    as revenue.read, plus the support people
# No agent reads another company's support data: the holding's two readers
# get statistics only.
package hq.internal

import rego.v1

support_charters := {"support_lead", "support_agent", "referral_rescue"}

# The company's support people: its support roles and its SALES manager.
support_people if {
	agent
	same_company(tv("company"))
	tv("charter") in support_charters
}

support_people if {
	agent
	same_company(tv("company"))
	p.role == "manager"
	p.department == "SALES"
}

# The holding's readers of statistics (rank two: the advisor, the overseer).
holding_stats_reader if {
	agent
	holding_reader
	p.role in {"advisor", "overseer"}
	is_string(tv("company"))
}

grant if {
	op == "support.read"
	support_people
}

grant if {
	op == "support.stats"
	support_people
}

grant if {
	op == "support.stats"
	agent
	p.role == "ceo"
	same_company(tv("company"))
}

grant if {
	op == "support.stats"
	holding_stats_reader
}

grant if {
	op == "kb.read"
	tv("status") == "approved"
	agent
	same_company(tv("company"))
}

grant if {
	op == "kb.read"
	support_people
}

# The radar's readers in their own company.
revenue_reader if {
	agent
	same_company(tv("company"))
	p.role == "ceo"
}

revenue_reader if {
	agent
	same_company(tv("company"))
	p.role == "manager"
	p.department in {"FIN", "SALES"}
}

revenue_reader if {
	agent
	same_company(tv("company"))
	tv("charter") == "revenue_analyst"
}

grant if {
	op in {"revenue.read", "funnel.read"}
	revenue_reader
}

grant if {
	op in {"revenue.read", "funnel.read"}
	holding_stats_reader
}

grant if {
	op == "funnel.read"
	support_people
}
