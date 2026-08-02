from __future__ import annotations

import ipaddress
from typing import Any, Callable

from psycopg2.extras import RealDictCursor

from core.ai.session_memory_store import (
    PUBLIC_ASSERTION_TYPES,
    SessionMemoryError,
    SessionMemoryValidationError,
    ThreadExpiredError,
    append_turn,
    create_thread,
    get_thread,
    list_turns,
    reset_thread,
)
from core.db import get_db_connection


SUPPORTED_ENTITY_TYPES = frozenset(
    {"investigation", "alert", "incident", "source_ip", "recon_activity", "response_registry", "detection", "dashboard", "general"}
)
SUPPORTED_PUBLIC_WORKFLOWS = frozenset(
    {"quick_explain", "deep_investigate", "decision_support", "generate_artifact"}
)


class ThreadTargetUnavailableError(SessionMemoryError):
    status_code = 409
    error_code = "thread_target_unavailable"


def create_thread_request(payload: dict[str, Any], *, owner_username: str) -> tuple[dict[str, Any], int]:
    data = _require_object(payload)

    def operation(conn):
        target = _normalize_and_validate_target(conn, data, owner_username=owner_username)
        thread, created = create_thread(
            conn,
            owner_username=owner_username,
            domain="siem",
            investigation_id=target["investigation_id"],
            primary_entity_type=target["entity_type"],
            primary_entity_id=target["entity_id"],
            scope_key=target["scope_key"],
            is_default=target["is_default"],
        )
        return {"thread": thread, "created": created, "llm_invoked": False}, 201 if created else 200

    return _transaction(operation)


def read_thread_request(thread_id: str, *, owner_username: str) -> tuple[dict[str, Any], int]:
    def operation(conn):
        thread = get_thread(conn, thread_id=thread_id, owner_username=owner_username)
        _validate_stored_thread_target(conn, thread, owner_username=owner_username)
        return {"thread": thread}, 200

    return _transaction(operation)


def list_thread_turns_request(
    thread_id: str,
    *,
    owner_username: str,
    cursor: Any = None,
    limit: Any = 50,
) -> tuple[dict[str, Any], int]:
    parsed_cursor = _optional_non_negative_int(cursor, "cursor")
    parsed_limit = _positive_int(limit, "limit", maximum=100)

    def operation(conn):
        thread = get_thread(conn, thread_id=thread_id, owner_username=owner_username)
        _validate_stored_thread_target(conn, thread, owner_username=owner_username)
        page = list_turns(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            after_sequence=parsed_cursor,
            limit=parsed_limit,
        )
        return {"thread_id": thread_id, **page}, 200

    return _transaction(operation)


def submit_thread_turn_request(
    thread_id: str,
    payload: dict[str, Any],
    *,
    owner_username: str,
) -> tuple[dict[str, Any], int]:
    data = _require_object(payload)
    assertion_type = str(data.get("assertion_type") or "analyst_statement").strip().lower()
    if assertion_type not in PUBLIC_ASSERTION_TYPES:
        raise SessionMemoryValidationError(
            "Public turn submission supports analyst_statement, correction, or unresolved_question only."
        )
    expected_version = _positive_int(data.get("expected_version"), "expected_version")
    client_request_id = _required_text(data.get("client_request_id"), "client_request_id", 256)
    workflow = str(data.get("workflow") or "").strip().lower() or None
    if workflow is not None and workflow not in SUPPORTED_PUBLIC_WORKFLOWS:
        raise SessionMemoryValidationError("workflow is unsupported for SIEM conversation threads.")
    structured_payload = data.get("structured_payload") or {}
    if not isinstance(structured_payload, dict):
        raise SessionMemoryValidationError("structured_payload must be an object.")
    entity_snapshot = data.get("entity_snapshot") or {}
    if not isinstance(entity_snapshot, dict):
        raise SessionMemoryValidationError("entity_snapshot must be an object.")
    parent_turn_id = _optional_positive_int(data.get("parent_turn_id"), "parent_turn_id")

    def operation(conn):
        thread = get_thread(conn, thread_id=thread_id, owner_username=owner_username)
        _validate_stored_thread_target(conn, thread, owner_username=owner_username)
        if assertion_type == "correction":
            _validate_correction_target(
                conn,
                thread_id=thread_id,
                owner_username=owner_username,
                parent_turn_id=parent_turn_id,
                structured_payload=structured_payload,
            )
        turn, updated_thread, created = append_turn(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            expected_version=expected_version,
            client_request_id=client_request_id,
            role="user",
            content=data.get("content"),
            assertion_type=assertion_type,
            workflow=workflow,
            structured_payload=structured_payload,
            parent_turn_id=parent_turn_id,
            entity_snapshot=entity_snapshot,
            lifecycle_status="recorded",
        )
        return {
            "thread": updated_thread,
            "turn": turn,
            "created": created,
            "duplicate": not created,
            "llm_invoked": False,
        }, 201 if created else 200

    return _transaction(operation)


