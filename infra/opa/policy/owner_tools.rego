# Prompt 12 §2 and §13 (contract §21.2, §21.10). Part of hq.internal (its ops
# list names them; classes in the api's OP_CLASS: ask.answer A1, dceo.predict
# A0, dceo.principles A1). The api sends the authenticated principal's charter
# in the target (never input).
#
#   ask.answer       the Hub Librarian (system role, holding scope, charter
#                    librarian) answers the owner's ask
#   dceo.predict     the digital CEO (service `dceo`) seals its own prediction
#   dceo.principles  ... and proposes principles for the owner
#
# The red line of §21.10: the digital CEO is a service that never acts. Every
# operation that is not its own `dceo.*` is refused to it here, whatever any
# other rule grants a service (context.read, notification.raise, a freeze);
# decisions.rego already refuses every service a decision.
package hq.internal

import rego.v1

grant if {
	op == "ask.answer"
	agent
	holding_reader
	p.role == "system"
	tv("charter") == "librarian"
}

grant if {
	op in {"dceo.predict", "dceo.principles"}
	service
	p.code == "dceo"
}

deny_reasons contains "dceo_never_acts" if {
	service
	p.code == "dceo"
	not startswith(op, "dceo.")
}
