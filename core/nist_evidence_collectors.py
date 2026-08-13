"""Bounded deterministic collectors for the NIST evidence v1 catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from core.nist_evidence_catalog import V1_MAPPINGS
from core.nist_evidence_engine import (
    CONFIDENCE_UNKNOWN,
    EvidenceBundle,
    EvidenceReference,
    classify_operational_record,
    classify_soar_outcome,
    deterministic_query_hash,
    validate_window,
)
from core.synthetic_data_policy import (
    SYNTHETIC_PROVENANCE_VALUES,
    build_operational_source_ip_exclusion_sql,
    build_synthetic_json_value_sql,
    load_synthetic_source_ip_exclusions,
)


DEFAULT_REFERENCE_LIMIT = 25
MAX_REFERENCE_LIMIT = 100

AUTHENTICATION_ALERT_TYPES = (
    "failed_login_threshold",
    "password_spraying_threshold",
    "successful_login_after_spray",
)


@dataclass(frozen=True)
class CollectorContext:
    source_ids: tuple[str, ...]
    environments: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    collected_at: datetime
    source_health_snapshot: dict[str, Any]
    reference_limit: int = DEFAULT_REFERENCE_LIMIT


def _source_health_map(snapshot: dict[str, Any]) -> dict[str, str]:
    result = {}
    for item in snapshot.get("sources", []):
        if not isinstance(item, dict) or not item.get("source"):
            continue
        status = item.get("health_status")
        if status not in {"healthy", "degraded", "unknown"}:
            status = item.get("connector_status")
        result[item["source"]] = (
            "healthy" if status == "healthy"
            else "degraded" if status in {"degraded", "failed"}
            else "unknown"
        )
    return result


def _safe_limit(value: int) -> int:
    return max(1, min(int(value), MAX_REFERENCE_LIMIT))


def _filters(context: CollectorContext, **extra: Any) -> dict[str, Any]:
    return {
        "source_ids": list(context.source_ids),
        "environments": list(context.environments),
        "window_start": context.window_start.isoformat(),
        "window_end": context.window_end.isoformat(),
        **extra,
    }


def _operational_ip_sql(column: str) -> tuple[str, list[Any]]:
    excluded_ips, excluded_networks = load_synthetic_source_ip_exclusions()
    clauses = [f"({column} IS NULL OR host({column}) <> ALL(%s))"]
    params: list[Any] = [sorted(excluded_ips)]
    clauses.append(f"({column} IS NULL OR NOT ({column} <<= ANY(%s::cidr[])))")
    params.append(sorted(excluded_networks))
    return " AND ".join(clauses), params


def _collect_rows(
    cur,
    *,
    category: str,
    evidence_type: str,
    query: str,
    params: list[Any],
    context: CollectorContext,
    filter_metadata: dict[str, Any],
    row_classifier: Callable[[tuple], str] | None = None,
    limitation: str | None = None,
) -> EvidenceBundle:
    limit = _safe_limit(context.reference_limit)
    cur.execute(query, tuple([*params, limit]))
    rows = cur.fetchall()
    total = int(rows[0][8]) if rows else 0
    health = _source_health_map(context.source_health_snapshot)
    query_hash = deterministic_query_hash(category, filter_metadata)
    references = []
    for row in rows:
        source = row[1]
        classification = row_classifier(row) if row_classifier else classify_operational_record(
            source_ip=str(row[3]) if row[3] is not None else None,
            provenance=row[7],
            record_id=int(row[0]) if row[0] is not None and str(row[0]).isdigit() else None,
            entity_type=row[9],
        )
        references.append(
            EvidenceReference(
                evidence_category=category,
                evidence_type=evidence_type,
                entity_type=row[9],
                entity_id=str(row[0]),
                canonical_source=source,
                source_type=row[2],
                occurrence_timestamp=row[4],
                ingestion_timestamp=row[5],
                collection_timestamp=context.collected_at,
                window_start=context.window_start,
                window_end=context.window_end,
                source_health_state=health.get(source, CONFIDENCE_UNKNOWN),
                operational_classification=classification,
                query_hash=query_hash,
                summary=str(row[6])[:240],
                metadata={
                    "occurrence_timestamp_available": row[4] is not None,
                    "collector_completed": True,
                },
            )
        )
    return EvidenceBundle(
        category=category,
        evidence_count=total,
        references=tuple(references),
        omitted_count=max(total - len(references), 0),
        limitation=limitation,
    )


def _event_collector(
    cur,
    context: CollectorContext,
    *,
    category: str,
    event_type: str | None = None,
    source_ids: tuple[str, ...] | None = None,
    require_occurrence: bool = False,
) -> EvidenceBundle:
    selected_sources = tuple(sorted(set(source_ids or context.source_ids) & set(context.source_ids)))
    if not selected_sources:
        return EvidenceBundle(category, 0, reason_code="source_not_in_boundary")
    clauses = [
        "source = ANY(%s)",
        "((event_timestamp IS NOT NULL AND event_timestamp >= %s AND event_timestamp <= %s) "
        "OR (event_timestamp IS NULL AND created_at >= %s AND created_at <= %s))",
    ]
    params: list[Any] = [
        list(selected_sources), context.window_start, context.window_end,
        context.window_start, context.window_end,
    ]
    if context.environments:
        clauses.append("environment = ANY(%s)")
        params.append(list(context.environments))
    if event_type:
        clauses.append("event_type = %s")
        params.append(event_type)
    if require_occurrence:
        clauses.append("event_timestamp IS NOT NULL")
    operational_sql, operational_params = build_operational_source_ip_exclusion_sql(
        context_column="raw_payload"
    )
    clauses.append(operational_sql)
    params.extend(operational_params)
    where_sql = " AND ".join(f"({clause})" for clause in clauses)
    query = f"""
        SELECT id, source, source_type, source_ip, event_timestamp, created_at,
               'event type=' || event_type || '; severity=' || severity,
               COALESCE(raw_payload->>'data_provenance', raw_payload->>'telemetry_provenance', ''),
               COUNT(*) OVER(), 'event'
        FROM events
        WHERE {where_sql}
        ORDER BY COALESCE(event_timestamp, created_at) DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur,
        category=category,
        evidence_type="normalized_event",
        query=query,
        params=params,
        context=context,
        filter_metadata=_filters(
            context, selected_sources=selected_sources, event_type=event_type,
            require_occurrence=require_occurrence,
        ),
        limitation=(
            "Only events with originating occurrence timestamps are counted."
            if require_occurrence else
            "The collection window uses occurrence time when available and separately labels ingestion-time fallback."
        ),
    )


