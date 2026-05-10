from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from core.audit_helpers import log_audit_event


logger = logging.getLogger(__name__)

APPROVAL_STATUSES = frozenset({"pending", "approved", "denied", "expired"})
TERMINAL_APPROVAL_STATUSES = frozenset({"approved", "denied", "expired"})
DEFAULT_APPROVAL_TTL_MINUTES = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _request_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        incident_id,
        queue_id,
        playbook_execution_id,
        playbook_step_index,
        requested_by,
        approved_by,
        decided_by,
        status,
        action,
        risk_level,
        request_reason,
        decision_comment,
        created_at,
        decided_at,
        expires_at,
    ) = row
    return {
        "id": row_id,
        "incident_id": incident_id,
        "queue_id": queue_id,
        "playbook_execution_id": playbook_execution_id,
        "playbook_step_index": playbook_step_index,
        "requested_by": requested_by,
        "approved_by": approved_by,
        "decided_by": decided_by,
        "status": status,
        "action": action,
        "risk_level": risk_level,
        "request_reason": request_reason,
        "decision_comment": decision_comment,
        "created_at": _iso(created_at),
        "decided_at": _iso(decided_at),
        "expires_at": _iso(expires_at),
    }


def _event_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        approval_request_id,
        event_type,
        actor_user_id,
        previous_status,
        new_status,
        comment,
        created_at,
    ) = row
    return {
        "id": row_id,
        "approval_request_id": approval_request_id,
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "comment": comment,
        "created_at": _iso(created_at),
    }


REQUEST_COLUMNS = """
    id, incident_id, queue_id, playbook_execution_id, playbook_step_index,
    requested_by, approved_by, decided_by, status, action, risk_level,
    request_reason, decision_comment, created_at, decided_at, expires_at
"""

EVENT_COLUMNS = """
    id, approval_request_id, event_type, actor_user_id, previous_status,
    new_status, comment, created_at
"""


def _insert_event(
    cur,
    approval_request_id: int,
    event_type: str,
    *,
    actor_user_id: int | None = None,
    previous_status: str | None = None,
    new_status: str,
    comment: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO approval_request_events (
            approval_request_id, event_type, actor_user_id, previous_status,
            new_status, comment
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            approval_request_id,
            event_type,
            actor_user_id,
            previous_status,
            new_status,
            comment,
        ),
    )


def _write_audit_event(
    event_type: str,
    *,
    actor_user_id: int | None = None,
    approval_request: dict[str, Any],
    previous_status: str | None,
    new_status: str,
    decision_comment: str | None = None,
) -> None:
    try:
        log_audit_event(
            event_type,
            actor_username=str(actor_user_id) if actor_user_id is not None else None,
            details={
                "approval_request_id": approval_request["id"],
                "incident_id": approval_request["incident_id"],
                "queue_id": approval_request["queue_id"],
                "action": approval_request["action"],
                "previous_status": previous_status,
                "new_status": new_status,
                "decision_comment": decision_comment,
            },
        )
    except Exception:
        logger.exception("Failed to write approval audit event type=%s", event_type)


def _materialize_expiration(
    cur,
    row: tuple[Any, ...],
    *,
    now: datetime,
) -> dict[str, Any]:
    current = _request_row_to_dict(row)
    if current["status"] != "pending":
        raise ValueError("approval request is not pending")

    cur.execute(
        f"""
        UPDATE approval_requests
        SET status = 'expired',
            approved_by = NULL,
            decided_by = NULL,
            decided_at = %s
        WHERE id = %s
        RETURNING {REQUEST_COLUMNS}
        """,
        (now, current["id"]),
    )
    expired = _request_row_to_dict(cur.fetchone())
    _insert_event(
        cur,
        expired["id"],
        "expired",
        previous_status="pending",
        new_status="expired",
        comment="approval request expired",
    )
    _write_audit_event(
        "approval_request_expired",
        approval_request=expired,
        previous_status="pending",
        new_status="expired",
        decision_comment="approval request expired",
    )
    return expired


