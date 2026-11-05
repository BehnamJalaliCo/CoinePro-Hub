# ⟨1.15⟩ Prompt 24 (contract §33.7): agents in parallel. Part of hq.internal (its ops list names
# `work.split`; class A1 in the api's OP_CLASS). The api sends the parent work's company and
# assignee, the most parts allowed (`max`, data: PARALLEL_MAX) and, for every part, the kind and
# department of the employee who would receive it; never the parts' text. Code has already refused
# parts that depend on each other.
#
#   work.split   the parent's assignee only, in its own company; at most `max` parts; each part
#                goes where a delegation of this assignee may go (a CEO to its managers, a
#                manager to the employees of its own department)
package hq.internal

import rego.v1

grant if {
	op == "work.split"
	agent
	tv("assignee") == p.code
	same_company(tv("company"))
	is_array(tv("parts"))
	count(tv("parts")) >= 2
	every part in tv("parts") {
		split_part_ok(part)
	}
}

split_part_ok(part) if {
	p.role == "ceo"
	part.to_role == "manager"
}

split_part_ok(part) if {
	p.role in {"manager", "inspector"}
	part.to_role == "employee"
	p.department != null
	part.to_department == p.department
}

deny_reasons contains "not_assignee" if {
	agent
	op == "work.split"
	tv("assignee") != p.code
}

deny_reasons contains "too_many_parts" if {
	op == "work.split"
	count(tv("parts")) > tv("max")
}

deny_reasons contains "part_not_delegable" if {
	agent
	op == "work.split"
	some part in tv("parts")
	not split_part_ok(part)
}
