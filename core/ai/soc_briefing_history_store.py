from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from core.notification_delivery_store import (
    redact_notification_delivery_metadata,
    sanitize_failure_message,
)
from core.notification_policy_store import load_notification_policy
from integrations.base_integration import REAL_MODE
from integrations.integration_registry import get_integration_adapter

BRIEFING_SECTION_KEYS = (
    "alerts_reviewed",
    "dismissed_low_priority_findings",
    "escalations",
    "critical_findings",
    "evidence",
    "recommendations",
)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
MAX_RUN_STEPS = 50
MAX_DELIVERY_ATTEMPTS = 25
MAX_SLACK_FINDINGS = 4
MAX_SLACK_RECOMMENDATIONS = 4
MAX_SLACK_CHARS = 1800
DEFAULT_MAX_DELIVERY_ATTEMPTS = 3
MAX_BACKOFF_SECONDS = 3600

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_SECRET_WORD_RE = re.compile(
    r"\b(token|secret|password|authorization|bearer|api[_-]?key|webhook)\b",
    re.IGNORECASE,
)
_VALID_STATUSES = frozenset({"pending", "success", "partial", "failed", "blocked", "skipped"})
_VALID_CONTENT_STATUSES = frozenset({"not_generated", "pending", "ready", "blocked", "failed", "skipped"})
_VALID_DELIVERY_STATUSES = frozenset(
    {"pending", "sent", "failed", "blocked", "skipped", "retry_scheduled", "duplicate_suppressed"}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sanitize_text(value: Any, *, max_chars: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = _URL_RE.sub("[REDACTED_URL]", text)
    text = _SECRET_WORD_RE.sub("[REDACTED]", text)
    return text[:max_chars]


def _sanitize_idempotency_key(value: str) -> str:
    return str(value or "").strip()[:200]


def _row_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _delivery_summary_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "latest_status": row.get("latest_delivery_status"),
        "latest_attempted_at": _iso(row.get("latest_delivery_attempted_at")),
        "latest_sent_at": _iso(row.get("latest_delivery_sent_at")),
        "attempt_count": int(row.get("delivery_attempt_count") or 0),
        "last_failure_code": row.get("latest_delivery_failure_code"),
        "next_retry_at": _iso(row.get("latest_delivery_next_retry_at")),
    }


def _briefing_list_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "briefing_type": row["briefing_type"],
        "status": row["status"],
        "lifecycle_status": row["lifecycle_status"],
        "content_status": row["content_status"],
        "generated_at": _iso(row["generated_at"]),
        "summary": _sanitize_text(row.get("summary"), max_chars=600),
        "error_code": row.get("error_code"),
        "error_message": _sanitize_text(row.get("error_message"), max_chars=400),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "schedule": {
            "id": row["schedule_id"],
            "name": row.get("schedule_name"),
            "timezone": row.get("schedule_timezone"),
        },
        "window": {
            "id": row["window_id"],
            "window_start": _iso(row.get("window_start")),
            "window_end": _iso(row.get("window_end")),
            "status": row.get("window_status"),
            "coalesced": bool(row.get("window_coalesced")),
        },
        "run": {
            "id": row["run_id"],
            "status": row.get("run_status"),
            "ai_gateway_status": row.get("ai_gateway_status"),
            "provider_status": row.get("provider_status"),
        },
        "delivery": _delivery_summary_from_row(row),
    }


def _parse_dt(value: str | None, field: str) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc


