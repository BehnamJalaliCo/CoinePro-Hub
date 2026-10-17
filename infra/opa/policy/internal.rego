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
	# prompt 05: the Tool Gateway's reads, the employee's memory, the run itself
	"work.read", "company.read", "health.read", "hub.read", "treasury.read",
	"knowledge.read", "audit.read", "memory.read", "memory.write",
	"run.reserve", "run.record", "thread.live",
	# prompt 06: files.read (an owner file attached in the agent's own company)
	"file.read",
	# prompt 07: backups.status (holding-scope roles: the overseer, the platform SRE)
	"backup.read",
	# prompt 06: the Code Workshop, for the driver of a grant
	"workshop.read", "workshop.session", "workshop.message",
	# prompt 07: an MCP tool of a server the owner enabled
	"mcp.call",
	# prompt 07: the agents' internet (a request out, its log; the egress log)
	"egress.use", "egress.read",
}

# Reads of the gateway's tools: an agent reads its own company; a holding-scope
# role (charter scope "holding": oversight, AI operations, the advisor) may
# read every company (never write in another).
read_ops := {"work.read", "company.read", "health.read", "treasury.read", "knowledge.read"}

work_ops := {"work.accept", "work.progress", "work.deliver", "work.fail"}

# Ops whose target must be in the agent's own company.
own_company_ops := work_ops | {
	"work.delegate", "decision.propose", "notification.raise", "file.upload",
	"workshop.read", "workshop.session", "workshop.message",
	"egress.use",
}

# Workshop ops on a grant or a session: its driver only (contract §17.3).
driver_ops := {"workshop.session", "workshop.message"}

# Decision kinds each role may propose (table-driven; change here, not in code).
propose_kinds := {
	"ceo": {
		"hire", "dismissal", "recurring_approval", "deploy",
		"a3_action", "proposal", "budget_change", "evaluation", "code_session",
	},
	"manager": {"hire", "recurring_approval", "a3_action", "deploy", "evaluation", "dismissal", "code_session"},
	"employee": {"a3_action", "deploy", "recurring_approval", "code_session"},
	"advisor": {"proposal", "code_session"},
	"inspector": {"proposal", "hire"},
}

# Data, not code (data.json). Without it nothing that depends on it is allowed.
config := data.hq.config

config_loaded if is_object(config)

# Kinds a role may propose only from one department (monthly HR evaluation,
# dismissal): data hq.config.propose_department, not code.
propose_department := object.get(config, "propose_department", {})

# Categories for which an agent may raise 🔴 urgent (data hq.config).
incident_categories := {c | some c in object.get(config, "incident_categories", [])}

levels := {"urgent", "decision", "report", "info", "learning"}

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
	tv("level") in levels
	urgent_ok
	unlocked_or_incident
}

# A CEO engages its own company's switch ...
grant if {
	op == "kill_switch.set"
	own_switch
	tv("state") == "engaged"
}

# ... and releases it only if an agent of its own company engaged it: a
# switch the owner engaged is released only by the owner (public API, 🔏).
grant if {
	op == "kill_switch.set"
	own_switch
	tv("state") == "released"
	engaged_by_own_agent
}

# Releasing a switch that is already released changes nothing (idempotent).
grant if {
	op == "kill_switch.set"
	own_switch
	tv("state") == "released"
	already_released
}

# Setting a freeze: services (the deploy pipeline) for any company, a CEO for
# its own company.
grant if {
	op == "deploy_freeze.set"
	not lifting
	service
}

grant if {
	op == "deploy_freeze.set"
	not lifting
	agent
	p.role == "ceo"
	same_company(tv("company"))
}

# Lifting follows authority: a service (the pipeline) lifts only the freezes
# it set itself, a CEO only its own; an owner freeze is lifted only by the
# owner (public API).
grant if {
	op == "deploy_freeze.set"
	lifting
	service
	object.get(freeze, "created_by_kind", "") == "service"
	object.get(freeze, "created_by_code", "") == p.code
}

grant if {
	op == "deploy_freeze.set"
	lifting
	agent
	p.role == "ceo"
	same_company(tv("company"))
	object.get(freeze, "created_by_kind", "") == "agent"
	object.get(freeze, "created_by_code", "") == p.code
}

grant if {
	op == "file.upload"
	agent
	same_company(tv("company"))
}

grant if {
	op in read_ops
	agent
	reads_company(tv("company"))
	knowledge_kinds_ok
}

# The internet through the egress service: an agent's own company only.
grant if {
	op == "egress.use"
	agent
	same_company(tv("company"))
}

# The egress log of every company (egress.recent): holding-scope roles only.
grant if {
	op == "egress.read"
	agent
	holding_reader
}

# The hub's own health, the audit trail: holding-scope roles only.
grant if {
	op in {"hub.read", "audit.read", "backup.read"}
	agent
	holding_reader
}

# A file of the agent's own company only (prompt 06 §2: files.read), never
# another company's, whatever the agent's charter scope.
grant if {
	op == "file.read"
	agent
	same_company(tv("company"))
}

# An MCP server's tool (prompt 07 §3): for the agent's own company only; which
# server and tool, and at which class, is the owner's sealed registration.
grant if {
	op == "mcp.call"
	agent
	same_company(tv("company"))
}

