# Shared helpers: the input normalised so that a missing or mistyped field can
# never turn a denial into an allow (every field has a safe default).
package hq.lib

import rego.v1

doc := input if {
	is_object(input)
} else := {}

obj(x) := x if {
	is_object(x)
} else := {}

raw_principal := obj(object.get(doc, "principal", {}))

principal := {
	"kind": object.get(raw_principal, "kind", ""),
	"code": object.get(raw_principal, "code", ""),
	"role": object.get(raw_principal, "role", ""),
	"company": object.get(raw_principal, "company", null),
	"department": object.get(raw_principal, "department", null),
	"status": object.get(raw_principal, "status", "active"),
}

principal_kinds := {"owner", "agent", "service"}

inactive_statuses := {"paused", "dismissed"}
