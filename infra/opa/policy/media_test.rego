package hq.media_test

import data.hq.actions
import data.hq.fixtures_test as f
import data.hq.internal as policy
import rego.v1

allowed(p, op, t) if policy.allow with input as {"principal": p, "op": op, "target": t}

acts(p, name) if actions.allow with input as {
	"principal": p,
	"action": {"class": "A2", "name": name, "company": p.company},
	"context": {"escrow_classes": [], "company_locked": false},
}

ty_media_01 := {"kind": "agent", "code": "TY-MEDIA-01", "role": "employee", "company": "TY", "department": "MEDIA"}

ty_media_mgr := {"kind": "agent", "code": "TY-MEDIA-MGR", "role": "manager", "company": "TY", "department": "MEDIA"}

media_svc := {"kind": "service", "code": "media", "role": "service", "company": null, "department": null}

tts := {"kind": "service", "code": "tts", "role": "service", "company": null, "department": null}

test_each_step_is_written_by_its_roles_in_their_own_company if {
	allowed(ty_media_01, "media.item", {"company": "TY", "charter": "scriptwriter"})
	allowed(ty_media_01, "media.item", {"company": "TY", "charter": "motion_designer"})
	not allowed(ty_media_01, "media.item", {"company": "FX", "charter": "scriptwriter"})
	not allowed(ty_media_01, "media.item", {"company": "TY", "charter": "voice_producer"})
	not allowed(ty_media_mgr, "media.item", {"company": "TY", "charter": "media_director"})
	allowed(ty_media_01, "media.render", {"company": "TY", "charter": "motion_designer"})
	not allowed(ty_media_01, "media.render", {"company": "TY", "charter": "scriptwriter"})
	allowed(ty_media_01, "media.voice", {"company": "TY", "charter": "voice_producer"})
	not allowed(ty_media_01, "media.voice", {"company": "TY", "charter": "motion_designer"})
}

test_only_the_media_director_reviews_and_proposes_series if {
	allowed(ty_media_mgr, "media.review", {"company": "TY", "charter": "media_director"})
	allowed(ty_media_mgr, "series.propose", {"company": "TY", "charter": "media_director"})
	not allowed(ty_media_01, "media.review", {"company": "TY", "charter": "motion_designer"})
	not allowed(ty_media_mgr, "media.review", {"company": "FX", "charter": "media_director"})
	not allowed(f.ty_ceo, "series.propose", {"company": "TY", "charter": "ceo"})
	not allowed(f.owner, "media.review", {"company": "TY"})
}

test_the_one_shots_take_only_their_own_queues if {
	allowed(media_svc, "media.jobs", {})
	not allowed(tts, "media.jobs", {})
	allowed(tts, "media.narration", {})
	not allowed(media_svc, "media.narration", {})
	not allowed(f.svc, "media.jobs", {})
	not allowed(ty_media_01, "media.jobs", {"company": "TY"})
}

test_render_voice_and_review_are_a2_grants if {
	acts(ty_media_01, "media.render")
	acts(ty_media_01, "media.voice")
	acts(ty_media_mgr, "media.review")
	not acts(ty_media_01, "media.review")
	acts(f.ty_ceo, "role.decide")
}
