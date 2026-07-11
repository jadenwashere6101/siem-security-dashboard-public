"""
Canonical SOAR response decision and outcome event persistence.

Callers own transaction boundaries (commit/rollback). This module never commits.
Outcome events are append-only. Decisions are inserted once per selected response.

Do not persist webhooks, tokens, headers, raw payloads, or raw provider responses.
"""

from __future__ import annotations

import copy
import os
import re
import uuid
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

EXECUTION_MODES = frozenset(
    {"observed", "simulation", "tracking_only", "real", "internal", "read_only"}
)
EXECUTION_STATES = frozenset(
    {
        "observed",
        "selected",
        "queued",
        "awaiting_approval",
        "running",
        "skipped",
        "blocked",
        "succeeded",
        "failed",
    }
)
DECISION_SOURCES = frozenset(
    {"detection_default", "correlation", "playbook", "manual", "migration"}
)
EXECUTION_ACTORS = frozenset(
    {
        "queue_worker",
        "playbook_worker",
        "adapter",
        "approval_service",
        "manual",
        "system",
    }
)
REASON_CODES = frozenset(
    {
        "approval_required",
        "approval_denied",
        "approval_expired",
        "simulation_mode",
        "tracking_only",
        "adapter_unavailable",
        "provider_error",
        "policy_blocked",
        "duplicate_suppressed",
        "unsupported_action",
    }
)

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

_SOAR_CORRELATION_ID_RE = re.compile(r"^[a-zA-Z0-9._:-]{1,128}$")
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

_DECISION_COLUMNS = (
    "id, soar_correlation_id, parent_soar_correlation_id, alert_id, incident_id, "
    "host(source_ip) AS source_ip, selected_action, decision_source, reason_code, "
    "outcome_summary, playbook_id, playbook_execution_id, playbook_step_index, "
    "queue_id, approval_request_id, created_by, safe_metadata, selected_at, "
    "created_at, updated_at"
)

_OUTCOME_EVENT_COLUMNS = (
    "id, decision_id, soar_correlation_id, event_type, alert_id, incident_id, "
    "host(source_ip) AS source_ip, execution_mode, execution_state, external_executed, "
    "tracking_recorded, simulated, execution_actor, reason_code, outcome_summary, "
    "queue_id, playbook_execution_id, playbook_step_index, approval_request_id, "
    "notification_delivery_attempt_id, response_action_log_id, provider, adapter_name, "
    "external_reference, idempotency_key, metadata, occurred_at, created_at"
)


class SoarResponseOutcomeValidationError(ValueError):
    """Raised when canonical outcome inputs fail validation before persistence."""


def generate_soar_correlation_id(alert_id: int | None = None) -> str:
    """Generate a safe SOAR lifecycle correlation id: soar-{alert_id|none}-{short_uuid}."""
    alert_part = str(alert_id) if alert_id is not None else "none"
    short_uuid = uuid.uuid4().hex[:12]
    correlation_id = f"soar-{alert_part}-{short_uuid}"
    return validate_soar_correlation_id(correlation_id)


def generate_legacy_soar_correlation_id(table: str, record_id: int) -> str:
    """Deterministic correlation id for migration/backfill rows."""
    if not table or not str(table).strip():
        raise SoarResponseOutcomeValidationError("table is required for legacy correlation id")
    if record_id is None or int(record_id) < 1:
        raise SoarResponseOutcomeValidationError("record_id must be a positive integer")
    safe_table = re.sub(r"[^a-z0-9_]", "", str(table).strip().lower())
    if not safe_table:
        raise SoarResponseOutcomeValidationError("table name must contain safe characters")
    return validate_soar_correlation_id(f"legacy-{safe_table}-{int(record_id)}")


def validate_soar_correlation_id(value: str) -> str:
    correlation_id = str(value).strip()
    if not correlation_id:
        raise SoarResponseOutcomeValidationError("soar_correlation_id is required")
    if len(correlation_id) > 128:
        raise SoarResponseOutcomeValidationError("soar_correlation_id must be at most 128 characters")
    if _URL_RE.search(correlation_id):
        raise SoarResponseOutcomeValidationError("soar_correlation_id must not contain URLs")
    if not _SOAR_CORRELATION_ID_RE.match(correlation_id):
        raise SoarResponseOutcomeValidationError(
            "soar_correlation_id contains unsupported characters"
        )
    return correlation_id


def validate_decision_source(value: str) -> str:
    decision_source = str(value).strip()
    if decision_source not in DECISION_SOURCES:
        raise SoarResponseOutcomeValidationError(
            f"decision_source must be one of {sorted(DECISION_SOURCES)}"
        )
    return decision_source


def validate_execution_mode(value: str) -> str:
    execution_mode = str(value).strip()
    if execution_mode not in EXECUTION_MODES:
        raise SoarResponseOutcomeValidationError(
            f"execution_mode must be one of {sorted(EXECUTION_MODES)}"
        )
    return execution_mode


def validate_execution_state(value: str) -> str:
    execution_state = str(value).strip()
    if execution_state not in EXECUTION_STATES:
        raise SoarResponseOutcomeValidationError(
            f"execution_state must be one of {sorted(EXECUTION_STATES)}"
        )
    return execution_state


def validate_execution_actor(value: str) -> str:
    execution_actor = str(value).strip()
    if execution_actor not in EXECUTION_ACTORS:
        raise SoarResponseOutcomeValidationError(
            f"execution_actor must be one of {sorted(EXECUTION_ACTORS)}"
        )
    return execution_actor


def validate_reason_code(value: str | None) -> str | None:
    if value is None:
        return None
    reason_code = str(value).strip()
    if not reason_code:
        return None
    if reason_code not in REASON_CODES:
        raise SoarResponseOutcomeValidationError(
            f"reason_code must be one of {sorted(REASON_CODES)}"
        )
    return reason_code


def validate_outcome_booleans(
    *,
    execution_mode: str,
    execution_state: str,
    external_executed: bool,
    tracking_recorded: bool,
    simulated: bool,
) -> None:
    if execution_mode == "observed":
        if external_executed or tracking_recorded or simulated:
            raise SoarResponseOutcomeValidationError(
                "observed outcomes must set external_executed, tracking_recorded, and simulated to false"
            )
        return

    if simulated and execution_mode != "simulation":
        raise SoarResponseOutcomeValidationError(
            "simulated may only be true when execution_mode is simulation"
        )

    if external_executed:
        if execution_mode != "real" or execution_state != "succeeded":
            raise SoarResponseOutcomeValidationError(
                "external_executed may only be true for real/succeeded outcomes"
            )

    if tracking_recorded:
        if execution_mode != "tracking_only" or execution_state != "succeeded":
            raise SoarResponseOutcomeValidationError(
                "tracking_recorded may only be true for tracking_only/succeeded outcomes"
            )

    if execution_mode == "simulation" and (external_executed or tracking_recorded):
        raise SoarResponseOutcomeValidationError(
            "simulation outcomes must set external_executed and tracking_recorded to false"
        )

    if execution_mode == "real" and (simulated or tracking_recorded):
        raise SoarResponseOutcomeValidationError(
            "real outcomes must set simulated and tracking_recorded to false"
        )

    if execution_mode == "tracking_only" and (simulated or external_executed):
        raise SoarResponseOutcomeValidationError(
            "tracking_only outcomes must set simulated and external_executed to false"
        )

    if execution_mode == "internal" and (
        simulated or external_executed or tracking_recorded
    ):
        raise SoarResponseOutcomeValidationError(
            "internal outcomes must set simulated, external_executed, and "
            "tracking_recorded to false"
        )

    if execution_mode == "read_only" and (
        simulated or external_executed or tracking_recorded
    ):
        raise SoarResponseOutcomeValidationError(
            "read_only outcomes must set simulated, external_executed, and "
            "tracking_recorded to false"
        )


