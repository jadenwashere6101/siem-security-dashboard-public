from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import uuid
from typing import Any

from psycopg2.extras import Json, RealDictCursor


ACTIVE_RETENTION = timedelta(days=7)
CONTENT_RETENTION = timedelta(days=90)
MAX_CONTENT_CHARS = 8000
MAX_JSON_CHARS = 32768
MAX_JSON_DEPTH = 6
MAX_COLLECTION_ITEMS = 100

THREAD_ACTIVE = "active"
THREAD_EXPIRED = "expired"
THREAD_RESET = "reset"
THREAD_CLOSED = "closed"
THREAD_ARCHIVED = "archived"

PUBLIC_ASSERTION_TYPES = frozenset({"analyst_statement", "correction", "unresolved_question"})
ASSERTION_TYPES = frozenset(
    {"analyst_statement", "model_inference", "correction", "unresolved_question", "artifact_preview", "system_event"}
)
MODEL_PROVENANCE = "model_inference"
EVIDENCE_PROVENANCE = "verified_evidence"

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "webhook",
)
_CONTROL_MARKERS = re.compile(
    r"(?i)(<\/?system>|<\/?assistant>|\[/?inst\]|<<\/?sys>>|begin\s+(?:system|developer)\s+(?:prompt|message))"
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SessionMemoryError(ValueError):
    status_code = 400
    error_code = "invalid_session_memory_request"


class ThreadNotFoundError(SessionMemoryError):
    status_code = 404
    error_code = "thread_not_found"


class ThreadExpiredError(SessionMemoryError):
    status_code = 410
    error_code = "thread_expired"


class ThreadClosedError(SessionMemoryError):
    status_code = 409
    error_code = "thread_not_mutable"


class ThreadVersionConflictError(SessionMemoryError):
    status_code = 409
    error_code = "stale_thread_version"


class ThreadExecutionInProgressError(SessionMemoryError):
    status_code = 409
    error_code = "thread_execution_in_progress"


class SessionMemoryValidationError(SessionMemoryError):
    status_code = 400
    error_code = "invalid_session_memory_request"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_text(value: Any, *, field_name: str = "content", max_chars: int = MAX_CONTENT_CHARS) -> str:
    text = _CONTROL_CHARS.sub("", str(value or "")).strip()
    text = _CONTROL_MARKERS.sub("[stored-untrusted-control-text]", text)
    if not text:
        raise SessionMemoryValidationError(f"{field_name} is required.")
    if len(text) > max_chars:
        raise SessionMemoryValidationError(f"{field_name} is too large.")
    return text


def sanitize_structured_value(value: Any, *, field_name: str = "structured payload") -> Any:
    sanitized = _sanitize_value(value, depth=0)
    try:
        encoded = json.dumps(sanitized, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as error:
        raise SessionMemoryValidationError(f"{field_name} is not JSON serializable.") from error
    if len(encoded) > MAX_JSON_CHARS:
        raise SessionMemoryValidationError(f"{field_name} is too large.")
    return sanitized


def validate_thread_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SessionMemoryValidationError("state must be an object.")
    allowed = {
        "schema_version",
        "conclusions",
        "unresolved_questions",
        "recommendations",
        "corrections",
        "compact_summary",
        "rebuild_metadata",
        "rebuild_required",
    }
    unknown = set(value) - allowed
    if unknown:
        raise SessionMemoryValidationError(f"state contains unsupported fields: {', '.join(sorted(unknown))}.")
    sanitized = sanitize_structured_value(value, field_name="state")
    for field in ("conclusions", "unresolved_questions", "recommendations", "corrections"):
        items = sanitized.get(field, [])
        if not isinstance(items, list):
            raise SessionMemoryValidationError(f"state.{field} must be a list.")
        for item in items:
            if not isinstance(item, dict):
                raise SessionMemoryValidationError(f"state.{field} entries must be objects.")
            assertion = str(item.get("assertion_type") or "").strip()
            permitted = {
                "conclusions": {"analyst_statement", "model_inference", "correction"},
                "unresolved_questions": {"unresolved_question"},
                "recommendations": {"analyst_statement", "model_inference"},
                "corrections": {"correction"},
            }[field]
            if assertion not in permitted:
                raise SessionMemoryValidationError(f"state.{field} has invalid assertion_type.")
            if assertion == MODEL_PROVENANCE:
                if item.get("confidence") not in {"low", "medium", "high"}:
                    raise SessionMemoryValidationError(f"state.{field} model inference requires confidence.")
                if not item.get("provenance"):
                    raise SessionMemoryValidationError(f"state.{field} model inference requires provenance.")
    schema_version = sanitized.get("schema_version", 1)
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version <= 0:
        raise SessionMemoryValidationError("state.schema_version must be a positive integer.")
    rebuild_metadata = sanitized.get("rebuild_metadata", {})
    if not isinstance(rebuild_metadata, dict):
        raise SessionMemoryValidationError("state.rebuild_metadata must be an object.")
    compact_summary = sanitized.get("compact_summary")
    if compact_summary is not None:
        sanitized["compact_summary"] = sanitize_text(compact_summary, field_name="state.compact_summary", max_chars=4000)
    return sanitized


def create_thread(
    conn,
    *,
    owner_username: str,
    primary_entity_type: str,
    primary_entity_id: str,
    scope_key: str,
    investigation_id: int | None = None,
    is_default: bool = True,
    domain: str = "siem",
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    owner = _required_text(owner_username, "owner_username", 128)
    entity_type = _required_text(primary_entity_type, "primary_entity_type", 64).lower()
    entity_id = _required_text(primary_entity_id, "primary_entity_id", 256)
    scope = _required_text(scope_key, "scope_key", 384)
    if domain != "siem":
        raise SessionMemoryValidationError("Only the SIEM thread domain is supported.")
    current = _as_utc(now) or utc_now()
    expires_at = current + ACTIVE_RETENTION
    delete_after = current + CONTENT_RETENTION
    thread_id = f"ath_{uuid.uuid4().hex}"

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if is_default:
            cur.execute(
                """
                UPDATE anakin_threads
                SET status = 'expired', archived_at = %s, closed_at = %s, updated_at = %s, version = version + 1
                WHERE owner_username = %s AND domain = %s AND scope_key = %s
                  AND is_default = TRUE AND status = 'active' AND expires_at <= %s
                """,
                (current, current, current, owner, domain, scope, current),
            )
            cur.execute(
                """
                INSERT INTO anakin_threads (
                    thread_id, owner_username, domain, investigation_id,
                    primary_entity_type, primary_entity_id, scope_key, is_default,
                    created_at, updated_at, last_active_at, expires_at, delete_after
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s)
                ON CONFLICT (owner_username, domain, scope_key)
                    WHERE is_default = TRUE AND status = 'active'
                    DO NOTHING
                RETURNING *
                """,
                (
                    thread_id,
                    owner,
                    domain,
                    investigation_id,
                    entity_type,
                    entity_id,
                    scope,
                    current,
                    current,
                    current,
                    expires_at,
                    delete_after,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO anakin_threads (
                    thread_id, owner_username, domain, investigation_id,
                    primary_entity_type, primary_entity_id, scope_key, is_default,
                    created_at, updated_at, last_active_at, expires_at, delete_after
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    thread_id,
                    owner,
                    domain,
                    investigation_id,
                    entity_type,
                    entity_id,
                    scope,
                    current,
                    current,
                    current,
                    expires_at,
                    delete_after,
                ),
            )
        row = cur.fetchone()
        created = row is not None
        if not created:
            cur.execute(
                """
                SELECT * FROM anakin_threads
                WHERE owner_username = %s AND domain = %s AND scope_key = %s
                  AND is_default = TRUE AND status = 'active'
                """,
                (owner, domain, scope),
            )
            row = cur.fetchone()
        if row is None:
            raise SessionMemoryError("Unable to resolve thread identity.")
        if created:
            cur.execute(
                """
                INSERT INTO anakin_thread_state (thread_id, owner_username, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                """,
                (row["thread_id"], owner, current, current),
            )
    return serialize_thread(dict(row)), created


def get_thread(conn, *, thread_id: str, owner_username: str, require_active: bool = True, now: datetime | None = None) -> dict[str, Any]:
    owner = _required_text(owner_username, "owner_username", 128)
    identifier = _required_text(thread_id, "thread_id", 128)
    current = _as_utc(now) or utc_now()
    _expire_thread_if_due(conn, thread_id=identifier, owner_username=owner, now=current)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT t.*, s.schema_version AS state_schema_version, s.state_version,
                   s.conclusions, s.unresolved_questions, s.recommendations, s.corrections,
                   s.compact_summary AS state_compact_summary, s.rebuild_metadata, s.rebuild_required
            FROM anakin_threads t
            LEFT JOIN anakin_thread_state s
              ON s.thread_id = t.thread_id AND s.owner_username = t.owner_username
            WHERE t.thread_id = %s AND t.owner_username = %s
            """,
            (identifier, owner),
        )
        row = cur.fetchone()
    if row is None:
        raise ThreadNotFoundError("Thread not found.")
    if require_active and row["status"] == THREAD_EXPIRED:
        raise ThreadExpiredError("Thread context has expired.")
    if require_active and row["status"] != THREAD_ACTIVE:
        raise ThreadClosedError("Thread is not active.")
    return serialize_thread(dict(row), include_state=True)


def list_turns(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    after_sequence: int | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    get_thread(conn, thread_id=thread_id, owner_username=owner_username, require_active=True, now=now)
    if isinstance(after_sequence, bool) or (after_sequence is not None and (not isinstance(after_sequence, int) or after_sequence < 0)):
        raise SessionMemoryValidationError("cursor must be a non-negative integer.")
    bounded_limit = max(1, min(int(limit), 100))
    cursor = after_sequence or 0
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT * FROM anakin_turns
            WHERE thread_id = %s AND owner_username = %s AND sequence > %s
            ORDER BY sequence ASC
            LIMIT %s
            """,
            (thread_id, owner_username, cursor, bounded_limit + 1),
        )
        rows = [dict(row) for row in cur.fetchall()]
    has_more = len(rows) > bounded_limit
    page = rows[:bounded_limit]
    return {
        "turns": [serialize_turn(row) for row in page],
        "next_cursor": page[-1]["sequence"] if has_more and page else None,
        "has_more": has_more,
    }


def append_turn(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    expected_version: int,
    client_request_id: str,
    role: str,
    content: str,
    assertion_type: str,
    workflow: str | None = None,
    structured_payload: dict[str, Any] | None = None,
    parent_turn_id: int | None = None,
    entity_snapshot: dict[str, Any] | None = None,
    lifecycle_status: str = "recorded",
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    owner = _required_text(owner_username, "owner_username", 128)
    identifier = _required_text(thread_id, "thread_id", 128)
    request_id = _required_text(client_request_id, "client_request_id", 256)
    clean_content = sanitize_text(content)
    clean_payload = sanitize_structured_value(structured_payload or {}, field_name="structured_payload")
    clean_snapshot = sanitize_structured_value(entity_snapshot or {}, field_name="entity_snapshot")
    if not isinstance(clean_payload, dict) or not isinstance(clean_snapshot, dict):
        raise SessionMemoryValidationError("structured_payload and entity_snapshot must be objects.")
    if assertion_type not in ASSERTION_TYPES:
        raise SessionMemoryValidationError("assertion_type is unsupported.")
    if role not in {"user", "assistant", "system"}:
        raise SessionMemoryValidationError("role is unsupported.")
    if assertion_type in {"analyst_statement", "correction", "unresolved_question"} and role != "user":
        raise SessionMemoryValidationError(f"{assertion_type} requires user role.")
    if assertion_type == MODEL_PROVENANCE:
        if role != "assistant":
            raise SessionMemoryValidationError("model_inference requires assistant role.")
        if clean_payload.get("confidence") not in {"low", "medium", "high"} or not clean_payload.get("provenance"):
            raise SessionMemoryValidationError("model_inference requires confidence and provenance.")
    if assertion_type == "artifact_preview" and (role != "assistant" or workflow != "generate_artifact"):
        raise SessionMemoryValidationError("artifact_preview requires assistant role and generate_artifact workflow.")
    if assertion_type == "system_event" and role != "system":
        raise SessionMemoryValidationError("system_event requires system role.")
    if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version <= 0:
        raise SessionMemoryValidationError("expected_version must be a positive integer.")
    current = _as_utc(now) or utc_now()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM anakin_threads WHERE thread_id = %s AND owner_username = %s FOR UPDATE",
            (identifier, owner),
        )
        thread = cur.fetchone()
        if thread is None:
            raise ThreadNotFoundError("Thread not found.")
        thread = _expire_locked_thread(cur, dict(thread), current)
        if thread["status"] == THREAD_EXPIRED:
            raise ThreadExpiredError("Thread context has expired.")
        if thread["status"] != THREAD_ACTIVE:
            raise ThreadClosedError("Thread is not active.")
        cur.execute(
            """
            SELECT * FROM anakin_turns
            WHERE owner_username = %s AND thread_id = %s AND client_request_id = %s
            """,
            (owner, identifier, request_id),
        )
        existing = cur.fetchone()
        if existing is not None:
            return serialize_turn(dict(existing)), serialize_thread(thread), False
        if int(thread["version"]) != expected_version:
            raise ThreadVersionConflictError(
                f"Thread version conflict: expected {expected_version}, current {thread['version']}."
            )
        if lifecycle_status in {"queued", "running"}:
            cur.execute(
                """
                SELECT id FROM anakin_turns
                WHERE thread_id = %s AND owner_username = %s
                  AND lifecycle_status IN ('queued', 'running')
                LIMIT 1
                """,
                (identifier, owner),
            )
            if cur.fetchone() is not None:
                raise ThreadExecutionInProgressError("Thread already has an active execution.")
        if parent_turn_id is not None:
            cur.execute(
                "SELECT assertion_type FROM anakin_turns WHERE id = %s AND thread_id = %s AND owner_username = %s",
                (parent_turn_id, identifier, owner),
            )
            if cur.fetchone() is None:
                raise SessionMemoryValidationError("parent_turn_id does not identify an owned turn in this thread.")
        sequence = int(thread["next_sequence"])
        turn_id = f"atn_{uuid.uuid4().hex}"
        is_artifact = assertion_type == "artifact_preview"
        cur.execute(
            """
            INSERT INTO anakin_turns (
                turn_id, thread_id, owner_username, sequence, thread_version_after_append, role, workflow, content,
                structured_payload, assertion_type, client_request_id, parent_turn_id,
                entity_snapshot, lifecycle_status, preview_only, persisted, applied,
                approval_required, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, FALSE, %s, %s)
            RETURNING *
            """,
            (
                turn_id,
                identifier,
                owner,
                sequence,
                expected_version + 1,
                role,
                workflow,
                clean_content,
                Json(clean_payload),
                assertion_type,
                request_id,
                parent_turn_id,
                Json(clean_snapshot),
                lifecycle_status,
                is_artifact,
                is_artifact,
                current,
            ),
        )
        turn = dict(cur.fetchone())
        expires_at = current + ACTIVE_RETENTION
        delete_after = current + CONTENT_RETENTION
        cur.execute(
            """
            UPDATE anakin_threads
            SET next_sequence = %s, version = version + 1, updated_at = %s,
                last_active_at = %s, expires_at = %s, delete_after = %s
            WHERE thread_id = %s AND owner_username = %s
            RETURNING *
            """,
            (sequence + 1, current, current, expires_at, delete_after, identifier, owner),
        )
        updated_thread = dict(cur.fetchone())
        cur.execute(
            """
            INSERT INTO anakin_thread_entities (
                thread_id, owner_username, entity_type, entity_id, display_alias,
                ordinal, salience, first_referenced_sequence, last_referenced_sequence,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, 1, 1.0, %s, %s, %s, %s)
            ON CONFLICT (thread_id, entity_type, entity_id) DO UPDATE
            SET last_referenced_sequence = EXCLUDED.last_referenced_sequence,
                salience = GREATEST(anakin_thread_entities.salience, EXCLUDED.salience),
                updated_at = EXCLUDED.updated_at
            """,
            (
                identifier,
                owner,
                updated_thread["primary_entity_type"],
                updated_thread["primary_entity_id"],
                clean_snapshot.get("display_alias"),
                sequence,
                sequence,
                current,
                current,
            ),
        )
    return serialize_turn(turn), serialize_thread(updated_thread), True


def reset_thread(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    expected_version: int,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    owner = _required_text(owner_username, "owner_username", 128)
    identifier = _required_text(thread_id, "thread_id", 128)
    current = _as_utc(now) or utc_now()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM anakin_threads WHERE thread_id = %s AND owner_username = %s FOR UPDATE",
            (identifier, owner),
        )
        old = cur.fetchone()
        if old is None:
            raise ThreadNotFoundError("Thread not found.")
        old = dict(old)
        if old["status"] == THREAD_RESET and old.get("replaced_by_thread_id"):
            cur.execute(
                "SELECT * FROM anakin_threads WHERE thread_id = %s AND owner_username = %s",
                (old["replaced_by_thread_id"], owner),
            )
            replacement = cur.fetchone()
            if replacement is not None:
                return serialize_thread(old), serialize_thread(dict(replacement))
        old = _expire_locked_thread(cur, old, current)
        if old["status"] == THREAD_EXPIRED:
            raise ThreadExpiredError("Thread context has expired.")
        if old["status"] != THREAD_ACTIVE:
            raise ThreadClosedError("Thread is not active.")
        if int(old["version"]) != expected_version:
            raise ThreadVersionConflictError(
                f"Thread version conflict: expected {expected_version}, current {old['version']}."
            )
        replacement_id = f"ath_{uuid.uuid4().hex}"
        expires_at = current + ACTIVE_RETENTION
        delete_after = current + CONTENT_RETENTION
        cur.execute(
            """
            UPDATE anakin_threads
            SET status = 'reset', closed_at = %s, archived_at = %s, updated_at = %s, version = version + 1
            WHERE thread_id = %s AND owner_username = %s
            RETURNING *
            """,
            (current, current, current, identifier, owner),
        )
        closed = dict(cur.fetchone())
        cur.execute(
            """
            INSERT INTO anakin_threads (
                thread_id, owner_username, domain, investigation_id,
                primary_entity_type, primary_entity_id, scope_key, is_default,
                created_at, updated_at, last_active_at, expires_at, delete_after
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                replacement_id,
                owner,
                old["domain"],
                old.get("investigation_id"),
                old["primary_entity_type"],
                old["primary_entity_id"],
                old["scope_key"],
                old["is_default"],
                current,
                current,
                current,
                expires_at,
                delete_after,
            ),
        )
        replacement = dict(cur.fetchone())
        cur.execute(
            "INSERT INTO anakin_thread_state (thread_id, owner_username, created_at, updated_at) VALUES (%s, %s, %s, %s)",
            (replacement_id, owner, current, current),
        )
        cur.execute(
            "UPDATE anakin_threads SET replaced_by_thread_id = %s WHERE thread_id = %s AND owner_username = %s RETURNING *",
            (replacement_id, identifier, owner),
        )
        closed = dict(cur.fetchone())
    return serialize_thread(closed), serialize_thread(replacement)


def save_thread_state(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    expected_version: int,
    state: dict[str, Any],
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    clean = validate_thread_state(state)
    current = _as_utc(now) or utc_now()
    owner = _required_text(owner_username, "owner_username", 128)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        thread = _lock_mutable_thread(cur, thread_id=thread_id, owner_username=owner, now=current)
        if int(thread["version"]) != expected_version:
            raise ThreadVersionConflictError(
                f"Thread version conflict: expected {expected_version}, current {thread['version']}."
            )
        cur.execute(
            """
            UPDATE anakin_thread_state
            SET schema_version = %s, state_version = state_version + 1,
                conclusions = %s, unresolved_questions = %s, recommendations = %s,
                corrections = %s, compact_summary = %s, rebuild_metadata = %s,
                rebuild_required = %s, updated_at = %s
            WHERE thread_id = %s AND owner_username = %s
            RETURNING *
            """,
            (
                clean.get("schema_version", 1),
                Json(clean.get("conclusions", [])),
                Json(clean.get("unresolved_questions", [])),
                Json(clean.get("recommendations", [])),
                Json(clean.get("corrections", [])),
                clean.get("compact_summary"),
                Json(clean.get("rebuild_metadata", {})),
                bool(clean.get("rebuild_required", False)),
                current,
                thread_id,
                owner,
            ),
        )
        state_row = dict(cur.fetchone())
        cur.execute(
            "UPDATE anakin_threads SET version = version + 1, updated_at = %s WHERE thread_id = %s AND owner_username = %s RETURNING *",
            (current, thread_id, owner),
        )
        updated_thread = dict(cur.fetchone())
    return _serialize_state(state_row), serialize_thread(updated_thread)


def create_hypothesis(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    hypothesis: str,
    confidence: str,
    provenance_type: str,
    provenance_turn_id: int | None = None,
    supersedes_hypothesis_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if provenance_type not in {"analyst_statement", MODEL_PROVENANCE, "correction"}:
        raise SessionMemoryValidationError("hypothesis provenance is unsupported.")
    if confidence not in {"low", "medium", "high"}:
        raise SessionMemoryValidationError("hypothesis confidence is unsupported.")
    current = _as_utc(now) or utc_now()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _lock_mutable_thread(cur, thread_id=thread_id, owner_username=owner_username, now=current)
        if provenance_turn_id is None:
            raise SessionMemoryValidationError("hypothesis provenance_turn_id is required.")
        cur.execute(
            """
            SELECT assertion_type FROM anakin_turns
            WHERE id = %s AND thread_id = %s AND owner_username = %s
            """,
            (provenance_turn_id, thread_id, owner_username),
        )
        provenance_turn = cur.fetchone()
        if provenance_turn is None or provenance_turn["assertion_type"] != provenance_type:
            raise SessionMemoryValidationError("hypothesis provenance does not match its source turn.")
        if supersedes_hypothesis_id is not None:
            cur.execute(
                """
                SELECT * FROM anakin_thread_hypotheses
                WHERE id = %s AND thread_id = %s AND owner_username = %s FOR UPDATE
                """,
                (supersedes_hypothesis_id, thread_id, owner_username),
            )
            prior = cur.fetchone()
            if prior is None:
                raise SessionMemoryValidationError("superseded hypothesis was not found in this thread.")
            if provenance_type != "correction":
                raise SessionMemoryValidationError("only a correction may supersede a hypothesis.")
        hypothesis_id = f"ahp_{uuid.uuid4().hex}"
        cur.execute(
            """
            INSERT INTO anakin_thread_hypotheses (
                hypothesis_id, thread_id, owner_username, hypothesis, confidence,
                provenance_type, provenance_turn_id, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                hypothesis_id,
                thread_id,
                owner_username,
                sanitize_text(hypothesis, field_name="hypothesis", max_chars=4000),
                confidence,
                provenance_type,
                provenance_turn_id,
                current,
                current,
            ),
        )
        created = dict(cur.fetchone())
        if supersedes_hypothesis_id is not None:
            cur.execute(
                """
                UPDATE anakin_thread_hypotheses
                SET status = 'weakened', superseded_by_id = %s, updated_at = %s
                WHERE id = %s AND thread_id = %s AND owner_username = %s
                """,
                (created["id"], current, supersedes_hypothesis_id, thread_id, owner_username),
            )
    return _serialize_hypothesis(created)


def create_evidence(
    conn,
    *,
    thread_id: str,
    owner_username: str,
    source_type: str,
    source_ref: str,
    observed_at: datetime,
    snapshot: dict[str, Any] | list[Any] | None = None,
    snapshot_hash: str | None = None,
    query_parameters: dict[str, Any] | None = None,
    entity_fingerprint: str | None = None,
    fresh_until: datetime | None = None,
    relationship_type: str = "context",
    hypothesis_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if relationship_type not in {"supports", "refutes", "context"}:
        raise SessionMemoryValidationError("evidence relationship_type is unsupported.")
    clean_snapshot = sanitize_structured_value(snapshot, field_name="evidence snapshot") if snapshot is not None else None
    clean_query = sanitize_structured_value(query_parameters or {}, field_name="evidence query_parameters")
    if not isinstance(clean_query, dict):
        raise SessionMemoryValidationError("evidence query_parameters must be an object.")
    if clean_snapshot is not None and not isinstance(clean_snapshot, (dict, list)):
        raise SessionMemoryValidationError("evidence snapshot must be an object or list.")
    if clean_snapshot is None and not str(snapshot_hash or "").strip():
        raise SessionMemoryValidationError("evidence snapshot or snapshot_hash is required.")
    current = _as_utc(now) or utc_now()
    observed = _as_utc(observed_at)
    freshness = _as_utc(fresh_until)
    if observed is None:
        raise SessionMemoryValidationError("observed_at is required.")
    if freshness is not None and freshness < observed:
        raise SessionMemoryValidationError("fresh_until cannot precede observed_at.")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _lock_mutable_thread(cur, thread_id=thread_id, owner_username=owner_username, now=current)
        evidence_id = f"aev_{uuid.uuid4().hex}"
        effective_hash = str(snapshot_hash or "").strip() or hashlib.sha256(
            json.dumps(clean_snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        cur.execute(
            """
            INSERT INTO anakin_thread_evidence (
                evidence_id, thread_id, owner_username, hypothesis_id, source_type,
                source_ref, snapshot, snapshot_hash, query_parameters, entity_fingerprint,
                observed_at, fresh_until, relationship_type, provenance_type, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'verified_evidence', %s)
            RETURNING *
            """,
            (
                evidence_id,
                thread_id,
                owner_username,
                hypothesis_id,
                _required_text(source_type, "source_type", 128),
                sanitize_text(source_ref, field_name="source_ref", max_chars=512),
                Json(clean_snapshot) if clean_snapshot is not None else None,
                effective_hash,
                Json(clean_query),
                str(entity_fingerprint or "").strip() or None,
                observed,
                freshness,
                relationship_type,
                current,
            ),
        )
        row = dict(cur.fetchone())
    return _serialize_evidence(row)


def link_async_request(
    conn,
    *,
    request_id: str,
    thread_id: str,
    turn_id: int,
    owner_username: str,
) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT request_id, actor_username, workflow, thread_id, turn_id
            FROM ai_workflow_requests
            WHERE request_id = %s AND actor_username = %s
            FOR UPDATE
            """,
            (request_id, owner_username),
        )
        request_row = cur.fetchone()
        if request_row is None:
            raise ThreadNotFoundError("Async request not found.")
        cur.execute(
            """
            SELECT id, workflow, lifecycle_status FROM anakin_turns
            WHERE id = %s AND thread_id = %s AND owner_username = %s
            """,
            (turn_id, thread_id, owner_username),
        )
        turn_row = cur.fetchone()
        if turn_row is None:
            raise SessionMemoryValidationError("Async request linkage does not match an owned thread turn.")
        if turn_row["lifecycle_status"] not in {"queued", "running"}:
            raise SessionMemoryValidationError("Async request linkage requires a queued or running turn.")
        if turn_row["workflow"] != request_row["workflow"]:
            raise SessionMemoryValidationError("Async request workflow does not match the linked turn.")
        existing_pair = (request_row.get("thread_id"), request_row.get("turn_id"))
        if existing_pair != (None, None) and existing_pair != (thread_id, turn_id):
            raise SessionMemoryValidationError("Async request is already linked to another turn.")
        cur.execute(
            """
            SELECT request_id FROM ai_workflow_requests
            WHERE turn_id = %s AND request_id <> %s
            LIMIT 1
            """,
            (turn_id, request_id),
        )
        if cur.fetchone() is not None:
            raise SessionMemoryValidationError("Turn is already linked to another async request.")
        cur.execute(
            """
            UPDATE ai_workflow_requests SET thread_id = %s, turn_id = %s, updated_at = NOW()
            WHERE request_id = %s AND actor_username = %s
            RETURNING request_id, actor_username, thread_id, turn_id
            """,
            (thread_id, turn_id, request_id, owner_username),
        )
        return dict(cur.fetchone())


def complete_linked_turn(
    conn,
    *,
    thread_id: str,
    turn_id: int,
    owner_username: str,
    expected_thread_version: int,
    lifecycle_status: str = "completed",
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if lifecycle_status not in {"completed", "failed", "cancelled"}:
        raise SessionMemoryValidationError("terminal lifecycle_status is unsupported.")
    current = _as_utc(now) or utc_now()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        thread = _lock_mutable_thread(cur, thread_id=thread_id, owner_username=owner_username, now=current)
        cur.execute(
            """
            SELECT * FROM anakin_turns
            WHERE id = %s AND thread_id = %s AND owner_username = %s FOR UPDATE
            """,
            (turn_id, thread_id, owner_username),
        )
        turn = cur.fetchone()
        if turn is None:
            raise ThreadNotFoundError("Linked turn not found.")
        if int(turn["thread_version_after_append"]) != expected_thread_version:
            raise ThreadVersionConflictError("Turn completion version does not match its submission version.")
        if int(thread["version"]) != expected_thread_version:
            raise ThreadVersionConflictError(
                f"Thread version conflict: expected {expected_thread_version}, current {thread['version']}."
            )
        if turn["lifecycle_status"] not in {"queued", "running"}:
            raise ThreadClosedError("Turn is not awaiting completion.")
        cur.execute(
            """
            UPDATE anakin_turns
            SET lifecycle_status = %s, completed_at = %s
            WHERE id = %s AND thread_id = %s AND owner_username = %s
            RETURNING *
            """,
            (lifecycle_status, current, turn_id, thread_id, owner_username),
        )
        completed = dict(cur.fetchone())
        cur.execute(
            """
            UPDATE anakin_threads
            SET version = version + 1, updated_at = %s
            WHERE thread_id = %s AND owner_username = %s
            RETURNING *
            """,
            (current, thread_id, owner_username),
        )
        updated_thread = dict(cur.fetchone())
    return serialize_turn(completed), serialize_thread(updated_thread)


def purge_due_threads(conn, *, limit: int = 100, now: datetime | None = None) -> list[str]:
    current = _as_utc(now) or utc_now()
    bounded_limit = max(1, min(int(limit), 500))
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE anakin_threads
            SET status = 'expired', archived_at = %s, closed_at = %s, updated_at = %s, version = version + 1
            WHERE status = 'active' AND expires_at <= %s
            """,
            (current, current, current, current),
        )
        cur.execute(
            """
            SELECT thread_id, domain FROM anakin_threads
            WHERE status <> 'active' AND delete_after <= %s
            ORDER BY delete_after ASC
            FOR UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (current, bounded_limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
        if not rows:
            return []
        identifiers = [row["thread_id"] for row in rows]
        cur.execute(
            "UPDATE ai_workflow_requests SET thread_id = NULL, turn_id = NULL WHERE thread_id = ANY(%s)",
            (identifiers,),
        )
        for row in rows:
            cur.execute(
                """
                INSERT INTO anakin_thread_tombstones (thread_id, domain, deletion_reason, deleted_at)
                VALUES (%s, %s, 'retention_expired', %s)
                ON CONFLICT (thread_id) DO NOTHING
                """,
                (row["thread_id"], row["domain"], current),
            )
        cur.execute("DELETE FROM anakin_threads WHERE thread_id = ANY(%s)", (identifiers,))
    return identifiers


def serialize_thread(row: dict[str, Any], *, include_state: bool = False) -> dict[str, Any]:
    payload = {
        "thread_id": row.get("thread_id"),
        "domain": row.get("domain"),
        "investigation_id": row.get("investigation_id"),
        "primary_entity": {"type": row.get("primary_entity_type"), "id": row.get("primary_entity_id")},
        "is_default": bool(row.get("is_default")),
        "status": row.get("status"),
        "focus_state": _json_object(row.get("focus_state")),
        "summary": row.get("compact_summary"),
        "summary_version": int(row.get("summary_version") or 0),
        "next_sequence": int(row.get("next_sequence") or 1),
        "version": int(row.get("version") or 1),
        "replaced_by_thread_id": row.get("replaced_by_thread_id"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "last_active_at": _iso(row.get("last_active_at")),
        "expires_at": _iso(row.get("expires_at")),
        "archived_at": _iso(row.get("archived_at")),
        "delete_after": _iso(row.get("delete_after")),
        "closed_at": _iso(row.get("closed_at")),
        "private": True,
    }
    if include_state:
        payload["state"] = _safe_state_from_join(row)
    return payload


def serialize_turn(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "turn_id": row.get("turn_id"),
        "thread_id": row.get("thread_id"),
        "sequence": int(row.get("sequence") or 0),
        "thread_version_after_append": int(row.get("thread_version_after_append") or 0),
        "role": row.get("role"),
        "workflow": row.get("workflow"),
        "content": row.get("content"),
        "structured_payload": _json_object(row.get("structured_payload")),
        "assertion_type": row.get("assertion_type"),
        "client_request_id": row.get("client_request_id"),
        "parent_turn_id": row.get("parent_turn_id"),
        "entity_snapshot": _json_object(row.get("entity_snapshot")),
        "lifecycle_status": row.get("lifecycle_status"),
        "artifact_safety": {
            "preview_only": bool(row.get("preview_only")),
            "persisted": bool(row.get("persisted")),
            "applied": bool(row.get("applied")),
            "approval_required": bool(row.get("approval_required")),
        },
        "created_at": _iso(row.get("created_at")),
        "completed_at": _iso(row.get("completed_at")),
    }


def _lock_mutable_thread(cur, *, thread_id: str, owner_username: str, now: datetime) -> dict[str, Any]:
    cur.execute(
        "SELECT * FROM anakin_threads WHERE thread_id = %s AND owner_username = %s FOR UPDATE",
        (thread_id, owner_username),
    )
    row = cur.fetchone()
    if row is None:
        raise ThreadNotFoundError("Thread not found.")
    thread = _expire_locked_thread(cur, dict(row), now)
    if thread["status"] == THREAD_EXPIRED:
        raise ThreadExpiredError("Thread context has expired.")
    if thread["status"] != THREAD_ACTIVE:
        raise ThreadClosedError("Thread is not active.")
    return thread


def _expire_locked_thread(cur, thread: dict[str, Any], now: datetime) -> dict[str, Any]:
    if thread["status"] == THREAD_ACTIVE and _as_utc(thread.get("expires_at")) <= now:
        cur.execute(
            """
            UPDATE anakin_threads
            SET status = 'expired', archived_at = %s, closed_at = %s, updated_at = %s, version = version + 1
            WHERE thread_id = %s AND owner_username = %s
            RETURNING *
            """,
            (now, now, now, thread["thread_id"], thread["owner_username"]),
        )
        return dict(cur.fetchone())
    return thread


def _expire_thread_if_due(conn, *, thread_id: str, owner_username: str, now: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE anakin_threads
            SET status = 'expired', archived_at = %s, closed_at = %s, updated_at = %s, version = version + 1
            WHERE thread_id = %s AND owner_username = %s AND status = 'active' AND expires_at <= %s
            """,
            (now, now, now, thread_id, owner_username, now),
        )


def _safe_state_from_join(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("state_schema_version") is None:
        return _empty_rebuild_state("state record missing")
    candidate = {
        "schema_version": row.get("state_schema_version"),
        "conclusions": row.get("conclusions"),
        "unresolved_questions": row.get("unresolved_questions"),
        "recommendations": row.get("recommendations"),
        "corrections": row.get("corrections"),
        "compact_summary": row.get("state_compact_summary"),
        "rebuild_metadata": row.get("rebuild_metadata"),
        "rebuild_required": bool(row.get("rebuild_required")),
    }
    try:
        clean = validate_thread_state(candidate)
    except SessionMemoryValidationError:
        return _empty_rebuild_state("stored state failed validation")
    clean["state_version"] = int(row.get("state_version") or 1)
    return clean


def _empty_rebuild_state(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "state_version": 0,
        "conclusions": [],
        "unresolved_questions": [],
        "recommendations": [],
        "corrections": [],
        "compact_summary": None,
        "rebuild_metadata": {"reason": reason},
        "rebuild_required": True,
    }


def _serialize_state(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": row.get("schema_version"),
        "state_version": row.get("state_version"),
        "conclusions": row.get("conclusions") or [],
        "unresolved_questions": row.get("unresolved_questions") or [],
        "recommendations": row.get("recommendations") or [],
        "corrections": row.get("corrections") or [],
        "compact_summary": row.get("compact_summary"),
        "rebuild_metadata": row.get("rebuild_metadata") or {},
        "rebuild_required": bool(row.get("rebuild_required")),
    }


def _serialize_hypothesis(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "hypothesis_id": row.get("hypothesis_id"),
        "thread_id": row.get("thread_id"),
        "hypothesis": row.get("hypothesis"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "provenance_type": row.get("provenance_type"),
        "provenance_turn_id": row.get("provenance_turn_id"),
        "superseded_by_id": row.get("superseded_by_id"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _serialize_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "evidence_id": row.get("evidence_id"),
        "thread_id": row.get("thread_id"),
        "hypothesis_id": row.get("hypothesis_id"),
        "source_type": row.get("source_type"),
        "source_ref": row.get("source_ref"),
        "snapshot": row.get("snapshot"),
        "snapshot_hash": row.get("snapshot_hash"),
        "query_parameters": row.get("query_parameters") or {},
        "entity_fingerprint": row.get("entity_fingerprint"),
        "observed_at": _iso(row.get("observed_at")),
        "fresh_until": _iso(row.get("fresh_until")),
        "relationship_type": row.get("relationship_type"),
        "provenance_type": row.get("provenance_type"),
        "created_at": _iso(row.get("created_at")),
    }


def _sanitize_value(value: Any, *, depth: int) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise SessionMemoryValidationError("structured value is nested too deeply.")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = _CONTROL_CHARS.sub("", value)
        return _CONTROL_MARKERS.sub("[stored-untrusted-control-text]", text)[:4000]
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise SessionMemoryValidationError("structured object has too many fields.")
        result = {}
        for key, child in value.items():
            key_text = str(key)[:128]
            normalized = key_text.lower().replace("-", "_")
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = _sanitize_value(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise SessionMemoryValidationError("structured list has too many items.")
        return [_sanitize_value(item, depth=depth + 1) for item in value]
    return _CONTROL_MARKERS.sub("[stored-untrusted-control-text]", str(value))[:4000]


def _required_text(value: Any, field_name: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise SessionMemoryValidationError(f"{field_name} is required.")
    if len(text) > max_chars:
        raise SessionMemoryValidationError(f"{field_name} is too large.")
    return text


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else (str(value) if value is not None else None)


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
