from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


INVESTIGATION_LABELS = {
    "high": "Investigate Now",
    "medium": "Review Soon",
    "low": "Monitor",
}


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _plural(value: int, noun: str) -> str:
    return f"{value} {noun}" if value == 1 else f"{value} {noun}s"


def _days_observed(first_seen: Any, last_seen: Any) -> int:
    first_dt = _to_datetime(first_seen)
    last_dt = _to_datetime(last_seen)
    if first_dt is None or last_dt is None:
        return 0
    return max((last_dt.date() - first_dt.date()).days + 1, 1)


def _reason(reason_id: str, text: str) -> dict[str, str]:
    return {"id": reason_id, "text": text}


def build_returning_attacker_context(history: dict[str, Any] | None) -> dict[str, Any]:
    history = history or {}
    first_seen = history.get("first_seen")
    last_seen = history.get("last_seen")
    days_observed = max(
        _coerce_int(history.get("days_observed")),
        _days_observed(first_seen, last_seen),
    )
    previous_incidents = _coerce_int(history.get("previous_incidents"))
    previous_responses = _coerce_int(history.get("previous_responses"))
    repeated_destinations = _coerce_int(history.get("repeated_destinations"))
    repeated_services = _coerce_int(history.get("repeated_services"))
    campaign_count = _coerce_int(history.get("campaign_count"))
    is_returning = days_observed > 1 or previous_incidents > 0 or previous_responses > 0

    reasons: list[dict[str, str]] = []
    if days_observed > 1:
        reasons.append(_reason("days_observed", f"Returning for {days_observed} days"))
    if previous_incidents > 0:
        reasons.append(_reason("previous_incidents", f"Linked to {previous_incidents} previous incidents"))
    if previous_responses > 0:
        reasons.append(_reason("previous_responses", f"{previous_responses} previous response actions recorded"))
    if repeated_destinations > 0:
        reasons.append(_reason("repeated_destinations", f"Repeatedly targeted {_plural(repeated_destinations, 'destination')}"))
    if repeated_services > 0:
        reasons.append(_reason("repeated_services", f"Repeatedly touched {_plural(repeated_services, 'service')}"))
    if campaign_count > 0:
        reasons.append(_reason("campaign_count", f"Seen in {_plural(campaign_count, 'campaign')}"))

    if not reasons:
        reasons.append(_reason("new_source", "No prior history for this source"))

    return {
        "is_returning": is_returning,
        "headline": "Returning attacker" if is_returning else "No prior history",
        "summary": reasons[0]["text"],
        "first_seen": first_seen,
        "last_seen": last_seen,
        "days_observed": days_observed,
        "previous_incidents": previous_incidents,
        "previous_responses": previous_responses,
        "repeated_destinations": repeated_destinations,
        "repeated_services": repeated_services,
        "campaign_count": campaign_count,
        "reasons": reasons,
    }


def build_campaign_intelligence(campaign: dict[str, Any] | None) -> dict[str, Any]:
    campaign = campaign or {}
    days_active = max(_coerce_int(campaign.get("days_active")), _days_observed(campaign.get("first_seen"), campaign.get("last_seen")))
    source_count = _coerce_int(campaign.get("source_count"))
    destination_count = _coerce_int(campaign.get("destination_count"))
    service_count = _coerce_int(campaign.get("service_count"))
    corroborating_alert_types = _coerce_int(campaign.get("corroborating_alert_types"))
    progression = bool(campaign.get("progression_observed"))
    timing = bool(campaign.get("timing_pattern"))
    relationship = campaign.get("relationship") or ""

    evidence: list[dict[str, str]] = []
    if days_active > 1:
        evidence.append(_reason("days_active", f"Observed across {days_active} days"))
    if source_count > 1:
        evidence.append(_reason("source_count", f"{source_count} sources targeted the same protected asset"))
    if destination_count > 0:
        evidence.append(_reason("destination_count", f"Repeated against {_plural(destination_count, 'destination')}"))
    if service_count > 0:
        evidence.append(_reason("service_count", f"Repeated across {_plural(service_count, 'service')}"))
    if corroborating_alert_types > 1:
        evidence.append(_reason("corroboration", f"Supported by {corroborating_alert_types} detection types"))
    if progression:
        evidence.append(_reason("progression", "Progression observed"))
    if timing:
        evidence.append(_reason("timing", "Repeated timing pattern observed"))
    if relationship:
        evidence.append(_reason("relationship", relationship))

    if source_count > 1 or progression or days_active > 1:
        summary = "Campaign evidence present"
    else:
        summary = "Limited campaign evidence"

    return {
        "present": bool(evidence),
        "headline": summary,
        "summary": evidence[0]["text"] if evidence else "No sustained target-focused pattern established",
        "reasons": evidence,
    }


