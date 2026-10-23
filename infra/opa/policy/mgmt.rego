# Prompt 12 part B (contract §21.4, §21.5, §21.9). Part of hq.internal (its
# ops list names them; classes in the api's OP_CLASS: tts.claim A0, tts.done
# A1, claim.verdict A2). The api sends the authenticated principal's charter
# in the target (never input).
#
#   claim.verdict  the fact checker, the overseer and QC (the inspector), all
#                  holding-scope oversight roles; for any company
#   tts.claim      the TTS one-shot (service `tts`) takes a briefing to speak
#   tts.done       ... and sends its audio back (or that it failed)
#
# The holding's monthly HR round is evaluated by its AI Ops head (§21.5): the
# head proposes its `evaluation` cards as a company's HR manager does.
package hq.internal

import rego.v1

claim_checkers := {"fact_checker", "overseer", "inspector"}

grant if {
	op == "claim.verdict"
	oversight_role
	tv("charter") in claim_checkers
}

grant if {
	op in {"tts.claim", "tts.done"}
	service
	p.code == "tts"
}

department_ok("evaluation") if {
	p.department == "AIOPS"
	holding_reader
}
