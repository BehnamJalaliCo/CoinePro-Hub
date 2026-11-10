# ⟨1.11⟩ Prompt 21 part 3 (contract §29.11-§29.12): the working groups' agent
# tools. Part of hq.internal (its ops list names them; classes in the api's
# OP_CLASS: group.plan A1, experiment.write A1, connection.read A0). The api
# sends the company and the agent's charter, never input.
#
#   group.plan        the content lead (media_director) or the CEO of the company:
#                     the plan of the day and a suggestion for the owner's home
#   experiment.write  the content analyst or the content lead of the company
#   connection.read   any agent of the company (figures, never a secret: only
#                     set/missing); the holding's readers (advisor, overseer, ...)
#                     for any company
#   topic.claim       ⟨1.31⟩ §47 (A1): any working agent, for a work of its own (the
#                     api finds the work and says it is the caller's: `assigned`)
#   narrator.set      ⟨1.31⟩ §48 (A1): an agent that works on an order of the owner
#                     (`assigned`: its work belongs to one), for that work's company
package hq.internal

import rego.v1

group_plan_roles := {"media_director", "ceo"}

experiment_roles := {"content_analyst", "media_director"}

grant if {
	op == "group.plan"
	agent
	tv("charter") in group_plan_roles
	same_company(tv("company"))
}

grant if {
	op == "experiment.write"
	agent
	tv("charter") in experiment_roles
	same_company(tv("company"))
}

grant if {
	op == "connection.read"
	agent
	same_company(tv("company"))
}

grant if {
	op == "connection.read"
	agent
	holding_reader
	is_string(tv("company"))
}

# ⟨1.31⟩ §47 today's topic, named before it is made: the agent whose work it is.
grant if {
	op == "topic.claim"
	agent
	p.role != "system"
	same_company(tv("company"))
	tv("assigned") == true
}

# ⟨1.31⟩ §48 a company's narrator, set by whoever works on the owner's own order.
grant if {
	op == "narrator.set"
	agent
	p.role != "system"
	same_company(tv("company"))
	tv("assigned") == true
}