def build_investigation_value(
    *,
    severity: str | None,
    returning_attacker: dict[str, Any] | None = None,
    campaign_intelligence: dict[str, Any] | None = None,
    progression_observed: bool = False,
    corroborating_detection_count: int = 0,
    destination_important: bool = False,
    response_history_present: bool = False,
    repeated_destination: bool = False,
    persistent_activity: bool = False,
) -> dict[str, Any]:
    severity_value = str(severity or "").lower()
    returning_attacker = returning_attacker or {}
    campaign_intelligence = campaign_intelligence or {}
    points = 0
    reasons: list[dict[str, str]] = []

    if severity_value == "critical":
        points += 3
        reasons.append(_reason("severity", "Critical severity increases urgency"))
    elif severity_value == "high":
        points += 2
        reasons.append(_reason("severity", "High severity raises review priority"))

    if progression_observed:
        points += 3
        reasons.append(_reason("progression", "Progression observed"))
    if campaign_intelligence.get("present"):
        points += 2
        reasons.append(_reason("campaign", campaign_intelligence.get("summary") or "Campaign evidence present"))
    if returning_attacker.get("is_returning"):
        points += 1
        reasons.append(_reason("returning_attacker", returning_attacker.get("summary") or "Returning attacker history present"))
    if corroborating_detection_count > 1:
        points += 2
        reasons.append(_reason("corroboration", f"Supported by {corroborating_detection_count} corroborating detections"))
    if destination_important:
        points += 2
        reasons.append(_reason("destination_importance", "Protected destination is important"))
    if response_history_present:
        points += 1
        reasons.append(_reason("response_history", "Previous response history exists"))
    if repeated_destination:
        points += 1
        reasons.append(_reason("repeated_destination", "Same destination was targeted repeatedly"))
    if persistent_activity:
        points += 1
        reasons.append(_reason("persistent_activity", "Activity persisted over time"))

    if points >= 6:
        level = "high"
    elif points >= 3:
        level = "medium"
    else:
        level = "low"

    if not reasons:
        reasons.append(_reason("limited_context", "No progression or campaign evidence"))

    return {
        "level": level,
        "label": INVESTIGATION_LABELS[level],
        "summary": reasons[0]["text"],
        "reasons": reasons[:5],
    }


def build_port_scan_story(
    *,
    investigation_value: dict[str, Any],
    returning_attacker: dict[str, Any] | None = None,
    campaign_intelligence: dict[str, Any] | None = None,
    repeated_destination: bool = False,
    progression_observed: bool = False,
) -> dict[str, Any]:
    returning_attacker = returning_attacker or {}
    campaign_intelligence = campaign_intelligence or {}
    if progression_observed:
        headline = "Progression-backed recon"
    elif campaign_intelligence.get("present"):
        headline = "Campaign-linked recon"
    elif repeated_destination or returning_attacker.get("is_returning"):
        headline = "Persistent internet recon"
    else:
        headline = "Routine internet recon"

    disposition = (
        "Investigation recommended"
        if investigation_value.get("level") == "high"
        else "Review when capacity allows"
        if investigation_value.get("level") == "medium"
        else "No immediate investigation recommended"
    )
    return {
        "headline": headline,
        "disposition": disposition,
    }


def build_incident_intelligence(
    *,
    incident: dict[str, Any],
    linked_alerts: list[dict[str, Any]],
) -> dict[str, Any]:
    priorities = Counter(str(alert.get("severity") or "").lower() for alert in linked_alerts)
    progression = any(
        bool((alert.get("investigation_intelligence") or {}).get("progression_observed"))
        or bool((alert.get("campaign_intelligence") or {}).get("present"))
        for alert in linked_alerts
    )
    all_resolved = bool(linked_alerts) and all(str(alert.get("status") or "").lower() == "resolved" for alert in linked_alerts)
    incident_title = str(incident.get("title") or "").lower()
    if "recon activity" in incident_title:
        ownership = "Recon-activity investigation"
    elif progression:
        ownership = "Campaign-owned investigation"
    elif len(linked_alerts) > 1:
        ownership = "Aggregate investigation"
    else:
        ownership = "Source-specific investigation"

    reasons = []
    priority = str(incident.get("priority") or "").upper()
    if priority == "P1":
        reasons.append(_reason("priority", "Priority P1 is reserved for immediate action"))
    elif priority == "P2":
        reasons.append(_reason("priority", "Priority P2 reflects actionable progression or a prompt containment decision"))
    else:
        reasons.append(_reason("priority", "Priority P3 tracks valid case work that is not immediately urgent"))
    if progression:
        reasons.append(_reason("progression", "Linked alerts show campaign or progression evidence"))
    if priorities.get("critical", 0) > 0:
        reasons.append(_reason("critical_alert", "Contains a critical linked alert"))
    if priorities.get("high", 0) > 0:
        reasons.append(_reason("high_alert", "Contains high-severity linked alerts"))
    if all_resolved:
        reasons.append(_reason("all_resolved", "All linked alerts are resolved"))
    if len(linked_alerts) > 1:
        reasons.append(_reason("linked_alerts", f"{len(linked_alerts)} alerts are grouped into this incident"))
    if not reasons:
        reasons.append(_reason("single_alert", "Incident tracks one active alert"))

    auto_close_recommended = bool(all_resolved and str(incident.get("priority") or "").upper() == "P3")
    return {
        "ownership": ownership,
        "summary": reasons[0]["text"],
        "reasons": reasons[:5],
        "auto_close_recommended": auto_close_recommended,
        "auto_close_reason": "All linked alerts are resolved and this is a lower-priority incident"
        if auto_close_recommended
        else None,
    }


def determine_incident_priority(
    *,
    severity: str | None,
    investigation_value_level: str,
    progression_observed: bool,
    campaign_present: bool,
) -> str:
    sev = str(severity or "").upper()
    if sev == "CRITICAL":
        return "P1"
    if progression_observed or (sev == "HIGH" and campaign_present and investigation_value_level == "high"):
        return "P2"
    return "P3"
