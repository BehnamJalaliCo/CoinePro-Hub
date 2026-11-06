# ⟨1.19⟩ Prompt 26 (contract §37.3): «پاکش کن» in words. Part of hq.internal (its ops list names
# it; class in the api's OP_CLASS: erase.propose A1).
#
#   erase.propose   every working role (not a system role) proposes erasing a session, an archive
#                   record or an output for good: a card `erase` to the owner. Only what it can
#                   read: the api sends `readable` (an order it works on; an output of its company
#                   or of an order it works on; a record within its clearance) and `company`
#                   (the thing's company, or its own); a holding-scope role reads every company.
#                   An agent never erases anything itself: only the owner's seal does.
package hq.internal

import rego.v1

erase_kinds := {"session", "archive_record", "output"}

grant if {
	op == "erase.propose"
	agent
	p.role != "system"
	tv("kind") in erase_kinds
	tv("readable") == true
	same_company(tv("company"))
}

grant if {
	op == "erase.propose"
	agent
	p.role != "system"
	tv("kind") in erase_kinds
	tv("readable") == true
	holding_reader
}
