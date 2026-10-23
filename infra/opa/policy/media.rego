# Prompt 13, the media half (contract §22.2). Part of hq.internal (its ops
# list names them; classes in the api's OP_CLASS: media.item A1, media.render
# A2, media.review A2, series.propose A1, media.jobs A0). The api sends the
# authenticated principal's charter and the item's company in the target
# (never input). media.voice and the TTS one-shot's queue (voices.claim,
# voices.done) are the voice registry's: legal_voice.rego.
#
#   media.item      the roles that write a step of an item of their company
#   media.render    the composers that preview a composition
#   media.review    the media director only (the `qc` check)
#   series.propose  the media director: a series for the owner's seal
#   media.jobs      the render one-shot (service `media`): claim, files, done
package hq.internal

import rego.v1

media_writers := {"scriptwriter", "video_director", "motion_designer", "visual_designer", "ui_designer"}

media_render_roles := {"motion_designer", "ui_designer"}

grant if {
	op == "media.item"
	agent
	same_company(tv("company"))
	tv("charter") in media_writers
}

grant if {
	op == "media.render"
	agent
	same_company(tv("company"))
	tv("charter") in media_render_roles
}

grant if {
	op in {"media.review", "series.propose"}
	agent
	same_company(tv("company"))
	tv("charter") == "media_director"
}

grant if {
	op == "media.jobs"
	service
	p.code == "media"
}