def _unsafe_metadata_key(key: str) -> bool:
    lk = key.lower()
    if lk in _METADATA_KEY_DENYLIST:
        return True
    if "webhook_url" in lk or lk in ("webhook", "incoming_webhook", "incoming_webhook_url"):
        return True
    if lk.endswith("_webhook_url") or lk.endswith("webhookurl"):
        return True
    return any(part in lk for part in _METADATA_KEY_SUBSTRING_DENY)


def _sanitize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        if _URL_RE.search(value):
            return "[REDACTED_URL]"
        return value
    if isinstance(value, dict):
        return redact_soar_outcome_metadata(value)
    if isinstance(value, list):
        return [_sanitize_scalar(item) for item in value]
    return value


def redact_soar_outcome_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
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


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _decision_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        soar_correlation_id,
        parent_soar_correlation_id,
        alert_id,
        incident_id,
        source_ip,
        selected_action,
        decision_source,
        reason_code,
        outcome_summary,
        playbook_id,
        playbook_execution_id,
        playbook_step_index,
        queue_id,
        approval_request_id,
        created_by,
        safe_metadata,
        selected_at,
        created_at,
        updated_at,
    ) = row
    return {
        "id": row_id,
        "soar_correlation_id": soar_correlation_id,
        "parent_soar_correlation_id": parent_soar_correlation_id,
        "alert_id": alert_id,
        "incident_id": incident_id,
        "source_ip": source_ip,
        "selected_action": selected_action,
        "decision_source": decision_source,
        "reason_code": reason_code,
        "outcome_summary": outcome_summary,
        "playbook_id": playbook_id,
        "playbook_execution_id": playbook_execution_id,
        "playbook_step_index": playbook_step_index,
        "queue_id": queue_id,
        "approval_request_id": approval_request_id,
        "created_by": created_by,
        "safe_metadata": safe_metadata if isinstance(safe_metadata, dict) else {},
        "selected_at": _iso(selected_at),
        "created_at": _iso(created_at),
        "updated_at": _iso(updated_at),
    }


def _outcome_event_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        decision_id,
        soar_correlation_id,
        event_type,
        alert_id,
        incident_id,
        source_ip,
        execution_mode,
        execution_state,
        external_executed,
        tracking_recorded,
        simulated,
        execution_actor,
        reason_code,
        outcome_summary,
        queue_id,
        playbook_execution_id,
        playbook_step_index,
        approval_request_id,
        notification_delivery_attempt_id,
        response_action_log_id,
        provider,
        adapter_name,
        external_reference,
        idempotency_key,
        metadata,
        occurred_at,
        created_at,
    ) = row
    return {
        "id": row_id,
        "decision_id": decision_id,
        "soar_correlation_id": soar_correlation_id,
        "event_type": event_type,
        "alert_id": alert_id,
        "incident_id": incident_id,
        "source_ip": source_ip,
        "execution_mode": execution_mode,
        "execution_state": execution_state,
        "external_executed": bool(external_executed),
        "tracking_recorded": bool(tracking_recorded),
        "simulated": bool(simulated),
        "execution_actor": execution_actor,
        "reason_code": reason_code,
        "outcome_summary": outcome_summary,
        "queue_id": queue_id,
        "playbook_execution_id": playbook_execution_id,
        "playbook_step_index": playbook_step_index,
        "approval_request_id": approval_request_id,
        "notification_delivery_attempt_id": notification_delivery_attempt_id,
        "response_action_log_id": response_action_log_id,
        "provider": provider,
        "adapter_name": adapter_name,
        "external_reference": external_reference,
        "idempotency_key": idempotency_key,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "occurred_at": _iso(occurred_at),
        "created_at": _iso(created_at),
    }


def derive_outcome_label(
    *,
    execution_mode: str,
    execution_state: str,
    external_executed: bool = False,
    tracking_recorded: bool = False,
    simulated: bool = False,
) -> str:
    state = validate_execution_state(execution_state)
    mode = validate_execution_mode(execution_mode)

    if state == "awaiting_approval":
        return "Awaiting approval"
    if state == "blocked":
        return "Blocked"
    if state == "skipped":
        return "Skipped"
    if state == "failed":
        return "Failed"
    if state == "running":
        return "Running"
    if state == "queued":
        return "Queued"
    if state == "selected":
        return "Selected"
    if mode == "observed":
        return "Observed only"
    if mode == "simulation" or simulated:
        return "Simulated"
    if mode == "tracking_only" or tracking_recorded:
        return "Tracking only"
    if mode == "real" and external_executed:
        return "Real executed"
    if mode == "real":
        return "Failed"
    if state == "succeeded":
        return "Selected"
    return "Observed only"


def _fetch_decision_by_id(conn, decision_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_DECISION_COLUMNS}
            FROM soar_response_decisions
            WHERE id = %s
            """,
            (decision_id,),
        )
        row = cur.fetchone()
    return _decision_row_to_dict(row) if row else None


def _fetch_decision_by_correlation_id(conn, soar_correlation_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_DECISION_COLUMNS}
            FROM soar_response_decisions
            WHERE soar_correlation_id = %s
            """,
            (soar_correlation_id,),
        )
        row = cur.fetchone()
    return _decision_row_to_dict(row) if row else None


