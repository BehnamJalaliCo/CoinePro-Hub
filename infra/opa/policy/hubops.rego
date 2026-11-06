# ⟨1.20⟩ contract §38.1: hub operations (`hub.ops`), one fixed catalogue run on
# the hub host by the hub-ops dispatcher (apps/api domain/hub_ops.py). Part of
# hq.internal (its ops list names them; classes in the api's OP_CLASS:
# hubops.read A0, hubops.run A2, hubops.propose A1, hubops.jobs A0). The api
# sends the agent's charter, whether its company is the holding, the op and its
# class (decided by the catalogue from the validated arguments), never input.
#
#   who        the holding's technical people only: the AI operations head and
#              the platform SRE (holding scope), and the holding's own CTO;
#              every other role asks them (work.request; contract §38.2)
#   A0 / A2    read / operate: queued for the dispatcher
#   A3         never run without the owner's sealed decision: only proposed
#              (a 🔏 hub_op card; approving it queues the job)
#   the queue  the dispatcher's service token only (service `hubops`)
package hq.internal

import rego.v1

hubops_charters := {"aiops_head", "hub_platform_sre"}

hubops_technical if {
	agent
	holding_reader
	tv("charter") in hubops_charters
}

hubops_technical if {
	agent
	tv("charter") == "cto"
	tv("holding") == true
}

grant if {
	op == "hubops.read"
	hubops_technical
	tv("class") == "A0"
}

grant if {
	op == "hubops.run"
	hubops_technical
	tv("class") == "A2"
}

grant if {
	op == "hubops.propose"
	hubops_technical
	tv("class") == "A3"
}

grant if {
	op == "hubops.jobs"
	service
	p.code == "hubops"
}

deny_reasons contains "a3_requires_decision" if {
	op in {"hubops.read", "hubops.run"}
	tv("class") in {"A3", "A4"}
}
