package hq.internal_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

reasons(p, op, t) := r if {
	r := policy.deny_reasons with input as {"principal": p, "op": op, "target": t}
}

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

work(assignee) := {"assignee": assignee, "company": "TY"}

# ------------------------------------------------------- context / activity --

test_agent_reads_and_sets_only_itself if {
	allowed(f.ty_growth_01, "context.read", {"employee": "TY-GROWTH-01"})
	allowed(f.ty_growth_01, "activity.set", {"employee": "TY-GROWTH-01"})
	reasons(f.ty_growth_01, "context.read", {"employee": "TY-CEO"}) == {"context.read_not_permitted"}
}

test_service_reads_and_sets_any_employee if {
	allowed(f.svc, "context.read", {"employee": "FX-CEO"})
	allowed(f.svc, "activity.set", {"employee": "TY-GROWTH-01"})
}

# ------------------------------------------------------------------- work --

test_assignee_works_on_its_work if {
	every op in policy.work_ops {
		allowed(f.ty_growth_01, op, work("TY-GROWTH-01"))
	}
}

test_not_the_assignee if {
	reasons(f.ty_growth_01, "work.deliver", work("TY-GROWTH-02")) == {"not_assignee", "work.deliver_not_permitted"}
}

test_work_of_other_company if {
	reasons(f.ty_growth_01, "work.accept", {"assignee": "TY-GROWTH-01", "company": "FX"}) == {"other_company", "work.accept_not_permitted"}
}

test_services_do_not_work if {
	reasons(f.svc, "work.accept", work("TY-GROWTH-01")) == {"work.accept_not_permitted"}
}

# ------------------------------------------------------------- delegation --

test_ceo_delegates_to_a_manager if {
	allowed(f.ty_ceo, "work.delegate", {"assignee": "TY-CEO", "company": "TY", "to_role": "manager", "to_department": "TECH"})
	reasons(f.ty_ceo, "work.delegate", {"assignee": "TY-CEO", "company": "TY", "to_role": "employee"}) == {"work.delegate_not_permitted"}
}

test_manager_delegates_inside_its_department if {
	allowed(f.ty_growth_mgr, "work.delegate", {"assignee": "TY-GROWTH-MGR", "company": "TY", "to_role": "employee", "to_department": "GROWTH"})
	not allowed(f.ty_growth_mgr, "work.delegate", {"assignee": "TY-GROWTH-MGR", "company": "TY", "to_role": "employee", "to_department": "TECH"})
	not allowed(f.ty_growth_mgr, "work.delegate", {"assignee": "TY-GROWTH-MGR", "company": "TY", "to_role": "manager", "to_department": "GROWTH"})
}

test_employees_and_others_cannot_delegate if {
	reasons(f.ty_growth_01, "work.delegate", {"assignee": "TY-GROWTH-01", "company": "TY", "to_role": "employee", "to_department": "GROWTH"}) == {"work.delegate_not_permitted"}
	not allowed(f.hq_adv, "work.delegate", {"assignee": "HQ-ADV", "company": "HQ", "to_role": "manager"})
	"not_assignee" in reasons(f.ty_ceo, "work.delegate", {"assignee": "TY-GROWTH-MGR", "company": "TY", "to_role": "manager"})
}

test_manager_without_department_cannot_delegate if {
	not allowed(object.union(f.ty_growth_mgr, {"department": null}), "work.delegate", {"assignee": "TY-GROWTH-MGR", "company": "TY", "to_role": "employee", "to_department": null})
}

# ------------------------------------------------------------ work.create --

test_manager_requests_another_department if {
	allowed(f.ty_growth_mgr, "work.create", {"company": "TY", "to_role": "manager", "to_department": "TECH"})
	not allowed(f.ty_growth_mgr, "work.create", {"company": "TY", "to_role": "manager", "to_department": "GROWTH"})
	not allowed(f.ty_growth_mgr, "work.create", {"company": "TY", "to_role": "manager", "to_department": null})
	reasons(f.ty_growth_mgr, "work.create", {"company": "FX", "to_role": "manager", "to_department": "TECH"}) == {"work.create_not_permitted"}
}

