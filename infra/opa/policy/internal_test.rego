package hq.internal_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

reasons(p, op, t) := r if {
	r := policy.deny_reasons with input as {"principal": p, "op": op, "target": t}
}

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

# ------------------------------------- founding and provisioning (prompt 09) --
hq_aiops := {"kind": "agent", "code": "HQ-AIOPS-MGR", "role": "manager", "company": "HQ", "department": "AIOPS", "scope": "holding"}

provisioner := {"kind": "service", "code": "provisioner", "role": "service", "company": null, "department": null}

test_a_holding_manager_proposes_a_company if {
	allowed(hq_aiops, "decision.propose", {"company": "HQ", "kind": "company_found"})
	not allowed(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "company_found"})
	not allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "company_found"})
}

test_server_plans_for_the_own_company_or_by_a_holding_role if {
	allowed(f.ty_growth_mgr, "provisioning.plan", {"company": "TY"})
	not allowed(f.ty_growth_mgr, "provisioning.plan", {"company": "FX"})
	allowed(f.hq_ovs, "provisioning.plan", {"company": "FX"})
	not allowed(f.svc, "provisioning.plan", {"company": "TY"})
}

# Review 9.2 §2.4: a founding's plan is a holding role's only.
test_a_company_role_never_plans_a_founding if {
	allowed(f.ty_growth_mgr, "provisioning.plan", {"company": "TY", "founding": null})
	not allowed(f.ty_growth_mgr, "provisioning.plan", {"company": "TY", "founding": "C-0001"})
	not allowed(f.ty_ceo, "provisioning.plan", {"company": "TY", "founding": "C-0001"})
	allowed(hq_aiops, "provisioning.plan", {"company": "NX", "founding": "C-0001"})
	allowed(f.hq_ovs, "provisioning.plan", {"company": "TY", "founding": "C-0001"})
}

test_only_the_provisioner_drives_runs if {
	allowed(provisioner, "provisioning.run", {})
	not allowed(f.svc, "provisioning.run", {})
	not allowed(f.ty_ceo, "provisioning.run", {})
	not allowed(f.owner, "provisioning.run", {})
}

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

	# ⟨1.4⟩ N is the overseer's, P the assistant's; no one else posts there
	allowed(f.hq_ovr, "message.post", {"thread_code": "N", "thread_kind": "overseer"})
	allowed(f.hq_pa, "message.post", {"thread_code": "P", "thread_kind": "assistant"})
	not allowed(f.hq_pa, "message.post", {"thread_code": "N", "thread_kind": "overseer"})
	not allowed(f.hq_ovr, "message.post", {"thread_code": "P", "thread_kind": "assistant"})
	not allowed(f.hq_adv, "message.post", {"thread_code": "N", "thread_kind": "overseer"})
	not allowed(f.hq_ovs, "message.post", {"thread_code": "N", "thread_kind": "overseer"})
}

test_inquiries if {
	# the overseer and the advisor ask anyone; a CEO inside its own company only
	allowed(f.hq_ovr, "inquiry.ask", {"company": "FX", "to": "FX-CEO"})
	allowed(f.hq_adv, "inquiry.ask", {"company": "TY", "to": "TY-TECH-MGR"})
	allowed(f.ty_ceo, "inquiry.ask", {"company": "TY", "to": "TY-TECH-MGR"})
	not allowed(f.ty_ceo, "inquiry.ask", {"company": "FX", "to": "FX-CEO"})
	not allowed(f.ty_growth_mgr, "inquiry.ask", {"company": "TY", "to": "TY-GROWTH-01"})
	not allowed(f.hq_adv, "inquiry.ask", {"company": null, "to": "XX-CEO"})
	not allowed(f.svc, "inquiry.ask", {"company": "TY", "to": "TY-CEO"})

	# only the asked one answers, in its own company
	allowed(f.ty_ceo, "inquiry.answer", {"to": "TY-CEO", "company": "TY"})
	not allowed(f.ty_growth_mgr, "inquiry.answer", {"to": "TY-CEO", "company": "TY"})
	not allowed(f.fx_ceo, "inquiry.answer", {"to": "TY-CEO", "company": "TY"})
}

