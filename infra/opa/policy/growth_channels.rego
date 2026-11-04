# ⟨1.13⟩ Prompt 22 part 3 (contract §31.3-§31.5): the owned channels, SEO rank and
# competitors, and the campaign calendar are the OWNER's routes (/api/v1, owner
# session). No agent tool is built on them: an agent reads the figures it needs
# through the connections (connection.read), and a competitor's jump reaches the
# growth lead as a work item, not as a call. These ops are named here so that a
# future tool list cannot reach them by accident: whoever the principal is, on
# /internal/v1 they are refused with a reason that says so.
package hq.internal

import rego.v1

owner_only_growth_ops := {
	"newsletter.read", "newsletter.campaign", "newsletter.send",
	"seo.keyword", "seo.competitor", "seo.rank",
	"campaign.write", "campaign.calendar",
}

deny_reasons contains "owner_only_growth" if op in owner_only_growth_ops