test_manager_proposes_recurring_work_in_its_own_department if {
	allowed(f.ty_growth_mgr, "work.create", {"company": "TY", "kind": "recurring", "to_role": "manager", "to_department": "GROWTH"})
	not allowed(f.ty_growth_mgr, "work.create", {"company": "TY", "kind": "one_off", "to_role": "manager", "to_department": "GROWTH"})
	not allowed(f.ty_growth_mgr, "work.create", {"company": "FX", "kind": "recurring", "to_role": "manager", "to_department": "GROWTH"})
	not allowed(f.ty_growth_01, "work.create", {"company": "TY", "kind": "recurring", "to_role": "employee", "to_department": "GROWTH"})
}

test_ceo_creates_work_for_its_managers if {
	allowed(f.ty_ceo, "work.create", {"company": "TY", "to_role": "manager", "to_department": "SALES"})
}

test_cross_company_only_ceo_to_ceo if {
	allowed(f.ty_ceo, "work.create", {"company": "FX", "to_role": "ceo"})
	not allowed(f.ty_ceo, "work.create", {"company": "FX", "to_role": "manager", "to_department": "TECH"})
	not allowed(f.ty_ceo, "work.create", {"company": null, "to_role": "ceo"})
	not allowed(object.union(f.ty_ceo, {"company": null}), "work.create", {"company": "FX", "to_role": "ceo"})
	not allowed(f.ty_growth_01, "work.create", {"company": "TY", "to_role": "manager", "to_department": "TECH"})
	not allowed(f.svc, "work.create", {"company": "TY", "to_role": "manager", "to_department": "TECH"})
}

# ------------------------------------------------------- decision.propose --

test_propose_kinds_by_role if {
	every kind in policy.propose_kinds.ceo - {"budget_change"} {
		allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": kind, "hiring": "open"})
	}
	allowed(f.ty_ceo, "decision.propose", budget("company", "TY"))
	allowed(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "hire", "hiring": "open"})
	allowed(f.ty_growth_01, "decision.propose", {"company": "TY", "kind": "deploy"})
	allowed(f.hq_adv, "decision.propose", {"company": "HQ", "kind": "proposal"})
	allowed(f.hq_ovs, "decision.propose", {"company": "HQ", "kind": "proposal"})
	reasons(f.ty_growth_01, "decision.propose", {"company": "TY", "kind": "hire", "hiring": "open"}) == {"decision.propose_not_permitted"}
	not allowed(f.hq_adv, "decision.propose", {"company": "HQ", "kind": "hire", "hiring": "open"})
	not allowed(f.svc, "decision.propose", {"company": "TY", "kind": "proposal"})
}

# Hiring starts with the owner (contract §18.11): closed, or no state at all, refuses
# an agent's hire; every other kind is unaffected.
test_hire_refused_while_hiring_is_closed if {
	reasons(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "hire", "hiring": "closed"}) == {"hiring_closed"}
	reasons(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "hire"}) == {"hiring_closed"}
	reasons(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "hire", "hiring": "self"}) == {"hiring_closed"}
	allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "hire", "hiring": "open"})
	allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "dismissal", "hiring": "closed"})
	allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "proposal"})
}

test_hr_only_kinds_for_managers if {
	allowed(f.ty_hr_mgr, "decision.propose", {"company": "TY", "kind": "evaluation"})
	allowed(f.ty_hr_mgr, "decision.propose", {"company": "TY", "kind": "dismissal"})
	not allowed(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "evaluation"})
	not allowed(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "dismissal"})
}

test_propose_only_for_own_company if {
	reasons(f.ty_ceo, "decision.propose", {"company": "FX", "kind": "proposal"}) == {"other_company", "decision.propose_not_permitted"}
}

