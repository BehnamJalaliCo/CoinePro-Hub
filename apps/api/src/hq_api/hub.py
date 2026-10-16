"""Everything a request handler needs, built once at startup (app.state.hub)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from hq_api.companies import Companies
from hq_api.config import Settings
from hq_api.db import Database
from hq_api.events import Bus
from hq_api.policy import Policy
from hq_api.ratelimit import RateLimiter
from hq_api.secrets import Secrets
from hq_api.storage import Storage


@dataclass
class Hub:
    settings: Settings
    db: Database
    companies: Companies
    secrets: Secrets
    policy: Policy
    storage: Storage
    bus: Bus | None = None
    limiter: RateLimiter = field(default_factory=RateLimiter)
    temporal: Any = None  # hq_api.workflows_client.Workflows, optional (best effort)
    channels: Any = None  # hq_api.channels.Channels


def get_hub(request: Request) -> Hub:
    hub: Hub = request.app.state.hub
    return hub
