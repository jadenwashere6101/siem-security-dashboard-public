from __future__ import annotations

import re
from typing import Any

from core.db import get_db_connection

NOTIFICATION_POLICY_ROW_ID = 1
ALLOWED_NOTIFICATION_SEVERITIES = ("low", "medium", "high", "critical")
ALLOWED_SLACK_FORMATS = ("compact", "detailed")
DEFAULT_NOTIFICATION_POLICY = {
    "slack_enabled": False,
    "minimum_severity": "high",
    "notify_on_alerts": True,
    "notify_on_incidents": True,
    "slack_format": "compact",
    "pfsense_destination": "pfSense destination",
    "honeypot_destination": "Honeypot destination",
}

_DESTINATION_LABEL_RE = re.compile(r"^[A-Za-z0-9#][A-Za-z0-9 #._/\-]{0,79}$")


def _normalize_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _normalize_destination(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    if "://" in normalized.lower():
        raise ValueError(f"{field} must be a routing label, not a URL")
    if not _DESTINATION_LABEL_RE.fullmatch(normalized):
        raise ValueError(
            f"{field} must start with a letter, number, or # and contain only bounded label characters"
        )
    return normalized


def validate_notification_policy_updates(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Notification policy payload must be an object")
    allowed_fields = {
        "slack_enabled",
        "minimum_severity",
        "notify_on_alerts",
        "notify_on_incidents",
        "slack_format",
        "pfsense_destination",
        "honeypot_destination",
    }
    unknown = set(payload) - allowed_fields
    if unknown:
        raise ValueError(f"Unknown notification policy field: {sorted(unknown)[0]}")

    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "slack_enabled":
            normalized[key] = _normalize_bool(value, key)
        elif key == "minimum_severity":
            candidate = str(value or "").strip().lower()
            if candidate not in ALLOWED_NOTIFICATION_SEVERITIES:
                raise ValueError(
                    f"minimum_severity must be one of {', '.join(ALLOWED_NOTIFICATION_SEVERITIES)}"
                )
            normalized[key] = candidate
        elif key == "notify_on_alerts":
            normalized[key] = _normalize_bool(value, key)
        elif key == "notify_on_incidents":
            normalized[key] = _normalize_bool(value, key)
        elif key == "slack_format":
            candidate = str(value or "").strip().lower()
            if candidate not in ALLOWED_SLACK_FORMATS:
                raise ValueError(f"slack_format must be one of {', '.join(ALLOWED_SLACK_FORMATS)}")
            normalized[key] = candidate
        elif key in {"pfsense_destination", "honeypot_destination"}:
            normalized[key] = _normalize_destination(value, key)
    return normalized


def default_notification_policy(status: str = "default") -> dict[str, Any]:
    return {
        "id": NOTIFICATION_POLICY_ROW_ID,
        **DEFAULT_NOTIFICATION_POLICY,
        "updated_at": None,
        "updated_by": None,
        "status": status,
    }


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "slack_enabled": row[1],
        "minimum_severity": row[2],
        "notify_on_alerts": row[3],
        "notify_on_incidents": row[4],
        "slack_format": row[5],
        "pfsense_destination": row[6],
        "honeypot_destination": row[7],
        "updated_at": str(row[8]) if row[8] is not None else None,
        "updated_by": row[9],
        "status": "applied",
    }


def load_notification_policy(cur) -> dict[str, Any]:
    try:
        cur.execute("SAVEPOINT notification_policy_read")
        cur.execute(
            """
            SELECT
                id,
                slack_enabled,
                minimum_severity,
                notify_on_alerts,
                notify_on_incidents,
                slack_format,
                pfsense_destination,
                honeypot_destination,
                updated_at,
                updated_by
            FROM notification_policy
            WHERE id = %s
            """,
            (NOTIFICATION_POLICY_ROW_ID,),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT notification_policy_read")
        if row is None:
            return default_notification_policy(status="default")
        policy = _row_to_dict(row)
        validate_notification_policy_updates(
            {
                "slack_enabled": policy["slack_enabled"],
                "minimum_severity": policy["minimum_severity"],
                "notify_on_alerts": policy["notify_on_alerts"],
                "notify_on_incidents": policy["notify_on_incidents"],
                "slack_format": policy["slack_format"],
                "pfsense_destination": policy["pfsense_destination"],
                "honeypot_destination": policy["honeypot_destination"],
            }
        )
        return policy
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT notification_policy_read")
            cur.execute("RELEASE SAVEPOINT notification_policy_read")
        except Exception:
            pass
        return default_notification_policy(status="unavailable")


def get_effective_notification_policy() -> dict[str, Any]:
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        return load_notification_policy(cur)
    except Exception:
        return default_notification_policy(status="unavailable")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def upsert_notification_policy(cur, updates: dict[str, Any], updated_by: str | None) -> dict[str, Any]:
    normalized = validate_notification_policy_updates(updates)
    current = load_notification_policy(cur)
    merged = {
        "slack_enabled": normalized.get("slack_enabled", current["slack_enabled"]),
        "minimum_severity": normalized.get("minimum_severity", current["minimum_severity"]),
        "notify_on_alerts": normalized.get("notify_on_alerts", current["notify_on_alerts"]),
        "notify_on_incidents": normalized.get("notify_on_incidents", current["notify_on_incidents"]),
        "slack_format": normalized.get("slack_format", current["slack_format"]),
        "pfsense_destination": normalized.get("pfsense_destination", current["pfsense_destination"]),
        "honeypot_destination": normalized.get("honeypot_destination", current["honeypot_destination"]),
    }
    cur.execute(
        """
        INSERT INTO notification_policy (
            id,
            slack_enabled,
            minimum_severity,
            notify_on_alerts,
            notify_on_incidents,
            slack_format,
            pfsense_destination,
            honeypot_destination,
            updated_at,
            updated_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        ON CONFLICT (id) DO UPDATE
        SET
            slack_enabled = EXCLUDED.slack_enabled,
            minimum_severity = EXCLUDED.minimum_severity,
            notify_on_alerts = EXCLUDED.notify_on_alerts,
            notify_on_incidents = EXCLUDED.notify_on_incidents,
            slack_format = EXCLUDED.slack_format,
            pfsense_destination = EXCLUDED.pfsense_destination,
            honeypot_destination = EXCLUDED.honeypot_destination,
            updated_at = NOW(),
            updated_by = EXCLUDED.updated_by
        """,
        (
            NOTIFICATION_POLICY_ROW_ID,
            merged["slack_enabled"],
            merged["minimum_severity"],
            merged["notify_on_alerts"],
            merged["notify_on_incidents"],
            merged["slack_format"],
            merged["pfsense_destination"],
            merged["honeypot_destination"],
            updated_by,
        ),
    )
    return merged
