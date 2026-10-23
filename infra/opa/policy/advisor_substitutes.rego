# Prompt 12 part A (contract §21.1, §21.13). Part of hq.internal (its ops
# list names them; OP_CLASS gives each its class). The api sends the
# authenticated principal's charter (never input).
#
#   memo.write        the holding's advisor (A1; the api adds: pending cards only)
#   substitute.call   a seat the role may use (A0), in its own company:
#                       advisor    its second and third opinions, long reads,
#                                  quick searches, drafts and a code review
#                       overseer   cross-checks, third opinions, long reads,
#                                  quick searches and a code review
#                       assistant  errands, drafts, long reads, quick searches, creatives
#                       a CEO      drafts, errands, long reads, quick searches,
#                                  creatives and a code review
#                       a CTO, QC  a code review only
#   substitutes.jobs  the runner's host dispatcher (service `substitutes`) only
package hq.internal

import rego.v1

seats_of_kind := {
	"advisor": {"advisor_second_opinion", "third_opinion", "long_read", "quick_search", "content_draft", "code_review"},
	"overseer": {"overseer_cross_check", "third_opinion", "long_read", "quick_search", "code_review"},
	"assistant": {"assistant_errand", "content_draft", "long_read", "quick_search", "creative"},
	"ceo": {"content_draft", "assistant_errand", "long_read", "quick_search", "creative", "code_review"},
}

grant if {
	op == "memo.write"
	agent
	holding_reader
	p.role == "advisor"
	tv("charter") == "advisor"
}

grant if {
	op == "substitute.call"
	agent
	same_company(tv("company"))
	tv("seat") in seats_of_kind[p.role]
}

# A CTO (charter cto) or QC (the inspector) asks for a second code review only.
grant if {
	op == "substitute.call"
	agent
	same_company(tv("company"))
	tv("seat") == "code_review"
	code_reviewer
}

code_reviewer if tv("charter") == "cto"

code_reviewer if p.role == "inspector"

grant if {
	op == "substitutes.jobs"
	service
	p.code == "substitutes"
}
