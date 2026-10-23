# Prompt 14 (contract §23.11): the archive's agent tools. Part of hq.internal
# (its ops list names them; classes in the api's OP_CLASS: archive.search and
# archive.read A0, archive.file and archive.link A1, archive.hold A2, which is
# in the employee's A2 grants of data.json). The api sends the authenticated
# principal's charter in the target (never input) and re-checks the reader's
# clearance itself (archive.can_see, under RLS).
#
#   archive.search · archive.read · archive.file · archive.link
#                  the archivist (HQ-ARC, a system role of the holding) and
#                  the holding's legal counsel: holding roles only
#   archive.hold   the legal counsel only, and only with its case (LC-…)
package hq.internal

import rego.v1

archive_ops := {"archive.search", "archive.read", "archive.file", "archive.link"}

archive_roles := {"archivist", "legal_counsel"}

archive_reader if {
	agent
	holding_reader
	tv("charter") in archive_roles
}

grant if {
	op in archive_ops
	archive_reader
}

grant if {
	op == "archive.hold"
	counsel
	is_string(tv("case"))
	regex.match(`^LC-[0-9]{4,}$`, tv("case"))
}