budget(scope_type, ref) := {"company": "TY", "kind": "budget_change", "scope": {"scope_type": scope_type, "scope_ref": ref}}

test_budget_change_stays_inside_the_company if {
	allowed(f.ty_ceo, "decision.propose", budget("company", "TY"))
	allowed(f.ty_ceo, "decision.propose", budget("department", "TY-GROWTH"))
	allowed(f.ty_ceo, "decision.propose", budget("role", "TY:TY-GROWTH-01"))
	allowed(f.ty_ceo, "decision.propose", budget("task_class", "TY:general"))
	reasons(f.ty_ceo, "decision.propose", budget("company", "FX")) == {"scope_outside_company", "decision.propose_not_permitted"}
	not allowed(f.ty_ceo, "decision.propose", budget("department", "FX-GROWTH"))
	not allowed(f.ty_ceo, "decision.propose", budget("role", "advisor"))
	not allowed(f.ty_ceo, "decision.propose", budget("task_class", "FX:general"))
	not allowed(f.ty_ceo, "decision.propose", budget("holding", "HQ"))
	"scope_outside_company" in reasons(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "budget_change"})
}

# ------------------------------------------------------- decision.approve --

test_ceo_approves_through_the_decisions_policy if {
	by_mgr := {"kind": "agent", "code": "TY-GROWTH-MGR"}
	allowed(f.ty_ceo, "decision.approve", {
		"decision": {"kind": "recurring_approval", "company": "TY", "action_class": "A2", "payload": {}, "proposer": by_mgr},
		"context": {"within_quota": true},
	})
	reasons(f.ty_ceo, "decision.approve", {
		"decision": {"kind": "deploy", "company": "TY", "action_class": "A3", "payload": {}, "proposer": by_mgr},
		"context": {},
	}) == {"owner_only"}
	reasons(f.ty_ceo, "decision.approve", {
		"decision": {"kind": "recurring_approval", "company": "TY", "action_class": "A2", "payload": {}, "proposer": {"kind": "agent", "code": "TY-CEO"}},
		"context": {"within_quota": true},
	}) == {"own_proposal"}
	"services_never_decide" in reasons(f.svc, "decision.approve", {"decision": {"kind": "proposal", "company": "TY", "action_class": "A1", "proposer": by_mgr}})
}

# ----------------------------------------------------------- message.post --

test_agent_posts_in_its_own_thread if {
	allowed(f.ty_growth_01, "message.post", {"thread_code": "TY-GROWTH-01", "thread_kind": "employee"})
	reasons(f.ty_growth_01, "message.post", {"thread_code": "TY-GROWTH-02", "thread_kind": "employee"}) == {"message.post_not_permitted"}
}

test_department_group_thread if {
	allowed(f.ty_growth_01, "message.post", {"thread_code": "TY-GROWTH", "thread_kind": "department", "thread_company": "TY", "thread_department": "GROWTH"})
	not allowed(f.ty_growth_01, "message.post", {"thread_code": "TY-TECH", "thread_kind": "department", "thread_company": "TY", "thread_department": "TECH"})
	not allowed(f.ty_ceo, "message.post", {"thread_code": "TY-TECH", "thread_kind": "department", "thread_company": "TY", "thread_department": null})
}

test_advisor_and_ceo_threads if {
	allowed(f.hq_adv, "message.post", {"thread_code": "A", "thread_kind": "advisor"})
	not allowed(f.ty_ceo, "message.post", {"thread_code": "A", "thread_kind": "advisor"})
	allowed(f.ty_ceo, "message.post", {"thread_code": "TY-CEO-2", "thread_kind": "ceo", "thread_company": "TY"})
	not allowed(f.fx_ceo, "message.post", {"thread_code": "TY-CEO", "thread_kind": "ceo", "thread_company": "TY"})
	not allowed(f.svc, "message.post", {"thread_code": "A", "thread_kind": "advisor"})
}

