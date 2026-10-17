# Action classes A0..A4 (OPERATING_MODEL §1.12) — the gate for every agent write.
#   owner:   everything, A0..A4, never locked out
#   agent:   own company only; A0 and A1; A2 when the role's grant table (data
#            hq.config.a2_grants) lists the action, or inside its escrow; A3
#            only through a decision; A4 never
#   service: A0..A2; A3 and A4 never
#   company_locked (kill switch or deploy freeze): every non-owner action >= A1,
#   except an agent's 🔴 incident notification (context.incident; hq.internal
#   checks the incident category) and the controls themselves (hq.internal
#   decides who may release a switch or lift a freeze)
package hq.actions

import data.hq.lib
import rego.v1

classes := {"A0", "A1", "A2", "A3", "A4"}

p := lib.principal

action := lib.obj(object.get(lib.doc, "action", {}))

ctx := lib.obj(object.get(lib.doc, "context", {}))

class := object.get(action, "class", "")

company := object.get(action, "company", null)

name := object.get(action, "name", "")

escrow := object.get(ctx, "escrow_classes", [])

# Internal A2 actions each role may take without an escrow (data, not code).
role_a2 := object.get(object.get(data.hq.config, "a2_grants", {}), p.role, [])

a2_ok if name in role_a2

a2_ok if "A2" in escrow

# Missing lock information counts as locked (the safe side, as in hq.internal).
locked := object.get(ctx, "company_locked", true) != false

# The Tool Gateway sends the tool's name (agents/tools.md); the lock rules speak
# of policy actions. This is the one map from the one to the other.
tool_actions := {"notify": "notification.raise"}

policy_action := object.get(tool_actions, name, name)

# A locked company's agent may still raise a 🔴 incident (service down, ...).
lock_exempt if {
	policy_action == "notification.raise"
	object.get(ctx, "incident", false) == true
}

# The controls themselves (kill switch, deploy freeze) are what the lock is
# about: hq.internal decides who may set or release them.
lock_exempt if name in {"kill_switch.set", "deploy_freeze.set"}

default allow := false

allow if {
	grant
	count(deny_reasons) == 0
}

grant if {
	p.kind == "owner"
	class in classes
}

grant if {
	p.kind == "agent"
	class in {"A0", "A1"}
}

grant if {
	p.kind == "agent"
	class == "A2"
	a2_ok
}

grant if {
	p.kind == "service"
	class in {"A0", "A1", "A2"}
}

deny_reasons contains "unknown_class" if not class in classes

deny_reasons contains "unknown_principal" if not p.kind in lib.principal_kinds

deny_reasons contains "a4_forbidden_for_ai" if {
	class == "A4"
	p.kind != "owner"
}

deny_reasons contains "a3_requires_decision" if {
	class == "A3"
	p.kind == "agent"
}

deny_reasons contains "a3_not_for_services" if {
	class == "A3"
	p.kind == "service"
}

deny_reasons contains "a2_needs_role_or_escrow" if {
	class == "A2"
	p.kind == "agent"
	not a2_ok
}

deny_reasons contains "other_company" if {
	p.kind == "agent"
	p.company != company
}

deny_reasons contains "other_company" if {
	p.kind == "agent"
	p.company == null
}

deny_reasons contains "company_locked" if {
	p.kind != "owner"
	locked
	class in classes
	class != "A0"
	not lock_exempt
}

deny_reasons contains "agent_inactive" if {
	p.kind == "agent"
	p.status in lib.inactive_statuses
	class != "A0"
}