def create_response_decision(
    conn,
    *,
    selected_action: str,
    decision_source: str,
    outcome_summary: str,
    alert_id: int | None = None,
    incident_id: int | None = None,
    source_ip: str | None = None,
    reason_code: str | None = None,
    soar_correlation_id: str | None = None,
    parent_soar_correlation_id: str | None = None,
    playbook_id: str | None = None,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    queue_id: int | None = None,
    approval_request_id: int | None = None,
    created_by: int | None = None,
    safe_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not selected_action or not str(selected_action).strip():
        raise SoarResponseOutcomeValidationError("selected_action is required")
    if not outcome_summary or not str(outcome_summary).strip():
        raise SoarResponseOutcomeValidationError("outcome_summary is required")

    validated_source = validate_decision_source(decision_source)
    validated_reason = validate_reason_code(reason_code)
    correlation_id = (
        validate_soar_correlation_id(soar_correlation_id)
        if soar_correlation_id
        else generate_soar_correlation_id(alert_id)
    )
    parent_correlation_id = (
        validate_soar_correlation_id(parent_soar_correlation_id)
        if parent_soar_correlation_id
        else None
    )
    if playbook_step_index is not None and int(playbook_step_index) < 0:
        raise SoarResponseOutcomeValidationError("playbook_step_index must be >= 0")

    metadata = redact_soar_outcome_metadata(safe_metadata)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO soar_response_decisions (
                soar_correlation_id,
                parent_soar_correlation_id,
                alert_id,
                incident_id,
                source_ip,
                selected_action,
                decision_source,
                reason_code,
                outcome_summary,
                playbook_id,
                playbook_execution_id,
                playbook_step_index,
                queue_id,
                approval_request_id,
                created_by,
                safe_metadata
            )
            VALUES (
                %s, %s, %s, %s, %s::inet, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING {_DECISION_COLUMNS}
            """,
            (
                correlation_id,
                parent_correlation_id,
                alert_id,
                incident_id,
                source_ip,
                str(selected_action).strip(),
                validated_source,
                validated_reason,
                str(outcome_summary).strip(),
                playbook_id,
                playbook_execution_id,
                playbook_step_index,
                queue_id,
                approval_request_id,
                created_by,
                Json(metadata),
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("failed to create response decision")
    return _decision_row_to_dict(row)


def _get_outcome_event_by_idempotency_key(
    conn, idempotency_key: str
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        )
        row = cur.fetchone()
    return _outcome_event_row_to_dict(row) if row else None


def append_outcome_event(
    conn,
    *,
    execution_mode: str,
    execution_state: str,
    execution_actor: str,
    outcome_summary: str,
    decision_id: int | None = None,
    soar_correlation_id: str | None = None,
    event_type: str | None = None,
    external_executed: bool = False,
    tracking_recorded: bool = False,
    simulated: bool = False,
    reason_code: str | None = None,
    alert_id: int | None = None,
    incident_id: int | None = None,
    source_ip: str | None = None,
    queue_id: int | None = None,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    approval_request_id: int | None = None,
    notification_delivery_attempt_id: int | None = None,
    response_action_log_id: int | None = None,
    provider: str | None = None,
    adapter_name: str | None = None,
    external_reference: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    if decision_id is None and not soar_correlation_id:
        raise SoarResponseOutcomeValidationError(
            "decision_id or soar_correlation_id is required"
        )
    if not outcome_summary or not str(outcome_summary).strip():
        raise SoarResponseOutcomeValidationError("outcome_summary is required")

    validated_mode = validate_execution_mode(execution_mode)
    validated_state = validate_execution_state(execution_state)
    validated_actor = validate_execution_actor(execution_actor)
    validated_reason = validate_reason_code(reason_code)
    validate_outcome_booleans(
        execution_mode=validated_mode,
        execution_state=validated_state,
        external_executed=bool(external_executed),
        tracking_recorded=bool(tracking_recorded),
        simulated=bool(simulated),
    )

    decision = None
    if decision_id is not None:
        decision = _fetch_decision_by_id(conn, int(decision_id))
        if decision is None:
            raise SoarResponseOutcomeValidationError(f"decision_id {decision_id} not found")
    else:
        correlation_lookup = validate_soar_correlation_id(soar_correlation_id or "")
        decision = _fetch_decision_by_correlation_id(conn, correlation_lookup)
        if decision is None:
            raise SoarResponseOutcomeValidationError(
                f"no decision found for soar_correlation_id {correlation_lookup}"
            )
        decision_id = decision["id"]

    correlation_id = decision["soar_correlation_id"]
    event_type_value = (event_type or validated_state).strip()
    if not event_type_value:
        raise SoarResponseOutcomeValidationError("event_type is required")

    if idempotency_key:
        idempotency_key = str(idempotency_key).strip()
        if not idempotency_key:
            raise SoarResponseOutcomeValidationError("idempotency_key must not be blank")
        existing = _get_outcome_event_by_idempotency_key(conn, idempotency_key)
        if existing is not None:
            return existing

    if playbook_step_index is not None and int(playbook_step_index) < 0:
        raise SoarResponseOutcomeValidationError("playbook_step_index must be >= 0")

    resolved_alert_id = alert_id if alert_id is not None else decision.get("alert_id")
    resolved_incident_id = incident_id if incident_id is not None else decision.get("incident_id")
    resolved_source_ip = source_ip if source_ip is not None else decision.get("source_ip")
    safe_metadata = redact_soar_outcome_metadata(metadata)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO soar_response_outcome_events (
                decision_id,
                soar_correlation_id,
                event_type,
                alert_id,
                incident_id,
                source_ip,
                execution_mode,
                execution_state,
                external_executed,
                tracking_recorded,
                simulated,
                execution_actor,
                reason_code,
                outcome_summary,
                queue_id,
                playbook_execution_id,
                playbook_step_index,
                approval_request_id,
                notification_delivery_attempt_id,
                response_action_log_id,
                provider,
                adapter_name,
                external_reference,
                idempotency_key,
                metadata,
                occurred_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s::inet, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW())
            )
            RETURNING {_OUTCOME_EVENT_COLUMNS}
            """,
            (
                decision_id,
                correlation_id,
                event_type_value,
                resolved_alert_id,
                resolved_incident_id,
                resolved_source_ip,
                validated_mode,
                validated_state,
                bool(external_executed),
                bool(tracking_recorded),
                bool(simulated),
                validated_actor,
                validated_reason,
                str(outcome_summary).strip(),
                queue_id,
                playbook_execution_id,
                playbook_step_index,
                approval_request_id,
                notification_delivery_attempt_id,
                response_action_log_id,
                provider,
                adapter_name,
                external_reference,
                idempotency_key,
                Json(safe_metadata),
                occurred_at,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("failed to append outcome event")
    return _outcome_event_row_to_dict(row)


def get_latest_outcome_for_decision(conn, decision_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = %s
            ORDER BY occurred_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (decision_id,),
        )
        row = cur.fetchone()
    return _outcome_event_row_to_dict(row) if row else None


def _get_latest_outcome_by_column(conn, column: str, value: Any) -> dict[str, Any] | None:
    if column not in {
        "alert_id",
        "incident_id",
        "source_ip",
        "queue_id",
        "playbook_execution_id",
        "approval_request_id",
        "notification_delivery_attempt_id",
    }:
        raise ValueError(f"unsupported outcome lookup column: {column}")

    if column == "source_ip":
        predicate = "source_ip = %s::inet"
    else:
        predicate = f"{column} = %s"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE {predicate}
            ORDER BY occurred_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (value,),
        )
        row = cur.fetchone()
    return _outcome_event_row_to_dict(row) if row else None


def get_latest_outcome_for_alert(conn, alert_id: int) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(conn, "alert_id", alert_id)


def get_latest_outcome_for_incident(conn, incident_id: int) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(conn, "incident_id", incident_id)


def get_latest_outcome_for_source_ip(conn, source_ip: str) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(conn, "source_ip", source_ip)


def get_latest_outcome_for_queue(conn, queue_id: int) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(conn, "queue_id", queue_id)


def get_latest_outcome_for_playbook_execution(
    conn, playbook_execution_id: int
) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(conn, "playbook_execution_id", playbook_execution_id)


def get_latest_outcome_for_approval_request(
    conn, approval_request_id: int
) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(conn, "approval_request_id", approval_request_id)


def get_latest_outcome_for_notification_delivery(
    conn, notification_delivery_attempt_id: int
) -> dict[str, Any] | None:
    return _get_latest_outcome_by_column(
        conn, "notification_delivery_attempt_id", notification_delivery_attempt_id
    )


def get_latest_outcome_by_correlation_id(
    conn, soar_correlation_id: str
) -> dict[str, Any] | None:
    correlation_id = validate_soar_correlation_id(soar_correlation_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE soar_correlation_id = %s
            ORDER BY occurred_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (correlation_id,),
        )
        row = cur.fetchone()
    return _outcome_event_row_to_dict(row) if row else None


def get_latest_outcomes_for_alerts_bulk(
    conn,
    alert_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return a dict mapping alert_id → latest outcome event using one query.

    Uses DISTINCT ON so there is no per-alert round-trip. alert_ids absent from
    the outcome_events table are absent from the returned dict. Callers should treat
    absent ids as response_outcome: null.
    """
    if not alert_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (alert_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE alert_id = ANY(%s)
            ORDER BY alert_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (list(alert_ids),),
        )
        rows = cur.fetchall() or []
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        event = _outcome_event_row_to_dict(row)
        if event["alert_id"] is not None:
            result[int(event["alert_id"])] = event
    return result


def get_latest_outcomes_for_playbook_executions_bulk(
    conn,
    execution_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return Design Decision 6 API shapes for linked playbook executions using batched reads."""
    if not execution_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH linked_decisions AS (
                SELECT DISTINCT ON (pe.id)
                    pe.id AS pe_execution_id,
                    d.id,
                    d.soar_correlation_id,
                    d.parent_soar_correlation_id,
                    d.alert_id,
                    d.incident_id,
                    host(d.source_ip) AS source_ip,
                    d.selected_action,
                    d.decision_source,
                    d.reason_code,
                    d.outcome_summary,
                    d.playbook_id,
                    d.playbook_execution_id,
                    d.playbook_step_index,
                    d.queue_id,
                    d.approval_request_id,
                    d.created_by,
                    d.safe_metadata,
                    d.selected_at,
                    d.created_at,
                    d.updated_at,
                    CASE WHEN pe.decision_id = d.id THEN 0 ELSE 1 END AS link_priority
                FROM playbook_executions pe
                JOIN soar_response_decisions d
                  ON d.id = pe.decision_id
                  OR (
                    pe.decision_id IS NULL
                    AND pe.soar_correlation_id IS NOT NULL
                    AND d.soar_correlation_id = pe.soar_correlation_id
                  )
                WHERE pe.id = ANY(%s)
                ORDER BY pe.id, link_priority, d.created_at DESC, d.id DESC
            )
            SELECT pe_execution_id, id, soar_correlation_id, parent_soar_correlation_id,
                   alert_id, incident_id, source_ip, selected_action, decision_source,
                   reason_code, outcome_summary, playbook_id, playbook_execution_id,
                   playbook_step_index, queue_id, approval_request_id, created_by,
                   safe_metadata, selected_at, created_at, updated_at
            FROM linked_decisions
            """,
            (list(execution_ids),),
        )
        decision_rows = cur.fetchall() or []

    decisions_by_execution: dict[int, dict[str, Any]] = {}
    decision_ids: list[int] = []
    for row in decision_rows:
        execution_id = int(row[0])
        decision = _decision_row_to_dict(row[1:])
        decisions_by_execution[execution_id] = decision
        decision_ids.append(int(decision["id"]))

    if not decisions_by_execution:
        return {}

    latest_events_by_decision: dict[int, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (decision_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = ANY(%s)
            ORDER BY decision_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (decision_ids,),
        )
        event_rows = cur.fetchall() or []

    for row in event_rows:
        event = _outcome_event_row_to_dict(row)
        latest_events_by_decision[int(event["decision_id"])] = event

    return {
        execution_id: build_latest_outcome_api_shape(
            decision,
            latest_events_by_decision.get(int(decision["id"])),
        )
        for execution_id, decision in decisions_by_execution.items()
    }


def get_latest_outcomes_for_queues_bulk(
    conn,
    queue_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return Design Decision 6 API shapes for linked queue rows using batched reads."""
    if not queue_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH linked_decisions AS (
                SELECT DISTINCT ON (q.id)
                    q.id AS q_queue_id,
                    d.id,
                    d.soar_correlation_id,
                    d.parent_soar_correlation_id,
                    d.alert_id,
                    d.incident_id,
                    host(d.source_ip) AS source_ip,
                    d.selected_action,
                    d.decision_source,
                    d.reason_code,
                    d.outcome_summary,
                    d.playbook_id,
                    d.playbook_execution_id,
                    d.playbook_step_index,
                    d.queue_id,
                    d.approval_request_id,
                    d.created_by,
                    d.safe_metadata,
                    d.selected_at,
                    d.created_at,
                    d.updated_at,
                    CASE WHEN q.decision_id = d.id THEN 0 ELSE 1 END AS link_priority
                FROM response_actions_queue q
                JOIN soar_response_decisions d
                  ON d.id = q.decision_id
                  OR (
                    q.decision_id IS NULL
                    AND q.soar_correlation_id IS NOT NULL
                    AND d.soar_correlation_id = q.soar_correlation_id
                  )
                WHERE q.id = ANY(%s)
                ORDER BY q.id, link_priority, d.created_at DESC, d.id DESC
            )
            SELECT q_queue_id, id, soar_correlation_id, parent_soar_correlation_id,
                   alert_id, incident_id, source_ip, selected_action, decision_source,
                   reason_code, outcome_summary, playbook_id, playbook_execution_id,
                   playbook_step_index, queue_id, approval_request_id, created_by,
                   safe_metadata, selected_at, created_at, updated_at
            FROM linked_decisions
            """,
            (list(queue_ids),),
        )
        decision_rows = cur.fetchall() or []

    decisions_by_queue: dict[int, dict[str, Any]] = {}
    decision_ids: list[int] = []
    for row in decision_rows:
        queue_id = int(row[0])
        decision = _decision_row_to_dict(row[1:])
        decisions_by_queue[queue_id] = decision
        decision_ids.append(int(decision["id"]))

    if not decisions_by_queue:
        return {}

    latest_events_by_decision: dict[int, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (decision_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = ANY(%s)
            ORDER BY decision_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (decision_ids,),
        )
        event_rows = cur.fetchall() or []

    for row in event_rows:
        event = _outcome_event_row_to_dict(row)
        latest_events_by_decision[int(event["decision_id"])] = event

    return {
        queue_id: build_latest_outcome_api_shape(
            decision,
            latest_events_by_decision.get(int(decision["id"])),
        )
        for queue_id, decision in decisions_by_queue.items()
    }


def get_latest_outcomes_for_approvals_bulk(
    conn,
    approval_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return Design Decision 6 API shapes for linked approval requests using batched reads."""
    if not approval_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH linked_decisions AS (
                SELECT DISTINCT ON (ar.id)
                    ar.id AS ar_approval_id,
                    d.id,
                    d.soar_correlation_id,
                    d.parent_soar_correlation_id,
                    d.alert_id,
                    d.incident_id,
                    host(d.source_ip) AS source_ip,
                    d.selected_action,
                    d.decision_source,
                    d.reason_code,
                    d.outcome_summary,
                    d.playbook_id,
                    d.playbook_execution_id,
                    d.playbook_step_index,
                    d.queue_id,
                    d.approval_request_id,
                    d.created_by,
                    d.safe_metadata,
                    d.selected_at,
                    d.created_at,
                    d.updated_at,
                    CASE WHEN ar.decision_id = d.id THEN 0
                         WHEN ar.soar_correlation_id IS NOT NULL
                              AND d.soar_correlation_id = ar.soar_correlation_id THEN 1
                         ELSE 2
                    END AS link_priority
                FROM approval_requests ar
                JOIN soar_response_decisions d
                  ON d.id = ar.decision_id
                  OR (
                    ar.decision_id IS NULL
                    AND ar.soar_correlation_id IS NOT NULL
                    AND d.soar_correlation_id = ar.soar_correlation_id
                  )
                  OR d.approval_request_id = ar.id
                WHERE ar.id = ANY(%s)
                ORDER BY ar.id, link_priority, d.created_at DESC, d.id DESC
            )
            SELECT ar_approval_id, id, soar_correlation_id, parent_soar_correlation_id,
                   alert_id, incident_id, source_ip, selected_action, decision_source,
                   reason_code, outcome_summary, playbook_id, playbook_execution_id,
                   playbook_step_index, queue_id, approval_request_id, created_by,
                   safe_metadata, selected_at, created_at, updated_at
            FROM linked_decisions
            """,
            (list(approval_ids),),
        )
        decision_rows = cur.fetchall() or []

    decisions_by_approval: dict[int, dict[str, Any]] = {}
    decision_ids: list[int] = []
    for row in decision_rows:
        approval_id = int(row[0])
        decision = _decision_row_to_dict(row[1:])
        decisions_by_approval[approval_id] = decision
        decision_ids.append(int(decision["id"]))

    if not decisions_by_approval:
        return {}

    latest_events_by_decision: dict[int, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (decision_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = ANY(%s)
            ORDER BY decision_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (decision_ids,),
        )
        event_rows = cur.fetchall() or []

    for row in event_rows:
        event = _outcome_event_row_to_dict(row)
        latest_events_by_decision[int(event["decision_id"])] = event

    return {
        approval_id: build_latest_outcome_api_shape(
            decision,
            latest_events_by_decision.get(int(decision["id"])),
        )
        for approval_id, decision in decisions_by_approval.items()
    }


def get_latest_outcomes_for_notification_deliveries_bulk(
    conn,
    attempt_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return latest outcome API shapes for linked notification delivery attempts."""
    if not attempt_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH linked_decisions AS (
                SELECT DISTINCT ON (nda.id)
                    nda.id AS nda_attempt_id,
                    d.id,
                    d.soar_correlation_id,
                    d.parent_soar_correlation_id,
                    d.alert_id,
                    d.incident_id,
                    host(d.source_ip) AS source_ip,
                    d.selected_action,
                    d.decision_source,
                    d.reason_code,
                    d.outcome_summary,
                    d.playbook_id,
                    d.playbook_execution_id,
                    d.playbook_step_index,
                    d.queue_id,
                    d.approval_request_id,
                    d.created_by,
                    d.safe_metadata,
                    d.selected_at,
                    d.created_at,
                    d.updated_at,
                    CASE WHEN nda.decision_id = d.id THEN 0
                         WHEN nda.soar_correlation_id IS NOT NULL
                              AND d.soar_correlation_id = nda.soar_correlation_id THEN 1
                         ELSE 2
                    END AS link_priority
                FROM notification_delivery_attempts nda
                JOIN soar_response_decisions d
                  ON d.id = nda.decision_id
                  OR (
                    nda.decision_id IS NULL
                    AND nda.soar_correlation_id IS NOT NULL
                    AND d.soar_correlation_id = nda.soar_correlation_id
                  )
                  OR d.approval_request_id = nda.approval_request_id
                  OR d.playbook_execution_id = nda.playbook_execution_id
                WHERE nda.id = ANY(%s)
                ORDER BY nda.id, link_priority, d.created_at DESC, d.id DESC
            )
            SELECT nda_attempt_id, id, soar_correlation_id, parent_soar_correlation_id,
                   alert_id, incident_id, source_ip, selected_action, decision_source,
                   reason_code, outcome_summary, playbook_id, playbook_execution_id,
                   playbook_step_index, queue_id, approval_request_id, created_by,
                   safe_metadata, selected_at, created_at, updated_at
            FROM linked_decisions
            """,
            (list(attempt_ids),),
        )
        decision_rows = cur.fetchall() or []

    decisions_by_attempt: dict[int, dict[str, Any]] = {}
    decision_ids: list[int] = []
    for row in decision_rows:
        attempt_id = int(row[0])
        decision = _decision_row_to_dict(row[1:])
        decisions_by_attempt[attempt_id] = decision
        decision_ids.append(int(decision["id"]))

    if not decisions_by_attempt:
        return {}

    latest_events_by_decision: dict[int, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (decision_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = ANY(%s)
            ORDER BY decision_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (decision_ids,),
        )
        event_rows = cur.fetchall() or []

    for row in event_rows:
        event = _outcome_event_row_to_dict(row)
        latest_events_by_decision[int(event["decision_id"])] = event

    return {
        attempt_id: build_latest_outcome_api_shape(
            decision,
            latest_events_by_decision.get(int(decision["id"])),
        )
        for attempt_id, decision in decisions_by_attempt.items()
    }


def get_latest_outcomes_for_incidents_bulk(
    conn,
    incident_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return latest outcome API shapes for incidents using one decision/event batch."""
    if not incident_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (incident_id) {_DECISION_COLUMNS}
            FROM soar_response_decisions
            WHERE incident_id = ANY(%s)
            ORDER BY incident_id, created_at DESC, id DESC
            """,
            (list(incident_ids),),
        )
        decision_rows = cur.fetchall() or []

    decisions_by_incident: dict[int, dict[str, Any]] = {}
    decision_ids: list[int] = []
    for row in decision_rows:
        decision = _decision_row_to_dict(row)
        if decision["incident_id"] is not None:
            incident_id = int(decision["incident_id"])
            decisions_by_incident[incident_id] = decision
            decision_ids.append(int(decision["id"]))

    if not decisions_by_incident:
        return {}

    latest_events_by_decision: dict[int, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (decision_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = ANY(%s)
            ORDER BY decision_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (decision_ids,),
        )
        event_rows = cur.fetchall() or []

    for row in event_rows:
        event = _outcome_event_row_to_dict(row)
        latest_events_by_decision[int(event["decision_id"])] = event

    return {
        incident_id: build_latest_outcome_api_shape(
            decision,
            latest_events_by_decision.get(int(decision["id"])),
        )
        for incident_id, decision in decisions_by_incident.items()
    }


def get_latest_outcomes_for_blocked_ips_bulk(
    conn,
    block_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return latest canonical outcome shapes for blocklist rows via source alert linkage."""
    if not block_ids:
        return {}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source_alert_id
            FROM blocked_ips
            WHERE id = ANY(%s)
              AND source_alert_id IS NOT NULL
            """,
            (list(block_ids),),
        )
        block_rows = cur.fetchall() or []

    if not block_rows:
        return {}

    alert_ids = [int(row[1]) for row in block_rows]
    decisions_by_alert = get_latest_decisions_for_alerts_bulk(conn, alert_ids)
    if not decisions_by_alert:
        return {}

    decision_ids = [int(decision["id"]) for decision in decisions_by_alert.values()]
    latest_events_by_decision: dict[int, dict[str, Any]] = {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (decision_id) {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE decision_id = ANY(%s)
            ORDER BY decision_id, occurred_at DESC, created_at DESC, id DESC
            """,
            (decision_ids,),
        )
        event_rows = cur.fetchall() or []

    for row in event_rows:
        event = _outcome_event_row_to_dict(row)
        latest_events_by_decision[int(event["decision_id"])] = event

    result: dict[int, dict[str, Any]] = {}
    for block_id, alert_id in block_rows:
        decision = decisions_by_alert.get(int(alert_id))
        if decision is not None:
            result[int(block_id)] = build_latest_outcome_api_shape(
                decision,
                latest_events_by_decision.get(int(decision["id"])),
            )
    return result


def serialize_incident_outcome_timeline_entries(
    conn,
    incident_id: int,
) -> list[dict[str, Any]]:
    """Return canonical outcome timeline entries for one incident, oldest first."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_OUTCOME_EVENT_COLUMNS}
            FROM soar_response_outcome_events
            WHERE incident_id = %s
            ORDER BY occurred_at ASC, created_at ASC, id ASC
            """,
            (incident_id,),
        )
        rows = cur.fetchall() or []

    entries: list[dict[str, Any]] = []
    for row in rows:
        event = _outcome_event_row_to_dict(row)
        entries.append(
            {
                "type": "response_outcome",
                "timestamp": event["occurred_at"] or event["created_at"],
                "title": "Response outcome recorded",
                "description": event["outcome_summary"],
                "severity": "info",
                "metadata": {
                    "incident_id": incident_id,
                    "outcome_event_id": event["id"],
                    "decision_id": event["decision_id"],
                    "soar_correlation_id": event["soar_correlation_id"],
                    "execution_mode": event["execution_mode"],
                    "execution_state": event["execution_state"],
                    "external_executed": event["external_executed"],
                    "tracking_recorded": event["tracking_recorded"],
                    "simulated": event["simulated"],
                    "reason_code": event["reason_code"],
                    "related": {
                        "alert_id": event["alert_id"],
                        "queue_id": event["queue_id"],
                        "playbook_execution_id": event["playbook_execution_id"],
                        "playbook_step_index": event["playbook_step_index"],
                        "approval_request_id": event["approval_request_id"],
                        "notification_delivery_attempt_id": event[
                            "notification_delivery_attempt_id"
                        ],
                        "response_action_log_id": event["response_action_log_id"],
                    },
                },
            }
        )
    return entries


def _empty_outcome_count_groups() -> dict[str, dict[str, int]]:
    return {
        "execution_mode": {mode: 0 for mode in EXECUTION_MODES},
        "execution_state": {state: 0 for state in EXECUTION_STATES},
        "external_executed": {"true": 0, "false": 0},
        "tracking_recorded": {"true": 0, "false": 0},
        "simulated": {"true": 0, "false": 0},
    }


def _merge_outcome_count_rows(rows: list[tuple[str, Any, int]]) -> dict[str, dict[str, int]]:
    counts = _empty_outcome_count_groups()
    for group_name, raw_value, raw_count in rows:
        if group_name in {"external_executed", "tracking_recorded", "simulated"}:
            key = "true" if str(raw_value).lower() in {"true", "t", "1"} else "false"
        else:
            key = str(raw_value)
        counts.setdefault(str(group_name), {})
        counts[str(group_name)][key] = int(raw_count)
    return counts


def get_outcome_count_groups(conn, *, source_ip: str | None = None) -> dict[str, dict[str, int]]:
    """Return canonical outcome counts grouped for metrics or a specific source IP."""
    params: list[Any] = []
    predicate = ""
    if source_ip is not None:
        predicate = "WHERE source_ip = %s::inet"
        params.append(source_ip)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT 'execution_mode' AS group_name, execution_mode::text AS value, COUNT(*)
            FROM soar_response_outcome_events
            {predicate}
            GROUP BY execution_mode
            UNION ALL
            SELECT 'execution_state', execution_state::text, COUNT(*)
            FROM soar_response_outcome_events
            {predicate}
            GROUP BY execution_state
            UNION ALL
            SELECT 'external_executed', external_executed::text, COUNT(*)
            FROM soar_response_outcome_events
            {predicate}
            GROUP BY external_executed
            UNION ALL
            SELECT 'tracking_recorded', tracking_recorded::text, COUNT(*)
            FROM soar_response_outcome_events
            {predicate}
            GROUP BY tracking_recorded
            UNION ALL
            SELECT 'simulated', simulated::text, COUNT(*)
            FROM soar_response_outcome_events
            {predicate}
            GROUP BY simulated
            """,
            params * 5,
        )
        rows = cur.fetchall() or []
    return _merge_outcome_count_rows(rows)


def get_recent_outcomes_for_source_ip(
    conn,
    source_ip: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return recent canonical latest-outcome API shapes for one source IP."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                e.id, e.decision_id, e.soar_correlation_id, e.event_type,
                e.alert_id, e.incident_id, host(e.source_ip) AS source_ip,
                e.execution_mode, e.execution_state, e.external_executed,
                e.tracking_recorded, e.simulated, e.execution_actor,
                e.reason_code, e.outcome_summary, e.queue_id,
                e.playbook_execution_id, e.playbook_step_index,
                e.approval_request_id, e.notification_delivery_attempt_id,
                e.response_action_log_id, e.provider, e.adapter_name,
                e.external_reference, e.idempotency_key, e.metadata,
                e.occurred_at, e.created_at,
                d.id, d.soar_correlation_id, d.parent_soar_correlation_id,
                d.alert_id, d.incident_id, host(d.source_ip) AS source_ip,
                d.selected_action, d.decision_source, d.reason_code,
                d.outcome_summary, d.playbook_id, d.playbook_execution_id,
                d.playbook_step_index, d.queue_id, d.approval_request_id,
                d.created_by, d.safe_metadata, d.selected_at, d.created_at,
                d.updated_at
            FROM soar_response_outcome_events e
            JOIN soar_response_decisions d ON d.id = e.decision_id
            WHERE e.source_ip = %s::inet
            ORDER BY e.occurred_at DESC, e.created_at DESC, e.id DESC
            LIMIT %s
            """,
            (source_ip, int(limit)),
        )
        rows = cur.fetchall() or []

    event_column_count = 28
    recent: list[dict[str, Any]] = []
    for row in rows:
        event = _outcome_event_row_to_dict(row[:event_column_count])
        decision = _decision_row_to_dict(row[event_column_count:])
        recent.append(build_latest_outcome_api_shape(decision, event))
    return recent


