from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
from typing import Any

from flask import current_app, request
from psycopg2.extras import Json

from core.ai.action_schemas import (
    ACTION_ADD_ALERT_NOTE,
    ACTION_ADD_INCIDENT_NOTE,
    ACTION_CHANGE_INCIDENT_STATUS,
    ACTION_CREATE_INCIDENT_FROM_ALERT,
    ACTION_CREATE_PLAYBOOK_DRAFT,
    ACTION_UPDATE_DETECTION_RULE_PARAMETERS,
    OUTCOME_DUPLICATE,
    OUTCOME_FAILED,
    OUTCOME_REAL,
    STATUS_CONFIRMED,
    STATUS_DUPLICATE_SUPPRESSED,
    STATUS_FORBIDDEN,
    STATUS_INVALID_REQUEST,
    STATUS_PREVIEW_READY,
    STATUS_STALE_SOURCE,
    AiActionValidationError,
    get_action_definition,
    normalize_action_payload,
    normalize_idempotency_key,
    payload_digest,
    safe_payload_for_response,
)
from core.audit_helpers import log_audit_event
from core.db import get_db_connection
from core.incident_store import maybe_create_or_link_incident, update_incident_status
from core.note_store import create_alert_note, create_incident_note
from core.playbook_store import create_playbook_definition
from engines.detection_config import (
    get_detection_rule_defaults,
    get_effective_detection_rule,
    validate_detection_rule_config,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiActionServiceResult:
    payload: dict[str, Any]
    status_code: int = 200


def preview_ai_action(payload: dict[str, Any], *, actor: Any) -> AiActionServiceResult:
    request_data = _parse_common_payload(payload, actor=actor, require_confirm_fields=False)
    conn = None
    try:
        conn = get_db_connection()
        target = _load_target_snapshot(conn, request_data["action_type"], request_data["payload"])
        token = _build_confirmation_token(
            action_type=request_data["action_type"],
            payload_digest_value=request_data["payload_digest"],
            target_fingerprint=target["fingerprint"],
            idempotency_key=request_data["idempotency_key"],
            actor_role=request_data["actor_role"],
        )
        preview = {
            "action_type": request_data["action_type"],
            "description": request_data["definition"].description,
            "required_role": request_data["definition"].required_role,
            "dispatch_path": request_data["definition"].dispatch_path,
            "target_resource_keys": target["resource_keys"],
            "target_fingerprint": target["fingerprint"],
            "payload": safe_payload_for_response(request_data["payload"]),
            "payload_digest": request_data["payload_digest"],
            "idempotency_key": request_data["idempotency_key"],
            "confirmation_token": token,
            "requires_confirmation": True,
            "source_draft": _safe_source_draft(payload.get("source_draft")),
            "stale": False,
            "read_only_preview": True,
        }
        return AiActionServiceResult(
            {
                "status": STATUS_PREVIEW_READY,
                "preview": preview,
                "result": None,
                "error": None,
            },
            200,
        )
    finally:
        if conn:
            conn.close()


def confirm_ai_action(payload: dict[str, Any], *, actor: Any) -> AiActionServiceResult:
    request_data = _parse_common_payload(payload, actor=actor, require_confirm_fields=True)
    confirmation_token = str(payload.get("confirmation_token") or "").strip()
    expected_fingerprint = str(payload.get("target_fingerprint") or "").strip()

    conn = None
    try:
        conn = get_db_connection()
        target = _load_target_snapshot(conn, request_data["action_type"], request_data["payload"])
        if expected_fingerprint and expected_fingerprint != target["fingerprint"]:
            return _safe_rejection_response(
                STATUS_STALE_SOURCE,
                "Target state changed after preview. Regenerate the action preview.",
                request_data,
                target,
                status_code=409,
            )

        expected_token = _build_confirmation_token(
            action_type=request_data["action_type"],
            payload_digest_value=request_data["payload_digest"],
            target_fingerprint=target["fingerprint"],
            idempotency_key=request_data["idempotency_key"],
            actor_role=request_data["actor_role"],
        )
        if not hmac.compare_digest(confirmation_token, expected_token):
            return _safe_rejection_response(
                STATUS_INVALID_REQUEST,
                "confirmation_token does not match the current action payload",
                request_data,
                target,
                status_code=400,
            )

        existing = _get_idempotency_record(conn, request_data["idempotency_key"])
        if existing is not None:
            if existing["payload_digest"] != request_data["payload_digest"] or existing["action_type"] != request_data["action_type"]:
                return _safe_rejection_response(
                    STATUS_INVALID_REQUEST,
                    "idempotency_key was already used for a different action payload",
                    request_data,
                    target,
                    status_code=409,
                )
            result_payload = dict(existing["result_payload"] or {})
            result_payload["outcome"] = OUTCOME_DUPLICATE
            return AiActionServiceResult(
                {"status": STATUS_DUPLICATE_SUPPRESSED, "preview": None, "result": result_payload, "error": None},
                200,
            )

        try:
            result = _dispatch_confirmed_action(conn, request_data["action_type"], request_data["payload"], actor=actor)
            _record_idempotency(conn, request_data, target, result)
            conn.commit()
        except Exception as error:
            if conn:
                conn.rollback()
            _LOGGER.error("ai_action_confirm_failed action_type=%s error=%s", request_data["action_type"], error)
            result = {
                "outcome": OUTCOME_FAILED,
                "message": "AI action failed before a successful mutation could be confirmed.",
                "error_code": "dispatch_failed",
                "target_resource_keys": target["resource_keys"],
            }
            _write_ai_action_audit(request_data, target, result, actor=actor, attempted=True)
            return AiActionServiceResult({"status": STATUS_CONFIRMED, "preview": None, "result": result, "error": result["message"]}, 500)

        _write_result_action_audit(result, actor=actor)
        _write_ai_action_audit(request_data, target, result, actor=actor, attempted=True)
        return AiActionServiceResult({"status": STATUS_CONFIRMED, "preview": None, "result": result, "error": None}, 200)
    finally:
        if conn:
            conn.close()


def service_error_response(error: Exception) -> AiActionServiceResult:
    status = getattr(error, "status", STATUS_INVALID_REQUEST)
    status_code = getattr(error, "status_code", 400)
    return AiActionServiceResult(
        {
            "status": status,
            "preview": None,
            "result": {
                "outcome": OUTCOME_FAILED,
                "message": str(error),
                "no_production_change": True,
            },
            "error": str(error),
        },
        status_code,
    )


def _parse_common_payload(payload: dict[str, Any], *, actor: Any, require_confirm_fields: bool) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AiActionValidationError("JSON object body is required")

    definition = get_action_definition(payload.get("action_type"))
    actor_role = str(getattr(actor, "role", "") or "")
    if not _role_allowed(actor_role, definition.required_role):
        raise AiActionValidationError(
            "current role cannot perform this AI action",
            status=STATUS_FORBIDDEN,
            status_code=403,
        )
    normalized_payload = normalize_action_payload(definition.action_type, payload.get("payload"))
    idempotency_key = normalize_idempotency_key(payload.get("idempotency_key"))
    digest = payload_digest({"action_type": definition.action_type, "payload": normalized_payload})

    if require_confirm_fields:
        if payload.get("confirm") is not True:
            raise AiActionValidationError("confirm=true is required")
        supplied_digest = str(payload.get("payload_digest") or "").strip()
        if supplied_digest != digest:
            raise AiActionValidationError("payload_digest does not match the normalized payload")
        if not str(payload.get("confirmation_token") or "").strip():
            raise AiActionValidationError("confirmation_token is required")

    return {
        "definition": definition,
        "action_type": definition.action_type,
        "payload": normalized_payload,
        "idempotency_key": idempotency_key,
        "payload_digest": digest,
        "actor_role": actor_role,
        "actor_username": str(getattr(actor, "id", None) or getattr(actor, "username", "") or "unknown"),
    }


def _role_allowed(actor_role: str, required_role: str) -> bool:
    if required_role == "super_admin":
        return actor_role == "super_admin"
    if required_role == "analyst_or_super_admin":
        return actor_role in {"analyst", "super_admin"}
    return False


def _load_target_snapshot(conn, action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_type == ACTION_ADD_ALERT_NOTE:
        alert = _fetch_alert(conn, payload["alert_id"])
        return _target(["alert:%s" % payload["alert_id"]], {"alert": alert})
    if action_type == ACTION_ADD_INCIDENT_NOTE:
        incident = _fetch_incident(conn, payload["incident_id"])
        return _target(["incident:%s" % payload["incident_id"]], {"incident": incident})
    if action_type == ACTION_CHANGE_INCIDENT_STATUS:
        incident = _fetch_incident(conn, payload["incident_id"])
        return _target(["incident:%s" % payload["incident_id"]], {"incident": incident})
    if action_type == ACTION_CREATE_PLAYBOOK_DRAFT:
        with conn.cursor() as cur:
            cur.execute("SELECT id, enabled, updated_at FROM playbook_definitions WHERE id = %s", (payload["playbook_id"],))
            existing = cur.fetchone()
        if existing is not None:
            raise AiActionValidationError("playbook_id already exists", status_code=409)
        return _target(["playbook:%s" % payload["playbook_id"]], {"playbook_id": payload["playbook_id"], "exists": False})
    if action_type == ACTION_UPDATE_DETECTION_RULE_PARAMETERS:
        defaults = get_detection_rule_defaults()
        if payload["rule_id"] not in defaults:
            raise AiActionValidationError("detection rule not found", status_code=404)
        with conn.cursor() as cur:
            rule = get_effective_detection_rule(payload["rule_id"], cur=cur)
        return _target(["detection_rule:%s" % payload["rule_id"]], {"rule": rule})
    if action_type == ACTION_CREATE_INCIDENT_FROM_ALERT:
        alert = _fetch_alert(conn, payload["alert_id"])
        return _target(["alert:%s" % payload["alert_id"], "incident"], {"alert": alert})
    raise AiActionValidationError(f"unsupported action type: {action_type}")


def _dispatch_confirmed_action(conn, action_type: str, payload: dict[str, Any], *, actor: Any) -> dict[str, Any]:
    actor_username = str(getattr(actor, "id", None) or getattr(actor, "username", "") or "unknown")
    if action_type == ACTION_ADD_ALERT_NOTE:
        note = create_alert_note(conn, alert_id=payload["alert_id"], author=actor_username, note_text=payload["note_text"])
        return _result(OUTCOME_REAL, "Alert note added.", ["alert:%s" % payload["alert_id"], "alert_note:%s" % note["id"]], {"note": note})
    if action_type == ACTION_ADD_INCIDENT_NOTE:
        note = create_incident_note(conn, incident_id=payload["incident_id"], author=actor_username, note_text=payload["note_text"])
        return _result(
            OUTCOME_REAL,
            "Incident note added.",
            ["incident:%s" % payload["incident_id"], "incident_note:%s" % note["id"]],
            {"note": note},
            action_audit={
                "event_type": "ADD_INCIDENT_NOTE",
                "target_alert_id": None,
                "details": {"incident_id": payload["incident_id"], "note_id": note["id"]},
            },
        )
    if action_type == ACTION_CHANGE_INCIDENT_STATUS:
        incident = update_incident_status(conn, payload["incident_id"], payload["status"], actor_username)
        return _result(
            OUTCOME_REAL,
            "Incident status changed.",
            ["incident:%s" % payload["incident_id"]],
            {"incident": incident},
            action_audit={
                "event_type": "UPDATE_INCIDENT_STATUS",
                "target_alert_id": None,
                "details": {"incident_id": payload["incident_id"], "status": payload["status"]},
            },
        )
    if action_type == ACTION_CREATE_PLAYBOOK_DRAFT:
        row = create_playbook_definition(
            conn,
            payload["playbook_id"],
            payload["name"],
            description=payload.get("description"),
            trigger_config=payload.get("trigger_config") or {},
            steps=payload["steps"],
            enabled=False,
        )
        return _result(OUTCOME_REAL, "Disabled playbook draft created.", ["playbook:%s" % payload["playbook_id"]], {"playbook": row})
    if action_type == ACTION_UPDATE_DETECTION_RULE_PARAMETERS:
        with conn.cursor() as cur:
            old_rule = get_effective_detection_rule(payload["rule_id"], cur=cur)
            validated = validate_detection_rule_config(payload["rule_id"], payload["parameters"], old_rule["active"])
            merged_parameters = dict(old_rule["parameters"])
            merged_parameters.update(validated["parameters"])
            cur.execute(
                """
                INSERT INTO detection_config (rule_id, parameters, active, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (rule_id) DO UPDATE
                SET parameters = EXCLUDED.parameters,
                    active = EXCLUDED.active,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = NOW()
                """,
                (payload["rule_id"], Json(merged_parameters), old_rule["active"], actor_username),
            )
            updated = get_effective_detection_rule(payload["rule_id"], cur=cur)
        return _result(
            OUTCOME_REAL,
            "Detection rule parameters updated.",
            ["detection_rule:%s" % payload["rule_id"]],
            {"rule": updated},
            action_audit={
                "event_type": "detection_rule_updated",
                "target_alert_id": None,
                "details": {
                    "rule_id": payload["rule_id"],
                    "old_parameters": old_rule["parameters"],
                    "new_parameters": updated["parameters"],
                    "old_active": old_rule["active"],
                    "new_active": updated["active"],
                    "changes": _parameter_changes(old_rule["parameters"], updated["parameters"]),
                    "actor": actor_username,
                },
            },
        )
    if action_type == ACTION_CREATE_INCIDENT_FROM_ALERT:
        alert = _fetch_alert(conn, payload["alert_id"])
        incident = maybe_create_or_link_incident(
            conn,
            payload["alert_id"],
            alert["severity"],
            alert["source_ip"],
            alert_type=alert.get("alert_type"),
            context=alert.get("context") or {},
        )
        if incident is None:
            return _result(OUTCOME_FAILED, "Existing incident policy did not create or link an incident for this alert.", ["alert:%s" % payload["alert_id"]], {})
        return _result(OUTCOME_REAL, "Incident created or linked from alert.", ["alert:%s" % payload["alert_id"], "incident:%s" % incident["id"]], {"incident": incident})
    raise AiActionValidationError(f"unsupported action type: {action_type}")


def _fetch_alert(conn, alert_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, alert_type, severity, host(source_ip), status, message,
                   source, source_type, context, created_at
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise AiActionValidationError("alert not found", status_code=404)
    return {
        "id": row[0],
        "alert_type": row[1],
        "severity": row[2],
        "source_ip": row[3],
        "status": row[4],
        "message": row[5],
        "source": row[6],
        "source_type": row[7],
        "context": row[8] if isinstance(row[8], dict) else {},
        "created_at": str(row[9]),
    }


def _fetch_incident(conn, incident_id: int) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            WHERE id = %s
            """,
            (incident_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise AiActionValidationError("incident not found", status_code=404)
    return {
        "id": row[0],
        "title": row[1],
        "severity": row[2],
        "priority": row[3],
        "status": row[4],
        "source_ip": row[5],
        "assigned_to": row[6],
        "created_at": str(row[7]),
        "resolved_at": str(row[8]) if row[8] is not None else None,
    }


def _target(resource_keys: list[str], state: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_keys": resource_keys,
        "fingerprint": payload_digest({"resource_keys": resource_keys, "state": state}),
        "state": state,
    }


def _build_confirmation_token(
    *,
    action_type: str,
    payload_digest_value: str,
    target_fingerprint: str,
    idempotency_key: str,
    actor_role: str,
) -> str:
    secret = str(current_app.config.get("SECRET_KEY") or "development-secret").encode("utf-8")
    message = "|".join([action_type, payload_digest_value, target_fingerprint, idempotency_key, actor_role]).encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _get_idempotency_record(conn, key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT idempotency_key, payload_digest, action_type, outcome, result_payload
            FROM ai_action_idempotency
            WHERE idempotency_key = %s
            """,
            (key,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "idempotency_key": row[0],
        "payload_digest": row[1],
        "action_type": row[2],
        "outcome": row[3],
        "result_payload": row[4] if isinstance(row[4], dict) else {},
    }


def _record_idempotency(conn, request_data: dict[str, Any], target: dict[str, Any], result: dict[str, Any]) -> None:
    stored_result = dict(result)
    stored_result.pop("_action_audit", None)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_action_idempotency (
                idempotency_key, payload_digest, action_type, target_resource_keys,
                outcome, result_payload, actor_username
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request_data["idempotency_key"],
                request_data["payload_digest"],
                request_data["action_type"],
                Json(target["resource_keys"], dumps=_json_dumps),
                result.get("outcome") or OUTCOME_FAILED,
                Json(stored_result, dumps=_json_dumps),
                request_data.get("actor_username"),
            ),
        )


def _write_ai_action_audit(request_data: dict[str, Any], target: dict[str, Any], result: dict[str, Any], *, actor: Any, attempted: bool) -> None:
    details = {
        "action_type": request_data["action_type"],
        "target_resource_keys": target["resource_keys"],
        "idempotency_key": request_data["idempotency_key"],
        "payload_digest": request_data["payload_digest"],
        "outcome": result.get("outcome"),
        "status": STATUS_CONFIRMED if attempted else STATUS_INVALID_REQUEST,
        "dispatch_path": request_data["definition"].dispatch_path,
        "error_code": result.get("error_code"),
    }
    log_audit_event(
        "AI_ACTION_CONFIRMED",
        actor_username=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        http_method=getattr(request, "method", None),
        request_path=getattr(request, "path", None),
        source_ip=getattr(request, "remote_addr", None),
        details=details,
    )


def _write_result_action_audit(result: dict[str, Any], *, actor: Any) -> None:
    action_audit = result.get("_action_audit")
    if not isinstance(action_audit, dict):
        return
    _write_action_specific_audit(
        str(action_audit.get("event_type") or ""),
        actor=actor,
        target_alert_id=action_audit.get("target_alert_id"),
        details=action_audit.get("details") if isinstance(action_audit.get("details"), dict) else {},
    )
    result.pop("_action_audit", None)


def _write_action_specific_audit(event_type: str, *, actor: Any, target_alert_id: int | None, details: dict[str, Any]) -> None:
    log_audit_event(
        event_type,
        actor_username=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        target_alert_id=target_alert_id,
        http_method=getattr(request, "method", None),
        request_path=getattr(request, "path", None),
        source_ip=getattr(request, "remote_addr", None),
        details=details,
    )


def _result(
    outcome: str,
    message: str,
    resource_keys: list[str],
    data: dict[str, Any],
    *,
    action_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "outcome": outcome,
        "message": message,
        "target_resource_keys": resource_keys,
        "data": data,
        "no_production_change": outcome != OUTCOME_REAL,
    }
    if action_audit is not None:
        result["_action_audit"] = action_audit
    return result


def _safe_rejection_response(
    status: str,
    message: str,
    request_data: dict[str, Any],
    target: dict[str, Any],
    *,
    status_code: int,
) -> AiActionServiceResult:
    return AiActionServiceResult(
        {
            "status": status,
            "preview": None,
            "result": {
                "outcome": _outcome_for_rejection_status(status),
                "message": message,
                "target_resource_keys": target["resource_keys"],
                "no_production_change": True,
                "action_type": request_data["action_type"],
            },
            "error": message,
        },
        status_code,
    )


def _outcome_for_rejection_status(status: str) -> str:
    if status == STATUS_DUPLICATE_SUPPRESSED:
        return OUTCOME_DUPLICATE
    return OUTCOME_FAILED


def _safe_source_draft(source_draft: Any) -> dict[str, Any] | None:
    if not isinstance(source_draft, dict):
        return None
    allowed = {}
    for key in ("draft_type", "client_request_id", "generated_at"):
        if source_draft.get(key) is not None:
            allowed[key] = str(source_draft.get(key))[:160]
    labels = source_draft.get("labels")
    if isinstance(labels, dict):
        allowed["labels"] = {
            "ai_generated": labels.get("ai_generated") is True,
            "read_only": labels.get("read_only") is True,
            "persisted": labels.get("persisted") is True,
            "applied": labels.get("applied") is True,
        }
    return allowed or None


def _parameter_changes(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            changes.append({"field": key, "old": old.get(key), "new": new.get(key)})
    return changes


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str)