def _alert_collector(
    cur,
    context: CollectorContext,
    *,
    category: str,
    alert_types: tuple[str, ...] | None = None,
    source_ids: tuple[str, ...] | None = None,
) -> EvidenceBundle:
    selected_sources = tuple(sorted(set(source_ids or context.source_ids) & set(context.source_ids)))
    if not selected_sources:
        return EvidenceBundle(category, 0, reason_code="source_not_in_boundary")
    clauses = ["source = ANY(%s)", "created_at >= %s", "created_at <= %s"]
    params: list[Any] = [list(selected_sources), context.window_start, context.window_end]
    if alert_types:
        clauses.append("alert_type = ANY(%s)")
        params.append(list(alert_types))
    operational_sql, operational_params = build_operational_source_ip_exclusion_sql(
        context_column="context"
    )
    clauses.append(operational_sql)
    params.extend(operational_params)
    query = f"""
        SELECT id, source, source_type, source_ip, created_at, created_at,
               'alert type=' || alert_type || '; severity=' || severity || '; status=' || status,
               COALESCE(context->>'data_provenance', context->>'telemetry_provenance', ''),
               COUNT(*) OVER(), 'alert'
        FROM alerts
        WHERE {' AND '.join(f'({clause})' for clause in clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category=category, evidence_type="security_alert", query=query,
        params=params, context=context,
        filter_metadata=_filters(
            context, selected_sources=selected_sources, alert_types=alert_types,
        ),
    )


def _detection_configuration(cur, context: CollectorContext) -> EvidenceBundle:
    query = """
        SELECT rule_id, NULL, NULL, NULL, updated_at, updated_at,
               'detection rule=' || rule_id || '; active=' || active::text,
               '', COUNT(*) OVER(), 'detection_rule'
        FROM detection_config
        WHERE active = TRUE
        ORDER BY rule_id
        LIMIT %s
    """
    return _collect_rows(
        cur, category="detection_configuration", evidence_type="detection_configuration",
        query=query, params=[], context=context,
        filter_metadata=_filters(context, active=True),
        limitation="Current detection configuration is not evidence of organizational event-selection review.",
    )


def _ingestion_health(cur, context: CollectorContext) -> EvidenceBundle:
    query = """
        SELECT connector_name, connector_name, NULL, NULL, last_processed_at, updated_at,
               'connector=' || connector_name || '; poll_status=' || COALESCE(last_poll_status, 'unknown'),
               '', COUNT(*) OVER(), 'ingestion_checkpoint'
        FROM ingestion_checkpoints
        WHERE connector_name = ANY(%s)
        ORDER BY connector_name
        LIMIT %s
    """
    return _collect_rows(
        cur, category="ingestion_health", evidence_type="ingestion_checkpoint",
        query=query, params=[list(context.source_ids)], context=context,
        filter_metadata=_filters(context),
    )


def _collection_response(cur, context: CollectorContext) -> EvidenceBundle:
    query = """
        SELECT id, NULL, NULL, source_ip, created_at, created_at,
               'audit event=' || event_type, COALESCE(details->>'data_provenance', ''),
               COUNT(*) OVER(), 'audit_log'
        FROM audit_log
        WHERE created_at >= %s AND created_at <= %s
          AND (event_type ILIKE '%%ingest%%' OR event_type ILIKE '%%source_health%%' OR event_type ILIKE '%%collector%%')
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category="collection_response", evidence_type="collection_response_audit",
        query=query, params=[context.window_start, context.window_end], context=context,
        filter_metadata=_filters(context),
        limitation="An ingestion failure without an attributable response record remains partial evidence.",
    )


