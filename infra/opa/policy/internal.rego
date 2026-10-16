# What an agent or a service may do on /internal/v1 (contract §12; OPERATING_MODEL §1.4).
# Every agent acts only in its own company, department and role. Delegation is
# a database record (§1.4): a CEO hands work to its managers, a manager to the
# employees of its own department. Cross-company work only from CEO to CEO.
package hq.internal

import data.hq.lib
import rego.v1

ops := {
	"context.read", "activity.set",
	"work.accept", "work.progress", "work.deliver", "work.fail",
	"work.delegate", "work.create",
	"decision.propose", "decision.approve",
	"message.post", "notification.raise",
	"kill_switch.set", "deploy_freeze.set", "file.upload",
}

work_ops := {"work.accept", "work.progress", "work.deliver", "work.fail"}

# Ops whose target must be in the agent's own company.
own_company_ops := work_ops | {"work.delegate", "decision.propose", "notification.raise", "file.upload"}

# Decision kinds each role may propose (table-driven; change here, not in code).
propose_kinds := {
	"ceo": {
		"hire", "dismissal", "recurring_approval", "deploy",
		"a3_action", "proposal", "budget_change", "evaluation",
	},
	"manager": {"hire", "recurring_approval", "a3_action", "deploy", "evaluation", "dismissal"},
	"employee": {"a3_action", "deploy", "recurring_approval"},
	"advisor": {"proposal"},
	"inspector": {"proposal"},
}

# Kinds a role may propose only from one department (monthly HR evaluation, dismissal).
propose_department := {"manager": {"evaluation": "HR", "dismissal": "HR"}}

p := lib.principal

t := lib.obj(object.get(lib.doc, "target", {}))

op := object.get(lib.doc, "op", "")

tv(key) := object.get(t, key, null)

agent if p.kind == "agent"

service if p.kind == "service"

same_company(c) if {
	p.company != null
	c == p.company
}

default allow := false

allow if {
	grant
	count(deny_reasons) == 0
}

# ------------------------------------------------------------ grants ----

grant if {
	op in {"context.read", "activity.set"}
	service
}

grant if {
	op in {"context.read", "activity.set"}
	agent
	tv("employee") == p.code
}

grant if {
	op in work_ops
	agent
	tv("assignee") == p.code
	same_company(tv("company"))
}

grant if {
	op == "work.delegate"
	agent
	tv("assignee") == p.code
	same_company(tv("company"))
	delegate_ok
}

grant if {
	op == "work.create"
	agent
	work_create_ok
}

grant if {
	op == "decision.propose"
	agent
	same_company(tv("company"))
	propose_ok
}

grant if {
	op == "decision.approve"
	data.hq.decisions.allow with input as approve_input
}

grant if {
	op == "message.post"
	agent
	message_ok
}

grant if {
	op == "notification.raise"
	service
}

grant if {
	op == "notification.raise"
	agent
	same_company(tv("company"))
}

grant if {
	op == "kill_switch.set"
	agent
	p.role == "ceo"
	p.company != null
	tv("scope") == concat("", ["company:", p.company])
}

grant if {
	op == "deploy_freeze.set"
	service
}

grant if {
	op == "deploy_freeze.set"
	agent
	p.role == "ceo"
	same_company(tv("company"))
}

grant if {
	op == "file.upload"
	agent
	same_company(tv("company"))
}

# ------------------------------------------------------------ helpers ----

delegate_ok if {
	p.role == "ceo"
	tv("to_role") == "manager"
}

delegate_ok if {
	p.role == "manager"
	tv("to_role") == "employee"
	p.department != null
	tv("to_department") == p.department
}

# A manager asks another department of its own company.
work_create_ok if {
	p.role == "manager"
	same_company(tv("company"))
	tv("to_role") == "manager"
	tv("to_department") != null
	tv("to_department") != p.department
}

# A CEO hands work to a manager of its own company ...
work_create_ok if {
	p.role == "ceo"
	same_company(tv("company"))
	tv("to_role") == "manager"
}

# ... or asks another company's CEO (the only cross-company path).
work_create_ok if {
	p.role == "ceo"
	p.company != null
	tv("company") != null
	tv("company") != p.company
	tv("to_role") == "ceo"
}

propose_ok if {
	kind := tv("kind")
	kind in object.get(propose_kinds, p.role, set())
	department_ok(kind)
}

department_ok(kind) if not propose_department[p.role][kind]

department_ok(kind) if propose_department[p.role][kind] == p.department

message_ok if tv("thread_code") == p.code

message_ok if {
	tv("thread_kind") == "department"
	same_company(tv("thread_company"))
	p.department != null
	tv("thread_department") == p.department
}

message_ok if {
	p.role == "advisor"
	tv("thread_kind") == "advisor"
}

message_ok if {
	p.role == "ceo"
	tv("thread_kind") == "ceo"
	same_company(tv("thread_company"))
}

approve_input := {
	"principal": object.get(lib.doc, "principal", {}),
	"decision": object.get(t, "decision", {}),
	"context": object.get(t, "context", {}),
}

# ------------------------------------------------------------ denials ----

deny_reasons contains "unknown_op" if not op in ops

deny_reasons contains "unknown_principal" if not p.kind in lib.principal_kinds

deny_reasons contains "owner_uses_public_api" if p.kind == "owner"

deny_reasons contains "agent_inactive" if {
	agent
	p.status in lib.inactive_statuses
	op != "context.read"
}

deny_reasons contains "other_company" if {
	agent
	op in own_company_ops
	not same_company(tv("company"))
}

deny_reasons contains "not_assignee" if {
	agent
	op in (work_ops | {"work.delegate"})
	tv("assignee") != p.code
}

deny_reasons contains reason if {
	op == "decision.approve"
	reasons := data.hq.decisions.deny_reasons with input as approve_input
	some reason in reasons
}

# Every other refusal names the operation.
deny_reasons contains sprintf("%s_not_permitted", [op]) if {
	op in ops
	op != "decision.approve"
	not grant
}
