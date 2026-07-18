from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import re
import time
from typing import Any

from core.ai.config import AiGatewayConfig
from core.ai.context_builder import build_ai_context
from core.ai.soc_tools import (
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_TIME_WINDOW_HOURS,
    DEFAULT_TOOL_LIMIT,
    MAX_TIME_WINDOW_HOURS,
    TOOL_DEFINITIONS,
    TOOL_STATUS_FAILED,
    TOOL_STATUS_FORBIDDEN,
    TOOL_STATUS_NOT_FOUND,
    TOOL_STATUS_SUCCESS,
    TOOL_STATUS_TRUNCATED,
    TOOL_STATUS_UNSUPPORTED,
    TOOL_STATUS_VALIDATION_ERROR,
    SocToolExecutionSummary,
    SocToolResult,
    SocToolSource,
    SocToolValidationError,
    redact_sensitive_values,
    role_can_use_tool,
    utc_now,
    validate_tool_args,
    validate_tool_name,
)
from core.db import get_db_connection
from core.incident_store import get_incident_detail, list_incidents
from core.indicator_response_registry import get_registry_detail, list_registry_records
from core.pfsense_operational_baseline import normalize_operational_scope
from core.playbook_store import list_playbook_executions
from core.soar_response_outcomes import (
    get_latest_outcomes_for_incidents_bulk,
    get_latest_outcomes_for_playbook_executions_bulk,
    serialize_incident_outcome_timeline_entries,
)
from routes.alerts_events_routes import (
    _ALERT_SELECT,
    _build_alert_filter_sql,
    _build_alert_order_clause,
    _build_alert_payload,
    _build_alerts_where_clause,
    _fetch_alert_intelligence,
    _fetch_alert_rows,
    _fetch_alert_total,
    _fetch_latest_resolved_audits,
    _query_related_pfsense_events,
)
from routes.incident_routes import VALID_SEVERITIES, build_readonly_incident_timeline
from routes.playbook_routes import _serialize_execution_dict

_LOGGER = logging.getLogger(__name__)

_ALERT_SORT_OPTIONS = frozenset({"newest", "oldest", "severity"})
_EVENT_SOURCES = frozenset({"bank_app", "web_log", "azure", "otlp", "pfsense", "honeypot"})
_PLAYBOOK_STATUSES = frozenset(
    {
        "pending",
        "running",
        "awaiting_approval",
        "success",
        "failed",
        "abandoned",
        "permanently_failed",
        "not_actioned",
    }
)
_INCIDENT_STATUSES = frozenset({"open", "investigating", "resolved", "closed"})


@dataclass(frozen=True)
class SocToolPlan:
    calls: list[dict[str, Any]]
    reason: str | None = None


def should_skip_tools_for_gateway(config: AiGatewayConfig) -> bool:
    if not config.mode_valid or config.mode == "disabled":
        return True
    if config.mode == "local_only" and not config.local_configured:
        return True
    return False


