# ⟨1.15⟩ Prompt 24 (contract §33.1-§33.6): money and sales. Who reads the companies' payments,
# their reconcile, the revenue board, the leads and the affiliate follow-up, and who changes
# anything there. The api asks this before every route of routes/money.py and routes/sales.py,
# and before the agents' read (/internal/v1/money/read). The api sends the target's company
# (a code, or null for every company: the owner's lists only).
#
#   source.read      a company's payment sources (never a key: there is none)
#   source.write     add or change a payment source (🔏 payment.source): the owner only
#   source.pull      read a source now: the owner only
#   payment.read     a company's payments
#   reconcile.read   a company's reconcile by day
#   board.read       the revenue board (code only)
#   usage.read       the holding's usage reports: the owner only
#   usage.make       a usage report now (one model call): the owner only
#   lead.read        a company's leads and its pipeline
#   lead.write       add or change a lead: the owner only
#   lead.draft       a lead's follow-up draft (one model call, never sent): the owner only
#   affiliate.read   due against received commission
#   affiliate.receive what an exchange paid for a month: the owner only
#
# Readers besides the owner: the company's CEO and its FIN manager in their own company; the
# SALES manager reads its company's leads; the holding's advisor reads every company's board.
# Money is read, never moved: no op here approves, refunds or signs anything.
package hq.money

import data.hq.lib
import rego.v1

p := lib.principal

op := object.get(lib.doc, "op", "")

t := lib.obj(object.get(lib.doc, "target", {}))

company := object.get(t, "company", null)

owner_ops := {"source.write", "source.pull", "usage.read", "usage.make", "lead.write", "lead.draft", "affiliate.receive"}

read_ops := {"source.read", "payment.read", "reconcile.read", "board.read", "lead.read", "affiliate.read"}

ops := owner_ops | read_ops

default allow := false

allow if {
	op in ops
	p.kind == "owner"
	count(deny_reasons) == 0
}

allow if {
	reader
	count(deny_reasons) == 0
}

# The company's own readers: its CEO and its FIN manager.
own_company if {
	is_string(company)
	p.company == company
}

active if not p.status in lib.inactive_statuses

company_reader if {
	p.kind == "agent"
	active
	own_company
	p.role == "ceo"
}

company_reader if {
	p.kind == "agent"
	active
	own_company
	p.role == "manager"
	p.department == "FIN"
}

reader if {
	op in read_ops
	company_reader
}

# The SALES manager reads its company's leads and pipeline.
reader if {
	op == "lead.read"
	p.kind == "agent"
	active
	own_company
	p.role == "manager"
	p.department == "SALES"
}

# The holding's advisor reads every company's board (one company at a time).
reader if {
	op == "board.read"
	p.kind == "agent"
	active
	p.role == "advisor"
	object.get(lib.raw_principal, "scope", "company") == "holding"
	is_string(company)
}

deny_reasons contains "unknown_op" if not op in ops

deny_reasons contains "unknown_principal" if not p.kind in lib.principal_kinds

deny_reasons contains "owner_only" if {
	op in owner_ops
	p.kind != "owner"
}

deny_reasons contains "not_a_reader" if {
	op in read_ops
	p.kind != "owner"
	not reader
}
