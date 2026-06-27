"""
Post-commit SOAR playbook orchestration.

Creates inert pending playbook_executions records for committed alerts. It does not
execute steps, enqueue SOAR actions, create approvals, or call integrations.
"""

from __future__ import annotations

import logging
from typing import Any

from core.playbook_store import (
    create_pending_playbook_execution_once,
    set_playbook_execution_canonical_linkage,
)
from core.soar_response_outcomes import (
    append_outcome_event,
    create_response_decision,
    get_latest_outcome_for_alert,
)
from engines.playbook_engine import match_playbooks

logger = logging.getLogger(__name__)


def create_pending_executions_for_committed_alerts(
    alerts_created,
    conn,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    summary = {
        "processed_alerts": 0,
        "matched_playbooks": 0,
        "created": 0,
        "duplicates": 0,
        "skipped": 0,
        "errors": 0,
    }

    for index, alert in enumerate(alerts_created or []):
        if not isinstance(alert, dict):
            logger.warning(
                "[PLAYBOOK ORCHESTRATION SKIP] non-dict alert entry index=%s alert=%r",
                index,
                alert,
            )
            summary["skipped"] += 1
            results.append(
                {
                    "index": index,
                    "alert_id": None,
                    "playbook_id": None,
                    "execution_id": None,
                    "status": "skipped",
                    "skip_reason": "invalid_alert_dict",
                }
            )
            continue

        alert_id = alert.get("alert_id")
        if alert_id is None:
            logger.warning(
                "[PLAYBOOK ORCHESTRATION SKIP] missing alert_id index=%s alert=%r",
                index,
                alert,
            )
            summary["skipped"] += 1
            results.append(
                {
                    "index": index,
                    "alert_id": None,
                    "playbook_id": None,
                    "execution_id": None,
                    "status": "skipped",
                    "skip_reason": "missing_alert_id",
                }
            )
            continue

        summary["processed_alerts"] += 1

        # Get parent soar_correlation_id from alert's existing canonical decision (if any).
        # Used as parent_soar_correlation_id on the new execution-level playbook decision.
        parent_soar_correlation_id = _get_parent_soar_correlation_id(conn, int(alert_id))

        try:
            matches = match_playbooks(conn, int(alert_id))
        except Exception as error:
            logger.exception(
                "[PLAYBOOK ORCHESTRATION ERROR] match failed alert_id=%s index=%s",
                alert_id,
                index,
            )
            summary["errors"] += 1
            results.append(
                {
                    "index": index,
                    "alert_id": alert_id,
                    "playbook_id": None,
                    "execution_id": None,
                    "status": "error",
                    "error": str(error),
                    "error_type": type(error).__name__,
                }
            )
            continue

        if not matches:
            results.append(
                {
                    "index": index,
                    "alert_id": alert_id,
                    "playbook_id": None,
                    "execution_id": None,
                    "status": "no_match",
                }
            )
            continue

        for playbook in matches:
            playbook_id = playbook.get("id")
            if not playbook_id:
                logger.warning(
                    "[PLAYBOOK ORCHESTRATION SKIP] matched playbook missing id alert_id=%s playbook=%r",
                    alert_id,
                    playbook,
                )
                summary["skipped"] += 1
                results.append(
                    {
                        "index": index,
                        "alert_id": alert_id,
                        "playbook_id": None,
                        "execution_id": None,
                        "status": "skipped",
                        "skip_reason": "missing_playbook_id",
                    }
                )
                continue

            summary["matched_playbooks"] += 1
            try:
                execution_id = create_pending_playbook_execution_once(
                    conn,
                    str(playbook_id),
                    int(alert_id),
                    incident_id=None,
                )
            except Exception as error:
                logger.exception(
                    "[PLAYBOOK ORCHESTRATION ERROR] execution insert failed alert_id=%s playbook_id=%s",
                    alert_id,
                    playbook_id,
                )
                summary["errors"] += 1
                results.append(
                    {
                        "index": index,
                        "alert_id": alert_id,
                        "playbook_id": playbook_id,
                        "execution_id": None,
                        "status": "error",
                        "error": str(error),
                        "error_type": type(error).__name__,
                    }
                )
                continue

            duplicate = execution_id is None
            if duplicate:
                logger.info(
                    "[PLAYBOOK ORCHESTRATION] duplicate skipped alert_id=%s playbook_id=%s",
                    alert_id,
                    playbook_id,
                )
                summary["duplicates"] += 1
            else:
                logger.info(
                    "[PLAYBOOK ORCHESTRATION] pending execution created alert_id=%s playbook_id=%s execution_id=%s",
                    alert_id,
                    playbook_id,
                    execution_id,
                )
                summary["created"] += 1
                # Create execution-level canonical decision and link it back.
                # Failures are savepoint-protected and do not abort execution creation.
                _try_create_and_link_playbook_execution_decision(
                    conn,
                    execution_id,
                    playbook_id=str(playbook_id),
                    alert_id=int(alert_id),
                    incident_id=None,
                    parent_soar_correlation_id=parent_soar_correlation_id,
                )

            results.append(
                {
                    "index": index,
                    "alert_id": alert_id,
                    "playbook_id": playbook_id,
                    "execution_id": execution_id,
                    "status": "duplicate" if duplicate else "created",
                }
            )

    return {"summary": summary, "results": results}


def create_and_link_playbook_execution_decision(
    conn,
    execution_id: int,
    *,
    playbook_id: str,
    alert_id: int | None,
    incident_id: int | None = None,
    parent_soar_correlation_id: str | None = None,
    initial_event_type: str = "pending",
    initial_idempotency_key: str | None = None,
    initial_event_metadata: dict | None = None,
) -> dict | None:
    """
    Public entry point: create an execution-level canonical decision with
    decision_source=playbook, write linkage back to playbook_executions, and
    append the initial lifecycle event.

    Used by the retry route and any path that creates a playbook_execution outside
    the ingest orchestrator. Failures are savepoint-protected; never raises.
    """
    return _try_create_and_link_playbook_execution_decision(
        conn,
        execution_id,
        playbook_id=playbook_id,
        alert_id=alert_id,
        incident_id=incident_id,
        parent_soar_correlation_id=parent_soar_correlation_id,
        initial_event_type=initial_event_type,
        initial_idempotency_key=initial_idempotency_key,
        initial_event_metadata=initial_event_metadata,
    )


def _try_create_and_link_playbook_execution_decision(
    conn,
    execution_id: int,
    *,
    playbook_id: str,
    alert_id: int | None,
    incident_id: int | None,
    parent_soar_correlation_id: str | None,
    initial_event_type: str = "pending",
    initial_idempotency_key: str | None = None,
    initial_event_metadata: dict | None = None,
) -> dict | None:
    """
    Create one execution-level soar_response_decisions row per playbook_execution
    (decision_source='playbook'), write decision_id + soar_correlation_id back to
    playbook_executions, and append the initial lifecycle event.

    Phase 1 (create+link) runs under a savepoint so a failure there is a no-op for
    the caller's transaction. Phase 2 (initial event) runs under its own independent
    savepoint so an event-append failure never reverts the already-committed linkage.
    """
    source_ip = _get_alert_source_ip(conn, alert_id)

    # Phase 1: create decision row + write linkage back (atomic under savepoint)
    sp_decision = "canonical_pb_decision"
    sp_decision_created = False
    decision = None
    try:
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {sp_decision}")
        sp_decision_created = True

        decision = create_response_decision(
            conn,
            selected_action="run_playbook",
            decision_source="playbook",
            outcome_summary=f"Playbook {playbook_id} selected for simulated execution.",
            alert_id=alert_id,
            incident_id=incident_id,
            source_ip=source_ip,
            playbook_id=playbook_id,
            playbook_execution_id=execution_id,
            parent_soar_correlation_id=parent_soar_correlation_id,
            safe_metadata={
                "playbook_id": playbook_id,
                "playbook_execution_id": execution_id,
            },
        )
        set_playbook_execution_canonical_linkage(
            conn, execution_id, decision["id"], decision["soar_correlation_id"]
        )
        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {sp_decision}")
        sp_decision_created = False

    except Exception:
        if sp_decision_created:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp_decision}")
                    cur.execute(f"RELEASE SAVEPOINT {sp_decision}")
            except Exception:
                logger.exception(
                    "[PLAYBOOK ORCHESTRATION] savepoint rollback failed execution_id=%s",
                    execution_id,
                )
        logger.exception(
            "[PLAYBOOK ORCHESTRATION] failed to create canonical decision "
            "execution_id=%s playbook_id=%s",
            execution_id,
            playbook_id,
        )
        return None

    # Phase 2: append initial lifecycle event (independent savepoint)
    ikey = initial_idempotency_key or f"playbook-{initial_event_type}-{execution_id}"
    sp_event = "canonical_pb_initial_event"
    sp_event_created = False
    try:
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {sp_event}")
        sp_event_created = True
        append_outcome_event(
            conn,
            decision_id=decision["id"],
            soar_correlation_id=decision["soar_correlation_id"],
            event_type=initial_event_type,
            execution_mode="simulation",
            execution_state="selected",
            simulated=True,
            external_executed=False,
            tracking_recorded=False,
            execution_actor="system",
            reason_code="simulation_mode",
            outcome_summary=f"Playbook {playbook_id} execution created.",
            alert_id=alert_id,
            incident_id=incident_id,
            source_ip=source_ip,
            playbook_execution_id=execution_id,
            idempotency_key=ikey,
            metadata={
                "playbook_id": playbook_id,
                "playbook_execution_id": execution_id,
                **(initial_event_metadata or {}),
            },
        )
        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {sp_event}")
    except Exception:
        if sp_event_created:
            try:
                with conn.cursor() as cur:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp_event}")
                    cur.execute(f"RELEASE SAVEPOINT {sp_event}")
            except Exception:
                pass
        logger.warning(
            "[PLAYBOOK ORCHESTRATION] initial %s event failed for execution_id=%s; "
            "decision was created successfully",
            initial_event_type,
            execution_id,
        )

    return decision


def _get_parent_soar_correlation_id(conn, alert_id: int) -> str | None:
    """
    Return the soar_correlation_id of the alert's existing canonical decision, to be
    used as parent_soar_correlation_id on the new execution-level playbook decision.

    Returns None when no canonical decision exists yet, or on lookup failure.
    """
    try:
        outcome = get_latest_outcome_for_alert(conn, alert_id)
        if outcome is None:
            return None
        return outcome.get("soar_correlation_id")
    except Exception:
        logger.warning(
            "[PLAYBOOK ORCHESTRATION] parent canonical lookup failed alert_id=%s; "
            "playbook decision will be created without parent_soar_correlation_id",
            alert_id,
        )
        return None


def _get_alert_source_ip(conn, alert_id: int | None) -> str | None:
    if alert_id is None:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT host(source_ip) FROM alerts WHERE id = %s", (alert_id,))
        row = cur.fetchone()
    return row[0] if row and row[0] else None