def build_deterministic_tool_plan(
    *,
    question: str,
    context_type: str,
    context: dict[str, Any],
    tool_policy: dict[str, Any] | None = None,
) -> SocToolPlan:
    policy = tool_policy if isinstance(tool_policy, dict) else {}
    explicit = policy.get("tool_requests")
    if isinstance(explicit, list):
        return SocToolPlan(calls=[item for item in explicit if isinstance(item, dict)], reason="client_requested")

    text = f"{question} {json.dumps(context, default=str)}".lower()
    calls: list[dict[str, Any]] = []
    source_ip = _first_present(context, "source_ip", "selected_source_ip")
    alert_id = _first_present(context, "alert_id", "selected_alert_id")
    incident_id = _first_present(context, "incident_id", "selected_incident_id")
    registry_id = _first_present(context, "registry_id", "selected_registry_id")

    ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", question or "")
    if not source_ip and ip_match:
        source_ip = ip_match.group(0)

    if context_type == "alert" and alert_id:
        calls.append({"tool_name": "get_alert_detail", "arguments": {"alert_id": alert_id}})
        calls.append({"tool_name": "get_related_events", "arguments": {"alert_id": alert_id}})
    elif context_type == "incident" and incident_id:
        calls.append({"tool_name": "get_incident_timeline", "arguments": {"incident_id": incident_id}})
    elif context_type == "source_ip" and source_ip:
        calls.append({"tool_name": "get_source_ip_context", "arguments": {"source_ip": source_ip}})
        calls.append({"tool_name": "get_related_events", "arguments": {"source_ip": source_ip}})
    elif context_type == "response_registry" and registry_id:
        calls.append({"tool_name": "get_response_registry_context", "arguments": {"registry_id": registry_id}})

    if source_ip and any(word in text for word in ("everything", "tied", "source", "ip", "recon", "campaign")):
        calls.extend(
            [
                {"tool_name": "get_source_ip_context", "arguments": {"source_ip": source_ip}},
                {"tool_name": "search_alerts", "arguments": {"source_ip": source_ip}},
                {"tool_name": "get_related_events", "arguments": {"source_ip": source_ip}},
                {"tool_name": "get_response_registry_context", "arguments": {"source_ip": source_ip}},
            ]
        )
    if "incident" in text and not incident_id:
        calls.append({"tool_name": "search_incidents", "arguments": {}})
    if "playbook" in text or "response" in text:
        calls.append({"tool_name": "list_playbook_executions", "arguments": {}})
    if "audit" in text:
        calls.append({"tool_name": "read_audit_log", "arguments": {}})
    if not calls:
        calls.append({"tool_name": "search_alerts", "arguments": {}})

    return SocToolPlan(calls=_dedupe_calls(calls), reason="deterministic")


def execute_tool_plan(
    plan: SocToolPlan | list[dict[str, Any]],
    *,
    actor_role: str | None,
    config: AiGatewayConfig,
    tool_policy: dict[str, Any] | None = None,
) -> SocToolExecutionSummary:
    raw_calls = plan.calls if isinstance(plan, SocToolPlan) else plan
    policy = tool_policy if isinstance(tool_policy, dict) else {}
    max_calls = _bounded_positive_int(
        policy.get("max_tool_calls"),
        default=DEFAULT_MAX_TOOL_CALLS,
        maximum=DEFAULT_MAX_TOOL_CALLS,
    )
    calls: list[SocToolResult] = []
    sources: list[SocToolSource] = []
    truncated = False
    omitted_count = 0

    for index, raw_call in enumerate(raw_calls):
        if index >= max_calls:
            truncated = True
            omitted_count += 1
            continue
        result = execute_tool(raw_call, actor_role=actor_role, config=config)
        calls.append(result)
        sources.extend(result.sources)

    return SocToolExecutionSummary(
        used=bool(raw_calls),
        calls=calls,
        sources=sources,
        truncated=truncated or any(call.truncated for call in calls),
        omitted_count=omitted_count + sum(call.omitted_count for call in calls),
        error_code=_summary_error_code(calls),
    )


def execute_tool(
    raw_call: dict[str, Any],
    *,
    actor_role: str | None,
    config: AiGatewayConfig,
) -> SocToolResult:
    started = time.monotonic()
    tool_name = str(raw_call.get("tool_name") or raw_call.get("name") or "").strip().lower()
    try:
        tool_name = validate_tool_name(tool_name)
        if not role_can_use_tool(actor_role, tool_name):
            return _result(
                tool_name,
                TOOL_STATUS_FORBIDDEN,
                started=started,
                error="Tool is not allowed for this role.",
                error_code=TOOL_STATUS_FORBIDDEN,
            )
        args = validate_tool_args(tool_name, raw_call.get("arguments") or raw_call.get("args") or {})
        return _execute_validated_tool(tool_name, args, config=config, started=started)
    except SocToolValidationError as error:
        status = TOOL_STATUS_UNSUPPORTED if error.error_code == TOOL_STATUS_UNSUPPORTED else TOOL_STATUS_VALIDATION_ERROR
        return _result(
            tool_name or "unknown",
            status,
            started=started,
            error=str(error),
            error_code=error.error_code,
        )
    except Exception:
        _LOGGER.exception("soc_read_tool_failed tool=%s", tool_name or "unknown")
        return _result(
            tool_name or "unknown",
            TOOL_STATUS_FAILED,
            started=started,
            error="SOC read tool failed.",
            error_code=TOOL_STATUS_FAILED,
        )


