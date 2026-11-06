# ⟨1.11⟩ Prompt 21 part 1 (contract §29.1, §29.2, §29.6, §29.15): every order
# answered, the delegation budget, the destructive cards a CTO decides. Part
# of hq.internal (its ops list names them; classes in the api's OP_CLASS:
# order.ack A1, order.progress A1, order.ask A1, work.budget A2, card.decide A2).
#
#   order.ack, order.progress, order.ask   an agent that works on the order (one of its
#                               works is its own, or it is the CEO of a company
#                               with one): the api sends `assigned`
#   work.budget                 a CEO, a work of its own company («+X», inside
#                               the month envelope, which the api checks)
#   card.decide                 the approver the card names, in its own company
#                               (a company's CTO, its server_destructive cards;
#                               ⟨1.12⟩ its CEO, a line's step with gate: ceo)
package hq.internal

import rego.v1

grant if {
	op in {"order.ack", "order.progress", "order.ask"}
	agent
	same_company(tv("company"))
	tv("assigned") == true
}

grant if {
	op == "work.budget"
	agent
	p.role == "ceo"
	same_company(tv("company"))
}

grant if {
	op == "card.decide"
	agent
	same_company(tv("company"))
	tv("approver") == p.code
}