def list_briefings(
    conn,
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    status: str | None = None,
    content_status: str | None = None,
    schedule_id: int | None = None,
    delivery_status: str | None = None,
    provider_status: str | None = None,
    generated_from: str | None = None,
    generated_to: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if status and status not in _VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
    if content_status and content_status not in _VALID_CONTENT_STATUSES:
        raise ValueError(f"content_status must be one of {sorted(_VALID_CONTENT_STATUSES)}")
    if delivery_status and delivery_status not in _VALID_DELIVERY_STATUSES:
        raise ValueError(f"delivery_status must be one of {sorted(_VALID_DELIVERY_STATUSES)}")

    clauses = ["TRUE"]
    params: list[Any] = []
    if status:
        clauses.append("b.status = %s")
        params.append(status)
    if content_status:
        clauses.append("b.content_status = %s")
        params.append(content_status)
    if schedule_id is not None:
        clauses.append("b.schedule_id = %s")
        params.append(schedule_id)
    if delivery_status:
        clauses.append("COALESCE(latest_delivery.status, 'none') = %s")
        params.append(delivery_status)
    if provider_status:
        clauses.append("r.provider_status = %s")
        params.append(provider_status)
    start_dt = _parse_dt(generated_from, "generated_from")
    end_dt = _parse_dt(generated_to, "generated_to")
    if start_dt is not None:
        clauses.append("COALESCE(b.generated_at, b.created_at) >= %s")
        params.append(start_dt)
    if end_dt is not None:
        clauses.append("COALESCE(b.generated_at, b.created_at) <= %s")
        params.append(end_dt)
    normalized_search = str(search or "").strip()
    if normalized_search:
        clauses.append("(b.summary ILIKE %s OR s.name ILIKE %s OR b.error_code ILIKE %s)")
        pattern = f"%{normalized_search[:100]}%"
        params.extend([pattern, pattern, pattern])

    where_sql = " AND ".join(clauses)
    capped_limit = min(limit, MAX_LIMIT)
    query_params = [*params, capped_limit, offset]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            WITH delivery_counts AS (
                SELECT briefing_id, COUNT(*)::int AS attempt_count
                FROM soc_briefing_delivery_attempts
                GROUP BY briefing_id
            ),
            latest_delivery AS (
                SELECT DISTINCT ON (briefing_id)
                    briefing_id,
                    status,
                    last_attempted_at,
                    sent_at,
                    failure_code,
                    next_retry_at
                FROM soc_briefing_delivery_attempts
                ORDER BY briefing_id, created_at DESC, id DESC
            ),
            filtered AS (
                SELECT
                    b.id,
                    b.run_id,
                    b.schedule_id,
                    b.window_id,
                    b.status,
                    b.lifecycle_status,
                    b.briefing_type,
                    b.generated_at,
                    b.content_status,
                    b.summary,
                    b.error_code,
                    b.error_message,
                    b.created_at,
                    b.updated_at,
                    s.name AS schedule_name,
                    s.timezone AS schedule_timezone,
                    w.window_start,
                    w.window_end,
                    w.status AS window_status,
                    w.coalesced AS window_coalesced,
                    r.status AS run_status,
                    r.ai_gateway_status,
                    r.provider_status,
                    latest_delivery.status AS latest_delivery_status,
                    latest_delivery.last_attempted_at AS latest_delivery_attempted_at,
                    latest_delivery.sent_at AS latest_delivery_sent_at,
                    latest_delivery.failure_code AS latest_delivery_failure_code,
                    latest_delivery.next_retry_at AS latest_delivery_next_retry_at,
                    COALESCE(delivery_counts.attempt_count, 0) AS delivery_attempt_count,
                    COUNT(*) OVER()::int AS total_count
                FROM soc_briefings b
                JOIN soc_briefing_schedules s ON s.id = b.schedule_id
                JOIN soc_briefing_schedule_windows w ON w.id = b.window_id
                JOIN soc_briefing_runs r ON r.id = b.run_id
                LEFT JOIN delivery_counts ON delivery_counts.briefing_id = b.id
                LEFT JOIN latest_delivery ON latest_delivery.briefing_id = b.id
                WHERE {where_sql}
            )
            SELECT *
            FROM filtered
            ORDER BY COALESCE(generated_at, created_at) DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            query_params,
        )
        rows = [dict(row) for row in cur.fetchall()]
    total = rows[0]["total_count"] if rows else 0
    return {
        "items": [_briefing_list_item(row) for row in rows],
        "limit": capped_limit,
        "offset": offset,
        "total": total,
        "retention": {
            "briefing_days": 180,
            "delivery_days": 180,
            "automatic_cleanup": False,
        },
    }


