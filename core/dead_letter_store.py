"""
SOAR dead letter queue persistence helpers.

Callers own transaction boundaries. This module records operator-reviewable
failure context only; it never runs playbooks, sends notifications, or invokes
adapters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg2.extras import Json

from core.notification_delivery_store import (
    redact_notification_delivery_metadata,
    sanitize_failure_message,
)


VALID_SOURCE_TYPES = frozenset(
    {"playbook_execution", "notification_delivery", "response_action", "approval"}
)
VALID_STATUSES = frozenset({"open", "retrying", "retried", "dismissed"})

_RETRYABLE_FAILURE_CLASSES = frozenset(
    {
        "adapter_simulation_failed",
        "adapter_timeout",
        "circuit_breaker_open",
        "circuit_open",
        "provider_rate_limited",
        "rate_limited",
        "temporary_provider_failure",
        "timeout",
        "transient",
        "transient_network_error",
    }
)
_NON_RETRYABLE_FAILURE_CLASSES = frozenset(
    {
        "approval_denied",
        "approval_expired",
        "credential_invalid",
        "credential_missing",
        "guard_failed",
        "invalid_credentials",
        "malformed_payload",
        "non_transient",
        "permanent_provider_rejection",
        "simulation_only",
        "unsupported_action",
        "unknown",
    }
)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _require_text(value: str | None, field_name: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} is required")
    return str(value).strip()


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate_source_type(source_type: str) -> str:
    normalized = _require_text(source_type, "source_type")
    if normalized not in VALID_SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")
    return normalized


def _validate_status(status: str) -> str:
    normalized = _require_text(status, "status")
    if normalized not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
    return normalized


def _validate_source_id(source_id: int) -> int:
    if source_id is None:
        raise ValueError("source_id is required")
    try:
        return int(source_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("source_id must be an integer") from exc


def _validate_optional_nonnegative(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if integer < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return integer


def _validate_bool(value: bool, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


# spec: SPEC-INTEG-005
def classify_dead_letter_retryable(
    failure_class: str | None,
    *,
    source_type: str | None = None,
    status: str | None = None,
) -> bool:
    """Central retryability policy for operator-visible dead letters."""
    normalized_source = str(source_type or "").strip()
    if normalized_source:
        _validate_source_type(normalized_source)
        if normalized_source == "approval":
            return False

    normalized_status = str(status or "open").strip()
    if normalized_status:
        _validate_status(normalized_status)
        if normalized_status in {"retried", "dismissed"}:
            return False

    normalized_failure = str(failure_class or "").strip().lower()
    if normalized_failure in _RETRYABLE_FAILURE_CLASSES:
        return True
    if normalized_failure in _NON_RETRYABLE_FAILURE_CLASSES:
        return False
    return False


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        source_type,
        source_id,
        execution_id,
        incident_id,
        alert_id,
        playbook_id,
        step_index,
        action_name,
        failure_class,
        error_message,
        payload_json,
        retryable,
        status,
        retry_count,
        first_failed_at,
        last_failed_at,
        dismissed_at,
        dismissed_by,
        dismiss_reason,
        retry_requested_at,
        retry_requested_by,
        created_at,
    ) = row
    return {
        "id": row_id,
        "source_type": source_type,
        "source_id": source_id,
        "execution_id": execution_id,
        "incident_id": incident_id,
        "alert_id": alert_id,
        "playbook_id": playbook_id,
        "step_index": step_index,
        "action_name": action_name,
        "failure_class": failure_class,
        "error_message": error_message,
        "payload_json": payload_json if isinstance(payload_json, dict) else {},
        "retryable": retryable,
        "status": status,
        "retry_count": retry_count,
        "first_failed_at": _iso(first_failed_at),
        "last_failed_at": _iso(last_failed_at),
        "dismissed_at": _iso(dismissed_at),
        "dismissed_by": dismissed_by,
        "dismiss_reason": dismiss_reason,
        "retry_requested_at": _iso(retry_requested_at),
        "retry_requested_by": retry_requested_by,
        "created_at": _iso(created_at),
    }


_COLUMNS = (
    "id, source_type, source_id, execution_id, incident_id, alert_id, playbook_id, "
    "step_index, action_name, failure_class, error_message, payload_json, retryable, status, "
    "retry_count, first_failed_at, last_failed_at, dismissed_at, dismissed_by, "
    "dismiss_reason, retry_requested_at, retry_requested_by, created_at"
)


def create_dead_letter(
    conn,
    *,
    source_type: str,
    source_id: int,
    error_message: str,
    failure_class: str = "unknown",
    payload_json: dict[str, Any] | None = None,
    retryable: bool = False,
    execution_id: int | None = None,
    incident_id: int | None = None,
    alert_id: int | None = None,
    playbook_id: str | None = None,
    step_index: int | None = None,
    action_name: str | None = None,
    first_failed_at: datetime | None = None,
    last_failed_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Create or update the active dead letter for a source identity.

    Repeated failures for the same open/retrying source update the existing row
    and preserve first failure time and retry count.
    """
    safe_source_type = _validate_source_type(source_type)
    safe_source_id = _validate_source_id(source_id)
    safe_failure_class = _require_text(failure_class, "failure_class")
    safe_error_message = sanitize_failure_message(_require_text(error_message, "error_message"))
    if safe_error_message is None:
        raise ValueError("error_message is required")
    safe_payload = redact_notification_delivery_metadata(payload_json)
    safe_step_index = _validate_optional_nonnegative(step_index, "step_index")
    safe_retryable = _validate_bool(retryable, "retryable")

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO soar_dead_letters (
                source_type,
                source_id,
                execution_id,
                incident_id,
                alert_id,
                playbook_id,
                step_index,
                action_name,
                failure_class,
                error_message,
                payload_json,
                retryable,
                first_failed_at,
                last_failed_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                COALESCE(%s, NOW()),
                COALESCE(%s, NOW())
            )
            ON CONFLICT (source_type, source_id) WHERE status IN ('open', 'retrying')
            DO UPDATE SET
                execution_id = COALESCE(EXCLUDED.execution_id, soar_dead_letters.execution_id),
                incident_id = COALESCE(EXCLUDED.incident_id, soar_dead_letters.incident_id),
                alert_id = COALESCE(EXCLUDED.alert_id, soar_dead_letters.alert_id),
                playbook_id = COALESCE(EXCLUDED.playbook_id, soar_dead_letters.playbook_id),
                step_index = COALESCE(EXCLUDED.step_index, soar_dead_letters.step_index),
                action_name = COALESCE(EXCLUDED.action_name, soar_dead_letters.action_name),
                failure_class = EXCLUDED.failure_class,
                error_message = EXCLUDED.error_message,
                payload_json = EXCLUDED.payload_json,
                retryable = EXCLUDED.retryable,
                last_failed_at = EXCLUDED.last_failed_at
            RETURNING {_COLUMNS}
            """,
            (
                safe_source_type,
                safe_source_id,
                execution_id,
                incident_id,
                alert_id,
                _optional_text(playbook_id),
                safe_step_index,
                _optional_text(action_name),
                safe_failure_class,
                safe_error_message,
                Json(safe_payload),
                safe_retryable,
                first_failed_at,
                last_failed_at,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("INSERT soar_dead_letters returned no row")
    return _row_to_dict(row)


def get_dead_letter(conn, dead_letter_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM soar_dead_letters WHERE id = %s",
            (dead_letter_id,),
        )
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_dead_letters(
    conn,
    *,
    status: str | None = None,
    source_type: str | None = None,
    failure_class: str | None = None,
    retryable: bool | None = None,
    incident_id: int | None = None,
    alert_id: int | None = None,
    execution_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    cap = min(limit, 500)

    clauses: list[str] = []
    params: list[Any] = []

    if status is not None:
        clauses.append("status = %s")
        params.append(_validate_status(status))
    if source_type is not None:
        clauses.append("source_type = %s")
        params.append(_validate_source_type(source_type))
    if failure_class is not None:
        clauses.append("failure_class = %s")
        params.append(_require_text(failure_class, "failure_class"))
    if retryable is not None:
        clauses.append("retryable = %s")
        params.append(_validate_bool(retryable, "retryable"))
    if incident_id is not None:
        clauses.append("incident_id = %s")
        params.append(incident_id)
    if alert_id is not None:
        clauses.append("alert_id = %s")
        params.append(alert_id)
    if execution_id is not None:
        clauses.append("execution_id = %s")
        params.append(execution_id)

    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    params.extend([cap, offset])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_COLUMNS}
            FROM soar_dead_letters
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def mark_dead_letter_dismissed(
    conn,
    dead_letter_id: int,
    *,
    dismissed_by: int | None,
    reason: str,
    dismissed_at: datetime | None = None,
) -> dict[str, Any] | None:
    safe_reason = sanitize_failure_message(_require_text(reason, "reason"))
    if safe_reason is None:
        raise ValueError("reason is required")

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE soar_dead_letters
            SET status = 'dismissed',
                dismissed_at = COALESCE(%s, NOW()),
                dismissed_by = %s,
                dismiss_reason = %s
            WHERE id = %s
              AND status IN ('open', 'retrying')
            RETURNING {_COLUMNS}
            """,
            (dismissed_at, dismissed_by, safe_reason, dead_letter_id),
        )
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def mark_dead_letter_retry_requested(
    conn,
    dead_letter_id: int,
    *,
    requested_by: int | None,
    retry_requested_at: datetime | None = None,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE soar_dead_letters
            SET status = 'retrying',
                retry_requested_at = COALESCE(%s, NOW()),
                retry_requested_by = %s,
                retry_count = retry_count + 1
            WHERE id = %s
              AND status = 'open'
            RETURNING {_COLUMNS}
            """,
            (retry_requested_at, requested_by, dead_letter_id),
        )
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def mark_dead_letter_retried(
    conn,
    dead_letter_id: int,
) -> dict[str, Any] | None:
    """
    Mark a retry-requested dead letter as retried.

    This is a state transition primitive only. It does not execute retries,
    call adapters, send notifications, or run playbooks. Caller commits.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_COLUMNS}
            FROM soar_dead_letters
            WHERE id = %s
            FOR UPDATE
            """,
            (dead_letter_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        current = _row_to_dict(row)
        if current["status"] != "retrying":
            return None

        cur.execute(
            f"""
            UPDATE soar_dead_letters
            SET status = 'retried'
            WHERE id = %s
              AND status = 'retrying'
            RETURNING {_COLUMNS}
            """,
            (dead_letter_id,),
        )
        updated = cur.fetchone()
    return _row_to_dict(updated) if updated else None


def get_dead_letter_metrics(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*)
            FROM soar_dead_letters
            GROUP BY status
            """
        )
        status_counts = {status: count for status, count in cur.fetchall()}

        cur.execute(
            """
            SELECT source_type, COUNT(*)
            FROM soar_dead_letters
            GROUP BY source_type
            """
        )
        source_type_counts = {source_type: count for source_type, count in cur.fetchall()}

        cur.execute(
            """
            SELECT failure_class, COUNT(*)
            FROM soar_dead_letters
            GROUP BY failure_class
            """
        )
        failure_class_counts = {failure_class: count for failure_class, count in cur.fetchall()}

        cur.execute(
            """
            SELECT COUNT(*), MIN(created_at)
            FROM soar_dead_letters
            WHERE status IN ('open', 'retrying')
            """
        )
        active_count, oldest_active_at = cur.fetchone()

    by_status = {status: status_counts.get(status, 0) for status in sorted(VALID_STATUSES)}
    return {
        "total": sum(status_counts.values()),
        "open": by_status["open"],
        "retrying": by_status["retrying"],
        "retried": by_status["retried"],
        "dismissed": by_status["dismissed"],
        "active": active_count,
        "oldest_active_at": _iso(oldest_active_at),
        "by_status": by_status,
        "by_source_type": source_type_counts,
        "by_failure_class": failure_class_counts,
    }