def reset_thread_request(
    thread_id: str,
    payload: dict[str, Any],
    *,
    owner_username: str,
) -> tuple[dict[str, Any], int]:
    data = _require_object(payload)
    expected_version = _positive_int(data.get("expected_version"), "expected_version")

    def operation(conn):
        old = get_thread(conn, thread_id=thread_id, owner_username=owner_username, require_active=False)
        if old["status"] == "reset" and old.get("replaced_by_thread_id"):
            closed, replacement = reset_thread(
                conn,
                thread_id=thread_id,
                owner_username=owner_username,
                expected_version=expected_version,
            )
            return {"closed_thread": closed, "thread": replacement, "created": False}, 200
        if old["status"] == "expired":
            raise ThreadExpiredError("Thread context has expired.")
        _validate_stored_thread_target(conn, old, owner_username=owner_username)
        closed, replacement = reset_thread(
            conn,
            thread_id=thread_id,
            owner_username=owner_username,
            expected_version=expected_version,
        )
        return {"closed_thread": closed, "thread": replacement, "created": True}, 201

    return _transaction(operation)


def error_payload(error: SessionMemoryError) -> tuple[dict[str, Any], int]:
    return {
        "status": "error",
        "error_code": getattr(error, "error_code", "invalid_session_memory_request"),
        "error": str(error),
    }, getattr(error, "status_code", 400)


