"""
Canonical SOAR response decision and outcome event persistence.

Callers own transaction boundaries (commit/rollback). This module never commits.
Outcome events are append-only. Decisions are inserted once per selected response.

Do not persist webhooks, tokens, headers, raw payloads, or raw provider responses.
"""

from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

EXECUTION_MODES = frozenset({"observed", "simulation", "tracking_only", "real"})
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
    "BackfillDryRunPlan",
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
    "validate_decision_source",
    "validate_execution_actor",
    "validate_execution_mode",
    "validate_execution_state",
    "validate_outcome_booleans",
    "validate_reason_code",
    "validate_soar_correlation_id",
]
