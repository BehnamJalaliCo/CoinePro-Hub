# Prompt 17 (contract §26.2 ⟨1.8⟩): an agent's jobs on a company's own server,
# through its pull runner. Part of hq.internal (its ops list names them;
# classes in the api's OP_CLASS: server.read A0 for map and read,
# server.run A2 for exec, write and claude). The api sends the server's
# company, the agent's charter and how the call is allowed (`via`, which the
# api decided from the database), never input. The charter's tool list (the
# gateway) decides which of the five tools a role has.
#
#   own company       any agent whose charter lists the tool
#   every server      the holding's platform SRE and the overseer
#   another company   only through a cross-company request that company's
#                     CEO accepted (`via: accepted_request`); the job then
#                     runs as that CEO
package hq.internal

import rego.v1

server_ops := {"server.read", "server.run"}

holding_server_roles := {"hub_platform_sre", "overseer"}

grant if {
	op in server_ops
	agent
	same_company(tv("company"))
}

grant if {
	op in server_ops
	agent
	holding_reader
	tv("charter") in holding_server_roles
}

grant if {
	op in server_ops
	agent
	tv("via") == "accepted_request"
	is_string(tv("company"))
}
