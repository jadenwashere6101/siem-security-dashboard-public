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

SECTION_LIMITS = {
    "recent_alerts": 10,
    "related_events": 15,
    "timeline": 30,
    "source_ip_outcomes": 10,
    "recon_related_events": 15,
    "chat_history": 8,
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
    value = str(context_type or "").strip().lower()
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
    return {
        "summary": "Context was too large and was compacted before AI prompt construction.",
        "preview": text[: max(0, max_chars - 120)],
    }, True


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
            "alert": alert,
            "why_fired": why_fired,
            "related_events": related_events,
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
        return AiContextPayload(
            context_type="incident",
            data={"incident": incident, "timeline": timeline},
            sources=sources,
            insufficient_context=not _is_meaningful(incident),
            insufficient_reason=None if _is_meaningful(incident) else "No incident context available.",
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

        data = {
            "source_ip": source_ip,
            "alerts": alerts,
            "incidents": incidents,
            "queue": queue,
            "blocklist": blocklist,
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
            "playbook_executions": playbook_executions,
            "returning_attacker": returning_attacker,
            "campaigns": campaigns,
            "response_outcomes": response_outcomes,
            "response_outcome_counts": response_outcome_counts,
        }
        return AiContextPayload(
            context_type="source_ip",
            data=data,
            sources=[AiContextSource("source_ip", "/source-ip-context", [source_ip], _utc_now())],
            insufficient_context=not _is_meaningful(
                {
                    "alerts": alerts,
                    "incidents": incidents,
                    "queue": queue,
                    "blocklist": blocklist,
                    "response_outcomes": response_outcomes,
                    "campaigns": campaigns,
                }
            ),
            insufficient_reason="No meaningful source-IP context available.",
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
        return AiContextPayload(
            context_type="recon_activity",
            data={"recon_activity": detail, "related_events": related_events},
            sources=[
                AiContextSource("recon_activity", f"/recon-activities/{activity_id}", [activity_id], _utc_now()),
                AiContextSource("events", f"/recon-activities/{activity_id}/related-events", [activity_id], _utc_now()),
            ],
            insufficient_context=not _is_meaningful(detail),
            insufficient_reason=None if _is_meaningful(detail) else "No recon activity context available.",
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
        return AiContextPayload(
            context_type="response_registry",
            data={"response_registry": detail},
            sources=[AiContextSource("response_registry", f"/response-registry/{registry_id}", [registry_id], _utc_now())],
            insufficient_context=not _is_meaningful(detail),
            insufficient_reason=None if _is_meaningful(detail) else "No response registry context available.",
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
