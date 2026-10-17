# Who may approve or reject a decision (contract §5.1; OPERATING_MODEL §1.4, §1.12).
#   owner: every kind
#   a company's CEO (agent): recurring_approval within the company's quota, and
#     a3_action "publish" of a post that is in the approved content calendar
#   everything else (deploy, price changes, group/customer messages, ...): owner only
#   services never decide; A4 never appears in a decision
#   nobody decides their own proposal (input.decision.proposer), so a CEO's own
#   recurring proposal goes to the owner
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

proposer := lib.obj(object.get(decision, "proposer", {}))

proposer_code := object.get(proposer, "code", "")

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

# Proposer = approver is always refused, whoever the principal and whatever the kind.
deny_reasons contains "own_proposal" if {
	proposer_code != ""
	proposer_code == p.code
}

# The proposer is part of the input; without it nobody can decide.
deny_reasons contains "unknown_proposer" if not is_string(proposer_code)

deny_reasons contains "unknown_proposer" if proposer_code == ""