test_errands_are_the_assistants if {
	allowed(f.hq_pa, "errand.write", {"company": "HQ"})
	allowed(f.hq_pa, "planner.add", {"company": "HQ"})
	not allowed(f.hq_adv, "errand.write", {"company": "HQ"})
	not allowed(f.ty_ceo, "planner.add", {"company": "TY"})
	allowed(f.hq_pa, "decision.propose", {"company": "HQ", "kind": "errand_action"})
	not allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "errand_action"})
}

test_holding_readers_read_any_workshop if {
	allowed(f.hq_adv, "workshop.read", {"company": "TY"})
	allowed(f.hq_ovr, "workshop.read", {"company": "FX"})
	reasons(f.ty_growth_01, "workshop.read", {"company": "FX"}) == {"other_company", "workshop.read_not_permitted"}
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

test_backups_status_for_holding_scope_only if {
	allowed(f.hq_ovs, "backup.read", {})
	allowed(f.hq_adv, "backup.read", {})
	reasons(f.ty_ceo, "backup.read", {}) == {"backup.read_not_permitted"}
	not allowed(f.ty_growth_01, "backup.read", {})
}

test_own_memory_run_and_live_thread if {
	allowed(f.ty_growth_01, "file.read", {"company": "TY"})
	not allowed(f.ty_growth_01, "file.read", {"company": "FX"})
	not allowed(f.hq_adv, "file.read", {"company": "TY"})
	allowed(f.ty_ceo, "mcp.call", {"company": "TY"})
	not allowed(f.ty_ceo, "mcp.call", {"company": "FX"})
	not allowed(f.hq_adv, "mcp.call", {"company": "TY"})
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

# Prompt 07 §2: the internet through egress (own company); its log (holding scope).
test_egress_use_and_read if {
	allowed(f.ty_growth_01, "egress.use", {"company": "TY"})
	not allowed(f.ty_growth_01, "egress.use", {"company": "FX"})
	allowed(f.hq_adv, "egress.read", {"company": "TY"})
	allowed(f.hq_ovs, "egress.read", {})
	not allowed(f.ty_ceo, "egress.read", {"company": "TY"})
	not allowed(f.ty_growth_01, "egress.read", {"company": "TY"})
}

# --------------------------------------------------------------- workshop --

session(driver, company) := {"company": company, "driver": driver, "grant": "G-0001"}

test_the_driver_opens_and_steers_its_session if {
	allowed(f.ty_ceo, "workshop.session", session("TY-CEO", "TY"))
	allowed(f.ty_ceo, "workshop.message", session("TY-CEO", "TY"))
	allowed(f.hq_adv, "workshop.session", session("HQ-ADV", "HQ"))
}

test_not_the_driver if {
	reasons(f.ty_growth_mgr, "workshop.session", session("TY-CEO", "TY")) == {"not_driver", "workshop.session_not_permitted"}
	reasons(f.ty_growth_01, "workshop.message", session("TY-CEO", "TY")) == {"not_driver", "workshop.message_not_permitted"}
}

test_a_grant_of_another_company if {
	reasons(f.fx_ceo, "workshop.session", session("FX-CEO", "TY")) == {"other_company", "workshop.session_not_permitted"}
	reasons(f.hq_adv, "workshop.session", session("HQ-ADV", "TY")) == {"other_company", "workshop.session_not_permitted"}
}

test_services_do_not_drive_sessions if {
	reasons(f.svc, "workshop.session", session("TY-CEO", "TY")) == {"workshop.session_not_permitted"}
	not allowed(f.owner, "workshop.session", session("TY-CEO", "TY"))
}

test_agents_read_their_own_company_sessions if {
	allowed(f.ty_growth_01, "workshop.read", {"company": "TY"})
	reasons(f.ty_growth_01, "workshop.read", {"company": "FX"}) == {"other_company", "workshop.read_not_permitted"}
	not allowed(f.svc, "workshop.read", {"company": "TY"})
}

test_code_session_proposals if {
	every agent in [f.ty_ceo, f.ty_growth_mgr, f.ty_growth_01, f.hq_adv] {
		allowed(agent, "decision.propose", {"company": agent.company, "kind": "code_session"})
	}
	not allowed(f.hq_ovs, "decision.propose", {"company": "HQ", "kind": "code_session"})
	not allowed(f.ty_ceo, "decision.propose", {"company": "FX", "kind": "code_session"})
}

test_skills_and_academy_are_holding_roles_only if {
	every op in ["skill.review", "academy.eval", "academy.teach"] {
		allowed(f.hq_ovs, op, {"company": "HQ"})
		allowed(f.hq_adv, op, {"company": "HQ"})
		reasons(f.ty_ceo, op, {"company": "TY"}) == {concat("", [op, "_not_permitted"])}
		not allowed(f.ty_growth_01, op, {"company": "TY"})
		not allowed(f.svc, op, {"company": "HQ"})
	}
}

# ----------------------------------------------- oversight (prompt 08 §2) --
test_the_overseer_raises_and_holds_anywhere if {
	allowed(f.hq_ovr, "oversight.finding_raise", {"company": "TY", "severity": "high"})
	allowed(f.hq_ovr, "oversight.hold", {"kind": "decision"})
	allowed(f.hq_ovs, "oversight.finding_raise", {"company": "FX", "severity": "low"})
	allowed(f.hq_ovs_01, "oversight.hold", {"kind": "session"})
	not allowed(f.ty_ceo, "oversight.finding_raise", {"company": "TY", "severity": "low"})
	not allowed(f.hq_adv, "oversight.hold", {"kind": "decision"})
	not allowed(f.ty_growth_01, "oversight.hold", {"kind": "employee"})
}

test_findings_are_answered_in_their_company_and_verified_by_the_overseer if {
	allowed(f.ty_ceo, "oversight.finding_update", {"company": "TY", "status": "fixed"})
	not allowed(f.ty_ceo, "oversight.finding_update", {"company": "TY", "status": "verified"})
	not allowed(f.fx_ceo, "oversight.finding_update", {"company": "TY", "status": "acknowledged"})
	allowed(f.hq_ovr, "oversight.finding_update", {"company": "TY", "status": "verified"})
}

test_challenges_and_results if {
	allowed(f.hq_ovr, "oversight.challenge_issue", {"company": "TY"})
	not allowed(f.ty_ceo, "oversight.challenge_issue", {"company": "TY"})
	allowed(f.ty_ceo, "oversight.challenge_submit", {"company": "TY"})
	not allowed(f.fx_ceo, "oversight.challenge_submit", {"company": "TY"})
	allowed(f.hq_ovs, "oversight.challenge_score", {"challenge": "CH-0001"})
	allowed(f.hq_ovr, "oversight.protocol_result", {"protocol": "PR-001"})
	not allowed(f.ty_ceo, "oversight.protocol_result", {"protocol": "PR-001"})
}

test_the_overseer_engages_and_freezes_never_releases if {
	allowed(f.hq_ovr, "kill_switch.set", {"scope": "company:FX", "state": "engaged", "current": {}})
	not allowed(f.hq_ovr, "kill_switch.set", {"scope": "company:FX", "state": "released", "current": {"changed_by_kind": "agent", "changed_by_company": "HQ"}})
	not allowed(f.hq_ovr, "kill_switch.set", {"scope": "holding", "state": "engaged", "current": {}})
	allowed(f.hq_ovr, "deploy_freeze.set", {"company": "TY", "lift": false, "freeze": null})
	not allowed(f.hq_ovr, "deploy_freeze.set", {"company": "TY", "lift": true, "freeze": {"created_by_kind": "agent", "created_by_code": "HQ-OVR"}})
	allowed(f.hq_ovr, "decision.propose", {"company": "HQ", "kind": "protocol"})
	not allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": "protocol"})
}
