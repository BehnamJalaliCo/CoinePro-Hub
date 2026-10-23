package system.authz_test

import data.system.authz
import rego.v1

allowed(method, path) if authz.allow with input as {"method": method, "path": path}

test_evaluating_hq_policies_and_health if {
	allowed("POST", ["v1", "data", "hq", "actions"])
	allowed("POST", ["v1", "data", "hq", "internal"])
	allowed("GET", ["health"])
}

test_policy_and_data_writes_are_refused if {
	not allowed("PUT", ["v1", "policies", "x"])
	not allowed("DELETE", ["v1", "policies", "decisions.rego"])
	not allowed("PUT", ["v1", "data", "x"])
	not allowed("PATCH", ["v1", "data", "hq", "config"])
	not allowed("PUT", ["v1", "data", "hq", "config"])
	not allowed("DELETE", ["v1", "data", "hq"])
	not allowed("PATCH", ["v1", "data", "hq", "authority"])
	not allowed("DELETE", ["v1", "data", "hq", "authority"])
	not allowed("PUT", ["v1", "data", "hq", "authority", "rules"])
	not allowed("PUT", ["v1", "data", "hq", "limits"])
}

test_the_authority_matrix_is_the_one_data_write if {
	allowed("PUT", ["v1", "data", "hq", "authority"])
	allowed("POST", ["v1", "data", "hq", "limits", "version"])
}

test_reads_and_other_apis_are_refused if {
	not allowed("GET", ["v1", "data", "hq", "config"])
	not allowed("GET", ["v1", "policies"])
	not allowed("POST", ["v1", "data"])
	not allowed("POST", ["v1", "data", "system", "authz"])
	not allowed("POST", ["v1", "query"])
	not allowed("POST", ["v0", "data", "hq", "actions"])
	not allowed("GET", ["health", "bundles"])
	not authz.allow with input as {"method": "POST", "path": "v1/data/hq/actions"}
}