def get_latest_decisions_for_alerts_bulk(
    conn,
    alert_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Return a dict mapping alert_id → latest decision row using one query."""
    if not alert_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (alert_id) {_DECISION_COLUMNS}
            FROM soar_response_decisions
            WHERE alert_id = ANY(%s)
            ORDER BY alert_id, created_at DESC, id DESC
            """,
            (list(alert_ids),),
        )
        rows = cur.fetchall() or []
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        decision = _decision_row_to_dict(row)
        if decision["alert_id"] is not None:
            result[int(decision["alert_id"])] = decision
    return result


def build_latest_outcome_api_shape(
    decision: dict[str, Any],
    latest_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Design Decision 6 latest-outcome API shape from decision/event rows."""
    if latest_event is not None:
        execution_mode = latest_event["execution_mode"]
        execution_state = latest_event["execution_state"]
        external_executed = latest_event["external_executed"]
        tracking_recorded = latest_event["tracking_recorded"]
        simulated = latest_event["simulated"]
        execution_actor = latest_event["execution_actor"]
        reason_code = latest_event.get("reason_code")
        outcome_summary = latest_event["outcome_summary"]
        latest_outcome_event_id = latest_event["id"]
        occurred_at = latest_event.get("occurred_at")
        related_queue_id = latest_event.get("queue_id")
        related_playbook_execution_id = latest_event.get("playbook_execution_id")
        related_playbook_step_index = latest_event.get("playbook_step_index")
        related_approval_request_id = latest_event.get("approval_request_id")
        related_notification_delivery_attempt_id = latest_event.get(
            "notification_delivery_attempt_id"
        )
        related_response_action_log_id = latest_event.get("response_action_log_id")
    else:
        execution_mode = "observed"
        execution_state = "selected"
        external_executed = False
        tracking_recorded = False
        simulated = False
        execution_actor = None
        reason_code = decision.get("reason_code")
        outcome_summary = decision["outcome_summary"]
        latest_outcome_event_id = None
        occurred_at = None
        related_queue_id = decision.get("queue_id")
        related_playbook_execution_id = decision.get("playbook_execution_id")
        related_playbook_step_index = decision.get("playbook_step_index")
        related_approval_request_id = decision.get("approval_request_id")
        related_notification_delivery_attempt_id = None
        related_response_action_log_id = None

    return {
        "soar_correlation_id": decision["soar_correlation_id"],
        "decision_id": decision["id"],
        "latest_outcome_event_id": latest_outcome_event_id,
        "selected_action": decision["selected_action"],
        "decision_source": decision["decision_source"],
        "execution_actor": execution_actor,
        "execution_mode": execution_mode,
        "execution_state": execution_state,
        "external_executed": external_executed,
        "tracking_recorded": tracking_recorded,
        "simulated": simulated,
        "outcome_summary": outcome_summary,
        "reason_code": reason_code,
        "related": {
            "alert_id": decision.get("alert_id"),
            "incident_id": decision.get("incident_id"),
            "queue_id": related_queue_id,
            "playbook_id": decision.get("playbook_id"),
            "playbook_execution_id": related_playbook_execution_id,
            "playbook_step_index": related_playbook_step_index,
            "approval_request_id": related_approval_request_id,
            "notification_delivery_attempt_id": related_notification_delivery_attempt_id,
            "response_action_log_id": related_response_action_log_id,
        },
        "timestamps": {
            "selected_at": decision.get("selected_at"),
            "occurred_at": occurred_at,
        },
    }


def serialize_latest_outcome(
    conn,
    *,
    decision_id: int | None = None,
    soar_correlation_id: str | None = None,
    alert_id: int | None = None,
) -> dict[str, Any] | None:
    """Return the Design Decision 6 latest-outcome API shape, or None.

    Returns None when no decision record exists — the caller should emit
    response_outcome: null in the API response (never omit the key).

    outcome_summary is always sourced from the latest outcome event row.
    When a decision exists but no events have been appended yet, the fallback is
    the decision row's own outcome_summary with execution_mode=observed/selected state.

    Lookup priority: decision_id > soar_correlation_id > alert_id.
    """
    if decision_id is None and not soar_correlation_id and alert_id is None:
        raise SoarResponseOutcomeValidationError(
            "decision_id, soar_correlation_id, or alert_id is required"
        )

    decision: dict[str, Any] | None = None
    if decision_id is not None:
        decision = _fetch_decision_by_id(conn, int(decision_id))
    elif soar_correlation_id:
        decision = _fetch_decision_by_correlation_id(
            conn, validate_soar_correlation_id(soar_correlation_id)
        )
    else:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_DECISION_COLUMNS}
                FROM soar_response_decisions
                WHERE alert_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (alert_id,),
            )
            row = cur.fetchone()
        decision = _decision_row_to_dict(row) if row else None

    if decision is None:
        return None

    latest_event = get_latest_outcome_for_decision(conn, decision["id"])
    return build_latest_outcome_api_shape(decision, latest_event)


def serialize_outcome_timeline(
    conn,
    decision_id: int,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return ordered outcome events for a decision, oldest first (chronological).

    Returns [] when the decision does not exist or has no events. Never raises on
    missing data — callers can safely use the empty list without null-checking.
    """
    if _fetch_decision_by_id(conn, int(decision_id)) is None:
        return []

    sql = f"""
        SELECT {_OUTCOME_EVENT_COLUMNS}
        FROM soar_response_outcome_events
        WHERE decision_id = %s
        ORDER BY occurred_at ASC, created_at ASC, id ASC
    """
    params: list[Any] = [decision_id]
    if limit is not None and int(limit) > 0:
        sql += " LIMIT %s"
        params.append(int(limit))

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
    return [_outcome_event_row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Retention, archive, and reporting (Phase 10)
# ---------------------------------------------------------------------------

# Indefinite live retention until an operator sets SIEM_OUTCOME_RETENTION_DAYS.
DEFAULT_LIVE_RETENTION_DAYS: int | None = None
REAL_EXECUTION_AUDIT_RETENTION_DAYS: int | None = None

ARCHIVE_PRESERVED_FIELDS: tuple[str, ...] = (
    "decision_id",
    "soar_correlation_id",
    "selected_action",
    "decision_source",
    "execution_mode",
    "execution_state",
    "external_executed",
    "tracking_recorded",
    "simulated",
    "outcome_summary",
    "alert_id",
    "incident_id",
    "queue_id",
    "playbook_execution_id",
    "approval_request_id",
)

PRIMARY_ANALYST_QUESTION = (
    "What happened, what response was selected, what playbook ran, "
    "and was anything actually executed?"
)


def _parse_optional_positive_int_env(name: str) -> int | None:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return None
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def get_canonical_outcome_retention_policy() -> dict[str, Any]:
    """Document the live retention window used by metrics and reporting helpers."""
    live_window = _parse_optional_positive_int_env("SIEM_OUTCOME_RETENTION_DAYS")
    if live_window is None:
        live_window = DEFAULT_LIVE_RETENTION_DAYS
    return {
        "live_retention_days": live_window,
        "live_retention_policy": (
            "indefinite_by_default"
            if live_window is None
            else f"{live_window}_day_live_window"
        ),
        "archive_strategy": (
            "Events older than the live window are eligible for cold archive after "
            "a summary row is written. Real-execution evidence rows are never deleted "
            "during routine archival."
        ),
        "real_execution_audit_retention_days": REAL_EXECUTION_AUDIT_RETENTION_DAYS,
        "archive_preserved_fields": list(ARCHIVE_PRESERVED_FIELDS),
        "metrics_scope": (
            "canonical_outcome_counts aggregate all live canonical outcome events "
            "currently stored in soar_response_outcome_events. Archived summaries "
            "are not included until an archive aggregation job is deployed."
        ),
        "primary_analyst_question": PRIMARY_ANALYST_QUESTION,
    }


def build_archive_record(
    decision: dict[str, Any],
    latest_event: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the minimum archive summary row for a decision + latest outcome."""
    if latest_event is not None:
        execution_mode = latest_event["execution_mode"]
        execution_state = latest_event["execution_state"]
        external_executed = latest_event["external_executed"]
        tracking_recorded = latest_event["tracking_recorded"]
        simulated = latest_event["simulated"]
        outcome_summary = latest_event["outcome_summary"]
        playbook_execution_id = latest_event.get("playbook_execution_id") or decision.get(
            "playbook_execution_id"
        )
        approval_request_id = latest_event.get("approval_request_id") or decision.get(
            "approval_request_id"
        )
        alert_id = latest_event.get("alert_id") or decision.get("alert_id")
        incident_id = latest_event.get("incident_id") or decision.get("incident_id")
        queue_id = latest_event.get("queue_id") or decision.get("queue_id")
    else:
        execution_mode = "observed"
        execution_state = "selected"
        external_executed = False
        tracking_recorded = False
        simulated = False
        outcome_summary = decision["outcome_summary"]
        playbook_execution_id = decision.get("playbook_execution_id")
        approval_request_id = decision.get("approval_request_id")
        alert_id = decision.get("alert_id")
        incident_id = decision.get("incident_id")
        queue_id = decision.get("queue_id")

    record = {
        "decision_id": decision["id"],
        "soar_correlation_id": decision["soar_correlation_id"],
        "selected_action": decision["selected_action"],
        "decision_source": decision["decision_source"],
        "execution_mode": execution_mode,
        "execution_state": execution_state,
        "external_executed": external_executed,
        "tracking_recorded": tracking_recorded,
        "simulated": simulated,
        "outcome_summary": outcome_summary,
        "alert_id": alert_id,
        "incident_id": incident_id,
        "queue_id": queue_id,
        "playbook_execution_id": playbook_execution_id,
        "approval_request_id": approval_request_id,
    }
    return {key: record[key] for key in ARCHIVE_PRESERVED_FIELDS}


def _fetch_decisions_for_traceability(
    conn,
    *,
    alert_id: int | None = None,
    incident_id: int | None = None,
    soar_correlation_id: str | None = None,
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if alert_id is not None:
        filters.append("alert_id = %s")
        params.append(int(alert_id))
    if incident_id is not None:
        filters.append("incident_id = %s")
        params.append(int(incident_id))
    if soar_correlation_id is not None:
        filters.append("soar_correlation_id = %s")
        params.append(validate_soar_correlation_id(soar_correlation_id))

    if not filters:
        raise SoarResponseOutcomeValidationError(
            "alert_id, incident_id, or soar_correlation_id is required"
        )

    where_clause = " OR ".join(filters)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_DECISION_COLUMNS}
            FROM soar_response_decisions
            WHERE {where_clause}
            ORDER BY created_at DESC, id DESC
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []
    return [_decision_row_to_dict(row) for row in rows]


def _build_traceability_entry(
    conn,
    decision: dict[str, Any],
    *,
    include_timeline: bool = True,
) -> dict[str, Any]:
    latest_event = get_latest_outcome_for_decision(conn, decision["id"])
    archive_record = build_archive_record(decision, latest_event)
    latest_shape = build_latest_outcome_api_shape(decision, latest_event)
    playbook_execution_id = archive_record["playbook_execution_id"]
    timeline = (
        serialize_outcome_timeline(conn, int(decision["id"])) if include_timeline else []
    )

    return {
        "analyst_question": PRIMARY_ANALYST_QUESTION,
        "what_happened": archive_record["outcome_summary"],
        "selected_response": archive_record["selected_action"],
        "decision_source": archive_record["decision_source"],
        "playbook_ran": playbook_execution_id is not None,
        "playbook_execution_id": playbook_execution_id,
        "anything_actually_executed": bool(archive_record["external_executed"]),
        "outcome_label": derive_outcome_label(
            execution_mode=archive_record["execution_mode"],
            execution_state=archive_record["execution_state"],
            external_executed=archive_record["external_executed"],
            tracking_recorded=archive_record["tracking_recorded"],
            simulated=archive_record["simulated"],
        ),
        "archive_record": archive_record,
        "latest_outcome": latest_shape,
        "step_outcomes": timeline,
    }


def get_response_outcome_traceability_report(
    conn,
    *,
    alert_id: int | None = None,
    incident_id: int | None = None,
    soar_correlation_id: str | None = None,
    include_timeline: bool = True,
) -> list[dict[str, Any]]:
    """Answer the primary analyst question from canonical decision/event tables."""
    decisions = _fetch_decisions_for_traceability(
        conn,
        alert_id=alert_id,
        incident_id=incident_id,
        soar_correlation_id=soar_correlation_id,
    )
    return [
        _build_traceability_entry(conn, decision, include_timeline=include_timeline)
        for decision in decisions
    ]


def get_decision_with_latest_outcome(
    conn,
    *,
    decision_id: int | None = None,
    soar_correlation_id: str | None = None,
) -> dict[str, Any] | None:
    if decision_id is None and not soar_correlation_id:
        raise SoarResponseOutcomeValidationError(
            "decision_id or soar_correlation_id is required"
        )

    decision = (
        _fetch_decision_by_id(conn, int(decision_id))
        if decision_id is not None
        else _fetch_decision_by_correlation_id(
            conn, validate_soar_correlation_id(soar_correlation_id or "")
        )
    )
    if decision is None:
        return None

    latest_outcome = get_latest_outcome_for_decision(conn, decision["id"])
    if latest_outcome is None:
        execution_mode = "observed"
        execution_state = "selected"
        external_executed = False
        tracking_recorded = False
        simulated = False
        outcome_summary = decision["outcome_summary"]
        reason_code = decision.get("reason_code")
    else:
        execution_mode = latest_outcome["execution_mode"]
        execution_state = latest_outcome["execution_state"]
        external_executed = latest_outcome["external_executed"]
        tracking_recorded = latest_outcome["tracking_recorded"]
        simulated = latest_outcome["simulated"]
        outcome_summary = latest_outcome["outcome_summary"]
        reason_code = latest_outcome.get("reason_code")

    outcome_label = derive_outcome_label(
        execution_mode=execution_mode,
        execution_state=execution_state,
        external_executed=external_executed,
        tracking_recorded=tracking_recorded,
        simulated=simulated,
    )

    return {
        "decision": decision,
        "latest_outcome": latest_outcome,
        "soar_correlation_id": decision["soar_correlation_id"],
        "decision_id": decision["id"],
        "latest_outcome_event_id": latest_outcome["id"] if latest_outcome else None,
        "selected_action": decision["selected_action"],
        "decision_source": decision["decision_source"],
        "execution_actor": latest_outcome["execution_actor"] if latest_outcome else None,
        "outcome_label": outcome_label,
        "execution_mode": execution_mode,
        "execution_state": execution_state,
        "external_executed": external_executed,
        "tracking_recorded": tracking_recorded,
        "simulated": simulated,
        "outcome_summary": outcome_summary,
        "reason_code": reason_code,
    }


from core.soar_response_outcomes_legacy import (  # noqa: E402
    BackfillDryRunPlan,
    format_backfill_plan_summary,
    infer_alert_legacy_outcome,
    infer_approval_request_legacy_outcome,
    infer_blocked_ip_legacy_outcome,
    infer_notification_delivery_legacy_outcome,
    infer_playbook_execution_legacy_outcome,
    infer_queue_legacy_outcome,
    infer_response_log_legacy_outcome,
    plan_backfill_dry_run,
    resolve_alert_outcome,
    resolve_approval_request_outcome,
    resolve_blocked_ip_outcome,
    resolve_notification_delivery_outcome,
    resolve_playbook_execution_outcome,
    resolve_queue_outcome,
    resolve_response_log_outcome,
)

__all__ = [
    "ARCHIVE_PRESERVED_FIELDS",
    "DEFAULT_LIVE_RETENTION_DAYS",
    "PRIMARY_ANALYST_QUESTION",
    "DECISION_SOURCES",
    "EXECUTION_ACTORS",
    "EXECUTION_MODES",
    "EXECUTION_STATES",
    "REASON_CODES",
    "SoarResponseOutcomeValidationError",
    "append_outcome_event",
    "create_response_decision",
    "derive_outcome_label",
    "format_backfill_plan_summary",
    "generate_legacy_soar_correlation_id",
    "generate_soar_correlation_id",
    "get_decision_with_latest_outcome",
    "get_latest_outcome_by_correlation_id",
    "get_latest_outcome_for_alert",
    "get_latest_outcome_for_approval_request",
    "get_latest_outcome_for_decision",
    "get_latest_outcome_for_incident",
    "get_latest_outcome_for_notification_delivery",
    "get_latest_outcome_for_playbook_execution",
    "get_latest_outcome_for_queue",
    "get_latest_outcome_for_source_ip",
    "build_archive_record",
    "build_latest_outcome_api_shape",
    "get_canonical_outcome_retention_policy",
    "get_response_outcome_traceability_report",
    "get_latest_decisions_for_alerts_bulk",
    "get_latest_outcomes_for_alerts_bulk",
    "get_latest_outcomes_for_approvals_bulk",
    "get_latest_outcomes_for_blocked_ips_bulk",
    "get_latest_outcomes_for_incidents_bulk",
    "get_latest_outcomes_for_notification_deliveries_bulk",
    "get_latest_outcomes_for_playbook_executions_bulk",
    "get_latest_outcomes_for_queues_bulk",
    "get_outcome_count_groups",
    "get_recent_outcomes_for_source_ip",
    "infer_alert_legacy_outcome",
    "infer_approval_request_legacy_outcome",
    "infer_blocked_ip_legacy_outcome",
    "infer_notification_delivery_legacy_outcome",
    "infer_playbook_execution_legacy_outcome",
    "infer_queue_legacy_outcome",
    "infer_response_log_legacy_outcome",
    "plan_backfill_dry_run",
    "redact_soar_outcome_metadata",
    "resolve_alert_outcome",
    "resolve_approval_request_outcome",
    "resolve_blocked_ip_outcome",
    "resolve_notification_delivery_outcome",
    "resolve_playbook_execution_outcome",
    "resolve_queue_outcome",
    "resolve_response_log_outcome",
    "serialize_incident_outcome_timeline_entries",
    "serialize_latest_outcome",
    "serialize_outcome_timeline",
    "validate_decision_source",
    "validate_execution_actor",
    "validate_execution_mode",
    "validate_execution_state",
    "validate_outcome_booleans",
    "validate_reason_code",
    "validate_soar_correlation_id",
]
