# Principals shared by the tests.
package hq.fixtures_test

import rego.v1

owner := {"kind": "owner", "code": "owner", "role": "owner", "company": null, "department": null}

ty_ceo := {"kind": "agent", "code": "TY-CEO", "role": "ceo", "company": "TY", "department": null}

fx_ceo := {"kind": "agent", "code": "FX-CEO", "role": "ceo", "company": "FX", "department": null}

ty_growth_mgr := {"kind": "agent", "code": "TY-GROWTH-MGR", "role": "manager", "company": "TY", "department": "GROWTH"}

ty_hr_mgr := {"kind": "agent", "code": "TY-HR-MGR", "role": "manager", "company": "TY", "department": "HR"}

ty_growth_01 := {"kind": "agent", "code": "TY-GROWTH-01", "role": "employee", "company": "TY", "department": "GROWTH"}

hq_adv := {"kind": "agent", "code": "HQ-ADV", "role": "advisor", "company": "HQ", "department": null}

hq_ovs := {"kind": "agent", "code": "HQ-OVS-MGR", "role": "inspector", "company": "HQ", "department": "OVS"}

svc := {"kind": "service", "code": "llm-router", "role": "service", "company": null, "department": null}

stranger := {"kind": "robot", "code": "x", "role": "x", "company": "TY", "department": null}

paused(p) := object.union(p, {"status": "paused"})

dismissed(p) := object.union(p, {"status": "dismissed"})
