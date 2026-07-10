import logging

from core import soar_response_outcomes as outcomes
from core.ip_helpers import enqueue_response_action
from core.canonical_action_vocabulary import (
    CanonicalActionValidationError,
    validate_action_for_response_queue,
)
from core.response_action_queue_store import set_queue_linkage


logger = logging.getLogger(__name__)

# Frozen path notice:
# The response-action queue remains for historical processing and compatibility, but
# `soar-automation-path-consolidation-decision` designates the playbook engine as
# the authoritative path for new SOAR automation. New ingest-time automation should
# prefer playbooks; queue retirement/removal requires a separately approved change.


def enqueue_committed_alerts(alerts_created, conn, *, exclude_alert_ids=None):
    results = []
    cur = conn.cursor()
    excluded_ids = _normalize_excluded_alert_ids(exclude_alert_ids)

    for index, alert in enumerate(alerts_created or []):
        if not isinstance(alert, dict):
            logger.warning(
                "[SOAR ENQUEUE WARNING] Skipping non-dict alert entry index=%s alert=%r",
                index,
                alert,
            )
            results.append(
                {
                    "alert_id": None,
                    "source_ip": None,
                    "action": None,
                    "queue_id": None,
                    "skipped": True,
                    "status": "skipped",
                    "skip_reason": "invalid_alert_dict",
                    "index": index,
                }
            )
            continue

        alert_id = alert.get("alert_id")
        source_ip = alert.get("source_ip")
        action = alert.get("response_action")

        normalized_alert_id = _normalize_alert_id(alert_id)
        if normalized_alert_id is not None and normalized_alert_id in excluded_ids:
            source_ip_text = str(source_ip) if source_ip is not None else None
            logger.info(
                "[SOAR ENQUEUE] alert_id=%s skipped by playbook precedence",
                alert_id,
            )
            results.append(
                {
                    "alert_id": alert_id,
                    "source_ip": source_ip_text,
                    "action": action,
                    "queue_id": None,
                    "skipped": True,
                    "status": "skipped",
                    "skip_reason": "playbook_precedence",
                    "index": index,
                }
            )
            continue

        missing_field = _first_missing_required_field(alert_id, source_ip, action)
        if missing_field is not None:
            logger.warning(
                "[SOAR ENQUEUE WARNING] Skipping alert dict missing required field %r index=%s alert=%r",
                missing_field,
                index,
                alert,
            )
            results.append(
                {
                    "alert_id": alert_id,
                    "source_ip": source_ip,
                    "action": action,
                    "queue_id": None,
                    "skipped": True,
                    "status": "skipped",
                    "skip_reason": f"missing_{missing_field}",
                    "index": index,
                }
            )
            continue

        source_ip_text = str(source_ip)
        try:
            action = validate_action_for_response_queue(action)
        except CanonicalActionValidationError as error:
            logger.warning(
                "[SOAR ENQUEUE REJECTED] alert_id=%s action=%s code=%s error=%s",
                alert_id,
                action,
                error.code,
                error,
            )
            results.append(
                {
                    "alert_id": alert_id,
                    "source_ip": source_ip_text,
                    "action": action,
                    "queue_id": None,
                    "skipped": True,
                    "status": "rejected",
                    "skip_reason": error.code,
                    "error": str(error),
                    "index": index,
                }
            )
            continue

        try:
            queue_id = enqueue_response_action(cur, alert_id, source_ip_text, action)
        except Exception as error:
            logger.exception(
                "[SOAR ENQUEUE FAILED] alert_id=%s source_ip=%s action=%s index=%s",
                alert_id,
                source_ip_text,
                action,
                index,
            )
            results.append(
                {
                    "alert_id": alert_id,
                    "source_ip": source_ip_text,
                    "action": action,
                    "queue_id": None,
                    "skipped": True,
                    "status": "error",
                    "skip_reason": "enqueue_exception",
                    "error": str(error),
                    "error_type": type(error).__name__,
                    "index": index,
                }
            )
            continue

        duplicate = queue_id is None
        if duplicate:
            logger.info(
                "[SOAR ENQUEUE] alert_id=%s source_ip=%s action=%s queue_id=None (already enqueued)",
                alert_id,
                source_ip_text,
                action,
            )
        else:
            logger.info(
                "[SOAR ENQUEUE] alert_id=%s source_ip=%s action=%s queue_id=%s",
                alert_id,
                source_ip_text,
                action,
                queue_id,
            )
            _try_write_canonical_enqueue_outcome(
                conn, alert_id, source_ip_text, action, queue_id, alert
            )

        results.append(
            {
                "alert_id": alert_id,
                "source_ip": source_ip_text,
                "action": action,
                "queue_id": queue_id,
                "skipped": duplicate,
                "status": "duplicate_skipped" if duplicate else "enqueued",
                "skip_reason": "duplicate" if duplicate else None,
                "index": index,
            }
        )

    return results


def _normalize_excluded_alert_ids(exclude_alert_ids) -> set[int]:
    normalized: set[int] = set()
    for raw in exclude_alert_ids or []:
        alert_id = _normalize_alert_id(raw)
        if alert_id is not None:
            normalized.add(alert_id)
    return normalized


def _normalize_alert_id(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _first_missing_required_field(alert_id, source_ip, action):
    if alert_id is None:
        return "alert_id"
    if source_ip is None:
        return "source_ip"
    if action is None:
        return "response_action"
    return None


def _infer_decision_source(alert):
    alert_type = (alert.get("alert_type") or "").lower()
    if "correl" in alert_type:
        return "correlation"
    return "detection_default"


def _try_write_canonical_enqueue_outcome(conn, alert_id, source_ip, action, queue_id, alert):
    try:
        decision_source = _infer_decision_source(alert)
        decision = outcomes.create_response_decision(
            conn,
            alert_id=alert_id,
            source_ip=source_ip,
            selected_action=action,
            decision_source=decision_source,
            outcome_summary=(
                f"Response '{action}' selected and queued in simulation mode."
            ),
            queue_id=queue_id,
        )
        set_queue_linkage(
            conn,
            queue_id,
            decision_id=decision["id"],
            soar_correlation_id=decision["soar_correlation_id"],
        )
        outcomes.append_outcome_event(
            conn,
            decision_id=decision["id"],
            execution_mode="simulation",
            execution_state="queued",
            execution_actor="system",
            simulated=True,
            external_executed=False,
            tracking_recorded=False,
            reason_code="simulation_mode",
            outcome_summary=(
                f"Response '{action}' queued in simulation mode. "
                "No real execution has occurred."
            ),
            queue_id=queue_id,
            alert_id=alert_id,
            source_ip=source_ip,
            idempotency_key=f"queue-enqueue-{queue_id}",
        )
    except Exception:
        logger.exception(
            "[SOAR CANONICAL OUTCOME FAILED] alert_id=%s queue_id=%s action=%s",
            alert_id,
            queue_id,
            action,
        )
