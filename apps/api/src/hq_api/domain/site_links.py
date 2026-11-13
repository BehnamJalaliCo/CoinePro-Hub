"""⟨1.37⟩ Contract §59.5-§59.6 (prompt 38): a company's own links (UTM built by code) and a flow's
reply policy (validated, its public pool filled to ten from the hub's warm pool, in order).

STUB (groundwork): the links-and-replies builder fills this module. The use form (§59.4) calls
`save_links` and `fill_policy`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from hq_api.db import Tx
from hq_api.domain import flow_shapes as FS


async def save_links(
    tx: Tx, company_id: UUID, company: str, links: FS.SiteLinksIn, by_fa: str
) -> FS.SiteLinks:
    """PUT /companies/{code}/site-links: validated (422 `fields.*`), saved, audited."""
    raise NotImplementedError


async def load_links(tx: Tx, company_id: UUID, company: str) -> FS.SiteLinks | None:
    raise NotImplementedError


async def fill_policy(tx: Tx, company: str, policy: FS.ReplyPolicy | None) -> FS.ReplyPolicy:
    """A policy validated against the company's sections (422 `fields.*`) with its public pool
    filled to ten from the hub's pool, the policy's own lines first, order kept."""
    del tx, company
    return policy or FS.ReplyPolicy()


def link_for(links: FS.SiteLinks | None, section: str | None, path: str, flow: str, day: Any) -> str:
    """The reply's link: the section's url (else the site's) + utm_source, utm_medium (the path's),
    utm_campaign (`{flow}`), utm_content (YYYYMMDD); parameters already on the url are kept."""
    raise NotImplementedError
