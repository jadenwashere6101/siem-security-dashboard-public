"""
Post-commit SOAR playbook orchestration.

Creates inert pending playbook_executions records for committed alerts. It does not
execute steps, enqueue SOAR actions, create approvals, or call integrations.
"""

from __future__ import annotations

import logging
from typing import Any

from core.playbook_store import create_pending_playbook_execution_once
from core.soar_response_outcomes import get_latest_outcome_for_alert
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

        decision_id, soar_correlation_id = _resolve_alert_canonical_linkage(conn, int(alert_id))

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
                    decision_id=decision_id,
                    soar_correlation_id=soar_correlation_id,
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


def _resolve_alert_canonical_linkage(
    conn, alert_id: int
) -> tuple[int | None, str | None]:
    """
    Return (decision_id, soar_correlation_id) for the alert's existing canonical decision.

    Uses the latest outcome event for the alert as the lookup path. Returns (None, None)
    when no canonical decision exists yet — callers treat this as a nullable linkage gap
    and the playbook execution is still created without linkage (backward compatible).
    """
    try:
        outcome = get_latest_outcome_for_alert(conn, alert_id)
        if outcome is None:
            return None, None
        return outcome.get("decision_id"), outcome.get("soar_correlation_id")
    except Exception:
        logger.warning(
            "[PLAYBOOK ORCHESTRATION] canonical linkage lookup failed alert_id=%s; "
            "execution will be created without decision_id/soar_correlation_id",
            alert_id,
        )
        return None, None