def _transaction(operation: Callable[[Any], tuple[dict[str, Any], int]]) -> tuple[dict[str, Any], int]:
    conn = get_db_connection()
    try:
        result = operation(conn)
        conn.commit()
        return result
    except ThreadExpiredError:
        conn.commit()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalize_and_validate_target(conn, payload: dict[str, Any], *, owner_username: str) -> dict[str, Any]:
    domain = str(payload.get("domain") or "siem").strip().lower()
    if domain != "siem":
        raise SessionMemoryValidationError("Repo Assistant and SOC Briefing cannot use SIEM conversation threads.")
    investigation_id = _optional_positive_int(payload.get("investigation_id"), "investigation_id")
    raw_entity = payload.get("primary_entity") if isinstance(payload.get("primary_entity"), dict) else payload.get("entity")
    entity = raw_entity if isinstance(raw_entity, dict) else {}
    entity_type = str(entity.get("type") or payload.get("primary_entity_type") or "").strip().lower().replace("-", "_")
    entity_id = str(entity.get("id") or payload.get("primary_entity_id") or "").strip()
    if investigation_id is not None and not entity_type:
        entity_type, entity_id = "investigation", str(investigation_id)
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise SessionMemoryValidationError("primary entity type is unsupported.")
    entity_id = _required_text(entity_id, "primary_entity.id", 256)
    _validate_target_access(
        conn,
        owner_username=owner_username,
        investigation_id=investigation_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    scope_key = f"investigation:{investigation_id}" if investigation_id is not None else f"entity:{entity_type}:{entity_id}"
    is_default = payload.get("is_default", True)
    if not isinstance(is_default, bool):
        raise SessionMemoryValidationError("is_default must be a boolean.")
    return {
        "investigation_id": investigation_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "scope_key": scope_key,
        "is_default": is_default,
    }


def _validate_stored_thread_target(conn, thread: dict[str, Any], *, owner_username: str) -> None:
    entity = thread.get("primary_entity") or {}
    _validate_target_access(
        conn,
        owner_username=owner_username,
        investigation_id=thread.get("investigation_id"),
        entity_type=str(entity.get("type") or ""),
        entity_id=str(entity.get("id") or ""),
    )


def _validate_target_access(
    conn,
    *,
    owner_username: str,
    investigation_id: int | None,
    entity_type: str,
    entity_id: str,
) -> None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if investigation_id is not None:
            cur.execute(
                """
                SELECT id FROM investigations
                WHERE id = %s AND owner_username = %s AND visibility = 'private'
                FOR KEY SHARE
                """,
                (investigation_id, owner_username),
            )
            if cur.fetchone() is None:
                raise ThreadTargetUnavailableError("Investigation is unavailable or not owned by the current analyst.")
        if entity_type == "investigation":
            try:
                parsed_id = int(entity_id)
            except (TypeError, ValueError) as error:
                raise SessionMemoryValidationError("investigation entity id must be an integer.") from error
            cur.execute(
                """
                SELECT id FROM investigations
                WHERE id = %s AND owner_username = %s AND visibility = 'private'
                FOR KEY SHARE
                """,
                (parsed_id, owner_username),
            )
            if cur.fetchone() is None:
                raise ThreadTargetUnavailableError("Investigation is unavailable or not owned by the current analyst.")
            if investigation_id is not None and parsed_id != investigation_id:
                raise SessionMemoryValidationError("primary investigation entity does not match investigation_id.")
            return
        if entity_type in {"dashboard", "general"}:
            return
        if entity_type == "source_ip":
            try:
                normalized_ip = str(ipaddress.ip_address(entity_id))
            except ValueError as error:
                raise SessionMemoryValidationError("source_ip entity id must be a valid IP address.") from error
            cur.execute("SELECT id FROM alerts WHERE source_ip = %s::inet ORDER BY id LIMIT 1 FOR KEY SHARE", (normalized_ip,))
            if cur.fetchone() is None:
                cur.execute("SELECT id FROM events WHERE source_ip = %s::inet ORDER BY id LIMIT 1 FOR KEY SHARE", (normalized_ip,))
                if cur.fetchone() is None:
                    raise ThreadTargetUnavailableError("Source IP is unavailable in current SIEM evidence.")
            return
        table, identifier_field = {
            "alert": ("alerts", "id"),
            "incident": ("incidents", "id"),
            "recon_activity": ("recon_activities", "id"),
            "response_registry": ("indicator_registry", "id"),
            "detection": ("alerts", "id"),
        }[entity_type]
        try:
            parsed_id = int(entity_id)
        except (TypeError, ValueError) as error:
            raise SessionMemoryValidationError(f"{entity_type} entity id must be an integer.") from error
        cur.execute(f"SELECT 1 FROM {table} WHERE {identifier_field} = %s FOR KEY SHARE", (parsed_id,))
        if cur.fetchone() is None:
            raise ThreadTargetUnavailableError(f"{entity_type.replace('_', ' ').title()} is unavailable.")


def _validate_correction_target(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    parent_turn_id: int | None,
    structured_payload: dict[str, Any],
) -> None:
    supersedes = structured_payload.get("supersedes")
    if isinstance(supersedes, dict) and str(supersedes.get("type") or "").strip().lower() == "evidence":
        raise SessionMemoryValidationError("Corrections cannot supersede verified evidence.")
    if parent_turn_id is None:
        raise SessionMemoryValidationError("correction requires parent_turn_id.")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT assertion_type FROM anakin_turns
            WHERE id = %s AND thread_id = %s AND owner_username = %s
            """,
            (parent_turn_id, thread_id, owner_username),
        )
        target = cur.fetchone()
    if target is None:
        raise SessionMemoryValidationError("correction target was not found in this thread.")
    if target["assertion_type"] not in {"analyst_statement", "model_inference"}:
        raise SessionMemoryValidationError("correction target is not a statement or inference.")


def _require_object(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SessionMemoryValidationError("JSON object body is required.")
    return payload


def _required_text(value: Any, field_name: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise SessionMemoryValidationError(f"{field_name} is required.")
    if len(text) > max_chars:
        raise SessionMemoryValidationError(f"{field_name} is too large.")
    return text


def _positive_int(value: Any, field_name: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise SessionMemoryValidationError(f"{field_name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SessionMemoryValidationError(f"{field_name} must be a positive integer.") from error
    if parsed <= 0 or (maximum is not None and parsed > maximum):
        raise SessionMemoryValidationError(f"{field_name} must be a positive integer{f' no greater than {maximum}' if maximum else ''}.")
    return parsed


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    return _positive_int(value, field_name)


def _optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise SessionMemoryValidationError(f"{field_name} must be a non-negative integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise SessionMemoryValidationError(f"{field_name} must be a non-negative integer.") from error
    if parsed < 0:
        raise SessionMemoryValidationError(f"{field_name} must be a non-negative integer.")
    return parsed
