from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
from typing import Any

from core.ai.config import AiGatewayConfig
from core.db import get_db_connection
from core.incident_store import get_incident_detail
from core.indicator_response_registry import get_registry_detail
from core.recon_activity_store import get_recon_activity_detail
from engines.severity_response_matrix import build_severity_response_matrix
from routes.alerts_events_routes import (
    _ALERT_SELECT,
    _build_alert_payload,
    _build_pfsense_why_fired_payload,
    _fetch_alert_intelligence,
    _fetch_latest_resolved_audits,
    _query_related_pfsense_events,
)
from routes.incident_routes import build_readonly_incident_timeline
from routes.source_ip_context_routes import (
    _fetch_alert_context,
    _fetch_blocklist_context,
    _fetch_campaign_memberships,
    _fetch_external_reputation_snapshots,
    _fetch_incident_context,
    _fetch_playbook_execution_context,
    _fetch_queue_context,
    _fetch_returning_attacker_context,
)
from core.internet_noise import build_internet_noise_decision, get_internet_noise_assessment
from core.investigation_intelligence import build_local_evidence_override_reasons
from core.ip_helpers import get_ip_reputation
from core.soar_response_outcomes import get_outcome_count_groups, get_recent_outcomes_for_source_ip

SUPPORTED_CONTEXT_TYPES = frozenset(
    {
        "alert",
        "incident",
        "source_ip",
        "recon_activity",
        "dashboard",
        "response_registry",
        "detection",
        "general",
    }
)

WORKSPACE_CONTEXT_ALIASES = {
    "soc_command_center": "general",
    "soc_briefings": "general",
    "recon_history": "general",
    "analyst_workspace": "general",
    "detection_simulator": "general",
    "detection_rules": "general",
    "severity_response_matrix": "general",
    "source_health": "general",
    "threat_hunt": "general",
    "settings": "general",
    "admin_users": "general",
    "admin_audit_logs": "general",
    "soar_queue": "general",
    "soar_incidents": "general",
    "soar_approvals": "general",
    "soar_playbooks": "general",
    "soar_integrations": "general",
    "soar_playbook_metrics": "general",
    "soar_operations": "general",
}

SECTION_LIMITS = {
    "recent_alerts": 10,
    "related_events": 15,
    "timeline": 30,
    "source_ip_outcomes": 10,
    "recon_related_events": 15,
    "chat_history": 8,
    "compact_alerts": 8,
    "compact_incidents": 6,
    "compact_queue": 6,
    "compact_campaigns": 4,
}

SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "database_url",
        "dsn",
        "password",
        "private_key",
        "secret",
        "token",
        "api_key",
    }
)


class AiContextError(Exception):
    status_code = 400
    error_code = "invalid_context"


class AiContextValidationError(AiContextError):
    status_code = 400
    error_code = "invalid_context"


class AiContextNotFoundError(AiContextError):
    status_code = 404
    error_code = "context_not_found"


@dataclass
class AiContextSource:
    source_type: str
    source_path: str
    record_ids: list[int | str] = field(default_factory=list)
    generated_at: str | None = None
    truncated: bool = False
    omitted_count: int = 0
    truncation_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_path": self.source_path,
            "record_ids": list(self.record_ids),
            "generated_at": self.generated_at,
            "truncated": self.truncated,
            "omitted_count": self.omitted_count,
            "truncation_reason": self.truncation_reason,
        }


@dataclass
class AiContextPayload:
    context_type: str
    data: dict[str, Any]
    sources: list[AiContextSource]
    insufficient_context: bool = False
    insufficient_reason: str | None = None
    truncated: bool = False
    omitted_count: int = 0

    def __post_init__(self) -> None:
        self.data = _redact_sensitive_values(self.data)

    def metadata(self) -> dict[str, Any]:
        return {
            "context_type": self.context_type,
            "sources": [source.as_dict() for source in self.sources],
            "truncated": self.truncated or any(source.truncated for source in self.sources),
            "omitted_count": self.omitted_count + sum(source.omitted_count for source in self.sources),
            "evidence": self.data.get("_evidence") if isinstance(self.data.get("_evidence"), dict) else None,
            "insufficient_reason": self.insufficient_reason,
        }


