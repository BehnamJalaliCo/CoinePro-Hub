"""Workflows of the owned channels and SEO (prompt 22 part 3, contract §31.3, §31.4;
the activities are in channels_activities.py and are rule-based: no model)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=30), maximum_attempts=2)


@workflow.defn(name="NewsletterRead")
class NewsletterRead:
    """Hourly: the newsletter's figures of today (the read is an upsert)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "newsletter_read", start_to_close_timeout=timedelta(minutes=10), retry_policy=TRIES
        )
        return out


@workflow.defn(name="SeoRead")
class SeoRead:
    """Daily: positions, the SERP check, the competitors' public figures."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "seo_read", start_to_close_timeout=timedelta(minutes=40), retry_policy=TRIES
        )
        return out


CHANNELS_WORKFLOWS = [NewsletterRead, SeoRead]