def create_approval_request(
    conn,
    *,
    incident_id: int | None = None,
    queue_id: int | None = None,
    playbook_execution_id: int | None = None,
    playbook_step_index: int | None = None,
    action: str,
    requested_by: int | None = None,
    request_reason: str | None = None,
    risk_level: str = "high",
    expires_at=None,
    ttl_minutes: int = DEFAULT_APPROVAL_TTL_MINUTES,
) -> dict[str, Any]:
    if incident_id is None and queue_id is None and playbook_execution_id is None:
        raise ValueError("approval request target required")
    if not action or not str(action).strip():
        raise ValueError("action is required")

    computed_expires_at = expires_at
    if computed_expires_at is None:
        computed_expires_at = _utc_now() + timedelta(minutes=ttl_minutes)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO approval_requests (
                incident_id, queue_id, playbook_execution_id, playbook_step_index,
                requested_by, status, action, risk_level, request_reason, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s)
            RETURNING {REQUEST_COLUMNS}
            """,
            (
                incident_id,
                queue_id,
                playbook_execution_id,
                playbook_step_index,
                requested_by,
                str(action).strip(),
                risk_level,
                request_reason,
                computed_expires_at,
            ),
        )
        approval_request = _request_row_to_dict(cur.fetchone())
        _insert_event(
            cur,
            approval_request["id"],
            "created",
            actor_user_id=requested_by,
            previous_status=None,
            new_status="pending",
            comment=request_reason,
        )
        _write_audit_event(
            "approval_request_created",
            actor_user_id=requested_by,
            approval_request=approval_request,
            previous_status=None,
            new_status="pending",
            decision_comment=request_reason,
        )
        return approval_request


def get_active_playbook_step_approval_request(
    conn,
    *,
    playbook_execution_id: int,
    playbook_step_index: int,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            WHERE playbook_execution_id = %s
              AND playbook_step_index = %s
              AND status IN ('pending', 'approved')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (playbook_execution_id, playbook_step_index),
        )
        row = cur.fetchone()
        return _request_row_to_dict(row) if row is not None else None


def create_playbook_step_approval_request(
    conn,
    *,
    playbook_execution_id: int,
    playbook_step_index: int,
    action: str = "playbook.require_approval",
    requested_by: int | None = None,
    request_reason: str | None = None,
    risk_level: str = "high",
    expires_at=None,
    ttl_minutes: int = DEFAULT_APPROVAL_TTL_MINUTES,
) -> dict[str, Any]:
    existing = get_active_playbook_step_approval_request(
        conn,
        playbook_execution_id=playbook_execution_id,
        playbook_step_index=playbook_step_index,
    )
    if existing is not None:
        return existing

    return create_approval_request(
        conn,
        playbook_execution_id=playbook_execution_id,
        playbook_step_index=playbook_step_index,
        action=action,
        requested_by=requested_by,
        request_reason=request_reason,
        risk_level=risk_level,
        expires_at=expires_at,
        ttl_minutes=ttl_minutes,
    )


def get_approval_request(conn, approval_request_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            WHERE id = %s
            """,
            (approval_request_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        approval_request = _request_row_to_dict(row)
        cur.execute(
            f"""
            SELECT {EVENT_COLUMNS}
            FROM approval_request_events
            WHERE approval_request_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (approval_request_id,),
        )
        approval_request["events"] = [_event_row_to_dict(event) for event in cur.fetchall()]
        return approval_request


def list_approval_events(conn, approval_request_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {EVENT_COLUMNS}
            FROM approval_request_events
            WHERE approval_request_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (approval_request_id,),
        )
        return [_event_row_to_dict(row) for row in cur.fetchall()]


def list_approval_requests(
    conn,
    *,
    status: str | None = None,
    incident_id: int | None = None,
    queue_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    cap = min(max(int(limit), 0), 100)
    offset = max(int(offset), 0)
    filters: list[str] = []
    params: list[Any] = []

    if status is not None:
        filters.append("status = %s")
        params.append(status)
    if incident_id is not None:
        filters.append("incident_id = %s")
        params.append(incident_id)
    if queue_id is not None:
        filters.append("queue_id = %s")
        params.append(queue_id)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([cap, offset])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        return [_request_row_to_dict(row) for row in cur.fetchall()]


def get_latest_approval_for_queue_action(
    conn,
    *,
    queue_id: int,
    action: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            WHERE queue_id = %s
              AND action = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (queue_id, action),
        )
        row = cur.fetchone()
        return _request_row_to_dict(row) if row is not None else None


def approve_request(
    conn,
    approval_request_id: int,
    *,
    actor_user_id: int,
    decision_comment: str | None = None,
    now=None,
) -> dict[str, Any]:
    decision_time = now or _utc_now()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            WHERE id = %s
            FOR UPDATE
            """,
            (approval_request_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("approval request not found")
        current = _request_row_to_dict(row)
        if current["status"] != "pending":
            raise ValueError("approval request is not pending")
        if row[15] <= decision_time:
            _materialize_expiration(cur, row, now=decision_time)
            raise ValueError("approval request expired")

        cur.execute(
            f"""
            UPDATE approval_requests
            SET status = 'approved',
                approved_by = %s,
                decided_by = %s,
                decided_at = %s,
                decision_comment = %s
            WHERE id = %s
            RETURNING {REQUEST_COLUMNS}
            """,
            (
                actor_user_id,
                actor_user_id,
                decision_time,
                decision_comment,
                approval_request_id,
            ),
        )
        updated = _request_row_to_dict(cur.fetchone())
        _insert_event(
            cur,
            approval_request_id,
            "approved",
            actor_user_id=actor_user_id,
            previous_status="pending",
            new_status="approved",
            comment=decision_comment,
        )
        _write_audit_event(
            "approval_request_approved",
            actor_user_id=actor_user_id,
            approval_request=updated,
            previous_status="pending",
            new_status="approved",
            decision_comment=decision_comment,
        )
        return updated


def deny_request(
    conn,
    approval_request_id: int,
    *,
    actor_user_id: int,
    decision_comment: str | None = None,
    now=None,
) -> dict[str, Any]:
    decision_time = now or _utc_now()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            WHERE id = %s
            FOR UPDATE
            """,
            (approval_request_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("approval request not found")
        current = _request_row_to_dict(row)
        if current["status"] != "pending":
            raise ValueError("approval request is not pending")
        if row[15] <= decision_time:
            _materialize_expiration(cur, row, now=decision_time)
            raise ValueError("approval request expired")

        cur.execute(
            f"""
            UPDATE approval_requests
            SET status = 'denied',
                approved_by = NULL,
                decided_by = %s,
                decided_at = %s,
                decision_comment = %s
            WHERE id = %s
            RETURNING {REQUEST_COLUMNS}
            """,
            (
                actor_user_id,
                decision_time,
                decision_comment,
                approval_request_id,
            ),
        )
        updated = _request_row_to_dict(cur.fetchone())
        _insert_event(
            cur,
            approval_request_id,
            "denied",
            actor_user_id=actor_user_id,
            previous_status="pending",
            new_status="denied",
            comment=decision_comment,
        )
        _write_audit_event(
            "approval_request_denied",
            actor_user_id=actor_user_id,
            approval_request=updated,
            previous_status="pending",
            new_status="denied",
            decision_comment=decision_comment,
        )
        return updated


def expire_pending_requests(conn, *, now=None, limit: int = 100) -> list[dict[str, Any]]:
    expiration_time = now or _utc_now()
    cap = min(max(int(limit), 0), 100)
    expired_requests: list[dict[str, Any]] = []

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {REQUEST_COLUMNS}
            FROM approval_requests
            WHERE status = 'pending'
              AND expires_at <= %s
            ORDER BY expires_at ASC, id ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (expiration_time, cap),
        )
        rows = cur.fetchall()

        for row in rows:
            expired = _materialize_expiration(cur, row, now=expiration_time)
            expired_requests.append(expired)

    return expired_requests