def build_ai_context(
    *,
    context_type: str,
    context: dict[str, Any] | None,
    config: AiGatewayConfig,
    question: str | None = None,
    client_history: list[dict[str, Any]] | None = None,
) -> AiContextPayload:
    normalized_type = _normalize_context_type(context_type)
    safe_context = context if isinstance(context, dict) else {}

    if normalized_type == "alert":
        return _build_alert_context(safe_context, config)
    if normalized_type == "incident":
        return _build_incident_context(safe_context)
    if normalized_type == "source_ip":
        return _build_source_ip_context(safe_context)
    if normalized_type == "recon_activity":
        return _build_recon_activity_context(safe_context)
    if normalized_type == "dashboard":
        return _build_visible_context("dashboard", safe_context, config)
    if normalized_type == "response_registry":
        return _build_response_registry_context(safe_context)
    if normalized_type == "detection":
        return _build_detection_context(safe_context, config)
    if normalized_type == "general":
        return _build_general_context(safe_context, config, question=question, client_history=client_history)

    raise AiContextValidationError(f"Unsupported context_type: {context_type}")


def _normalize_context_type(context_type: str) -> str:
    value = str(context_type or "").strip().lower().replace("-", "_")
    value = WORKSPACE_CONTEXT_ALIASES.get(value, value)
    if value not in SUPPORTED_CONTEXT_TYPES:
        raise AiContextValidationError(f"Unsupported context_type: {context_type}")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_int(context: dict[str, Any], *names: str) -> int:
    for name in names:
        value = context.get(name)
        if value in (None, ""):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise AiContextValidationError(f"{name} must be an integer")
        if parsed <= 0:
            raise AiContextValidationError(f"{name} must be positive")
        return parsed
    raise AiContextValidationError(f"{names[0]} is required")


def _optional_int(context: dict[str, Any], *names: str) -> int | None:
    try:
        return _required_int(context, *names)
    except AiContextValidationError as error:
        if "is required" in str(error):
            return None
        raise


def _required_source_ip(context: dict[str, Any]) -> str:
    value = str(context.get("source_ip") or "").strip()
    if not value:
        raise AiContextValidationError("source_ip is required")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as error:
        raise AiContextValidationError("source_ip is invalid") from error


def _limit_list(items: Any, limit: int, *, reason: str) -> tuple[list[Any], AiContextSource | None]:
    if not isinstance(items, list):
        return [], None
    limited = items[:limit]
    omitted = max(0, len(items) - len(limited))
    if omitted <= 0:
        return limited, None
    return limited, AiContextSource(
        source_type="truncation",
        source_path="core.ai.context_builder",
        generated_at=_utc_now(),
        truncated=True,
        omitted_count=omitted,
        truncation_reason=reason,
    )


def _compact_payload(value: Any, *, max_chars: int) -> tuple[Any, bool]:
    value = _redact_sensitive_values(value)
    text = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
    if len(text) <= max_chars:
        return value, False
    compacted = {
        "summary": "Context was too large and was compacted before AI prompt construction.",
        "preview": text[: max(0, max_chars - 120)],
    }
    if isinstance(value, dict) and isinstance(value.get("_evidence"), dict):
        compacted["_evidence"] = value["_evidence"]
    return compacted, True


def _short_text(value: Any, *, max_chars: int = 320) -> Any:
    if value is None:
        return None
    text = str(value)
    if len(text) <= max_chars:
        return value
    return f"{text[: max(0, max_chars - 3)]}..."


def _summarize_mapping(record: Any, keys: list[str], *, max_text_chars: int = 320) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {"value": _short_text(record, max_chars=max_text_chars)}
    compact: dict[str, Any] = {}
    for key in keys:
        if key not in record:
            continue
        value = record.get(key)
        if isinstance(value, (dict, list)):
            preview, _truncated = _compact_payload(value, max_chars=max_text_chars)
            compact[key] = preview
        else:
            compact[key] = _short_text(value, max_chars=max_text_chars)
    return compact


def _record_list(items: Any) -> list[Any]:
    if isinstance(items, list):
        return items
    if isinstance(items, dict) and isinstance(items.get("recent"), list):
        return items["recent"]
    if isinstance(items, dict) and isinstance(items.get("items"), list):
        return items["items"]
    if isinstance(items, dict) and isinstance(items.get("entries"), list):
        return items["entries"]
    return []


def _summarize_records(items: Any, limit: int, keys: list[str], *, reason: str) -> tuple[list[dict[str, Any]], AiContextSource | None]:
    records = _record_list(items)
    if not records:
        return [], None
    limited, source = _limit_list(records, limit, reason=reason)
    return [_summarize_mapping(item, keys) for item in limited], source