# The employee's own memory, its own run, its own thread's live stream.
grant if {
	op in {"memory.read", "memory.write"}
	agent
	tv("employee") == p.code
}

grant if {
	op in {"run.reserve", "run.record"}
	agent
	tv("employee") == p.code
}

grant if {
	op == "thread.live"
	agent
	message_ok
}

# The Code Workshop: an agent reads its own company's sessions; only the
# grant's driver opens a session under it or steers one.
grant if {
	op == "workshop.read"
	agent
	same_company(tv("company"))
}

grant if {
	op in driver_ops
	agent
	same_company(tv("company"))
	tv("driver") == p.code
}

# ------------------------------------------------------------ helpers ----

delegate_ok if {
	p.role == "ceo"
	tv("to_role") == "manager"
}

delegate_ok if {
	p.role in {"manager", "inspector"}
	tv("to_role") == "employee"
	p.department != null
	tv("to_department") == p.department
}

holding_reader if object.get(lib.raw_principal, "scope", "company") == "holding"

reads_company(c) if same_company(c)

reads_company(c) if {
	holding_reader
	is_string(c)
}

# Message bodies (other threads) are searched by the advisor only.
knowledge_kinds_ok if op != "knowledge.read"

knowledge_kinds_ok if {
	op == "knowledge.read"
	not "messages" in {k | some k in object.get(t, "kinds", [])}
}

knowledge_kinds_ok if {
	op == "knowledge.read"
	p.role == "advisor"
}

# A manager asks another department of its own company.
work_create_ok if {
	p.role == "manager"
	same_company(tv("company"))
	tv("to_role") == "manager"
	tv("to_department") != null
	tv("to_department") != p.department
}

# A manager may also propose RECURRING work inside its own department: it
# stays inactive until a recurring_approval decision (owner, or the CEO
# within the company's quota) activates it (OPERATING_MODEL §1.4).
work_create_ok if {
	p.role == "manager"
	same_company(tv("company"))
	tv("kind") == "recurring"
	tv("to_department") == p.department
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
	config_loaded
	kind := tv("kind")
	kind in object.get(propose_kinds, p.role, set())
	department_ok(kind)
	scope_ok(kind)
}

department_ok(kind) if not propose_department[p.role][kind]

department_ok(kind) if propose_department[p.role][kind] == p.department

# budget_change: the scope lies inside the proposer's own company.
scope_ok(kind) if kind != "budget_change"

scope_ok("budget_change") if scope_inside_company

scope := lib.obj(tv("scope"))

scope_ref := object.get(scope, "scope_ref", "")

scope_inside_company if {
	scope.scope_type == "company"
	scope_ref == p.company
}

scope_inside_company if {
	scope.scope_type == "department"
	startswith(scope_ref, concat("", [p.company, "-"]))
}

scope_inside_company if {
	scope.scope_type in {"role", "task_class"}
	startswith(scope_ref, concat("", [p.company, ":"]))
}

urgent_ok if tv("level") != "urgent"

urgent_ok if tv("category") in incident_categories

incident if {
	tv("level") == "urgent"
	tv("category") in incident_categories
}

# Missing lock information counts as locked (the safe side).
company_locked := object.get(t, "company_locked", true) != false

unlocked_or_incident if not company_locked

unlocked_or_incident if incident

own_switch if {
	agent
	p.role == "ceo"
	p.company != null
	tv("scope") == concat("", ["company:", p.company])
}

current := lib.obj(tv("current"))

engaged_by_own_agent if {
	object.get(current, "changed_by_kind", "") == "agent"
	object.get(current, "changed_by_company", null) == p.company
}

already_released if object.get(current, "state", "") == "released"

lifting if tv("lift") == true

freeze := lib.obj(tv("freeze"))

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

# Hiring starts with the owner (contract §18.11): while hiring is closed no
# agent proposes a hire. The api sends the state; missing counts as closed.
deny_reasons contains "hiring_closed" if {
	agent
	op == "decision.propose"
	tv("kind") == "hire"
	tv("hiring") != "open"
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

deny_reasons contains "released_only_by_engager_authority" if {
	op == "kill_switch.set"
	own_switch
	tv("state") == "released"
	not engaged_by_own_agent
	not already_released
}

deny_reasons contains "lifted_only_by_setter_authority" if {
	op == "deploy_freeze.set"
	lifting
	not grant
}

deny_reasons contains "urgent_needs_incident" if {
	op == "notification.raise"
	agent
	tv("level") == "urgent"
	not tv("category") in incident_categories
}

deny_reasons contains "company_locked" if {
	op == "notification.raise"
	agent
	company_locked
	not incident
}

deny_reasons contains "unknown_level" if {
	op == "notification.raise"
	agent
	not tv("level") in levels
}

deny_reasons contains "not_driver" if {
	agent
	op in driver_ops
	tv("driver") != p.code
}

deny_reasons contains "scope_outside_company" if {
	op == "decision.propose"
	agent
	tv("kind") == "budget_change"
	not scope_inside_company
}

# Every other refusal names the operation.
deny_reasons contains sprintf("%s_not_permitted", [op]) if {
	op in ops
	op != "decision.approve"
	not grant
}
