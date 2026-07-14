from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


PFSENSE_BASELINE_LABEL = "Pre-Tuning"
OPERATIONAL_SCOPE_SINCE_TUNING = "since_tuning"
OPERATIONAL_SCOPE_ALL_HISTORY = "all_history"
VALID_OPERATIONAL_SCOPES = frozenset(
    {OPERATIONAL_SCOPE_SINCE_TUNING, OPERATIONAL_SCOPE_ALL_HISTORY}
)


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return None


def get_pfsense_tuning_baseline() -> datetime | None:
    raw_value = _env_first("SIEM_PFSENSE_TUNING_BASELINE", "PFSENSE_TUNING_BASELINE")
    if raw_value is None:
        return None
    parsed = datetime.fromisoformat(str(raw_value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_operational_scope(value: Any) -> str:
    if value in (None, ""):
        return OPERATIONAL_SCOPE_ALL_HISTORY
    normalized = str(value).strip().lower()
    if normalized not in VALID_OPERATIONAL_SCOPES:
        raise ValueError("invalid operational scope")
    return normalized


def build_pfsense_alert_baseline_filter(
    scope: str,
    *,
    created_at_column: str = "created_at",
    source_column: str = "source",
    source_type_column: str = "source_type",
) -> tuple[str | None, list[Any]]:
    baseline = get_pfsense_tuning_baseline()
    if scope != OPERATIONAL_SCOPE_SINCE_TUNING or baseline is None:
        return None, []
    clause = (
        f"(COALESCE({source_column}, 'legacy') <> 'pfsense' "
        f"OR COALESCE({source_type_column}, 'legacy') <> 'firewall' "
        f"OR {created_at_column} >= %s)"
    )
    return clause, [baseline]


def build_pfsense_incident_scope_filter(
    scope: str,
    *,
    incident_alias: str = "incidents",
) -> tuple[str | None, list[Any]]:
    baseline = get_pfsense_tuning_baseline()
    if scope != OPERATIONAL_SCOPE_SINCE_TUNING or baseline is None:
        return None, []
    clause = f"""
        (
            NOT EXISTS (
                SELECT 1
                FROM incident_alerts ia_any
                WHERE ia_any.incident_id = {incident_alias}.id
            )
            OR EXISTS (
                SELECT 1
                FROM incident_alerts ia
                JOIN alerts a ON a.id = ia.alert_id
                WHERE ia.incident_id = {incident_alias}.id
                  AND (
                    COALESCE(a.source, 'legacy') <> 'pfsense'
                    OR COALESCE(a.source_type, 'legacy') <> 'firewall'
                    OR a.created_at >= %s
                  )
            )
        )
    """
    return clause, [baseline]


def is_pre_tuning_pfsense_alert(
    *,
    created_at: Any,
    source: Any,
    source_type: Any,
) -> bool:
    baseline = get_pfsense_tuning_baseline()
    if baseline is None:
        return False
    if str(source or "").strip().lower() != "pfsense":
        return False
    if str(source_type or "").strip().lower() != "firewall":
        return False
    parsed = _parse_datetime(created_at)
    return parsed is not None and parsed < baseline


def build_alert_operational_history(
    *,
    created_at: Any,
    source: Any,
    source_type: Any,
) -> dict[str, Any] | None:
    if not is_pre_tuning_pfsense_alert(
        created_at=created_at,
        source=source,
        source_type=source_type,
    ):
        return None
    baseline = get_pfsense_tuning_baseline()
    return {
        "is_pre_tuning": True,
        "label": PFSENSE_BASELINE_LABEL,
        "baseline_timestamp": baseline.isoformat() if baseline is not None else None,
    }


def build_incident_operational_history(
    *,
    created_at: Any,
    linked_alerts: list[dict[str, Any]] | None = None,
    linked_alert_rows: list[tuple[Any, ...]] | None = None,
) -> dict[str, Any] | None:
    baseline = get_pfsense_tuning_baseline()
    if baseline is None:
        return None

    alert_dicts = linked_alerts
    if alert_dicts is None and linked_alert_rows is not None:
        alert_dicts = [
            {
                "created_at": row[5],
                "source": row[6],
                "source_type": row[7],
            }
            for row in linked_alert_rows
        ]
    if not alert_dicts:
        return None

    has_linked_pre_tuning_pfsense = any(
        is_pre_tuning_pfsense_alert(
            created_at=alert.get("created_at"),
            source=alert.get("source"),
            source_type=alert.get("source_type"),
        )
        for alert in alert_dicts
    )
    has_current_operational_alert = any(
        not is_pre_tuning_pfsense_alert(
            created_at=alert.get("created_at"),
            source=alert.get("source"),
            source_type=alert.get("source_type"),
        )
        for alert in alert_dicts
    )
    if not has_linked_pre_tuning_pfsense or has_current_operational_alert:
        return None

    parsed_created_at = _parse_datetime(created_at)
    return {
        "is_pre_tuning": True,
        "label": PFSENSE_BASELINE_LABEL,
        "baseline_timestamp": baseline.isoformat(),
        "created_at_before_baseline": bool(parsed_created_at and parsed_created_at < baseline),
    }


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