def _incident_collector(cur, context: CollectorContext, *, category: str) -> EvidenceBundle:
    operational_sql, operational_params = _operational_ip_sql("source_ip")
    query = f"""
        SELECT id, NULL, NULL, source_ip, created_at, created_at,
               'incident severity=' || severity || '; priority=' || priority || '; status=' || status,
               '', COUNT(*) OVER(), 'incident'
        FROM incidents
        WHERE created_at <= %s AND COALESCE(resolved_at, %s) >= %s
          AND ({operational_sql})
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category=category, evidence_type="incident", query=query,
        params=[
            context.window_end, context.window_end, context.window_start,
            *operational_params,
        ],
        context=context,
        filter_metadata=_filters(context),
    )


def _incident_evidence(cur, context: CollectorContext) -> EvidenceBundle:
    operational_sql, operational_params = build_operational_source_ip_exclusion_sql(
        source_ip_column="a.source_ip",
        source_column="a.source",
        source_type_column="a.source_type",
        context_column="a.context",
    )
    query = f"""
        SELECT incident_id::text || ':' || alert_id::text, a.source, a.source_type, a.source_ip,
               ia.linked_at, ia.linked_at,
               'incident=' || incident_id::text || '; linked alert=' || alert_id::text,
               COALESCE(a.context->>'data_provenance', ''), COUNT(*) OVER(), 'incident_alert_link'
        FROM incident_alerts ia
        JOIN alerts a ON a.id = ia.alert_id
        WHERE ia.linked_at >= %s AND ia.linked_at <= %s
          AND a.source = ANY(%s)
          AND ({operational_sql})
        ORDER BY ia.linked_at DESC, incident_id DESC, alert_id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category="incident_evidence", evidence_type="incident_alert_link", query=query,
        params=[
            context.window_start, context.window_end, list(context.source_ids),
            *operational_params,
        ],
        context=context,
        filter_metadata=_filters(context),
    )