def tool_summary_for_prompt(summary: SocToolExecutionSummary, *, max_chars: int) -> dict[str, Any]:
    payload = summary.as_dict()
    redacted = redact_sensitive_values(payload)
    text = json.dumps(redacted, default=str, sort_keys=True, separators=(",", ":"))
    if len(text) <= max_chars:
        return redacted
    return {
        "used": summary.used,
        "read_only": True,
        "truncated": True,
        "omitted_count": summary.omitted_count,
        "sources": [source.as_dict() for source in summary.sources],
        "summary": "Tool evidence exceeded prompt budget and was compacted.",
        "preview": text[: max(0, max_chars - 120)],
    }


def _execute_validated_tool(
    tool_name: str,
    args: dict[str, Any],
    *,
    config: AiGatewayConfig,
    started: float,
) -> SocToolResult:
    if tool_name == "search_alerts":
        return _execute_search_alerts(args, started=started)
    if tool_name == "get_alert_detail":
        return _context_tool_result(
            tool_name,
            "alert",
            {"alert_id": args["alert_id"]},
            config=config,
            started=started,
        )
    if tool_name == "get_related_events":
        return _execute_get_related_events(args, started=started)
    if tool_name == "get_source_ip_context":
        return _context_tool_result(tool_name, "source_ip", args, config=config, started=started)
    if tool_name == "search_incidents":
        return _execute_search_incidents(args, started=started)
    if tool_name == "get_incident_timeline":
        return _execute_incident_timeline(args, started=started)
    if tool_name == "list_playbook_executions":
        return _execute_playbook_executions(args, started=started)
    if tool_name == "read_audit_log":
        return _execute_read_audit_log(args, started=started)
    if tool_name == "get_response_registry_context":
        return _execute_response_registry_context(args, config=config, started=started)
    raise SocToolValidationError(f"Unsupported SOC read tool: {tool_name}", error_code=TOOL_STATUS_UNSUPPORTED)