def _evidence_stats(*, included: dict[str, int], omitted: dict[str, int] | None = None) -> dict[str, Any]:
    omitted = omitted or {}
    return {
        "included": {key: int(value) for key, value in included.items()},
        "omitted": {key: int(value) for key, value in omitted.items() if int(value) > 0},
        "truncated": any(int(value) > 0 for value in omitted.values()),
    }


def _append_compaction_source(
    sources: list[AiContextSource],
    *,
    truncated: bool,
    omitted_count: int = 0,
    reason: str,
) -> list[AiContextSource]:
    if not truncated:
        return sources
    return [
        *sources,
        AiContextSource(
            source_type="truncation",
            source_path="core.ai.context_builder",
            generated_at=_utc_now(),
            truncated=True,
            omitted_count=max(0, int(omitted_count)),
            truncation_reason=reason,
        ),
    ]


def _redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, child in value.items():
            key_text = str(key)
            normalized_key = key_text.lower().replace("-", "_")
            if any(fragment in normalized_key for fragment in SENSITIVE_KEY_FRAGMENTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_sensitive_values(child)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _is_meaningful(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, dict):
        return any(_is_meaningful(child) for child in value.values())
    if isinstance(value, list):
        return any(_is_meaningful(child) for child in value)
    return True


def _build_alert_context(context: dict[str, Any], config: AiGatewayConfig) -> AiContextPayload:
    alert_id = _required_int(context, "alert_id", "id")
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
        row = cur.fetchone()
        if row is None:
            raise AiContextNotFoundError("Alert not found")

        response_outcome = None
        try:
            from core.soar_response_outcomes import serialize_latest_outcome

            response_outcome = serialize_latest_outcome(conn, alert_id=alert_id)
        except Exception:
            response_outcome = None
        cooldown_by_alert_id = _fetch_latest_resolved_audits(cur, [alert_id])
        intelligence_by_alert_id = _fetch_alert_intelligence(conn, [row])
        alert = _build_alert_payload(
            row,
            cur=cur,
            reputation_by_ip={},
            response_outcome=response_outcome,
            cooldown_by_alert_id=cooldown_by_alert_id,
            intelligence=intelligence_by_alert_id.get(int(alert_id)),
        )
        why_fired = _build_pfsense_why_fired_payload(row, cooldown_by_alert_id)
        related_events = _related_events_from_alert_row(cur, row, SECTION_LIMITS["related_events"])
        data = {
            "alert": _summarize_mapping(
                alert,
                [
                    "id",
                    "alert_id",
                    "alert_type",
                    "severity",
                    "status",
                    "source_ip",
                    "target_ip",
                    "destination_ip",
                    "destination_port",
                    "message",
                    "created_at",
                    "updated_at",
                    "source",
                    "source_type",
                    "response_outcome",
                    "intelligence",
                ],
            ),
            "why_fired": why_fired,
            "related_events": [
                _summarize_mapping(
                    event,
                    [
                        "id",
                        "event_id",
                        "event_type",
                        "severity",
                        "source_ip",
                        "destination_ip",
                        "destination_port",
                        "protocol",
                        "action",
                        "message",
                        "created_at",
                        "timestamp",
                    ],
                )
                for event in related_events
            ],
            "_evidence": _evidence_stats(
                included={"related_events": len(related_events)},
            ),
        }
        data, truncated = _compact_payload(data, max_chars=max(config.max_prompt_chars // 2, 2000))
        return AiContextPayload(
            context_type="alert",
            data=data,
            sources=[
                AiContextSource("alert", f"/alerts/{alert_id}", [alert_id], _utc_now()),
                AiContextSource("detection", f"/alerts/{alert_id}/why-fired", [alert_id], _utc_now()),
                AiContextSource("events", f"/alerts/{alert_id}/related-events", [alert_id], _utc_now()),
            ],
            insufficient_context=not _is_meaningful(data),
            insufficient_reason=None if _is_meaningful(data) else "No alert context available.",
            truncated=truncated,
        )
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def _related_events_from_alert_row(cur, row: tuple[Any, ...], limit: int) -> list[dict[str, Any]]:
    context = row[19] if isinstance(row[19], dict) else {}
    related_filter = context.get("related_event_filter")
    if not isinstance(related_filter, dict):
        return []
    return _query_related_pfsense_events(cur, related_filter, limit=limit)


def _build_incident_context(context: dict[str, Any]) -> AiContextPayload:
    incident_id = _required_int(context, "incident_id", "id")
    conn = None
    try:
        conn = get_db_connection()
        incident = get_incident_detail(conn, incident_id)
        if incident is None:
            raise AiContextNotFoundError("Incident not found")
        timeline_payload = build_readonly_incident_timeline(conn, incident_id) or {"timeline": []}
        timeline, truncation_source = _limit_list(
            timeline_payload.get("timeline"),
            SECTION_LIMITS["timeline"],
            reason="Incident timeline exceeded AI context limit.",
        )
        sources = [
            AiContextSource("incident", f"/incidents/{incident_id}", [incident_id], _utc_now()),
            AiContextSource("incident_timeline", f"/incidents/{incident_id}/timeline", [incident_id], _utc_now()),
        ]
        if truncation_source:
            sources.append(truncation_source)
        compact_timeline, timeline_truncation_source = _summarize_records(
            timeline,
            SECTION_LIMITS["timeline"],
            [
                "id",
                "type",
                "event_type",
                "status",
                "severity",
                "source_ip",
                "message",
                "created_at",
                "timestamp",
                "description",
            ],
            reason="Incident timeline exceeded AI context limit.",
        )
        if timeline_truncation_source:
            sources.append(timeline_truncation_source)
        data = {
            "incident": _summarize_mapping(
                incident,
                [
                    "id",
                    "event_id",
                    "title",
                    "severity",
                    "priority",
                    "status",
                    "source_ip",
                    "summary",
                    "created_at",
                    "updated_at",
                    "last_seen",
                    "alert_count",
                    "affected_assets",
                ],
            ),
            "timeline": compact_timeline,
            "_evidence": _evidence_stats(
                included={"timeline": len(compact_timeline)},
                omitted={"timeline": max(0, len(timeline) - len(compact_timeline)) if isinstance(timeline, list) else 0},
            ),
        }
        data, truncated = _compact_payload(data, max_chars=6000)
        sources = _append_compaction_source(
            sources,
            truncated=truncated,
            reason="Incident context compacted before AI prompt construction.",
        )
        return AiContextPayload(
            context_type="incident",
            data=data,
            sources=sources,
            insufficient_context=not _is_meaningful(incident),
            insufficient_reason=None if _is_meaningful(incident) else "No incident context available.",
            truncated=truncated,
        )
    finally:
        if conn is not None:
            conn.close()


def _build_source_ip_context(context: dict[str, Any]) -> AiContextPayload:
    source_ip = _required_source_ip(context)
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            alerts, alert_ids = _fetch_alert_context(cur, source_ip)
            incidents, incident_ids = _fetch_incident_context(cur, source_ip, alert_ids)
            queue = _fetch_queue_context(cur, source_ip)
            blocklist = _fetch_blocklist_context(cur, source_ip)
            behavioral = get_ip_reputation(source_ip, cur=cur)
            external = _fetch_external_reputation_snapshots(cur, source_ip)
            playbook_executions = _fetch_playbook_execution_context(cur, alert_ids, incident_ids)
            returning_attacker = _fetch_returning_attacker_context(cur, source_ip)
            campaigns = _fetch_campaign_memberships(cur, source_ip)
            internet_noise = build_internet_noise_decision(
                get_internet_noise_assessment(source_ip),
                override_reasons=build_local_evidence_override_reasons(
                    returning_attacker=returning_attacker,
                    campaign_intelligence=(
                        campaigns["recent"][0]["campaign_intelligence"]
                        if campaigns.get("recent")
                        else {}
                    ),
                    corroborating_detection_count=max(campaigns.get("count") or 0, 1),
                    response_history_present=returning_attacker.get("previous_responses", 0) > 0,
                    repeated_destination=returning_attacker.get("repeated_destinations", 0) > 0,
                    persistent_activity=returning_attacker.get("days_observed", 0) > 1,
                ),
            )
            response_outcomes = get_recent_outcomes_for_source_ip(
                conn,
                source_ip,
                limit=SECTION_LIMITS["source_ip_outcomes"],
            )
            response_outcome_counts = get_outcome_count_groups(conn, source_ip=source_ip)

        compact_alerts, alert_truncation = _summarize_records(
            alerts,
            SECTION_LIMITS["compact_alerts"],
            ["id", "alert_id", "alert_type", "severity", "status", "source_ip", "message", "created_at"],
            reason="Source-IP alert evidence exceeded AI context limit.",
        )
        compact_incidents, incident_truncation = _summarize_records(
            incidents,
            SECTION_LIMITS["compact_incidents"],
            ["id", "title", "severity", "priority", "status", "source_ip", "created_at", "updated_at"],
            reason="Source-IP incident evidence exceeded AI context limit.",
        )
        compact_queue, queue_truncation = _summarize_records(
            queue,
            SECTION_LIMITS["compact_queue"],
            ["id", "alert_id", "source_ip", "action", "status", "created_at", "updated_at", "last_error"],
            reason="Source-IP response queue evidence exceeded AI context limit.",
        )
        compact_outcomes, outcome_truncation = _summarize_records(
            response_outcomes,
            SECTION_LIMITS["source_ip_outcomes"],
            ["id", "alert_id", "source_ip", "action", "outcome", "status", "created_at", "completed_at", "summary", "limit"],
            reason="Source-IP response outcome evidence exceeded AI context limit.",
        )
        alert_records = _record_list(alerts)
        incident_records = _record_list(incidents)
        queue_records = _record_list(queue)
        outcome_records = _record_list(response_outcomes)
        campaign_recent = campaigns.get("recent") if isinstance(campaigns, dict) else []
        compact_campaigns, campaign_truncation = _summarize_records(
            campaign_recent,
            SECTION_LIMITS["compact_campaigns"],
            ["id", "campaign_key", "label", "severity", "confidence", "first_seen", "last_seen", "campaign_intelligence"],
            reason="Source-IP campaign evidence exceeded AI context limit.",
        )
        data = {
            "source_ip": source_ip,
            "alerts": compact_alerts,
            "incidents": compact_incidents,
            "queue": compact_queue,
            "blocklist": _summarize_mapping(blocklist, ["listed", "status", "reason", "created_at", "updated_at"]),
            "reputation": {
                "behavioral": {
                    "score": behavioral["reputation_score"],
                    "label": behavioral["reputation_label"],
                    "source": "siem_internal",
                    "summary": behavioral["reputation_summary"],
                    "contributing_signals": behavioral.get("contributing_signals", []),
                },
                **external,
            },
            "internet_noise": internet_noise,
            "playbook_executions": [
                _summarize_mapping(item, ["id", "playbook_id", "status", "created_at", "updated_at", "failure_reason"])
                for item in _record_list(playbook_executions)[: SECTION_LIMITS["compact_queue"]]
            ],
            "returning_attacker": returning_attacker,
            "campaigns": {
                **(campaigns if isinstance(campaigns, dict) else {}),
                "recent": compact_campaigns,
            },
            "response_outcomes": compact_outcomes,
            "response_outcome_counts": response_outcome_counts,
            "_evidence": _evidence_stats(
                included={
                    "alerts": len(compact_alerts),
                    "incidents": len(compact_incidents),
                    "queue": len(compact_queue),
                    "response_outcomes": len(compact_outcomes),
                    "campaigns": len(compact_campaigns),
                },
                omitted={
                    "alerts": max(0, len(alert_records) - len(compact_alerts)),
                    "incidents": max(0, len(incident_records) - len(compact_incidents)),
                    "queue": max(0, len(queue_records) - len(compact_queue)),
                    "response_outcomes": max(0, len(outcome_records) - len(compact_outcomes)),
                    "campaigns": max(0, len(campaign_recent) - len(compact_campaigns)) if isinstance(campaign_recent, list) else 0,
                },
            ),
        }
        data, truncated = _compact_payload(data, max_chars=9000)
        sources = [AiContextSource("source_ip", "/source-ip-context", [source_ip], _utc_now())]
        for source in (alert_truncation, incident_truncation, queue_truncation, outcome_truncation, campaign_truncation):
            if source:
                sources.append(source)
        sources = _append_compaction_source(
            sources,
            truncated=truncated,
            reason="Source-IP context compacted before AI prompt construction.",
        )
        return AiContextPayload(
            context_type="source_ip",
            data=data,
            sources=sources,
            insufficient_context=not _is_meaningful(
                {
                    "alerts": compact_alerts,
                    "incidents": compact_incidents,
                    "queue": compact_queue,
                    "blocklist": blocklist,
                    "response_outcomes": compact_outcomes,
                    "campaigns": compact_campaigns,
                }
            ),
            insufficient_reason="No meaningful source-IP context available.",
            truncated=truncated,
        )
    finally:
        if conn is not None:
            conn.close()


def _build_recon_activity_context(context: dict[str, Any]) -> AiContextPayload:
    activity_id = _required_int(context, "activity_id", "recon_activity_id", "id")
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        detail = get_recon_activity_detail(conn, activity_id)
        if detail is None:
            raise AiContextNotFoundError("Recon activity not found")
        related_events: list[dict[str, Any]] = []
        cur = conn.cursor()
        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
        target_context = summary.get("target_context") if isinstance(summary.get("target_context"), dict) else {}
        representative_sources = summary.get("representative_sources") or []
        related_events = _query_related_pfsense_events(
            cur,
            {
                "event_types": ["firewall_block", "firewall_allow"],
                "source_ip": representative_sources[0] if representative_sources else None,
                "destination_ips": target_context.get("sample_destination_ips") or [],
                "destination_ports": target_context.get("sample_destination_ports") or [],
                "first_seen": detail.get("first_seen"),
                "last_seen": detail.get("last_seen"),
            },
            limit=SECTION_LIMITS["recon_related_events"],
        )
        related_events, related_truncation_source = _limit_list(
            related_events,
            SECTION_LIMITS["recon_related_events"],
            reason="Recon related event evidence exceeded AI context limit.",
        )
        compact_detail = _summarize_mapping(
            detail,
            [
                "id",
                "title",
                "label",
                "severity",
                "status",
                "confidence",
                "confidence_tier",
                "first_seen",
                "last_seen",
                "display",
                "story",
                "investigation_value",
                "summary",
                "related_incident_id",
            ],
            max_text_chars=700,
        )
        compact_events = [
            _summarize_mapping(
                event,
                [
                    "id",
                    "event_id",
                    "event_type",
                    "source_ip",
                    "destination_ip",
                    "destination_port",
                    "protocol",
                    "action",
                    "message",
                    "created_at",
                    "timestamp",
                ],
                max_text_chars=160,
            )
            for event in related_events
        ]
        data = {
            "recon_activity": compact_detail,
            "related_events": compact_events,
            "_evidence": _evidence_stats(
                included={"related_events": len(compact_events)},
            ),
        }
        data, truncated = _compact_payload(data, max_chars=9000)
        sources = [
                AiContextSource("recon_activity", f"/recon-activities/{activity_id}", [activity_id], _utc_now()),
                AiContextSource("events", f"/recon-activities/{activity_id}/related-events", [activity_id], _utc_now()),
            ]
        if related_truncation_source:
            sources.append(related_truncation_source)
        sources = _append_compaction_source(
            sources,
            truncated=truncated,
            reason="Recon activity context compacted before AI prompt construction.",
        )
        return AiContextPayload(
            context_type="recon_activity",
            data=data,
            sources=sources,
            insufficient_context=not _is_meaningful(detail),
            insufficient_reason=None if _is_meaningful(detail) else "No recon activity context available.",
            truncated=truncated,
        )
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def _build_visible_context(
    context_type: str,
    context: dict[str, Any],
    config: AiGatewayConfig,
) -> AiContextPayload:
    data = {
        "visible_filters": context.get("visible_filters") or context.get("dashboard_filters") or {},
        "dashboard_summary": context.get("dashboard_summary") or context.get("summary") or {},
        "timeline": (context.get("timeline") or [])[:SECTION_LIMITS["timeline"]],
        "top_source_ips": (context.get("top_source_ips") or [])[:SECTION_LIMITS["recent_alerts"]],
        "map_markers": (context.get("map_markers") or [])[:SECTION_LIMITS["recent_alerts"]],
        "recent_alerts": (context.get("recent_alerts") or context.get("alerts") or [])[:SECTION_LIMITS["recent_alerts"]],
        "active_section": context.get("active_section"),
    }
    data, truncated = _compact_payload(data, max_chars=max(config.max_prompt_chars // 2, 2000))
    return AiContextPayload(
        context_type=context_type,
        data=data,
        sources=[AiContextSource("dashboard", "/alerts/summary", [], _utc_now(), truncated=truncated)],
        insufficient_context=not _is_meaningful(data),
        insufficient_reason="No visible dashboard context available.",
        truncated=truncated,
    )


def _build_response_registry_context(context: dict[str, Any]) -> AiContextPayload:
    registry_id = _required_int(context, "registry_id", "id")
    conn = None
    try:
        conn = get_db_connection()
        detail = get_registry_detail(conn, registry_id)
        if detail is None:
            raise AiContextNotFoundError("Registry record not found")
        registry_record = detail.get("record") if isinstance(detail, dict) and isinstance(detail.get("record"), dict) else detail
        data = {
            "response_registry": _summarize_mapping(
                registry_record,
                [
                    "id",
                    "indicator_type",
                    "indicator_value",
                    "source_ip",
                    "status",
                    "action",
                    "disposition",
                    "severity",
                    "confidence",
                    "created_at",
                    "updated_at",
                    "last_seen",
                    "response_state",
                    "latest_outcome",
                    "cooldown",
                    "evidence",
                ],
                max_text_chars=1000,
            )
        }
        data, truncated = _compact_payload(data, max_chars=6000)
        sources = _append_compaction_source(
            [AiContextSource("response_registry", f"/response-registry/{registry_id}", [registry_id], _utc_now())],
            truncated=truncated,
            reason="Response registry context compacted before AI prompt construction.",
        )
        return AiContextPayload(
            context_type="response_registry",
            data=data,
            sources=sources,
            insufficient_context=not _is_meaningful(detail),
            insufficient_reason=None if _is_meaningful(detail) else "No response registry context available.",
            truncated=truncated,
        )
    finally:
        if conn is not None:
            conn.close()


def _build_detection_context(context: dict[str, Any], config: AiGatewayConfig) -> AiContextPayload:
    alert_id = _optional_int(context, "alert_id")
    rule_id = str(context.get("rule_id") or "").strip()
    if alert_id is None and not rule_id:
        raise AiContextValidationError("alert_id or rule_id is required")

    data: dict[str, Any] = {}
    sources: list[AiContextSource] = []
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        if alert_id is not None:
            cur = conn.cursor()
            cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (alert_id,))
            row = cur.fetchone()
            if row is None:
                raise AiContextNotFoundError("Alert not found")
            cooldown = _fetch_latest_resolved_audits(cur, [alert_id])
            data["why_fired"] = _build_pfsense_why_fired_payload(row, cooldown)
            data["alert_detection_metadata"] = {
                "alert_id": row[0],
                "alert_type": row[1],
                "severity": row[2],
                "message": row[3],
                "source": row[17] or "unknown",
                "source_type": row[18] or "legacy",
                "context": row[19] if isinstance(row[19], dict) else {},
            }
            sources.append(AiContextSource("detection", f"/alerts/{alert_id}/why-fired", [alert_id], _utc_now()))
        try:
            matrix = build_severity_response_matrix(conn)
            data["severity_response_matrix"] = matrix
            sources.append(AiContextSource("detection", "/api/severity-response-matrix", [], _utc_now()))
        except Exception:
            data["severity_response_matrix"] = None
        if rule_id:
            data["rule_id"] = rule_id
        data, truncated = _compact_payload(data, max_chars=max(config.max_prompt_chars // 2, 2000))
        return AiContextPayload(
            context_type="detection",
            data=data,
            sources=sources or [AiContextSource("detection", "core.ai.context_builder", [rule_id], _utc_now())],
            insufficient_context=not _is_meaningful(data),
            insufficient_reason="No detection context available.",
            truncated=truncated,
        )
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


def _build_general_context(
    context: dict[str, Any],
    config: AiGatewayConfig,
    *,
    question: str | None,
    client_history: list[dict[str, Any]] | None,
) -> AiContextPayload:
    history = []
    if isinstance(client_history, list):
        for item in client_history[-SECTION_LIMITS["chat_history"]:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                history.append({"role": role, "content": content[:1000]})
    data = {
        "question": str(question or "").strip(),
        "visible_context": context,
        "client_history": history,
    }
    data, truncated = _compact_payload(data, max_chars=max(config.max_prompt_chars // 2, 2000))
    return AiContextPayload(
        context_type="general",
        data=data,
        sources=[AiContextSource("visible_context", "frontend_visible_context", [], _utc_now(), truncated=truncated)],
        insufficient_context=not _is_meaningful(context),
        insufficient_reason="No visible SIEM context was supplied.",
        truncated=truncated,
    )
