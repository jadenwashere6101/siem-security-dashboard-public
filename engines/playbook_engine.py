"""
Playbook trigger matching (read-only).

Evaluates which enabled playbook definitions match a committed alert. Does not
enqueue work, execute steps, or create execution rows — callers own orchestration.
"""

from __future__ import annotations

import logging
from typing import Any

from core import playbook_store

logger = logging.getLogger(__name__)

# Keep aligned with correlated alert_type values produced by engines/correlation_engine.py.
# Do not import correlation_engine here (load-bearing module); update this set when new
# correlation alert types are added upstream.
CORRELATED_ALERT_TYPES: frozenset[str] = frozenset(
    {
        "correlated_activity",
        "web_to_app_attack_pattern",
        "spray_then_success_pattern",
        "cloud_app_error_pattern",
    }
)

SEVERITY_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

_KNOWN_TRIGGER_KEYS = frozenset(
    {
        "alert_type",
        "min_severity",
        "source",
        "correlation_flag",
        "reputation_score_min",
    }
)


def _fetch_alert(conn, alert_id: int) -> dict[str, Any] | None:
    """Load alert columns; source_ip returned as text via host()."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                alert_type,
                severity,
                host(source_ip) AS source_ip,
                source,
                source_type,
                message,
                status,
                country,
                city,
                latitude,
                longitude,
                reputation_score,
                reputation_label,
                reputation_source,
                reputation_summary,
                response_action,
                response_status,
                created_at
            FROM alerts
            WHERE id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        keys = (
            "id",
            "alert_type",
            "severity",
            "source_ip",
            "source",
            "source_type",
            "message",
            "status",
            "country",
            "city",
            "latitude",
            "longitude",
            "reputation_score",
            "reputation_label",
            "reputation_source",
            "reputation_summary",
            "response_action",
            "response_status",
            "created_at",
        )
        return dict(zip(keys, row))


def _evaluate_trigger(trigger_config: dict[str, Any], alert: dict[str, Any]) -> bool:
    """
    Pure AND evaluation over known trigger keys. Absent keys match any alert.
    Unrecognized keys in trigger_config are ignored (forward-compatible).
    """
    if not isinstance(trigger_config, dict):
        return False

    for key, value in trigger_config.items():
        if key not in _KNOWN_TRIGGER_KEYS:
            continue

        if key == "alert_type":
            want = value
            if want is None:
                continue
            at = alert.get("alert_type")
            if at is None:
                return False
            if str(at).lower() != str(want).lower():
                return False

        elif key == "min_severity":
            want = str(value).lower() if value is not None else None
            if want is None or want not in SEVERITY_RANK:
                return False
            alert_sev = alert.get("severity")
            if alert_sev is None:
                return False
            alert_l = str(alert_sev).lower()
            if alert_l not in SEVERITY_RANK:
                return False
            if SEVERITY_RANK[alert_l] < SEVERITY_RANK[want]:
                return False

        elif key == "source":
            want = str(value).lower() if value is not None else ""
            have_raw = alert.get("source")
            have = (have_raw or "").lower() if have_raw is not None else ""
            if have != want:
                return False

        elif key == "correlation_flag":
            if value is not True and value is not False:
                continue
            at = alert.get("alert_type")
            if at is None:
                return False
            is_corr = str(at) in CORRELATED_ALERT_TYPES
            if value is True and not is_corr:
                return False
            if value is False and is_corr:
                return False

        elif key == "reputation_score_min":
            try:
                minimum = float(value)
            except (TypeError, ValueError):
                return False
            score = alert.get("reputation_score")
            effective = 0.0 if score is None else float(score)
            if effective < minimum:
                return False

    return True


def match_playbooks(conn, alert_id: int) -> list[dict[str, Any]]:
    """
    Read-only: return enabled definitions whose trigger_config matches the alert.

    Safe only after the alert row is committed. Does not create executions or touch the queue.
    """
    try:
        alert = _fetch_alert(conn, alert_id)
        if alert is None:
            logger.warning("[PLAYBOOK MATCH] alert not found alert_id=%s", alert_id)
            return []

        definitions = playbook_store.list_enabled_playbook_definitions(conn)
        matched: list[dict[str, Any]] = []
        for definition in definitions:
            trigger = definition.get("trigger_config") or {}
            if not isinstance(trigger, dict):
                trigger = {}
            if _evaluate_trigger(trigger, alert):
                matched.append(definition)
        return matched
    except Exception:
        logger.exception("[PLAYBOOK MATCH] unexpected error alert_id=%s", alert_id)
        return []
