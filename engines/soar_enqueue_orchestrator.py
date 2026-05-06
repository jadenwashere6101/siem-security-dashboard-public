import logging

from core.ip_helpers import enqueue_response_action


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