def _incident_documentation(cur, context: CollectorContext) -> EvidenceBundle:
    operational_sql, operational_params = _operational_ip_sql("i.source_ip")
    query = f"""
        SELECT n.id, NULL, NULL, i.source_ip, n.created_at, n.created_at,
               'incident note for incident=' || n.incident_id::text,
               '', COUNT(*) OVER(), 'incident_note'
        FROM incident_notes n
        JOIN incidents i ON i.id = n.incident_id
        WHERE n.created_at >= %s AND n.created_at <= %s
          AND ({operational_sql})
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category="incident_documentation", evidence_type="incident_note", query=query,
        params=[context.window_start, context.window_end, *operational_params], context=context,
        filter_metadata=_filters(context),
    )


def _existing_evidence_references(cur, context: CollectorContext) -> EvidenceBundle:
    synthetic_values = sorted(SYNTHETIC_PROVENANCE_VALUES)
    query = f"""
        SELECT id, source, NULL, NULL, created_at, created_at,
               'reference object=' || referenced_object_type || '; relationship=' || relationship_type,
               COALESCE(metadata->>'data_provenance', ''), COUNT(*) OVER(), 'evidence_reference'
        FROM evidence_references
        WHERE created_at >= %s AND created_at <= %s
          AND {build_synthetic_json_value_sql('metadata')} <> ALL(%s)
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category="evidence_references", evidence_type="investigation_evidence_reference",
        query=query, params=[context.window_start, context.window_end, synthetic_values], context=context,
        filter_metadata=_filters(context),
    )


def _response_workflow(cur, context: CollectorContext) -> EvidenceBundle:
    operational_sql, operational_params = build_operational_source_ip_exclusion_sql(
        source_column="provider",
        source_type_column="adapter_name",
        context_column="metadata",
    )
    query = f"""
        SELECT id, NULL, NULL, source_ip, occurred_at, created_at,
               'response mode=' || execution_mode || '; state=' || execution_state,
               COALESCE(metadata->>'data_provenance', ''), COUNT(*) OVER(), 'soar_outcome'
        FROM soar_response_outcome_events
        WHERE occurred_at >= %s AND occurred_at <= %s
          AND ({operational_sql})
        ORDER BY occurred_at DESC, created_at DESC, id DESC
        LIMIT %s
    """

    def classify(row: tuple) -> str:
        # Classification fields are embedded in the deterministic summary to
        # avoid selecting or persisting unrestricted metadata.
        parts = dict(part.split("=", 1) for part in str(row[6]).replace("response ", "").split("; "))
        mode = parts.get("mode", "unknown")
        state = parts.get("state", "unknown")
        # The query is intentionally reference-oriented. Real execution is
        # confirmed by a narrow follow-up lookup for each bounded row.
        cur.execute(
            """
            SELECT external_executed, tracking_recorded, simulated
            FROM soar_response_outcome_events WHERE id = %s
            """,
            (row[0],),
        )
        booleans = cur.fetchone()
        return classify_soar_outcome(
            execution_mode=mode,
            execution_state=state,
            external_executed=bool(booleans[0]),
            tracking_recorded=bool(booleans[1]),
            simulated=bool(booleans[2]),
        )

    outcome_bundle = _collect_rows(
        cur, category="response_workflow", evidence_type="soar_response_outcome",
        query=query, params=[context.window_start, context.window_end, *operational_params],
        context=context, filter_metadata=_filters(context), row_classifier=classify,
    )
    approval_bundle = _approval_workflow(cur, context)
    playbook_bundle = _playbook_workflow(cur, context)
    bundles = (outcome_bundle, approval_bundle, playbook_bundle)
    return EvidenceBundle(
        category="response_workflow",
        evidence_count=sum(bundle.evidence_count for bundle in bundles),
        references=tuple(reference for bundle in bundles for reference in bundle.references),
        omitted_count=sum(bundle.omitted_count for bundle in bundles),
        collector_completed=all(bundle.collector_completed for bundle in bundles),
        reason_code="collected",
        limitation=(
            "Approval records demonstrate authorization workflow, playbook records demonstrate internal "
            "orchestration, and only qualifying canonical outcomes demonstrate real external execution."
        ),
    )


