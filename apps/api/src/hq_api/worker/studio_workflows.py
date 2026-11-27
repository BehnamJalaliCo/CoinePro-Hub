"""Workflows of the media studio (prompt 13 §2; the activities are in
studio_activities.py and ask the launch gate first)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TRIES = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)


@workflow.defn(name="MediaSweep")
class MediaSweep:
    """Every 5 minutes: series schedules, due publishing, the rule re-check."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "media_sweep", start_to_close_timeout=timedelta(minutes=20), retry_policy=TRIES
        )
        return out


@workflow.defn(name="MediaPublish")
class MediaPublish:
    """One item now (an approved card; Instagram polls its container)."""

    @workflow.run
    async def run(self, ref: str) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "media_publish", ref, start_to_close_timeout=timedelta(minutes=15), retry_policy=TRIES
        )
        return out


@workflow.defn(name="MediaUnpublish")
class MediaUnpublish:
    """The owner's sealed request to take an item down."""

    @workflow.run
    async def run(self, ref: str) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "media_unpublish", ref, start_to_close_timeout=timedelta(minutes=5), retry_policy=TRIES
        )
        return out


@workflow.defn(name="TelegramTick")
class TelegramTick:
    """⟨2026-11-19⟩ Every minute: a page's Telegram channel's due posts (each once)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "telegram_tick",
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=1),  # (a send is never repeated by a retry)
        )
        return out


@workflow.defn(name="TrialReelsTick")
class TrialReelsTick:
    """⟨2026-11-26⟩ Every 5 minutes: one Instagram reel's Trial Reel copy, made and set for its hour
    (a copy is sent once: its IG-Hub key is the same on every try)."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "trial_reels_tick",
            start_to_close_timeout=timedelta(minutes=40),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return out


STUDIO_WORKFLOWS = [MediaSweep, MediaPublish, MediaUnpublish, TelegramTick, TrialReelsTick]
