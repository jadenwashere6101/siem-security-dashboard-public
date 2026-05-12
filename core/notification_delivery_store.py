"""
Immutable notification delivery attempt persistence (simulation and future real).

Callers own transaction boundaries (commit/rollback). This module never commits.
Records are append-only: create and read/list only — no update helpers.

Do not persist webhooks, tokens, headers, raw payloads, or raw provider responses.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

_VALID_MODES = frozenset({"simulation", "real"})
_VALID_STATUSES = frozenset({"pending", "success", "failed", "timeout", "blocked"})
_VALID_CIRCUIT_STATES = frozenset({"closed", "open", "half_open", "unknown", "invalid"})

# spec: SPEC-NOTIFY-001
# Keys (case-insensitive) and substrings in keys that must never be stored.
_METADATA_KEY_DENYLIST = frozenset(
    {
        "authorization",
        "cookie",
        "cookies",
        "headers",
        "raw_payload",
        "raw_response",
        "webhook_url",
        "slack_webhook_url",
        "teams_webhook_url",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "api_key",
        "apikey",
    }
)
_METADATA_KEY_SUBSTRING_DENY = (
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "bearer",
    "api_key",
    "apikey",
    "_url",
    "slack_webhook",
    "teams_webhook",
)


def _unsafe_metadata_key_extra(lk: str) -> bool:
    """Webhook-related secret keys; allow safe flags like webhook_configured."""
    if "webhook_url" in lk:
        return True
    if lk in ("webhook", "incoming_webhook", "incoming_webhook_url"):
        return True
    if lk.endswith("_webhook_url") or lk.endswith("webhookurl"):
        return True
    return False

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _unsafe_metadata_key(key: str) -> bool:
    lk = key.lower()
    if lk in _METADATA_KEY_DENYLIST:
        return True
    if _unsafe_metadata_key_extra(lk):
        return True
    return any(part in lk for part in _METADATA_KEY_SUBSTRING_DENY)


def _sanitize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        if _URL_RE.search(value):
            return "[REDACTED_URL]"
        return value
    if isinstance(value, dict):
        return redact_notification_delivery_metadata(value)
    if isinstance(value, list):
        return [_sanitize_scalar(v) for v in value]
    return value


def redact_notification_delivery_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return a shallow-deep copy of metadata with unsafe keys removed and string values
    scrubbed of URL-like content. Intended for values persisted to JSONB.
    """
    if not metadata:
        return {}
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dict or None")
    out: dict[str, Any] = {}
    for key, value in metadata.items():
        if _unsafe_metadata_key(key):
            continue
        out[key] = _sanitize_scalar(copy.deepcopy(value))
    return out


