"""Temporal activities of the owned channels and SEO (prompt 22 part 3, contract
§31.3, §31.4). Rule-based: no model is called here.

newsletter_read   hourly (hq-newsletter-read): each company's lists and recent campaigns
                  into growth.metrics_daily (kind `newsletter`); nothing while the
                  newsletter profile is off or the holding is locked
seo_read          daily 05:00 the owner's time (hq-seo-read): our positions (Search
                  Console), the SERP check (SearXNG), the competitors' public figures,
                  their jumps -> a work item for the growth lead
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from hq_api.domain import newsletter as NL
from hq_api.domain import seo as SEO
from hq_api.hub import Hub


class ChannelsActivities:
    def __init__(self, hub: Hub, tx: Any) -> None:
        self.hub = hub
        self._tx = tx

    def all(self) -> list[Any]:
        return [self.newsletter_read, self.seo_read]

    @activity.defn(name="newsletter_read")
    async def newsletter_read(self) -> dict[str, Any]:
        return await NL.read_daily(self.hub)

    @activity.defn(name="seo_read")
    async def seo_read(self) -> dict[str, Any]:
        return await SEO.read_daily(self.hub)