# ----------------------------------------------------- notification.raise --

note(company, level, category, locked) := {"company": company, "level": level, "category": category, "company_locked": locked}

test_notifications if {
	allowed(f.svc, "notification.raise", {"company": "FX"})
	allowed(f.svc, "notification.raise", note("FX", "urgent", null, true))
	allowed(f.ty_growth_mgr, "notification.raise", note("TY", "decision", null, false))
	reasons(f.ty_growth_mgr, "notification.raise", note("FX", "info", null, false)) == {"other_company", "notification.raise_not_permitted"}
	reasons(f.ty_growth_mgr, "notification.raise", note("TY", "loud", null, false)) == {"unknown_level", "notification.raise_not_permitted"}
}

test_agents_raise_urgent_only_for_incidents if {
	every category in policy.incident_categories {
		allowed(f.ty_ceo, "notification.raise", note("TY", "urgent", category, false))
	}
	reasons(f.ty_ceo, "notification.raise", note("TY", "urgent", "marketing", false)) == {"urgent_needs_incident", "notification.raise_not_permitted"}
	reasons(f.ty_ceo, "notification.raise", note("TY", "urgent", null, false)) == {"urgent_needs_incident", "notification.raise_not_permitted"}
}

test_locked_company_raises_only_urgent_incidents if {
	allowed(f.ty_ceo, "notification.raise", note("TY", "urgent", "security", true))
	reasons(f.ty_ceo, "notification.raise", note("TY", "decision", null, true)) == {"company_locked", "notification.raise_not_permitted"}
	reasons(f.ty_ceo, "notification.raise", note("TY", "urgent", "marketing", true)) == {"company_locked", "urgent_needs_incident", "notification.raise_not_permitted"}
	"company_locked" in reasons(f.ty_ceo, "notification.raise", {"company": "TY", "level": "info"})
}

# --------------------------------------------------- kill switch / freeze --

switch(scope, state, by_kind, by_code, by_company) := {
	"scope": scope, "state": state,
	"current": {"state": "engaged", "changed_by_kind": by_kind, "changed_by_code": by_code, "changed_by_company": by_company},
}

test_ceo_engages_only_its_company if {
	allowed(f.ty_ceo, "kill_switch.set", {"scope": "company:TY", "state": "engaged"})
	reasons(f.ty_ceo, "kill_switch.set", {"scope": "company:FX", "state": "engaged"}) == {"kill_switch.set_not_permitted"}
	not allowed(f.ty_ceo, "kill_switch.set", {"scope": "holding", "state": "engaged"})
	not allowed(f.ty_growth_mgr, "kill_switch.set", {"scope": "company:TY", "state": "engaged"})
	not allowed(object.union(f.ty_ceo, {"company": null}), "kill_switch.set", {"scope": "company:", "state": "engaged"})
	not allowed(f.svc, "kill_switch.set", {"scope": "company:TY", "state": "engaged"})
	not allowed(f.ty_ceo, "kill_switch.set", {"scope": "company:TY", "state": "maybe"})
}

test_release_follows_the_engager_authority if {
	allowed(f.ty_ceo, "kill_switch.set", switch("company:TY", "released", "agent", "TY-CEO", "TY"))
	allowed(f.ty_ceo, "kill_switch.set", switch("company:TY", "released", "agent", "TY-TECH-MGR", "TY"))
	reasons(f.ty_ceo, "kill_switch.set", switch("company:TY", "released", "owner", "owner", null)) == {"released_only_by_engager_authority", "kill_switch.set_not_permitted"}
	reasons(f.ty_ceo, "kill_switch.set", switch("company:TY", "released", "agent", "FX-CEO", "FX")) == {"released_only_by_engager_authority", "kill_switch.set_not_permitted"}
	"released_only_by_engager_authority" in reasons(f.ty_ceo, "kill_switch.set", {"scope": "company:TY", "state": "released"})
	not allowed(f.ty_ceo, "kill_switch.set", switch("holding", "released", "agent", "TY-CEO", "TY"))
}