def sanitize_failure_message(message: str | None) -> str | None:
    """Remove URL-like segments from operator-facing failure text before persistence."""
    if message is None:
        return None
    text = message.strip()
    if not text:
        return None
    scrubbed = _URL_RE.sub("[REDACTED_URL]", text)
    return scrubbed if scrubbed else None


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        correlation_id,
        idempotency_key,
        provider,
        mode,
        status,
        playbook_execution_id,
        playbook_step_index,
        incident_id,
        approval_request_id,
        alert_id,
        adapter_name,
        action,
        requested_at,
        started_at,
        completed_at,
        created_at,
        failure_code,
        failure_message,
        timeout_seconds,
        circuit_breaker_state,
        metadata,
    ) = row
    return {
        "id": row_id,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "provider": provider,
        "mode": mode,
        "status": status,
        "playbook_execution_id": playbook_execution_id,
        "playbook_step_index": playbook_step_index,
        "incident_id": incident_id,
        "approval_request_id": approval_request_id,
        "alert_id": alert_id,
        "adapter_name": adapter_name,
        "action": action,
        "requested_at": _iso(requested_at),
        "started_at": _iso(started_at),
        "completed_at": _iso(completed_at),
        "created_at": _iso(created_at),
        "failure_code": failure_code,
        "failure_message": failure_message,
        "timeout_seconds": timeout_seconds,
        "circuit_breaker_state": circuit_breaker_state,
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


_COLUMNS = (
    "id, correlation_id, idempotency_key, provider, mode, status, "
    "playbook_execution_id, playbook_step_index, incident_id, approval_request_id, alert_id, "
    "adapter_name, action, requested_at, started_at, completed_at, created_at, "
    "failure_code, failure_message, timeout_seconds, circuit_breaker_state, metadata"
)


def create_notification_delivery_attempt(
    conn,
    *,
    correlation_id: str,
    idempotency_key: str,
    provider: str,
    mode: str,
    status: str,
    adapter_name: str,
    action: str,
    metadata: dict[str, Any] | None = None,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    incident_id: int | None = None,
    approval_request_id: int | None = None,
    alert_id: int | None = None,
    requested_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    timeout_seconds: int | None = None,
    circuit_breaker_state: str | None = None,
) -> dict[str, Any]:
    """
    Insert one delivery attempt row. Caller must commit.

    Raises ValueError for invalid enums or empty required strings.
    """
    if not correlation_id or not str(correlation_id).strip():
        raise ValueError("correlation_id is required")
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError("idempotency_key is required")
    if not provider or not str(provider).strip():
        raise ValueError("provider is required")
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}")
    if status not in _VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
    if not adapter_name or not str(adapter_name).strip():
        raise ValueError("adapter_name is required")
    if not action or not str(action).strip():
        raise ValueError("action is required")
    if circuit_breaker_state is not None and circuit_breaker_state not in _VALID_CIRCUIT_STATES:
        raise ValueError(
            f"circuit_breaker_state must be one of {sorted(_VALID_CIRCUIT_STATES)} or None"
        )

    safe_meta = redact_notification_delivery_metadata(metadata)
    safe_failure_message = sanitize_failure_message(failure_message)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO notification_delivery_attempts (
                correlation_id,
                idempotency_key,
                provider,
                mode,
                status,
                playbook_execution_id,
                playbook_step_index,
                incident_id,
                approval_request_id,
                alert_id,
                adapter_name,
                action,
                requested_at,
                started_at,
                completed_at,
                failure_code,
                failure_message,
                timeout_seconds,
                circuit_breaker_state,
                metadata
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                COALESCE(%s, NOW()),
                %s, %s,
                %s, %s, %s, %s,
                %s
            )
            RETURNING {_COLUMNS}
            """,
            (
                correlation_id.strip(),
                idempotency_key.strip(),
                provider.strip(),
                mode,
                status,
                playbook_execution_id,
                playbook_step_index,
                incident_id,
                approval_request_id,
                alert_id,
                adapter_name.strip(),
                action.strip(),
                requested_at,
                started_at,
                completed_at,
                failure_code,
                safe_failure_message,
                timeout_seconds,
                circuit_breaker_state,
                Json(safe_meta),
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("INSERT notification_delivery_attempts returned no row")
    return _row_to_dict(row)


def get_notification_delivery_attempt(conn, attempt_id: int) -> dict[str, Any] | None:
    """Return one attempt by primary key, or None."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM notification_delivery_attempts WHERE id = %s",
            (attempt_id,),
        )
        row = cur.fetchone()
    return _row_to_dict(row) if row else None


def list_notification_delivery_attempts(
    conn,
    *,
    limit: int = 100,
    offset: int = 0,
    provider: str | None = None,
    mode: str | None = None,
    status: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    playbook_execution_id: int | None = None,
    incident_id: int | None = None,
    approval_request_id: int | None = None,
    alert_id: int | None = None,
    adapter_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    List attempts newest-first with optional filters. Read-only.

    limit is capped at 500.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    cap = min(limit, 500)

    clauses: list[str] = []
    params: list[Any] = []

    if provider is not None:
        clauses.append("provider = %s")
        params.append(provider)
    if mode is not None:
        if mode not in _VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}")
        clauses.append("mode = %s")
        params.append(mode)
    if status is not None:
        if status not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
        clauses.append("status = %s")
        params.append(status)
    if correlation_id is not None:
        clauses.append("correlation_id = %s")
        params.append(correlation_id)
    if idempotency_key is not None:
        clauses.append("idempotency_key = %s")
        params.append(idempotency_key)
    if playbook_execution_id is not None:
        clauses.append("playbook_execution_id = %s")
        params.append(playbook_execution_id)
    if incident_id is not None:
        clauses.append("incident_id = %s")
        params.append(incident_id)
    if approval_request_id is not None:
        clauses.append("approval_request_id = %s")
        params.append(approval_request_id)
    if alert_id is not None:
        clauses.append("alert_id = %s")
        params.append(alert_id)
    if adapter_name is not None:
        clauses.append("adapter_name = %s")
        params.append(adapter_name.strip())

    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    params.extend([cap, offset])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_COLUMNS}
            FROM notification_delivery_attempts
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        rows = cur.fetchall()
    return [_row_to_dict(r) for r in rows]
