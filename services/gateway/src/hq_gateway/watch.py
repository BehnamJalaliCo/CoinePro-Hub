"""⟨1.10⟩ Prompt 19 (contract §28.2-§28.3): the company catalogue and the apps'
own error reports, as tools.

    company.catalogue (A1)  {company?, start?}: the company's latest deep
                            catalogue; `start` (or none yet) starts a run on
                            every paired server (read-only jobs). A CEO for
                            its own company (an order to "go through the
                            server and extract everything" is this, never a
                            summary of its own); the overseer, the advisor
                            and the platform SRE for any company.
    client.errors (A0)      {app?, version?, from?}: the apps' error log,
                            newest first (the overseer's daily app health).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hq_gateway import tools as T


class CatalogueIn(T.In):
    company: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}$")
    start: bool = False


class ClientErrorsIn(T.In):
    app: Literal["android", "web"] | None = None
    version: str | None = Field(default=None, max_length=60)
    from_: datetime | None = Field(default=None, alias="from")


async def company_catalogue(api: T.Api, call: T.Call, a: CatalogueIn) -> T.Result:
    resp = await api.request(
        "POST",
        "/internal/v1/catalogue",
        call.token,
        json=a.model_dump(mode="json", exclude_none=True),
        idem=call.idem("company.catalogue"),
    )
    r = T.from_response(resp, "company")
    if r.outcome == "ok" and isinstance(r.data, dict):
        r.ref = f"catalogue:{r.data.get('company')}"
    return r


async def client_errors(api: T.Api, call: T.Call, a: ClientErrorsIn) -> T.Result:
    params = {
        k: v
        for k, v in {
            "app": a.app,
            "version": a.version,
            "from": a.from_.isoformat() if a.from_ else None,
        }.items()
        if v is not None
    }
    return T.from_response(
        await api.request("GET", "/internal/v1/client/errors", call.token, params=params), None
    )


TOOLS: dict[str, tuple[type[T.In], T.Handler]] = {
    "company.catalogue": (CatalogueIn, company_catalogue),
    "client.errors": (ClientErrorsIn, client_errors),
}
T.TOOLS.update(TOOLS)
