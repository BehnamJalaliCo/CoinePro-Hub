"""The API's side of Temporal: best-effort starts and signals after commit.

The database is the source of truth; if Temporal is unreachable the worker's
periodic reconciliation (workflow `Maintenance`) catches up, so a request
never fails because of Temporal. Workflows are addressed by name:
    DecisionLifecycle(ref)   id decision-<ref>, signal "decided"
    Reconcile()              id hq-reconcile (schedules, morning report)
    OrderRouting(req)        id order-route-<uuid>, awaited (the only one awaited)
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

log = logging.getLogger("hq_api.workflows_client")

DECISION_WORKFLOW = "DecisionLifecycle"
RECONCILE_WORKFLOW = "Reconcile"
ORDER_WORKFLOW = "OrderRouting"


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


async def route_order(
    hub: Any, req: dict[str, Any], timeout_s: float = 60.0
) -> dict[str, Any] | None:
    """The light model's routing of an order (workflow OrderRouting on the
    worker), awaited; None when Temporal or the model is not there."""
    client = _client(hub)
    if client is None:
        return None
    try:
        out: dict[str, Any] = await client.execute_workflow(
            ORDER_WORKFLOW,
            req,
            id=f"order-route-{uuid.uuid4()}",
            task_queue=hub.settings.task_queue,
            execution_timeout=timedelta(seconds=timeout_s),
        )
    except Exception:  # noqa: BLE001 - the order then goes to the advisor
        log.warning("could not route the order with the model")
        return None
    return out


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


FILE_WORKFLOW = "FileProcess"
TRANSCRIBE_WORKFLOW = "Transcribe"


async def file_uploaded(hub: Any, file_id: str) -> None:
    """A video or audio upload: the worker makes its frames and transcript."""
    client = _client(hub)
    if client is None:
        return
    try:
        await client.start_workflow(
            FILE_WORKFLOW,
            file_id,
            id=f"file-{file_id}",
            task_queue=hub.settings.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )
    except Exception:  # noqa: BLE001 - Maintenance picks up files still processing
        log.warning("could not start file processing", extra={"file": file_id})


async def transcribe(hub: Any, file_id: str, timeout_s: int) -> dict[str, Any]:
    """Runs the transcription on the worker and waits for its result."""
    client = _client(hub)
    if client is None:
        raise RuntimeError("no Temporal client")
    result: dict[str, Any] = await client.execute_workflow(
        TRANSCRIBE_WORKFLOW,
        file_id,
        id=f"transcribe-{file_id}",
        task_queue=hub.settings.task_queue,
        execution_timeout=timedelta(seconds=timeout_s),
    )
    return result
