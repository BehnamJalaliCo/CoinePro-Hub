"""Workflows of the production lines (prompt 22, contract §30.3; the
activities are in lines_activities.py).

LineRun(ref)        one per run (id line-run-<ref>): its steps one by one; at a
                    gate or a callback it waits for the signal `wake` (the
                    owner's seal, n8n's answer) and looks again every 10
                    minutes by itself
LinesTick()         every 5 minutes (hq-lines-tick)
LineStepTest(...)   the owner's «آزمودن» of one step, awaited by the api
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

TERMINAL = ("done", "failed", "skipped", "cancelled", "missing")
LOOK_AGAIN = timedelta(minutes=10)
STEP_BACKSTOP = timedelta(seconds=7200 + 300)  # templates.MAX_TIMEOUT_S and a margin
LOOPS = 400  # then continue as new: the history stays small
STEP_TRIES = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=5)


@workflow.defn(name="LineRun")
class LineRun:
    def __init__(self) -> None:
        self._woken = False

    @workflow.signal(name="wake")
    def wake(self) -> None:
        self._woken = True

    @workflow.run
    async def run(self, ref: str) -> dict[str, Any]:
        loops = 0
        while True:
            loops += 1
            if loops > LOOPS:
                workflow.continue_as_new(ref)  # the history stays small
            out: dict[str, Any] = await workflow.execute_activity(
                "line_advance",
                ref,
                start_to_close_timeout=STEP_BACKSTOP,
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=STEP_TRIES,
            )
            if out.get("state") in TERMINAL:
                return out
            if out.get("state") == "waiting":
                self._woken = False
                with contextlib.suppress(TimeoutError):  # asyncio's, since 3.11
                    await workflow.wait_condition(lambda: self._woken, timeout=LOOK_AGAIN)


@workflow.defn(name="LinesTick")
class LinesTick:
    """Every 5 minutes: the schedules due, open runs, the 24h / 7d reads."""

    @workflow.run
    async def run(self) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "lines_tick",
            start_to_close_timeout=timedelta(minutes=4),
            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2),
        )
        return out


@workflow.defn(name="LineStepTest")
class LineStepTest:
    """One step of a line alone, now (the owner's «آزمودن»); nothing kept."""

    @workflow.run
    async def run(self, line_ref: str, key: str, given: dict[str, Any] | None) -> dict[str, Any]:
        out: dict[str, Any] = await workflow.execute_activity(
            "line_step_test",
            args=[line_ref, key, given],
            start_to_close_timeout=timedelta(seconds=330),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        return out


LINES_WORKFLOWS = [LineRun, LinesTick, LineStepTest]