def _execute_search_alerts(args: dict[str, Any], *, started: float) -> SocToolResult:
    if args.get("sort") not in _ALERT_SORT_OPTIONS:
        raise SocToolValidationError("sort is unsupported")
    filters = {
        "search": args.get("search"),
        "exact_source_ip": args.get("source_ip"),
        "exact_target_ip": None,
        "alert_id": None,
        "severity": args.get("severity"),
        "status": args.get("status"),
        "source": args.get("source"),
        "sort": args.get("sort") or "newest",
        "operational_scope": "all_history",
    }
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        clauses, params = _build_alert_filter_sql(filters)
        where_clause = _build_alerts_where_clause(clauses)
        order_clause = _build_alert_order_clause(filters["sort"])
        total = _fetch_alert_total(cur, where_clause, params)
        rows = _fetch_alert_rows(
            cur,
            where_clause,
            order_clause,
            params,
            limit=args["limit"],
            offset=args["offset"],
        )
        cooldown = _fetch_latest_resolved_audits(cur, [row[0] for row in rows])
        intelligence = _fetch_alert_intelligence(conn, rows)
        items = [
            _build_alert_payload(
                row,
                cur=cur,
                reputation_by_ip={},
                response_outcome=None,
                cooldown_by_alert_id=cooldown,
                intelligence=intelligence.get(int(row[0])),
            )
            for row in rows
        ]
        truncated = total > len(items)
        return _result(
            "search_alerts",
            TOOL_STATUS_SUCCESS,
            data={"items": items, "total": total, "limit": args["limit"], "offset": args["offset"]},
            sources=[_source("search_alerts", "alerts", "/alerts", "routes.alerts_events_routes alert list helpers")],
            truncated=truncated,
            omitted_count=max(0, total - len(items) - args["offset"]),
            started=started,
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _execute_get_related_events(args: dict[str, Any], *, started: float) -> SocToolResult:
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if args.get("alert_id"):
            cur.execute(f"{_ALERT_SELECT} WHERE id = %s", (args["alert_id"],))
            row = cur.fetchone()
            if row is None:
                return _result("get_related_events", TOOL_STATUS_NOT_FOUND, started=started, error="Alert not found")
            context = row[19] if isinstance(row[19], dict) else {}
            related_filter = context.get("related_event_filter") if isinstance(context.get("related_event_filter"), dict) else {}
            events = _query_related_pfsense_events(cur, related_filter, limit=args["limit"])
            return _result(
                "get_related_events",
                TOOL_STATUS_SUCCESS,
                data={"events": events, "count": len(events)},
                sources=[_source("get_related_events", "events", f"/alerts/{args['alert_id']}/related-events", "routes.alerts_events_routes._query_related_pfsense_events", [args["alert_id"]])],
                started=started,
            )
        if args.get("source_ip"):
            events = _search_events_by_filters(cur, args)
            return _result(
                "get_related_events",
                TOOL_STATUS_SUCCESS,
                data={"events": events, "count": len(events)},
                sources=[_source("get_related_events", "events", "/events/search", "routes.alerts_events_routes search_events semantics", [args["source_ip"]])],
                started=started,
            )
        if args.get("activity_id"):
            ai_context = build_ai_context(
                context_type="recon_activity",
                context={"activity_id": args["activity_id"]},
                config=_minimal_config(),
            )
            events = ai_context.data.get("related_events") if isinstance(ai_context.data, dict) else []
            return _result(
                "get_related_events",
                TOOL_STATUS_SUCCESS,
                data={"events": events or [], "count": len(events or [])},
                sources=[_source("get_related_events", "events", f"/recon-activities/{args['activity_id']}/related-events", "core.ai.context_builder recon_activity context", [args["activity_id"]])],
                started=started,
            )
        return _result("get_related_events", TOOL_STATUS_VALIDATION_ERROR, started=started, error="No event scope supplied")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _execute_search_incidents(args: dict[str, Any], *, started: float) -> SocToolResult:
    status = args.get("status")
    if status and status not in _INCIDENT_STATUSES:
        raise SocToolValidationError("status is unsupported")
    severity = args.get("severity")
    if severity and severity not in VALID_SEVERITIES:
        raise SocToolValidationError("severity is unsupported")
    try:
        operational_scope = normalize_operational_scope(args.get("operational_scope"))
    except ValueError as error:
        raise SocToolValidationError("operational_scope is unsupported") from error

    conn = None
    try:
        conn = get_db_connection()
        incidents = list_incidents(
            conn,
            status=status,
            severity=severity,
            operational_scope=operational_scope,
            limit=args["limit"],
            offset=args["offset"],
        )
        outcomes = get_latest_outcomes_for_incidents_bulk(conn, [incident["id"] for incident in incidents])
        for incident in incidents:
            incident["response_outcome"] = outcomes.get(incident["id"])
        return _result(
            "search_incidents",
            TOOL_STATUS_SUCCESS,
            data={"incidents": incidents, "count": len(incidents), "limit": args["limit"]},
            sources=[_source("search_incidents", "incidents", "/incidents", "core.incident_store.list_incidents")],
            started=started,
        )
    finally:
        if conn:
            conn.close()


def _execute_incident_timeline(args: dict[str, Any], *, started: float) -> SocToolResult:
    incident_id = args["incident_id"]
    conn = None
    try:
        conn = get_db_connection()
        incident = get_incident_detail(conn, incident_id)
        if incident is None:
            return _result("get_incident_timeline", TOOL_STATUS_NOT_FOUND, started=started, error="Incident not found")
        timeline = build_readonly_incident_timeline(conn, incident_id) or {"timeline": []}
        outcome_entries = serialize_incident_outcome_timeline_entries(conn, incident_id)
        if outcome_entries:
            timeline["timeline"].extend(outcome_entries)
            timeline["timeline"].sort(key=lambda entry: entry.get("timestamp") or "")
        return _result(
            "get_incident_timeline",
            TOOL_STATUS_SUCCESS,
            data={"incident": incident, "timeline": timeline},
            sources=[_source("get_incident_timeline", "incident_timeline", f"/incidents/{incident_id}/timeline", "routes.incident_routes.build_readonly_incident_timeline", [incident_id])],
            started=started,
        )
    finally:
        if conn:
            conn.close()


def _execute_playbook_executions(args: dict[str, Any], *, started: float) -> SocToolResult:
    status = args.get("status")
    if status and status not in _PLAYBOOK_STATUSES:
        raise SocToolValidationError("status is unsupported")
    conn = None
    try:
        conn = get_db_connection()
        rows = list_playbook_executions(
            conn,
            playbook_id=args.get("playbook_id"),
            status=status,
            limit=args["limit"],
        )
        outcomes = get_latest_outcomes_for_playbook_executions_bulk(conn, [row["id"] for row in rows])
        items = [_serialize_execution_dict(row, response_outcome=outcomes.get(row["id"])) for row in rows]
        return _result(
            "list_playbook_executions",
            TOOL_STATUS_SUCCESS,
            data={"items": items, "count": len(items), "limit": args["limit"]},
            sources=[_source("list_playbook_executions", "playbook_executions", "/playbook-executions", "core.playbook_store.list_playbook_executions")],
            started=started,
        )
    finally:
        if conn:
            conn.close()


def _execute_read_audit_log(args: dict[str, Any], *, started: float) -> SocToolResult:
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                event_type,
                actor_username,
                actor_role,
                target_username,
                target_alert_id,
                request_path,
                source_ip,
                created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (args["limit"],),
        )
        events = [
            {
                "event_type": row[0],
                "actor_username": row[1],
                "actor_role": row[2],
                "target_username": row[3],
                "target_alert_id": row[4],
                "request_path": row[5],
                "source_ip": str(row[6]) if row[6] is not None else None,
                "created_at": row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7]),
            }
            for row in cur.fetchall()
        ]
        return _result(
            "read_audit_log",
            TOOL_STATUS_SUCCESS,
            data={"events": events, "count": len(events), "limit": args["limit"]},
            sources=[_source("read_audit_log", "audit_log", "/admin/audit-log", "routes.admin_routes.list_audit_log semantics")],
            started=started,
        )
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def _execute_response_registry_context(
    args: dict[str, Any],
    *,
    config: AiGatewayConfig,
    started: float,
) -> SocToolResult:
    registry_id = args.get("registry_id")
    if registry_id is not None:
        ai_context = build_ai_context(
            context_type="response_registry",
            context={"registry_id": registry_id},
            config=config,
        )
        return _context_result_from_payload("get_response_registry_context", ai_context, started=started)

    source_ip = args.get("source_ip")
    conn = None
    try:
        conn = get_db_connection()
        payload = list_registry_records(
            conn,
            exact_indicator_value=source_ip,
            limit=args["limit"],
            offset=0,
        )
        return _result(
            "get_response_registry_context",
            TOOL_STATUS_SUCCESS,
            data=payload,
            sources=[
                _source(
                    "get_response_registry_context",
                    "response_registry",
                    "/response-registry",
                    "core.indicator_response_registry.list_registry_records",
                    [source_ip],
                )
            ],
            started=started,
        )
    finally:
        if conn:
            conn.close()


