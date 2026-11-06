# ⟨2026-11-06⟩ The owner: «شرکت‌ها بتونن دیتا به هم بدهند … عین رگ انسان باید باشه».
# linked.read (A0 in the api's OP_CLASS; routes/linked.py): another company's profile, KPIs,
# outputs, catalogue in short, connections' figures or links. Part of hq.internal (its ops list
# names it). The same rule as a cross-company request (contract §35.6): while the owner's
# `links_enforced` is off, any active company is read by any other; while it is on, only along an
# `on` link. The api sends the facts, never input: the company read, its kind (`company_kind`,
# null when there is none) and whether it is active, `linked` (core.company_linked, either way),
# `links_enforced` (owner.settings; missing counts as enforced, the safe side), the charter.
#
#   own company      any agent
#   links not enforced
#                    any agent, any other active company (never the holding)
#   along a link     any agent of either end of an `on` link, the other end active (the holding
#                    has no link rows: its data is never read along one)
#   any company      the holding's readers (charter scope "holding": the advisor, the overseer,
#                    AI operations), as with every read tool
#
# Never a write; never customer data or a secret (the api leaves them out and masks the rest).
package hq.internal

import rego.v1

other_active_company if {
	p.company != null
	is_string(tv("company"))
	tv("company") != p.company
	tv("company_kind") == "company"
	tv("company_active") == true
}

grant if {
	op == "linked.read"
	agent
	same_company(tv("company"))
}

grant if {
	op == "linked.read"
	agent
	other_active_company
	tv("links_enforced") == false
}

grant if {
	op == "linked.read"
	agent
	other_active_company
	tv("linked") == true
}

grant if {
	op == "linked.read"
	agent
	holding_reader
	is_string(tv("company"))
}
