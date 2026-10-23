# Prompt 13, the legal and voice half (contract §22.3, §22.4). Part of
# hq.internal (its ops list names them; classes in the api's OP_CLASS:
# legal.case_open/case_note/email_draft A1, legal.mail_read A0, media.voice A2,
# voices.claim A0, voices.done A1). The api sends the authenticated
# principal's charter in the target (never input).
#
#   legal.*        the holding's legal counsel (charter legal_counsel, a
#                  holding role) only; the api adds "its own cases only"
#   media.voice    a company's voice producer, in its own company
#   voices.*       the TTS one-shot (service `tts`): a bake-off sample or a
#                  narration to speak, and its audio back
#   thread L       only its own counsel posts there (the api sends the
#                  thread's employee)
#   work.create    a CEO asks the holding's counsel through a work item to
#                  the holding's LEGAL department (the one cross-company path
#                  that is not CEO to CEO)
package hq.internal

import rego.v1

legal_ops := {"legal.case_open", "legal.case_note", "legal.email_draft", "legal.mail_read"}

counsel if {
	agent
	holding_reader
	tv("charter") == "legal_counsel"
}

grant if {
	op in legal_ops
	counsel
}

grant if {
	op == "media.voice"
	agent
	same_company(tv("company"))
	tv("charter") == "voice_producer"
}

grant if {
	op in {"voices.claim", "voices.done"}
	service
	p.code == "tts"
}

message_ok if {
	tv("thread_kind") == "legal"
	tv("thread_employee") == p.code
}

work_create_ok if {
	p.role == "ceo"
	p.company != null
	tv("company") != p.company
	tv("to_holding") == true
	tv("to_department") == "LEGAL"
	tv("to_role") == "employee"
}
