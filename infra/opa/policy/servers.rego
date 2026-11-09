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
#   another company   through a cross-company request that company's CEO
#                     accepted (`via: accepted_request`; the job then runs as
#                     that CEO), or ⟨2026-11-08⟩ a technical role within reach
#                     (`via: linked`: links not enforced, an `on` link, or the
#                     company present in the session)
#   the workshop      ⟨2026-11-09⟩ any working agent of any company, a Claude Code
#                     turn on the holding's workshop server (`via: workshop`, which
#                     the api sets only for a `claude` job of workshop.run on a
#                     server of the holding; exec and write there stay closed)
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

# ⟨2026-11-08⟩ H1 (the owner: «همه شرکت‌ها به هم راه داشته باشند»): a company's technical role
# (the TECH department's charters) on another company's server by the rule of linked.read — the
# api sets `via: linked` when the owner does not enforce links, or the two share an `on` link, or
# the company sits in the session of the run's order. Destructive commands still wait for the seal.
grant if {
	op in server_ops
	agent
	tv("via") == "linked"
	is_string(tv("company"))
	tv("company") != p.company
}

# ⟨2026-11-09⟩ the workshop (contract §43; the owner: «اپ وسیله‌ی ارتباط است؛ سرور کامپیوتر است»):
# every working role hands a task with no tool of its own to Claude Code on the holding's workshop
# server. Only server.run (a `claude` job: the api refuses any other kind with this via), only on
# the holding's server (the api decides `via` from the database), never a system role.
grant if {
	op == "server.run"
	agent
	tv("via") == "workshop"
	is_string(tv("company"))
	p.role != "system"
}
