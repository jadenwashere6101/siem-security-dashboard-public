import logging

from core import soar_response_outcomes as outcomes
from core.ip_helpers import enqueue_response_action
from core.response_action_queue_store import set_queue_linkage


logger = logging.getLogger(__name__)


def enqueue_committed_alerts(alerts_created, conn):
    results = []
    cur = conn.cursor()

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