def _delivery_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "briefing_id": row["briefing_id"],
        "channel": row["channel"],
        "status": row["status"],
        "attempt_count": row["attempt_count"],
        "max_attempts": row["max_attempts"],
        "next_retry_at": _iso(row["next_retry_at"]),
        "last_attempted_at": _iso(row["last_attempted_at"]),
        "sent_at": _iso(row["sent_at"]),
        "provider": row["provider"],
        "provider_mode": row["provider_mode"],
        "failure_code": row["failure_code"],
        "failure_message": _sanitize_text(row["failure_message"], max_chars=400),
        "metadata": _json_object(row["delivery_metadata"]),
        "created_by": row["created_by"],
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def get_briefing_detail(conn, briefing_id: int) -> dict[str, Any] | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                b.*,
                s.name AS schedule_name,
                s.timezone AS schedule_timezone,
                s.cadence_minutes,
                w.window_start,
                w.window_end,
                w.status AS window_status,
                w.skip_reason AS window_skip_reason,
                w.coalesced AS window_coalesced,
                r.status AS run_status,
                r.service_actor,
                r.started_at AS run_started_at,
                r.completed_at AS run_completed_at,
                r.runtime_ms,
                r.ai_gateway_status,
                r.provider_status,
                r.error_code AS run_error_code,
                r.error_message AS run_error_message,
                r.metadata AS run_metadata
            FROM soc_briefings b
            JOIN soc_briefing_schedules s ON s.id = b.schedule_id
            JOIN soc_briefing_schedule_windows w ON w.id = b.window_id
            JOIN soc_briefing_runs r ON r.id = b.run_id
            WHERE b.id = %s
            """,
            (briefing_id,),
        )
        briefing = _row_dict(cur.fetchone())
        if briefing is None:
            return None

        cur.execute(
            """
            SELECT
                id,
                step_index,
                step_type,
                status,
                tool_name,
                evidence_refs,
                decision_summary,
                latency_ms,
                error_code,
                error_message,
                read_only,
                created_at,
                updated_at
            FROM soc_briefing_run_steps
            WHERE run_id = %s
            ORDER BY step_index ASC
            LIMIT %s
            """,
            (briefing["run_id"], MAX_RUN_STEPS),
        )
        steps = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT *
            FROM soc_briefing_delivery_attempts
            WHERE briefing_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (briefing_id, MAX_DELIVERY_ATTEMPTS),
        )
        deliveries = [dict(row) for row in cur.fetchall()]

    sections = _json_object(briefing["sections"])
    normalized_sections = {key: _json_array(sections.get(key)) for key in BRIEFING_SECTION_KEYS}
    return {
        "id": briefing["id"],
        "briefing_type": briefing["briefing_type"],
        "status": briefing["status"],
        "lifecycle_status": briefing["lifecycle_status"],
        "content_status": briefing["content_status"],
        "generated_at": _iso(briefing["generated_at"]),
        "summary": _sanitize_text(briefing["summary"], max_chars=1200),
        "sections": normalized_sections,
        "evidence_refs": _json_array(briefing["evidence_refs"])[:100],
        "error_code": briefing["error_code"],
        "error_message": _sanitize_text(briefing["error_message"], max_chars=500),
        "created_at": _iso(briefing["created_at"]),
        "updated_at": _iso(briefing["updated_at"]),
        "schedule": {
            "id": briefing["schedule_id"],
            "name": briefing["schedule_name"],
            "timezone": briefing["schedule_timezone"],
            "cadence_minutes": briefing["cadence_minutes"],
        },
        "window": {
            "id": briefing["window_id"],
            "window_start": _iso(briefing["window_start"]),
            "window_end": _iso(briefing["window_end"]),
            "status": briefing["window_status"],
            "skip_reason": briefing["window_skip_reason"],
            "coalesced": bool(briefing["window_coalesced"]),
        },
        "run": {
            "id": briefing["run_id"],
            "status": briefing["run_status"],
            "service_actor": briefing["service_actor"],
            "started_at": _iso(briefing["run_started_at"]),
            "completed_at": _iso(briefing["run_completed_at"]),
            "runtime_ms": briefing["runtime_ms"],
            "ai_gateway_status": briefing["ai_gateway_status"],
            "provider_status": briefing["provider_status"],
            "error_code": briefing["run_error_code"],
            "error_message": _sanitize_text(briefing["run_error_message"], max_chars=500),
            "metadata": _json_object(briefing["run_metadata"]),
        },
        "run_steps": [
            {
                "id": step["id"],
                "step_index": step["step_index"],
                "step_type": step["step_type"],
                "status": step["status"],
                "tool_name": step["tool_name"],
                "evidence_refs": _json_array(step["evidence_refs"])[:50],
                "decision_summary": _sanitize_text(step["decision_summary"], max_chars=800),
                "latency_ms": step["latency_ms"],
                "error_code": step["error_code"],
                "error_message": _sanitize_text(step["error_message"], max_chars=500),
                "read_only": bool(step["read_only"]),
                "created_at": _iso(step["created_at"]),
                "updated_at": _iso(step["updated_at"]),
            }
            for step in steps
        ],
        "deliveries": [_delivery_row_to_dict(row) for row in deliveries],
        "retention": {
            "briefing_days": 180,
            "delivery_days": 180,
            "automatic_cleanup": False,
        },
    }


def _summary_fingerprint(briefing: dict[str, Any]) -> str:
    payload = {
        "briefing_id": briefing["id"],
        "generated_at": briefing.get("generated_at"),
        "summary": briefing.get("summary"),
        "sections": briefing.get("sections"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def delivery_idempotency_key(briefing: dict[str, Any], *, channel: str = "slack") -> str:
    return f"soc-briefing:{briefing['id']}:{channel}:{_summary_fingerprint(briefing)}"


def build_slack_summary(briefing: dict[str, Any], *, siem_url: str | None = None) -> dict[str, str]:
    sections = _json_object(briefing.get("sections"))
    critical = [_sanitize_text(item, max_chars=180) for item in _json_array(sections.get("critical_findings"))]
    escalations = [_sanitize_text(item, max_chars=180) for item in _json_array(sections.get("escalations"))]
    recommendations = [_sanitize_text(item, max_chars=180) for item in _json_array(sections.get("recommendations"))]
    findings = [item for item in [*critical, *escalations] if item][:MAX_SLACK_FINDINGS]
    recs = [item for item in recommendations if item][:MAX_SLACK_RECOMMENDATIONS]
    window_start = briefing.get("window_start") or briefing.get("window", {}).get("window_start")
    window_end = briefing.get("window_end") or briefing.get("window", {}).get("window_end")
    lines = [
        "Scheduled SOC briefing",
        f"Briefing: #{briefing['id']} status={briefing.get('status')} content={briefing.get('content_status')}",
        f"Window: {_iso(window_start) or 'unknown'} to {_iso(window_end) or 'unknown'}",
    ]
    summary = _sanitize_text(briefing.get("summary"), max_chars=350)
    if summary:
        lines.append(f"Summary: {summary}")
    if findings:
        lines.append("Findings:")
        lines.extend(f"- {item}" for item in findings)
    if recs:
        lines.append("Recommendations:")
        lines.extend(f"- {item}" for item in recs)
    if siem_url:
        safe_url = _URL_RE.sub("[REDACTED_URL]", str(siem_url).strip())
        lines.append(f"Open SIEM briefing: {safe_url}")
    else:
        lines.append("Open the SIEM SOC Briefings workspace for full details.")
    text = "\n".join(lines)[:MAX_SLACK_CHARS]
    return {
        "text": text,
        "message": summary or "Scheduled SOC briefing is available in the SIEM.",
    }


def _audit_delivery(
    conn,
    *,
    event_type: str,
    briefing_id: int,
    channel: str,
    status: str,
    idempotency_key: str,
    actor_username: str | None,
    actor_role: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    safe_details = redact_notification_delivery_metadata(
        {
            "briefing_id": briefing_id,
            "channel": channel,
            "status": status,
            "idempotency_key": _sanitize_idempotency_key(idempotency_key),
            **(details or {}),
        }
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (
                event_type,
                actor_username,
                actor_role,
                details
            )
            VALUES (%s, %s, %s, %s)
            """,
            (event_type, actor_username, actor_role, Json(safe_details)),
        )


