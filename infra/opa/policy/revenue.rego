# The revenue and growth half of prompt 10 (§2, §3, §8; contract §19.1,
# §19.10). Part of hq.internal (its ops list names them; OP_CLASS gives each
# its class). The api sends the target's company and, for agents, the charter
# of the authenticated principal (never input).
#
#   egress.connector  a connector call's account and egress-log row: the
#                     worker's own service token only (the revenue pulls)
#   referral.check    the company's support agent and rescue specialist
#   rescue.update     the company's rescue specialist (it sends nothing)
#   feedback.tag      the company's support lead and its PRODUCT manager
package hq.internal

import rego.v1

grant if {
	op == "egress.connector"
	service
	p.code == "worker"
}

grant if {
	op == "referral.check"
	agent
	same_company(tv("company"))
	tv("charter") in {"support_agent", "referral_rescue"}
}

grant if {
	op == "rescue.update"
	agent
	same_company(tv("company"))
	tv("charter") == "referral_rescue"
}

grant if {
	op == "feedback.tag"
	agent
	same_company(tv("company"))
	tv("charter") == "support_lead"
}

grant if {
	op == "feedback.tag"
	agent
	same_company(tv("company"))
	p.role == "manager"
	p.department == "PRODUCT"
}