def _context_tool_result(
    tool_name: str,
    context_type: str,
    context: dict[str, Any],
    *,
    config: AiGatewayConfig,
    started: float,
) -> SocToolResult:
    ai_context = build_ai_context(context_type=context_type, context=context, config=config)
    return _context_result_from_payload(tool_name, ai_context, started=started)


def _context_result_from_payload(tool_name: str, ai_context, *, started: float) -> SocToolResult:
    data = ai_context.data if isinstance(ai_context.data, dict) else {}
    sources = [
        SocToolSource(
            tool_name=tool_name,
            source_type=source.source_type,
            source_path=source.source_path,
            source_helper="core.ai.context_builder",
            record_ids=list(source.record_ids),
            generated_at=source.generated_at,
            status=TOOL_STATUS_SUCCESS,
            truncated=source.truncated,
            omitted_count=source.omitted_count,
        )
        for source in ai_context.sources
    ]
    status = TOOL_STATUS_TRUNCATED if ai_context.truncated else TOOL_STATUS_SUCCESS
    return _result(
        tool_name,
        status,
        data=data,
        sources=sources,
        truncated=ai_context.truncated,
        omitted_count=ai_context.omitted_count,
        started=started,
    )


def _search_events_by_filters(cur, args: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if args.get("source_ip"):
        clauses.append("source_ip = %s")
        params.append(args["source_ip"])
    if args.get("source"):
        if args["source"] not in _EVENT_SOURCES:
            raise SocToolValidationError("source is unsupported")
        clauses.append("source = %s")
        params.append(args["source"])
    if args.get("event_type"):
        clauses.append("event_type = %s")
        params.append(args["event_type"])
    clauses.append("created_at >= %s")
    params.append(datetime.now(timezone.utc) - timedelta(hours=DEFAULT_TIME_WINDOW_HOURS))
    query = """
        SELECT id, event_type, severity, source_ip, message, app_name,
               environment, source, source_type, raw_payload, created_at
        FROM events
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY id DESC LIMIT %s"
    params.append(args["limit"])
    cur.execute(query, tuple(params))
    return [
        {
            "id": row[0],
            "event_type": row[1],
            "severity": row[2],
            "source_ip": str(row[3]) if row[3] is not None else None,
            "message": row[4],
            "app_name": row[5],
            "environment": row[6],
            "source": row[7],
            "source_type": row[8],
            "raw_payload": row[9],
            "created_at": row[10].isoformat() if hasattr(row[10], "isoformat") else str(row[10]),
        }
        for row in cur.fetchall()
    ]


def _result(
    tool_name: str,
    status: str,
    *,
    started: float,
    data: Any = None,
    sources: list[SocToolSource] | None = None,
    truncated: bool = False,
    omitted_count: int = 0,
    error_code: str | None = None,
    error: str | None = None,
) -> SocToolResult:
    return SocToolResult(
        tool_name=tool_name,
        status=status,
        data=redact_sensitive_values(data),
        sources=sources or [],
        truncated=truncated,
        omitted_count=omitted_count,
        latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        error_code=error_code or (None if status == TOOL_STATUS_SUCCESS else status),
        error=error,
        read_only=True,
    )


def _source(
    tool_name: str,
    source_type: str,
    source_path: str,
    source_helper: str,
    record_ids: list[int | str] | None = None,
) -> SocToolSource:
    return SocToolSource(
        tool_name=tool_name,
        source_type=source_type,
        source_path=source_path,
        source_helper=source_helper,
        record_ids=record_ids or [],
        generated_at=utc_now(),
        status=TOOL_STATUS_SUCCESS,
    )


def _first_present(context: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = context.get(name)
        if value not in (None, ""):
            return value
    visible = context.get("visible_context") if isinstance(context.get("visible_context"), dict) else {}
    for name in names:
        value = visible.get(name)
        if value not in (None, ""):
            return value
    return None


def _dedupe_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for call in calls:
        key = json.dumps(call, default=str, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(call)
    return unique


def _bounded_positive_int(value: Any, *, default: int, maximum: int) -> int:
    if value in (None, ""):
        return min(default, maximum)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return min(default, maximum)
    return max(1, min(parsed, maximum))


def _summary_error_code(calls: list[SocToolResult]) -> str | None:
    failures = [call.error_code or call.status for call in calls if call.status != TOOL_STATUS_SUCCESS]
    return failures[0] if failures else None


def _minimal_config() -> AiGatewayConfig:
    from core.ai.config import load_ai_gateway_config

    return load_ai_gateway_config()


def normalize_tool_policy(raw_policy: Any) -> dict[str, Any]:
    policy = raw_policy if isinstance(raw_policy, dict) else {}
    return {
        "max_tool_calls": _bounded_positive_int(
            policy.get("max_tool_calls"),
            default=DEFAULT_MAX_TOOL_CALLS,
            maximum=DEFAULT_MAX_TOOL_CALLS,
        ),
        "time_window_hours": _bounded_positive_int(
            policy.get("time_window_hours"),
            default=DEFAULT_TIME_WINDOW_HOURS,
            maximum=MAX_TIME_WINDOW_HOURS,
        ),
        "tool_requests": policy.get("tool_requests") if isinstance(policy.get("tool_requests"), list) else None,
    }


__all__ = [
    "SocToolPlan",
    "TOOL_DEFINITIONS",
    "build_deterministic_tool_plan",
    "execute_tool",
    "execute_tool_plan",
    "normalize_tool_policy",
    "should_skip_tools_for_gateway",
    "tool_summary_for_prompt",
]
