# OPA's own API (opa run --authorization=basic): the only things any container
# may do are evaluate the hq policies (POST /v1/data/hq/...) and check health.
# Policies and data come only from the mounted files: every PUT, PATCH or
# DELETE on /v1/policies or /v1/data, every GET of data, and the query API are
# refused for everyone.
package system.authz

import rego.v1

default allow := false

allow if {
	input.method == "POST"
	is_array(input.path)
	count(input.path) >= 3
	array.slice(input.path, 0, 3) == ["v1", "data", "hq"]
}

allow if {
	input.method == "GET"
	input.path == ["health"]
}
