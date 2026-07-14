from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.pfsense_operational_baseline import (
    build_alert_operational_history,
    build_incident_operational_history,
    build_pfsense_incident_scope_filter,
)

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


def _incident_row_to_dict(
    record: tuple[Any, ...],
    *,
    operational_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "operational_history": operational_history,
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
    operational_scope: str = "all_history",
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
    operational_clause, operational_params = build_pfsense_incident_scope_filter(
        operational_scope,
        incident_alias="incidents",
    )
    if operational_clause:
        filters.append(operational_clause)
        params.extend(operational_params)

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
        rows = cur.fetchall()
        incident_ids = [row[0] for row in rows]
        legacy_by_incident_id = _build_incident_legacy_map(cur, incident_ids)
        return [
            _incident_row_to_dict(
                row,
                operational_history=legacy_by_incident_id.get(row[0]),
            )
            for row in rows
        ]


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
                   a.source, a.source_type,
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
                a_source,
                a_source_type,
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
                    "source": a_source,
                    "source_type": a_source_type,
                    "operational_history": build_alert_operational_history(
                        created_at=a_created,
                        source=a_source,
                        source_type=a_source_type,
                    ),
                    "linked_at": _iso(linked_at),
                }
            )
        base["alerts"] = alerts
        base["operational_history"] = build_incident_operational_history(
            created_at=base["created_at"],
            linked_alerts=alerts,
        )
        return base


def _build_incident_legacy_map(cur, incident_ids: list[int]) -> dict[int, dict[str, Any] | None]:
    filtered_ids = [int(incident_id) for incident_id in incident_ids if incident_id is not None]
    if not filtered_ids:
        return {}
    cur.execute(
        """
        SELECT
            i.id,
            i.created_at,
            a.created_at,
            a.source,
            a.source_type
        FROM incidents i
        LEFT JOIN incident_alerts ia ON ia.incident_id = i.id
        LEFT JOIN alerts a ON a.id = ia.alert_id
        WHERE i.id = ANY(%s)
        ORDER BY i.id ASC, ia.linked_at ASC
        """,
        (filtered_ids,),
    )
    grouped: dict[int, dict[str, Any]] = {}
    for incident_id, incident_created_at, alert_created_at, alert_source, alert_source_type in cur.fetchall():
        bucket = grouped.setdefault(
            incident_id,
            {"created_at": incident_created_at, "alerts": []},
        )
        if alert_created_at is not None:
            bucket["alerts"].append(
                {
                    "created_at": alert_created_at,
                    "source": alert_source,
                    "source_type": alert_source_type,
                }
            )
    return {
        incident_id: build_incident_operational_history(
            created_at=bucket["created_at"],
            linked_alerts=bucket["alerts"],
        )
        for incident_id, bucket in grouped.items()
    }


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
