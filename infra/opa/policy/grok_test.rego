package hq.internal_test

import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

split_input(who, t) := {"principal": who, "op": "work.split", "target": t}

managers := [
	{"to_role": "manager", "to_department": "GROWTH"},
	{"to_role": "manager", "to_department": "TECH"},
]

growth_emps := [
	{"to_role": "employee", "to_department": "GROWTH"},
	{"to_role": "employee", "to_department": "GROWTH"},
	{"to_role": "employee", "to_department": "GROWTH"},
]

test_the_ceo_splits_its_work_between_managers if {
	policy.allow with input as split_input(f.ty_ceo, {"company": "TY", "assignee": "TY-CEO", "parts": managers, "max": 3})
}

test_a_manager_splits_between_its_own_department if {
	policy.allow with input as split_input(f.ty_growth_mgr, {"company": "TY", "assignee": "TY-GROWTH-MGR", "parts": growth_emps, "max": 3})
}

test_only_the_assignee_splits if {
	t := {"company": "TY", "assignee": "TY-GROWTH-MGR", "parts": managers, "max": 3}
	not policy.allow with input as split_input(f.ty_ceo, t)
	"not_assignee" in policy.deny_reasons with input as split_input(f.ty_ceo, t)
}

test_no_more_parts_than_the_maximum if {
	t := {"company": "TY", "assignee": "TY-GROWTH-MGR", "parts": growth_emps, "max": 2}
	not policy.allow with input as split_input(f.ty_growth_mgr, t)
	"too_many_parts" in policy.deny_reasons with input as split_input(f.ty_growth_mgr, t)
}

test_a_part_goes_only_where_a_delegation_may if {
	other_dept := [{"to_role": "employee", "to_department": "GROWTH"}, {"to_role": "employee", "to_department": "HR"}]
	t := {"company": "TY", "assignee": "TY-GROWTH-MGR", "parts": other_dept, "max": 3}
	not policy.allow with input as split_input(f.ty_growth_mgr, t)
	"part_not_delegable" in policy.deny_reasons with input as split_input(f.ty_growth_mgr, t)
	ceo_to_emps := {"company": "TY", "assignee": "TY-CEO", "parts": growth_emps, "max": 3}
	not policy.allow with input as split_input(f.ty_ceo, ceo_to_emps)
}

test_an_employee_never_splits if {
	t := {"company": "TY", "assignee": "TY-GROWTH-01", "parts": growth_emps, "max": 3}
	not policy.allow with input as split_input(f.ty_growth_01, t)
}

test_not_in_another_company if {
	t := {"company": "FX", "assignee": "TY-CEO", "parts": managers, "max": 3}
	not policy.allow with input as split_input(f.ty_ceo, t)
}

test_one_part_is_no_split if {
	t := {"company": "TY", "assignee": "TY-CEO", "parts": [managers[0]], "max": 3}
	not policy.allow with input as split_input(f.ty_ceo, t)
}

test_a_service_never_splits if {
	t := {"company": "TY", "assignee": "llm-router", "parts": managers, "max": 3}
	not policy.allow with input as split_input(f.svc, t)
}