def _approval_workflow(cur, context: CollectorContext) -> EvidenceBundle:
    query = """
        SELECT id, NULL, NULL, NULL, COALESCE(decided_at, created_at), created_at,
               'approval action=' || action || '; status=' || status,
               '', COUNT(*) OVER(), 'approval_request'
        FROM approval_requests
        WHERE created_at >= %s AND created_at <= %s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category="response_workflow", evidence_type="approval_workflow",
        query=query, params=[context.window_start, context.window_end], context=context,
        filter_metadata=_filters(context, workflow="approval"),
        row_classifier=lambda _row: "approval_only",
        limitation="Approval demonstrates authorization workflow, not successful external execution.",
    )


def _playbook_workflow(cur, context: CollectorContext) -> EvidenceBundle:
    query = """
        SELECT id, NULL, NULL, NULL, COALESCE(completed_at, started_at, created_at), created_at,
               'playbook=' || playbook_id || '; status=' || status,
               '', COUNT(*) OVER(), 'playbook_execution'
        FROM playbook_executions
        WHERE created_at >= %s AND created_at <= %s
        ORDER BY created_at DESC, id DESC
        LIMIT %s
    """
    return _collect_rows(
        cur, category="response_workflow", evidence_type="playbook_execution",
        query=query, params=[context.window_start, context.window_end], context=context,
        filter_metadata=_filters(context, workflow="playbook"),
        row_classifier=lambda _row: "internal_workflow",
        limitation="Playbook state demonstrates internal orchestration, not external execution by itself.",
    )


CATEGORY_COLLECTORS: dict[str, Callable[[Any, CollectorContext], EvidenceBundle]] = {
    "event_types": lambda cur, ctx: _event_collector(cur, ctx, category="event_types"),
    "detection_configuration": _detection_configuration,
    "audit_record_content": lambda cur, ctx: _event_collector(cur, ctx, category="audit_record_content"),
    "generated_records": lambda cur, ctx: _event_collector(cur, ctx, category="generated_records"),
    "ingestion_health": _ingestion_health,
    "collection_response": _collection_response,
    "security_findings": lambda cur, ctx: _alert_collector(cur, ctx, category="security_findings"),
    "incident_analysis": lambda cur, ctx: _incident_collector(cur, ctx, category="incident_analysis"),
    "searchable_records": lambda cur, ctx: _event_collector(cur, ctx, category="searchable_records"),
    "evidence_references": _existing_evidence_references,
    "occurrence_timestamps": lambda cur, ctx: _event_collector(cur, ctx, category="occurrence_timestamps", require_occurrence=True),
    "incidents": lambda cur, ctx: _incident_collector(cur, ctx, category="incidents"),
    "incident_evidence": _incident_evidence,
    "response_workflow": _response_workflow,
    "incident_tracking": lambda cur, ctx: _incident_collector(cur, ctx, category="incident_tracking"),
    "incident_documentation": _incident_documentation,
    "monitored_events": lambda cur, ctx: _event_collector(cur, ctx, category="monitored_events"),
    "security_alerts": lambda cur, ctx: _alert_collector(cur, ctx, category="security_alerts"),
    "firewall_events": lambda cur, ctx: _event_collector(cur, ctx, category="firewall_events", source_ids=("pfsense",)),
    "firewall_findings": lambda cur, ctx: _alert_collector(cur, ctx, category="firewall_findings", source_ids=("pfsense",)),
    "failed_logons": lambda cur, ctx: _event_collector(
        cur, ctx, category="failed_logons", event_type="failed_login",
        source_ids=("bank_app", "azure_insights", "opentelemetry", "nginx"),
    ),
    "authentication_detections": lambda cur, ctx: _alert_collector(
        cur, ctx, category="authentication_detections",
        alert_types=AUTHENTICATION_ALERT_TYPES,
        source_ids=("bank_app", "azure_insights", "opentelemetry", "nginx"),
    ),
}


def collect_all_categories(cur, context: CollectorContext) -> dict[str, EvidenceBundle]:
    start, end = validate_window(context.window_start, context.window_end)
    if context.collected_at.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    normalized_context = CollectorContext(
        source_ids=context.source_ids,
        environments=context.environments,
        window_start=start,
        window_end=end,
        collected_at=context.collected_at.astimezone(timezone.utc),
        source_health_snapshot=context.source_health_snapshot,
        reference_limit=_safe_limit(context.reference_limit),
    )
    categories = sorted({category for mapping in V1_MAPPINGS for category in mapping.evidence_categories})
    return {
        category: CATEGORY_COLLECTORS[category](cur, normalized_context)
        for category in categories
    }
