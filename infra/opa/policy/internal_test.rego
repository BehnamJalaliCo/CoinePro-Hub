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
	every kind in policy.propose_kinds.ceo {
		allowed(f.ty_ceo, "decision.propose", {"company": "TY", "kind": kind})
	}
	allowed(f.ty_growth_mgr, "decision.propose", {"company": "TY", "kind": "hire"})
	allowed(f.ty_growth_01, "decision.propose", {"company": "TY", "kind": "deploy"})
	allowed(f.hq_adv, "decision.propose", {"company": "HQ", "kind": "proposal"})
	allowed(f.hq_ovs, "decision.propose", {"company": "HQ", "kind": "proposal"})
	reasons(f.ty_growth_01, "decision.propose", {"company": "TY", "kind": "hire"}) == {"decision.propose_not_permitted"}
	not allowed(f.hq_adv, "decision.propose", {"company": "HQ", "kind": "hire"})
	not allowed(f.svc, "decision.propose", {"company": "TY", "kind": "proposal"})
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

# ------------------------------------------------------- decision.approve --

test_ceo_approves_through_the_decisions_policy if {
	allowed(f.ty_ceo, "decision.approve", {
		"decision": {"kind": "recurring_approval", "company": "TY", "action_class": "A2", "payload": {}},
		"context": {"within_quota": true},
	})
	reasons(f.ty_ceo, "decision.approve", {
		"decision": {"kind": "deploy", "company": "TY", "action_class": "A3", "payload": {}},
		"context": {},
	}) == {"owner_only"}
	"services_never_decide" in reasons(f.svc, "decision.approve", {"decision": {"kind": "proposal", "company": "TY", "action_class": "A1"}})
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

test_notifications if {
	allowed(f.svc, "notification.raise", {"company": "FX"})
	allowed(f.ty_growth_mgr, "notification.raise", {"company": "TY"})
	reasons(f.ty_growth_mgr, "notification.raise", {"company": "FX"}) == {"other_company", "notification.raise_not_permitted"}
}

# --------------------------------------------------- kill switch / freeze --

test_ceo_kill_switch_only_for_its_company if {
	allowed(f.ty_ceo, "kill_switch.set", {"scope": "company:TY"})
	reasons(f.ty_ceo, "kill_switch.set", {"scope": "company:FX"}) == {"kill_switch.set_not_permitted"}
	not allowed(f.ty_ceo, "kill_switch.set", {"scope": "holding"})
	not allowed(f.ty_growth_mgr, "kill_switch.set", {"scope": "company:TY"})
	not allowed(object.union(f.ty_ceo, {"company": null}), "kill_switch.set", {"scope": "company:"})
	not allowed(f.svc, "kill_switch.set", {"scope": "company:TY"})
}

test_deploy_freeze if {
	allowed(f.svc, "deploy_freeze.set", {"company": "TY"})
	allowed(f.ty_ceo, "deploy_freeze.set", {"company": "TY"})
	not allowed(f.ty_ceo, "deploy_freeze.set", {"company": "FX"})
	reasons(f.ty_growth_mgr, "deploy_freeze.set", {"company": "TY"}) == {"deploy_freeze.set_not_permitted"}
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
