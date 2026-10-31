# ⟨1.10⟩ Prompt 19 (contract §28.2-§28.3): the company catalogue and the
# apps' own error reports. Part of hq.internal (its ops list names them;
# classes in the api's OP_CLASS: catalogue.start A1, client_errors.read A0).
# The api sends the company and the agent's charter, never input.
#
#   catalogue.start      a CEO for its own company ("go through the server and
#                        extract everything" starts the catalogue, §28.2); the
#                        holding's overseer, advisor and platform SRE for any
#                        company (the watch)
#   client_errors.read   the oversight roles of the holding (the daily app
#                        health, §28.3) and the platform SRE
package hq.internal

import rego.v1

catalogue_holding_roles := {"overseer", "advisor", "hub_platform_sre"}

grant if {
	op == "catalogue.start"
	agent
	tv("charter") == "ceo"
	same_company(tv("company"))
}

grant if {
	op == "catalogue.start"
	agent
	holding_reader
	tv("charter") in catalogue_holding_roles
	is_string(tv("company"))
}

grant if {
	op == "client_errors.read"
	oversight_role
}

grant if {
	op == "client_errors.read"
	agent
	holding_reader
	tv("charter") == "hub_platform_sre"
}