test_releasing_a_released_switch_is_a_no_op if {
	released := {"scope": "company:TY", "state": "released", "current": {"state": "released", "changed_by_kind": "owner", "changed_by_code": "owner", "changed_by_company": null}}
	allowed(f.ty_ceo, "kill_switch.set", released)
	not allowed(f.fx_ceo, "kill_switch.set", released)
	not allowed(f.ty_growth_mgr, "kill_switch.set", released)
}

freeze(company, lift, by_kind, by_code) := {
	"company": company, "lift": lift,
	"freeze": {"created_by_kind": by_kind, "created_by_code": by_code, "created_by_company": company},
}

test_deploy_freeze_set if {
	allowed(f.svc, "deploy_freeze.set", {"company": "TY"})
	allowed(f.svc, "deploy_freeze.set", {"company": "FX", "lift": false})
	allowed(f.ty_ceo, "deploy_freeze.set", {"company": "TY", "lift": false})
	not allowed(f.ty_ceo, "deploy_freeze.set", {"company": "FX"})
	reasons(f.ty_growth_mgr, "deploy_freeze.set", {"company": "TY"}) == {"deploy_freeze.set_not_permitted"}
}

test_deploy_freeze_lift_follows_authority if {
	allowed(f.svc, "deploy_freeze.set", freeze("TY", true, "service", "llm-router"))
	reasons(f.svc, "deploy_freeze.set", freeze("TY", true, "service", "deploy-pipeline")) == {"lifted_only_by_setter_authority", "deploy_freeze.set_not_permitted"}
	reasons(f.svc, "deploy_freeze.set", freeze("TY", true, "owner", "owner")) == {"lifted_only_by_setter_authority", "deploy_freeze.set_not_permitted"}
	reasons(f.svc, "deploy_freeze.set", freeze("TY", true, "agent", "TY-CEO")) == {"lifted_only_by_setter_authority", "deploy_freeze.set_not_permitted"}
	allowed(f.ty_ceo, "deploy_freeze.set", freeze("TY", true, "agent", "TY-CEO"))
	not allowed(f.ty_ceo, "deploy_freeze.set", freeze("TY", true, "agent", "TY-TECH-MGR"))
	not allowed(f.ty_ceo, "deploy_freeze.set", freeze("TY", true, "service", "deploy-pipeline"))
	not allowed(f.ty_ceo, "deploy_freeze.set", freeze("TY", true, "owner", "owner"))
	not allowed(f.ty_ceo, "deploy_freeze.set", freeze("FX", true, "agent", "TY-CEO"))
	"lifted_only_by_setter_authority" in reasons(f.ty_ceo, "deploy_freeze.set", {"company": "TY", "lift": true})
}

# ------------------------------------------------------------ file.upload --

test_file_upload if {
	allowed(f.ty_growth_01, "file.upload", {"company": "TY"})
	reasons(f.ty_growth_01, "file.upload", {"company": "FX"}) == {"other_company", "file.upload_not_permitted"}
	not allowed(f.svc, "file.upload", {"company": "TY"})
}

# ---------------------------------------------------------- cross-cutting --

test_inactive_agents_may_only_read_context if {
	allowed(f.paused(f.ty_growth_01), "context.read", {"employee": "TY-GROWTH-01"})
	reasons(f.paused(f.ty_growth_01), "activity.set", {"employee": "TY-GROWTH-01"}) == {"agent_inactive"}
	reasons(f.dismissed(f.ty_growth_01), "work.deliver", work("TY-GROWTH-01")) == {"agent_inactive"}
}

test_owner_uses_the_public_api if {
	reasons(f.owner, "context.read", {"employee": "TY-CEO"}) == {"owner_uses_public_api", "context.read_not_permitted"}
}

