from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_TO_PRIORITY = {"CRITICAL": "P1", "HIGH": "P2"}

ALL_INCIDENT_STATUSES = frozenset({"open", "investigating", "resolved", "closed"})

ALLOWED_STATUS_TRANSITIONS = {
    "open": frozenset({"investigating", "resolved", "closed"}),
    "investigating": frozenset({"resolved", "closed"}),
    "resolved": frozenset({"closed", "open"}),
    "closed": frozenset(),
}


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _incident_row_to_dict(record: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        title,
        severity,
        priority,
        status,
        source_ip,
        assigned_to,
        created_at,
        resolved_at,
    ) = record
    return {
        "id": row_id,
        "title": title,
        "severity": severity,
        "priority": priority,
        "status": status,
        "source_ip": source_ip,
        "assigned_to": assigned_to,
        "created_at": _iso(created_at),
        "resolved_at": _iso(resolved_at),
    }


def create_incident(conn, title: str, severity: str, source_ip: str) -> dict[str, Any]:
    sev_upper = severity.upper()
    priority = SEVERITY_TO_PRIORITY.get(sev_upper, "P2")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES (%s, %s, %s, 'open', %s::inet)
            RETURNING id, title, severity, priority, status, host(source_ip),
                      assigned_to, created_at, resolved_at
            """,
            (title, severity, priority, source_ip),
        )
        return _incident_row_to_dict(cur.fetchone())


def link_alert_to_incident(conn, incident_id: int, alert_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incident_alerts (incident_id, alert_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            RETURNING incident_id
            """,
            (incident_id, alert_id),
        )
        if cur.fetchone() is not None:
            logger.info(
                "[INCIDENT LINK] incident_id=%s alert_id=%s",
                incident_id,
                alert_id,
            )
        else:
            logger.info(
                "[INCIDENT LINK] already linked incident_id=%s alert_id=%s",
                incident_id,
                alert_id,
            )


def find_open_incident_by_source_ip(
    conn, source_ip: str, dedup_window_minutes: int = 60
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            WHERE source_ip = %s::inet
              AND status IN ('open', 'investigating')
              AND created_at >= NOW() - (%s * INTERVAL '1 minute')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (source_ip, dedup_window_minutes),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _incident_row_to_dict(row)


def maybe_create_or_link_incident(
    conn, alert_id: int, severity: str, source_ip: str
) -> dict[str, Any] | None:
    sev_upper = (severity or "").upper()
    if sev_upper not in {"HIGH", "CRITICAL"}:
        return None

    existing = find_open_incident_by_source_ip(conn, source_ip)
    if existing is not None:
        iid = existing["id"]
        link_alert_to_incident(conn, iid, alert_id)
        logger.info(
            "[INCIDENT LINKED] alert_id=%s to existing incident_id=%s",
            alert_id,
            iid,
        )
        return existing

    title = f"[AUTO] {sev_upper} alert from {source_ip}"
    new_inc = create_incident(conn, title, severity, source_ip)
    link_alert_to_incident(conn, new_inc["id"], alert_id)
    logger.info(
        "[INCIDENT CREATED] incident_id=%s for alert_id=%s",
        new_inc["id"],
        alert_id,
    )
    return new_inc


def list_incidents(
    conn,
    status: str | None = None,
    severity: str | None = None,
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
    if severity is not None:
        filters.append("severity = %s")
        params.append(severity)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([cap, offset])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params,
        )
        return [_incident_row_to_dict(row) for row in cur.fetchall()]


def get_incident_detail(conn, incident_id: int) -> dict[str, Any] | None:
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
        inc_row = cur.fetchone()
        if inc_row is None:
            return None
        base = _incident_row_to_dict(inc_row)
        cur.execute(
            """
            SELECT a.id, a.alert_type, a.severity, host(a.source_ip), a.status, a.created_at,
                   ia.linked_at
            FROM incident_alerts ia
            JOIN alerts a ON a.id = ia.alert_id
            WHERE ia.incident_id = %s
            ORDER BY ia.linked_at ASC
            """,
            (incident_id,),
        )
        alerts = []
        for a_row in cur.fetchall():
            (
                aid,
                alert_type,
                a_sev,
                a_ip,
                a_status,
                a_created,
                linked_at,
            ) = a_row
            alerts.append(
                {
                    "alert_id": aid,
                    "alert_type": alert_type,
                    "severity": a_sev,
                    "source_ip": a_ip,
                    "status": a_status,
                    "created_at": _iso(a_created),
                    "linked_at": _iso(linked_at),
                }
            )
        base["alerts"] = alerts
        return base


def update_incident_status(
    conn, incident_id: int, new_status: str, actor_username: str
) -> dict[str, Any]:
    _ = actor_username
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, severity, priority, status, host(source_ip),
                   assigned_to, created_at, resolved_at
            FROM incidents
            WHERE id = %s
            FOR UPDATE
            """,
            (incident_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("incident not found")

        current = row[4]
        if new_status not in ALL_INCIDENT_STATUSES:
            raise ValueError(f"invalid status transition: {current} -> {new_status}")
        allowed = ALLOWED_STATUS_TRANSITIONS.get(current, frozenset())
        if new_status not in allowed:
            raise ValueError(f"invalid status transition: {current} -> {new_status}")

        if new_status == "resolved":
            cur.execute(
                """
                UPDATE incidents
                SET status = %s, resolved_at = NOW()
                WHERE id = %s
                RETURNING id, title, severity, priority, status, host(source_ip),
                          assigned_to, created_at, resolved_at
                """,
                (new_status, incident_id),
            )
        else:
            cur.execute(
                """
                UPDATE incidents
                SET status = %s
                WHERE id = %s
                RETURNING id, title, severity, priority, status, host(source_ip),
                          assigned_to, created_at, resolved_at
                """,
                (new_status, incident_id),
            )
        return _incident_row_to_dict(cur.fetchone())
