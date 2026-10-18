# Stars, lessons, stories and the CEOs' hire decisions (contract §18.4, §18.11,
# §18.12; prompt 08 §4, §8, §9). Part of hq.internal (its ops list names them);
# the action class of each is in hq.actions' a2_grants (data.json).
package hq.internal

import rego.v1

# A CEO writes its own company's rubric and gives its own employees stars.
grant if {
	op in {"star.rubric", "star.give"}
	agent
	p.role == "ceo"
	same_company(tv("company"))
}

# The overseer audits any company's stars.
grant if {
	op == "star.audit"
	agent
	p.role == "overseer"
}

# Lessons: the overseer, or the holding's AI Ops head (its charter, sent by
# the api from the authenticated principal).
grant if {
	op == "lesson.write"
	agent
	p.role == "overseer"
}

grant if {
	op == "lesson.write"
	agent
	holding_reader
	tv("charter") == "aiops_head"
}

# Stories: CEOs, and the holding's heads, in their own company.
story_heads := {"manager", "inspector", "overseer", "advisor"}

grant if {
	op == "story.post"
	agent
	p.role == "ceo"
	same_company(tv("company"))
}

grant if {
	op == "story.post"
	agent
	holding_reader
	p.role in story_heads
	same_company(tv("company"))
}

# A CEO decides a hire card of its own company whose approver it is
# (delegated hiring), its own proposals included.
grant if {
	op == "hire.decide"
	agent
	p.role == "ceo"
	same_company(tv("company"))
	tv("approver") == p.code
}
