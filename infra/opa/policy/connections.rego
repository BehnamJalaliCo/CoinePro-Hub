# ⟨2026-11-08⟩ H2 (the owner: «نام حساب‌ها و دستور خواندن را نمیتوانم ثبت کنم … همه از طریق شبکه
# به هاب وصل باشند»): connection.set (A2 in the api's OP_CLASS; routes/connections.py) registers a
# connection's NON-SECRET settings — Instagram's account names and that they are read through
# IG-Hub, a read-only command, Telegram channels, a site's address. Part of hq.internal (its ops
# list names it). The api sends the facts, never input: the company written, the agent's charter,
# whether that charter is technical (the TECH department's, read from the charters) and whether
# the company is within the agent's reach by the linked rule (H1: links not enforced, an `on`
# link, the company present in the session). Secrets never pass here (the api refuses them).
#
#   own company        its CEO, its media director, its technical roles
#   another company    a technical role within reach (`linked: true`)
package hq.internal

import rego.v1

connection_set_roles := {"ceo", "media_director"}

grant if {
	op == "connection.set"
	agent
	same_company(tv("company"))
	tv("charter") in connection_set_roles
}

grant if {
	op == "connection.set"
	agent
	same_company(tv("company"))
	tv("technical") == true
}

grant if {
	op == "connection.set"
	agent
	is_string(tv("company"))
	tv("company") != p.company
	tv("technical") == true
	tv("linked") == true
}