def _insert_delivery(
    conn,
    *,
    briefing: dict[str, Any],
    idempotency_key: str,
    status: str,
    attempt_count: int,
    max_attempts: int,
    provider_mode: str,
    summary_fingerprint: str,
    failure_code: str | None = None,
    failure_message: str | None = None,
    next_retry_at: datetime | None = None,
    last_attempted_at: datetime | None = None,
    sent_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO soc_briefing_delivery_attempts (
                briefing_id,
                run_id,
                schedule_id,
                window_id,
                idempotency_key,
                channel,
                status,
                attempt_count,
                max_attempts,
                next_retry_at,
                last_attempted_at,
                sent_at,
                provider,
                provider_mode,
                summary_fingerprint,
                failure_code,
                failure_message,
                delivery_metadata,
                created_by
            )
            VALUES (
                %s, %s, %s, %s, %s, 'slack', %s, %s, %s, %s, %s, %s,
                'slack', %s, %s, %s, %s, %s, %s
            )
            RETURNING *
            """,
            (
                briefing["id"],
                briefing["run_id"],
                briefing["schedule_id"],
                briefing["window_id"],
                idempotency_key,
                status,
                attempt_count,
                max_attempts,
                next_retry_at,
                last_attempted_at,
                sent_at,
                provider_mode,
                summary_fingerprint,
                failure_code,
                sanitize_failure_message(failure_message),
                Json(redact_notification_delivery_metadata(metadata)),
                created_by,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("INSERT soc_briefing_delivery_attempts returned no row")
    return _delivery_row_to_dict(dict(row))


def _update_delivery(
    conn,
    *,
    delivery_id: int,
    status: str,
    attempt_count: int,
    max_attempts: int,
    provider_mode: str,
    failure_code: str | None = None,
    failure_message: str | None = None,
    next_retry_at: datetime | None = None,
    last_attempted_at: datetime | None = None,
    sent_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    updated_by: str | None = None,
) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE soc_briefing_delivery_attempts
            SET status = %s,
                attempt_count = %s,
                max_attempts = %s,
                next_retry_at = %s,
                last_attempted_at = %s,
                sent_at = %s,
                provider_mode = %s,
                failure_code = %s,
                failure_message = %s,
                delivery_metadata = %s,
                created_by = COALESCE(created_by, %s),
                updated_at = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (
                status,
                attempt_count,
                max_attempts,
                next_retry_at,
                last_attempted_at,
                sent_at,
                provider_mode,
                failure_code,
                sanitize_failure_message(failure_message),
                Json(redact_notification_delivery_metadata(metadata)),
                updated_by,
                delivery_id,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("UPDATE soc_briefing_delivery_attempts returned no row")
    return _delivery_row_to_dict(dict(row))


def get_delivery_by_idempotency_key(conn, idempotency_key: str) -> dict[str, Any] | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM soc_briefing_delivery_attempts WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        row = cur.fetchone()
    return _delivery_row_to_dict(dict(row)) if row else None


def _briefing_for_delivery(conn, briefing_id: int) -> dict[str, Any] | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                b.*,
                w.window_start,
                w.window_end
            FROM soc_briefings b
            JOIN soc_briefing_schedule_windows w ON w.id = b.window_id
            WHERE b.id = %s
            """,
            (briefing_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _next_retry(now: datetime, attempt_count: int) -> datetime:
    delay = min(60 * (2 ** max(0, attempt_count - 1)), MAX_BACKOFF_SECONDS)
    return now + timedelta(seconds=delay)


def deliver_briefing_to_slack(
    conn,
    briefing_id: int,
    *,
    actor_username: str | None,
    actor_role: str | None,
    siem_url: str | None = None,
    max_attempts: int = DEFAULT_MAX_DELIVERY_ATTEMPTS,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _utc_now()
    briefing = _briefing_for_delivery(conn, briefing_id)
    if briefing is None:
        raise LookupError("briefing not found")
    fingerprint = _summary_fingerprint(briefing)
    idem = delivery_idempotency_key(briefing)
    existing = get_delivery_by_idempotency_key(conn, idem)
    if existing and existing["status"] in {"sent", "pending"}:
        _audit_delivery(
            conn,
            event_type="soc_briefing_slack_duplicate_suppressed",
            briefing_id=briefing_id,
            channel="slack",
            status="duplicate_suppressed",
            idempotency_key=idem,
            actor_username=actor_username,
            actor_role=actor_role,
            details={"existing_status": existing["status"]},
        )
        return {"status": "duplicate_suppressed", "attempt": existing, "duplicate": True}

    with conn.cursor() as cur:
        policy = load_notification_policy(cur)
    if policy.get("status") == "unavailable":
        if existing:
            attempt = _update_delivery(
                conn,
                delivery_id=int(existing["id"]),
                status="blocked",
                attempt_count=int(existing["attempt_count"] or 0),
                max_attempts=max_attempts,
                provider_mode="simulation",
                failure_code="notification_policy_unavailable",
                failure_message="Notification policy unavailable; Slack briefing summary was not sent.",
                metadata={"policy_status": "unavailable"},
                updated_by=actor_username,
            )
        else:
            attempt = _insert_delivery(
                conn,
                briefing=briefing,
                idempotency_key=idem,
                status="blocked",
                attempt_count=0,
                max_attempts=max_attempts,
                provider_mode="simulation",
                summary_fingerprint=fingerprint,
                failure_code="notification_policy_unavailable",
                failure_message="Notification policy unavailable; Slack briefing summary was not sent.",
                metadata={"policy_status": "unavailable"},
                created_by=actor_username,
            )
        _audit_delivery(
            conn,
            event_type="soc_briefing_slack_blocked",
            briefing_id=briefing_id,
            channel="slack",
            status="blocked",
            idempotency_key=idem,
            actor_username=actor_username,
            actor_role=actor_role,
            details={"reason": "notification_policy_unavailable"},
        )
        return {"status": "blocked", "attempt": attempt, "duplicate": False}
    if policy.get("slack_enabled") is not True:
        if existing:
            attempt = _update_delivery(
                conn,
                delivery_id=int(existing["id"]),
                status="skipped",
                attempt_count=int(existing["attempt_count"] or 0),
                max_attempts=max_attempts,
                provider_mode="simulation",
                failure_code="slack_disabled",
                failure_message="Slack briefing summaries are disabled by notification policy.",
                metadata={"policy_status": policy.get("status"), "slack_enabled": False},
                updated_by=actor_username,
            )
        else:
            attempt = _insert_delivery(
                conn,
                briefing=briefing,
                idempotency_key=idem,
                status="skipped",
                attempt_count=0,
                max_attempts=max_attempts,
                provider_mode="simulation",
                summary_fingerprint=fingerprint,
                failure_code="slack_disabled",
                failure_message="Slack briefing summaries are disabled by notification policy.",
                metadata={"policy_status": policy.get("status"), "slack_enabled": False},
                created_by=actor_username,
            )
        _audit_delivery(
            conn,
            event_type="soc_briefing_slack_skipped",
            briefing_id=briefing_id,
            channel="slack",
            status="skipped",
            idempotency_key=idem,
            actor_username=actor_username,
            actor_role=actor_role,
            details={"reason": "slack_disabled"},
        )
        return {"status": "skipped", "attempt": attempt, "duplicate": False}

    summary = build_slack_summary(briefing, siem_url=siem_url)
    try:
        adapter = get_integration_adapter("slack", mode=REAL_MODE)
        result = adapter.execute(
            "send_message",
            params={
                "text": summary["text"],
                "message": summary["message"],
                "destination_label": "SOC briefing summary",
            },
            context={
                "notification_policy": True,
                "route_key": "critical_cross_source",
                "purpose": "scheduled_soc_briefing",
                "briefing_id": briefing_id,
                "schedule_id": briefing["schedule_id"],
                "window_id": briefing["window_id"],
            },
        )
    except Exception as exc:
        result = {
            "success": False,
            "mode": "simulation",
            "message": str(exc),
            "metadata": {"failure_classification": "adapter_exception"},
        }

    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    provider_mode = str(result.get("mode") or "simulation")
    provider_mode = provider_mode if provider_mode in {"simulation", "real"} else "simulation"
    success = result.get("success") is True
    attempt_count = int(existing["attempt_count"] or 0) + 1 if existing else 1
    failure_code = None if success else str(metadata.get("failure_classification") or "delivery_failed")
    terminal_failed = not success and attempt_count >= max_attempts
    status = "sent" if success else ("failed" if terminal_failed else "retry_scheduled")
    delivery_metadata = {
        "adapter_mode": provider_mode,
        "executed": result.get("executed"),
        "simulated": result.get("simulated"),
        "provider_success": metadata.get("provider_success"),
        "failure_classification": metadata.get("failure_classification"),
        "rate_limited": metadata.get("rate_limited"),
        "summary_chars": len(summary["text"]),
    }
    if existing:
        attempt = _update_delivery(
            conn,
            delivery_id=int(existing["id"]),
            status=status,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            provider_mode=provider_mode,
            next_retry_at=None if success or terminal_failed else _next_retry(current, attempt_count),
            last_attempted_at=current,
            sent_at=current if success else None,
            failure_code=failure_code,
            failure_message=None if success else result.get("message"),
            metadata=delivery_metadata,
            updated_by=actor_username,
        )
    else:
        attempt = _insert_delivery(
            conn,
            briefing=briefing,
            idempotency_key=idem,
            status=status,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            provider_mode=provider_mode,
            summary_fingerprint=fingerprint,
            next_retry_at=None if success or terminal_failed else _next_retry(current, attempt_count),
            last_attempted_at=current,
            sent_at=current if success else None,
            failure_code=failure_code,
            failure_message=None if success else result.get("message"),
            metadata=delivery_metadata,
            created_by=actor_username,
        )
    event_type = "soc_briefing_slack_sent" if success else (
        "soc_briefing_slack_failed" if terminal_failed else "soc_briefing_slack_retry_scheduled"
    )
    _audit_delivery(
        conn,
        event_type=event_type,
        briefing_id=briefing_id,
        channel="slack",
        status=status,
        idempotency_key=idem,
        actor_username=actor_username,
        actor_role=actor_role,
        details={
            "attempt_count": attempt_count,
            "failure_code": failure_code,
            "provider_mode": provider_mode,
            "next_retry_at": _iso(attempt["next_retry_at"]),
        },
    )
    return {"status": status, "attempt": attempt, "duplicate": False}
