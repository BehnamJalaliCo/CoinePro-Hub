"""The API's side of Temporal: best-effort starts and signals after commit.

The database is the source of truth; if Temporal is unreachable the worker's
periodic reconciliation (workflow `Maintenance`) catches up, so a request
never fails because of Temporal. Workflows are addressed by name:
    DecisionLifecycle(ref)   id decision-<ref>, signal "decided"
    Reconcile()              id hq-reconcile (schedules, morning report)
"""

from __future__ import annotations

import logging
from typing import Any

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

log = logging.getLogger("hq_api.workflows_client")

DECISION_WORKFLOW = "DecisionLifecycle"
RECONCILE_WORKFLOW = "Reconcile"


async def connect(address: str, namespace: str) -> Client:
    return await Client.connect(address, namespace=namespace)


def _client(hub: Any) -> Client | None:
    client: Client | None = getattr(hub, "temporal", None)
    return client


async def decision_created(hub: Any, ref: str) -> None:
    client = _client(hub)
    if client is None:
        return
    try:
        await client.start_workflow(
            DECISION_WORKFLOW,
            ref,
            id=f"decision-{ref}",
            task_queue=hub.settings.task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
    except Exception:  # noqa: BLE001 - reconciled later by Maintenance
        log.warning("could not start the decision workflow", extra={"ref": ref})


async def decision_decided(hub: Any, ref: str) -> None:
    client = _client(hub)
    if client is None:
        return
    try:
        await client.start_workflow(
            DECISION_WORKFLOW,
            ref,
            id=f"decision-{ref}",
            task_queue=hub.settings.task_queue,
            start_signal="decided",
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
    except Exception:  # noqa: BLE001 - reconciled later by Maintenance
        log.warning("could not signal the decision workflow", extra={"ref": ref})


async def reconcile(hub: Any) -> None:
    """Schedules changed (recurring work, morning report time): sync now."""
    client = _client(hub)
    if client is None:
        return
    try:
        await client.start_workflow(
            RECONCILE_WORKFLOW,
            id="hq-reconcile",
            task_queue=hub.settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
    except Exception:  # noqa: BLE001 - the periodic run catches up
        log.warning("could not start reconciliation")
