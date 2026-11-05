package hq.money_test

import data.hq.money
import rego.v1

owner := {"kind": "owner", "code": "owner", "role": "owner"}

ceo := {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY"}

fin := {"kind": "agent", "code": "TY-FIN-MGR", "role": "manager", "company": "TY", "department": "FIN"}

sales := {"kind": "agent", "code": "TY-SALES-MGR", "role": "manager", "company": "TY", "department": "SALES"}

tech := {"kind": "agent", "code": "TY-TECH-MGR", "role": "manager", "company": "TY", "department": "TECH"}

worker := {"kind": "agent", "code": "TY-FIN-01", "role": "employee", "company": "TY", "department": "FIN"}

advisor := {"kind": "agent", "code": "HQ-ADV", "role": "advisor", "company": "HQ", "scope": "holding"}

service := {"kind": "service", "code": "worker", "role": "service"}

stranger := {"kind": "stranger", "code": "x", "role": "x"}

owner_ops := {"source.write", "source.pull", "usage.read", "usage.make", "lead.write", "lead.draft", "affiliate.receive"}

read_ops := {"source.read", "payment.read", "reconcile.read", "board.read", "lead.read", "affiliate.read"}

on(who, op, co) := {"principal": who, "op": op, "target": {"company": co}}

test_the_owner_may_do_every_op if {
	every op in owner_ops | read_ops {
		money.allow with input as on(owner, op, "TY")
	}
	money.allow with input as on(owner, "payment.read", null)
}

test_the_ceo_and_fin_read_their_own_company if {
	every op in read_ops {
		money.allow with input as on(ceo, op, "TY")
		money.allow with input as on(fin, op, "TY")
	}
}

test_nobody_reads_another_company if {
	every op in read_ops {
		not money.allow with input as on(ceo, op, "CF")
		not money.allow with input as on(fin, op, "CF")
		not money.allow with input as on(ceo, op, null)
	}
	"not_a_reader" in money.deny_reasons with input as on(ceo, "payment.read", "CF")
}

test_no_agent_changes_anything if {
	every op in owner_ops {
		not money.allow with input as on(ceo, op, "TY")
		not money.allow with input as on(fin, op, "TY")
	}
	"owner_only" in money.deny_reasons with input as on(fin, "source.write", "TY")
}

test_other_managers_and_employees_do_not_read_money if {
	not money.allow with input as on(tech, "payment.read", "TY")
	not money.allow with input as on(worker, "board.read", "TY")
	not money.allow with input as on(sales, "payment.read", "TY")
}

test_the_sales_manager_reads_the_leads_only if {
	money.allow with input as on(sales, "lead.read", "TY")
	not money.allow with input as on(sales, "lead.read", "CF")
	not money.allow with input as on(sales, "lead.write", "TY")
}

test_a_paused_reader_reads_nothing if {
	paused := object.union(ceo, {"status": "paused"})
	not money.allow with input as on(paused, "payment.read", "TY")
	paused_sales := object.union(sales, {"status": "dismissed"})
	not money.allow with input as on(paused_sales, "lead.read", "TY")
	paused_advisor := object.union(advisor, {"status": "paused"})
	not money.allow with input as on(paused_advisor, "board.read", "TY")
}

test_the_advisor_reads_every_board_but_nothing_else if {
	money.allow with input as on(advisor, "board.read", "TY")
	money.allow with input as on(advisor, "board.read", "CF")
	not money.allow with input as on(advisor, "board.read", null)
	not money.allow with input as on(advisor, "payment.read", "TY")
	company_advisor := object.union(advisor, {"scope": "company"})
	not money.allow with input as on(company_advisor, "board.read", "TY")
}

test_a_service_reads_nothing_here if {
	not money.allow with input as on(service, "payment.read", "TY")
	"not_a_reader" in money.deny_reasons with input as on(service, "payment.read", "TY")
	"owner_only" in money.deny_reasons with input as on(service, "usage.make", null)
}

test_an_unknown_op_is_refused if {
	not money.allow with input as on(owner, "payment.refund", "TY")
	"unknown_op" in money.deny_reasons with input as on(owner, "payment.refund", "TY")
}

test_an_unknown_principal_is_refused if {
	not money.allow with input as on(stranger, "payment.read", "TY")
	"unknown_principal" in money.deny_reasons with input as on(stranger, "payment.read", "TY")
}

test_a_missing_input_is_refused if {
	not money.allow with input as {}
	not money.allow with input as "nonsense"
}
