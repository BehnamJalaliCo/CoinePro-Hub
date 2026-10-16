# Who may approve or reject a decision (contract §5.1; OPERATING_MODEL §1.4, §1.12).
#   owner: every kind
#   a company's CEO (agent): recurring_approval within the company's quota, and
#     a3_action "publish" of a post that is in the approved content calendar
#   everything else (deploy, price changes, group/customer messages, ...): owner only
#   services never decide; A4 never appears in a decision
package hq.decisions

import data.hq.lib
import rego.v1

kinds := {
	"hire", "dismissal", "recurring_approval", "deploy",
	"a3_action", "proposal", "budget_change", "evaluation",
}

# Kinds a CEO may decide for its own company (each with its own condition below).
ceo_kinds := {"recurring_approval", "a3_action"}

action_classes := {"A1", "A2", "A3"}

p := lib.principal

decision := lib.obj(object.get(lib.doc, "decision", {}))

ctx := lib.obj(object.get(lib.doc, "context", {}))

kind := object.get(decision, "kind", "")

company := object.get(decision, "company", null)

action_class := object.get(decision, "action_class", "")

payload := lib.obj(object.get(decision, "payload", {}))

default allow := false

allow if {
	grant
	count(deny_reasons) == 0
}

grant if p.kind == "owner"

grant if {
	p.kind == "agent"
	p.role == "ceo"
	kind in ceo_kinds
}

deny_reasons contains "unknown_kind" if not kind in kinds

deny_reasons contains "a4_never_in_decisions" if action_class == "A4"

deny_reasons contains "unknown_action_class" if {
	action_class != "A4"
	not action_class in action_classes
}

deny_reasons contains "unknown_principal" if not p.kind in lib.principal_kinds

deny_reasons contains "services_never_decide" if p.kind == "service"

deny_reasons contains "owner_only" if {
	p.kind == "agent"
	not kind in ceo_kinds
}

deny_reasons contains "ceo_only" if {
	p.kind == "agent"
	kind in ceo_kinds
	p.role != "ceo"
}

deny_reasons contains "other_company" if {
	p.kind == "agent"
	p.company != company
}

deny_reasons contains "other_company" if {
	p.kind == "agent"
	p.company == null
}

deny_reasons contains "agent_inactive" if {
	p.kind == "agent"
	p.status in lib.inactive_statuses
}

deny_reasons contains "outside_quota" if {
	p.kind == "agent"
	kind == "recurring_approval"
	object.get(ctx, "within_quota", false) != true
}

# Price changes, group or customer messages, restarts: owner only.
deny_reasons contains "owner_only_action" if {
	p.kind == "agent"
	kind == "a3_action"
	object.get(payload, "action", "") != "publish"
}

deny_reasons contains "not_in_content_calendar" if {
	p.kind == "agent"
	kind == "a3_action"
	object.get(ctx, "in_content_calendar", false) != true
}