test_unknown_op_and_principal if {
	reasons(f.ty_ceo, "trade.execute", {}) == {"unknown_op"}
	not allowed(f.ty_ceo, "trade.execute", {})
	"unknown_principal" in reasons(f.stranger, "context.read", {"employee": "x"})
	not policy.allow with input as {"op": "context.read", "target": {"employee": ""}}
	not policy.allow with input as []
}

# ------------------------------------------------- prompt 05: gateway reads --

test_reads_stay_in_the_company_unless_holding_scope if {
	every op in {"work.read", "company.read", "health.read", "treasury.read", "knowledge.read"} {
		allowed(f.ty_ceo, op, {"company": "TY"})
		not allowed(f.ty_ceo, op, {"company": "FX"})
		allowed(f.hq_ovs, op, {"company": "FX"})
		allowed(f.hq_adv, op, {"company": "TY"})
	}
	reasons(f.ty_growth_01, "work.read", {"company": "FX"}) == {"work.read_not_permitted"}
	not allowed(f.hq_ovs, "work.read", {"company": null})
	not allowed(f.svc, "work.read", {"company": "TY"})
}

test_only_the_advisor_searches_message_bodies if {
	allowed(f.hq_adv, "knowledge.read", {"company": "TY", "kinds": ["messages", "decisions"]})
	not allowed(f.hq_ovs, "knowledge.read", {"company": "TY", "kinds": ["messages"]})
	allowed(f.hq_ovs, "knowledge.read", {"company": "TY", "kinds": ["resolutions"]})
	not allowed(f.ty_ceo, "knowledge.read", {"company": "TY", "kinds": ["messages"]})
}

test_hub_and_audit_for_holding_scope_only if {
	allowed(f.hq_ovs, "audit.read", {})
	allowed(f.hq_adv, "hub.read", {})
	reasons(f.ty_ceo, "audit.read", {}) == {"audit.read_not_permitted"}
	not allowed(f.ty_ceo, "hub.read", {})
}

test_own_memory_run_and_live_thread if {
	allowed(f.ty_growth_01, "memory.read", {"employee": "TY-GROWTH-01"})
	allowed(f.ty_growth_01, "memory.write", {"employee": "TY-GROWTH-01"})
	not allowed(f.ty_growth_01, "memory.read", {"employee": "TY-GROWTH-02"})
	allowed(f.ty_ceo, "run.reserve", {"employee": "TY-CEO"})
	allowed(f.ty_ceo, "run.record", {"employee": "TY-CEO"})
	not allowed(f.ty_ceo, "run.record", {"employee": "FX-CEO"})
	allowed(f.hq_adv, "thread.live", {"thread_code": "A", "thread_kind": "advisor", "thread_company": "HQ"})
	not allowed(f.ty_ceo, "thread.live", {"thread_code": "A", "thread_kind": "advisor", "thread_company": "HQ"})
	allowed(f.ty_ceo, "thread.live", {"thread_code": "TY-CEO", "thread_kind": "ceo", "thread_company": "TY"})
}

test_inspector_delegates_to_its_team_and_proposes_hires if {
	allowed(f.hq_ovs, "work.delegate", {"assignee": "HQ-OVS-MGR", "company": "HQ", "to_role": "employee", "to_department": "OVS"})
	not allowed(f.hq_ovs, "work.delegate", {"assignee": "HQ-OVS-MGR", "company": "HQ", "to_role": "employee", "to_department": "AIOPS"})
	allowed(f.hq_ovs, "decision.propose", {"company": "HQ", "kind": "hire", "hiring": "open"})
	not allowed(f.hq_ovs, "decision.propose", {"company": "HQ", "kind": "hire"})
	not allowed(f.hq_ovs, "decision.propose", {"company": "HQ", "kind": "deploy"})
	not allowed(f.hq_ovs_01, "work.delegate", {"assignee": "HQ-OVS-01", "company": "HQ", "to_role": "employee", "to_department": "OVS"})
}
