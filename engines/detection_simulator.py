"""Detection Simulator orchestrator — OpenSpec Phases 1-3.

Runs analyst-pasted events through the real production ingest, detection,
MITRE-mapping, and playbook/response-selection pipeline inside one
rollback-only database transaction. Nothing in this module ever calls
``conn.commit()``.

This is safe by construction, not by convention: ``engines/*.py`` and
``core/*.py`` contain zero ``commit``/``rollback`` calls anywhere in this
codebase (every commit lives in the route layer, e.g.
``routes/ingest_routes.py``), so calling those engine-layer functions here
and rolling back at the end reuses their exact logic without duplicating or
forking any detection, threshold, MITRE, or playbook-matching code.

See openspec/changes/add-detection-simulator-workspace/design.md for the
full rationale (rollback boundary vs. a `dry_run` flag, the production
write-boundary inventory, and the worker-safety hazard this design exists
to prevent).
"""
from __future__ import annotations

import ipaddress
import logging
from unittest.mock import patch

from adapters.azure_insights_adapter import (
    normalize_azure_identity_telemetry,
    normalize_azure_insights_telemetry,
)
from adapters.nginx_adapter import parse_nginx_access_log_line
from adapters.otel_adapter import normalize_otel_telemetry
from adapters.pfsense_filterlog_adapter import (
    parse_pfsense_filterlog_packet,
    validate_pfsense_normalized_event,
)
from core.db import get_db_connection
from engines.detection_applicability import (
    CANONICAL_SOURCE_IDENTITIES,
    get_rule_applicability_metadata,
    rule_applies_to_source,
)
from engines.detection_config import (
    DETECTION_THRESHOLD_MIN,
    get_detection_rule_defaults,
    get_effective_detection_rule,
)
from engines.detection_engine import (
    _generate_admin_probe_alerts_core,
    _generate_application_exception_alerts_core,
    _generate_credential_stuffing_alerts_core,
    _generate_env_probe_alerts_core,
    _generate_failed_login_alerts_core,
    _generate_high_request_rate_alerts_core,
    _generate_http_error_alerts_core,
    _generate_password_spraying_alerts_core,
    _generate_pfsense_noisy_source_alerts_core,
    _generate_pfsense_port_scan_alerts_core,
    _generate_pfsense_repeated_deny_alerts_core,
    _generate_pfsense_suspicious_allow_alerts_core,
    _generate_port_scan_alerts_core,
    _generate_scanner_detected_alerts_core,
    _generate_successful_login_after_spray_alerts_core,
)
from engines.ingest_engine import ingest_normalized_event
from engines.playbook_engine import match_playbooks
from helpers.enrichment_helpers import enrich_alert_with_correlation_context, enrich_alert_with_mitre
from helpers.ingest_normalizers import (
    _get_azure_app_name,
    _get_azure_identity_app_name,
    _get_otel_app_name,
    _is_azure_identity_payload,
)

# Reused deliberately rather than duplicated: this is the same private
# honeypot normalizer routes/ingest_routes.py uses for the real
# /ingest/honeypot path, and the same public validation constants the real
# /ingest path uses for bank_app events. See design.md's "no duplicate
# parser or normalization logic" requirement.
from routes.ingest_routes import VALID_EVENT_TYPES, VALID_SEVERITIES, _normalize_honeypot_event

logger = logging.getLogger(__name__)


class SimulationValidationError(ValueError):
    """Request-shape problem the route layer should turn into an HTTP 400."""


# Reputation lookups are stubbed for every simulation run so that pasted
# analyst input never triggers a live AbuseIPDB call or pollutes the
# process-level reputation cache shared with production ingest. See
# design.md's "External API calls are stubbed for simulation in V1" decision.
SIMULATED_REPUTATION = {
    "reputation_score": 0,
    "reputation_label": "unknown",
    "reputation_source": "simulated",
    "reputation_summary": "Reputation lookup stubbed during simulation; no live third-party API call was made.",
}

# Geolocation is intentionally never enriched for simulated events (no call
# to core.ip_helpers.lookup_ip_location anywhere in this module). If pasted
# input already contains a raw_payload.location, it is used as-is.

SOURCE_TYPE_BY_SOURCE = {identity.source: identity.source_type for identity in CANONICAL_SOURCE_IDENTITIES}

SUPPORTED_INPUT_FORMATS = {
    "pfsense": frozenset({"raw", "json"}),
    "nginx": frozenset({"raw"}),
    "honeypot": frozenset({"json"}),
    "bank_app": frozenset({"json"}),
    "azure_insights": frozenset({"json"}),
    "opentelemetry": frozenset({"json"}),
}

STAGE_NAMES = (
    "raw_input",
    "parser",
    "normalized_event",
    "detection_applicability",
    "detection_evaluation",
    "threshold_window_evaluation",
    "alert_preview",
    "mitre_mapping",
    "soar_preview",
)

MAX_BATCH_SIZE = 25

ALERT_ROW_COLUMNS = (
    "id",
    "alert_type",
    "severity",
    "source_ip",
    "source",
    "source_type",
    "message",
    "status",
    "response_action",
    "response_status",
    "country",
    "city",
    "reputation_score",
    "reputation_label",
    "reputation_source",
    "reputation_summary",
    "context",
)

# Maps each Version-1 rule id to the exact, unmodified production detector
# function that evaluates it (imported directly from engines.detection_engine
# above -- the same function objects engines.ingest_engine calls on the real
# /ingest path). Used only by _fetch_threshold_evidence to re-invoke that
# same function with an evidence-only threshold override; no detector SQL or
# logic is duplicated or reimplemented anywhere in this module.
RULE_ID_TO_DETECTOR = {
    "failed_login_threshold": _generate_failed_login_alerts_core,
    "port_scan_threshold": _generate_port_scan_alerts_core,
    "password_spraying_threshold": _generate_password_spraying_alerts_core,
    "http_error_threshold": _generate_http_error_alerts_core,
    "application_exception_threshold": _generate_application_exception_alerts_core,
    "high_request_rate_threshold": _generate_high_request_rate_alerts_core,
    "successful_login_after_spray": _generate_successful_login_after_spray_alerts_core,
    "honeypot_env_probe_threshold": _generate_env_probe_alerts_core,
    "honeypot_admin_probe_threshold": _generate_admin_probe_alerts_core,
    "honeypot_scanner_detected": _generate_scanner_detected_alerts_core,
    "honeypot_credential_stuffing_threshold": _generate_credential_stuffing_alerts_core,
    "pfsense_firewall_repeated_deny": _generate_pfsense_repeated_deny_alerts_core,
    "pfsense_firewall_port_scan": _generate_pfsense_port_scan_alerts_core,
    "pfsense_firewall_noisy_source": _generate_pfsense_noisy_source_alerts_core,
    "pfsense_firewall_suspicious_allow": _generate_pfsense_suspicious_allow_alerts_core,
}

# Every detector's alerts_created dict carries these bookkeeping fields; none
# of them is the rule's observed count/condition value.
_NON_EVIDENCE_ALERT_FIELDS = frozenset({"source_ip", "alert_id", "response_action", "severity", "success_at"})


def _extract_observed_value(alert_result):
    """Return (field_name, value) for the first integer field in a detector's
    own returned dict that isn't a fixed bookkeeping field. This reads a
    value the detector itself already computed; it never recomputes one.
    """
    for key, value in alert_result.items():
        if key in _NON_EVIDENCE_ALERT_FIELDS or isinstance(value, bool):
            continue
        if isinstance(value, int):
            return key, value
    return None, None


def _fetch_threshold_evidence(*, conn, cur, rule_id, rule_config, source, source_type, source_ip):
    """Re-invoke the exact same, unmodified production detector function
    engines.ingest_engine.ingest_normalized_event already called, with its
    threshold parameter temporarily lowered to the minimum valid value, so a
    below-threshold group becomes visible for explainability.

    This is not a shadow evaluator: it is the real detector, called with
    real (if temporarily adjusted) rule configuration, against the real
    events table, on the same cursor/transaction the caller already owns.
    It never runs on the production /ingest path -- only here, inside the
    simulator's own rollback-only transaction. Any alert it inserts is
    discarded by the caller's rollback and is never added to the
    simulation's real alerts_created list.
    """
    detector = RULE_ID_TO_DETECTOR.get(rule_id)
    if detector is None:
        return None, None

    evidence_parameters = dict(rule_config["parameters"])
    if "threshold" not in evidence_parameters:
        return None, None
    evidence_parameters["threshold"] = DETECTION_THRESHOLD_MIN

    evidence_rule_config = dict(rule_config)
    evidence_rule_config["parameters"] = evidence_parameters

    evidence_results = detector(
        cur,
        conn,
        source=source,
        source_type=source_type,
        source_ip=source_ip,
        rule_config=evidence_rule_config,
    )
    if not evidence_results:
        return None, None

    return _extract_observed_value(evidence_results[0])


# --- per-source parse+normalize functions -----------------------------------
# Each function reuses the same adapter/normalizer functions the real ingest
# routes use, and raises ValueError with a human-readable reason on failure,
# never crashing the request.


def _parse_and_normalize_pfsense_raw(line, environment):
    result = parse_pfsense_filterlog_packet(line, environment=environment)
    if not result.get("ok"):
        raise ValueError(result["error"]["reason"])
    return result["event"]


def _parse_and_normalize_pfsense_json(item, environment):
    return validate_pfsense_normalized_event(item)


def _parse_and_normalize_nginx_raw(line, environment):
    # Mirrors routes.ingest_routes.add_web_log_event's field derivation
    # exactly (status-code -> event_type/severity/message), since that glue
    # is inline route code with no standalone importable function. The
    # substantive parsing (parse_nginx_access_log_line) is fully reused.
    parsed_line = parse_nginx_access_log_line(line)

    status_code = parsed_line["status"]
    if status_code in {401, 403}:
        event_type, severity = "unauthorized_access", "medium"
    elif 500 <= status_code <= 599:
        event_type, severity = "http_error", "medium"
    else:
        event_type, severity = "normal_activity", "low"

    method = parsed_line.get("method") or "UNKNOWN"
    path = parsed_line.get("path") or "/"
    source_ip = parsed_line["source_ip"]
    raw_payload = {"line": line, "log_format": "nginx_access", **parsed_line}

    if event_type == "unauthorized_access":
        message = f"Unauthorized web access detected: HTTP {status_code} for {method} {path}"
    elif event_type == "http_error":
        message = f"Web server error detected: HTTP {status_code} for {method} {path}"
    else:
        message = f"Web request observed: HTTP {status_code} for {method} {path}"

    return {
        "event_type": event_type,
        "severity": severity,
        "source_ip": source_ip,
        "source": "nginx",
        "source_type": "web_log",
        "event_timestamp": parsed_line.get("event_timestamp"),
        "message": message,
        "app_name": "nginx",
        "environment": environment,
        "raw_payload": raw_payload,
    }


def _parse_and_normalize_honeypot_json(item, environment):
    del environment  # honeypot normalizer derives its own environment field
    return _normalize_honeypot_event(item)


def _parse_and_normalize_bank_app_json(item, environment):
    # Mirrors routes.ingest_routes.add_event's validation exactly (inline
    # route code with no standalone function); reuses the same VALID_*
    # constants so the accepted contract cannot drift from production.
    del environment
    if not isinstance(item, dict):
        raise ValueError("Invalid JSON event")

    event_type = item.get("event_type")
    severity = item.get("severity")
    source_ip = item.get("source_ip")
    message = item.get("message")
    app_name = item.get("app_name")
    event_environment = item.get("environment")
    raw_payload = dict(item)

    if not event_type or not severity or not source_ip:
        raise ValueError("Missing required fields")

    try:
        ipaddress.ip_address(str(source_ip))
    except ValueError as error:
        raise ValueError("Invalid source_ip") from error

    if not message:
        raise ValueError("Missing required field: message")
    if not app_name:
        raise ValueError("Missing required field: app_name")
    if not event_environment:
        raise ValueError("Missing required field: environment")
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError("Invalid event_type")
    if severity not in VALID_SEVERITIES:
        raise ValueError("Invalid severity")

    return {
        "event_type": event_type,
        "severity": severity,
        "source_ip": source_ip,
        "source": "bank_app",
        "source_type": "custom",
        "event_timestamp": item.get("event_timestamp"),
        "message": message,
        "app_name": app_name,
        "environment": event_environment,
        "raw_payload": raw_payload,
    }


def _parse_and_normalize_azure_json(item, environment):
    del environment
    is_identity_payload = _is_azure_identity_payload(item)
    normalized = (
        normalize_azure_identity_telemetry(item)
        if is_identity_payload
        else normalize_azure_insights_telemetry(item)
    )

    raw_payload = dict(item) if isinstance(item, dict) else item
    if is_identity_payload and isinstance(raw_payload, dict):
        raw_payload["username"] = normalized["username"]

    return {
        "event_type": normalized["event_type"],
        "severity": normalized["severity"],
        "source_ip": normalized["source_ip"],
        "source": "azure_insights",
        "source_type": "cloud_api",
        "event_timestamp": normalized.get("event_timestamp"),
        "message": normalized["message"],
        "app_name": (
            _get_azure_identity_app_name(item) if is_identity_payload else _get_azure_app_name(item)
        ),
        "environment": (item.get("environment") or "prod") if isinstance(item, dict) else "prod",
        "raw_payload": raw_payload,
    }


def _parse_and_normalize_otel_json(item, environment):
    del environment
    normalized = normalize_otel_telemetry(item)
    return {
        "event_type": normalized["event_type"],
        "severity": normalized["severity"],
        "source_ip": normalized["source_ip"],
        "source": "opentelemetry",
        "source_type": "telemetry",
        "event_timestamp": normalized.get("event_timestamp"),
        "message": normalized["message"],
        "app_name": _get_otel_app_name(normalized, item),
        "environment": (item.get("environment") or "prod") if isinstance(item, dict) else "prod",
        "raw_payload": item,
    }


PARSE_DISPATCH = {
    ("pfsense", "raw"): _parse_and_normalize_pfsense_raw,
    ("pfsense", "json"): _parse_and_normalize_pfsense_json,
    ("nginx", "raw"): _parse_and_normalize_nginx_raw,
    ("honeypot", "json"): _parse_and_normalize_honeypot_json,
    ("bank_app", "json"): _parse_and_normalize_bank_app_json,
    ("azure_insights", "json"): _parse_and_normalize_azure_json,
    ("opentelemetry", "json"): _parse_and_normalize_otel_json,
}


def _new_stages():
    return {name: {"status": "skipped", "reason": "not_reached"} for name in STAGE_NAMES}


def _skip_from(stages, start_stage_name, reason):
    start_index = STAGE_NAMES.index(start_stage_name)
    for name in STAGE_NAMES[start_index:]:
        stages[name] = {"status": "skipped", "reason": reason}


def _finalize(source, rule_id, stages):
    return {"simulated": True, "source": source, "rule_id": rule_id, "stages": stages}


def run_detection_simulation(
    *,
    source,
    rule_id,
    input_format,
    raw_lines=None,
    json_events=None,
    environment="prod",
):
    """Entry point. Validates the request, parses/normalizes input, then runs
    the rollback-only transaction. Raises SimulationValidationError for
    request-shape problems; never touches the database for those.
    """
    if source not in SOURCE_TYPE_BY_SOURCE:
        raise SimulationValidationError("Unknown source")
    if rule_id not in get_detection_rule_defaults():
        raise SimulationValidationError("Unknown rule_id")
    if input_format not in ("raw", "json"):
        raise SimulationValidationError("input_format must be 'raw' or 'json'")
    if input_format not in SUPPORTED_INPUT_FORMATS[source]:
        raise SimulationValidationError(
            f"Source '{source}' does not support input_format '{input_format}'"
        )
    if not isinstance(environment, str) or not environment.strip():
        raise SimulationValidationError("environment must be a non-empty string")

    if input_format == "raw":
        items = [line for line in (raw_lines or []) if isinstance(line, str) and line.strip()]
        if not items:
            raise SimulationValidationError("raw_lines must contain at least one non-empty line")
    else:
        items = [item for item in (json_events or []) if isinstance(item, dict)]
        if not items:
            raise SimulationValidationError("json_events must contain at least one JSON object")

    if len(items) > MAX_BATCH_SIZE:
        raise SimulationValidationError(f"Input batch exceeds maximum size of {MAX_BATCH_SIZE}")

    source_type = SOURCE_TYPE_BY_SOURCE[source]
    stages = _new_stages()
    stages["raw_input"] = {"status": "succeeded", "input_count": len(items)}

    # Parser + Normalized Event always run first: they depend only on source
    # and pasted input, never on which rule was selected, matching the
    # Raw Input -> Parser -> Normalized Event -> ... pipeline order.
    handler = PARSE_DISPATCH[(source, input_format)]
    parser_results = []
    normalized_events = []
    for index, raw_item in enumerate(items):
        try:
            normalized = handler(raw_item, environment)
            parser_results.append({"index": index, "status": "succeeded"})
            normalized_events.append(normalized)
        except ValueError as error:
            parser_results.append({"index": index, "status": "failed", "error": str(error)})
        except Exception:
            logger.exception(
                "[DETECTION SIMULATOR] unexpected parser failure source=%s index=%s", source, index
            )
            parser_results.append({"index": index, "status": "failed", "error": "Unexpected parser error"})

    any_parsed = len(normalized_events) > 0
    stages["parser"] = {"status": "succeeded" if any_parsed else "failed", "results": parser_results}

    if not any_parsed:
        _skip_from(stages, "normalized_event", "parser_failed")
        return _finalize(source, rule_id, stages)

    stages["normalized_event"] = {"status": "succeeded", "events": normalized_events}

    applicable = rule_applies_to_source(rule_id, source, source_type)
    applicability_metadata = get_rule_applicability_metadata(rule_id)
    if not applicable:
        stages["detection_applicability"] = {
            "status": "failed",
            "reason": f"Rule '{rule_id}' is not applicable to source '{source}'",
            "metadata": applicability_metadata,
        }
        _skip_from(stages, "detection_evaluation", "rule_not_applicable_to_source")
        return _finalize(source, rule_id, stages)

    stages["detection_applicability"] = {"status": "succeeded", "metadata": applicability_metadata}

    # --- rollback-only transaction boundary -------------------------------
    # This is the single load-bearing safety property of the entire
    # simulator (see design.md's Worker-safety decision). conn.commit() must
    # never be called anywhere in this module or in anything it calls.
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            _run_pipeline(
                conn=conn,
                cur=cur,
                rule_id=rule_id,
                source=source,
                source_type=source_type,
                normalized_events=normalized_events,
                stages=stages,
            )
        finally:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()

    return _finalize(source, rule_id, stages)


def _fetch_alert_rows(cur, alert_ids):
    alert_ids = [alert_id for alert_id in alert_ids if alert_id is not None]
    if not alert_ids:
        return []
    select_columns = ", ".join(
        "host(source_ip) AS source_ip" if column == "source_ip" else column for column in ALERT_ROW_COLUMNS
    )
    cur.execute(
        f"SELECT {select_columns} FROM alerts WHERE id = ANY(%s)",
        (alert_ids,),
    )
    rows = cur.fetchall()
    return [dict(zip(ALERT_ROW_COLUMNS, row)) for row in rows]


def _run_pipeline(*, conn, cur, rule_id, source, source_type, normalized_events, stages):
    """All database work for one simulation run. Never commits or rolls back
    itself — the caller (run_detection_simulation) owns that boundary so it
    can guarantee rollback runs exactly once regardless of what happens here.
    """
    primary_source_ip = normalized_events[-1].get("source_ip")
    rule_config = get_effective_detection_rule(rule_id, cur=cur)
    window_minutes = rule_config["parameters"].get("window_minutes")

    # Disclosure pre-checks, run BEFORE inserting any simulated event, so
    # they reflect only real, already-committed production state.
    existing_open_alert = False
    if primary_source_ip is not None:
        cur.execute(
            "SELECT 1 FROM alerts WHERE source_ip = %s AND alert_type = %s AND status = 'open'",
            (primary_source_ip, rule_id),
        )
        existing_open_alert = cur.fetchone() is not None

    blended_with_real_history = False
    if window_minutes:
        cur.execute(
            f"""
            SELECT COUNT(*) FROM events
            WHERE source = %s AND source_type = %s
              AND created_at >= NOW() - INTERVAL '{int(window_minutes)} minutes'
            """,
            (source, source_type),
        )
        blended_with_real_history = (cur.fetchone()[0] or 0) > 0

    # Reputation lookups are stubbed for the duration of this call and the
    # threshold-evidence call below (see SIMULATED_REPUTATION above);
    # production /ingest is unaffected because this patch is scoped to this
    # single, rolled-back call.
    alerts_created = []
    with patch("engines.detection_engine.lookup_ip_reputation", return_value=SIMULATED_REPUTATION), patch(
        "engines.correlation_engine.lookup_ip_reputation", return_value=SIMULATED_REPUTATION
    ):
        for event_dict in normalized_events:
            alerts_created.extend(ingest_normalized_event(event_dict, conn, cur))

        stages["detection_evaluation"] = {
            "status": "succeeded",
            "events_ingested": len(normalized_events),
            "total_alerts_created_across_all_applicable_rules": len(alerts_created),
        }

        alert_rows = _fetch_alert_rows(cur, [alert.get("alert_id") for alert in alerts_created])
        matching_alert = next((row for row in alert_rows if row["alert_type"] == rule_id), None)

        observed_value = None
        observed_value_label = None
        evidence_available = False

        if matching_alert is not None:
            # The rule's threshold was met: the observed value is already
            # sitting in the real detector's own return value for this
            # alert_id -- no extra query needed.
            matching_result = next(
                (alert for alert in alerts_created if alert.get("alert_id") == matching_alert["id"]),
                None,
            )
            if matching_result is not None:
                observed_value_label, observed_value = _extract_observed_value(matching_result)
                evidence_available = observed_value is not None
        elif not existing_open_alert:
            # Not matched, and not suppressed by dedup: re-invoke the exact
            # same production detector function with its threshold
            # temporarily lowered, to surface the true observed value for a
            # below-threshold group. See _fetch_threshold_evidence.
            observed_value_label, observed_value = _fetch_threshold_evidence(
                conn=conn,
                cur=cur,
                rule_id=rule_id,
                rule_config=rule_config,
                source=source,
                source_type=source_type,
                source_ip=primary_source_ip,
            )
            evidence_available = observed_value is not None

    threshold = rule_config["parameters"].get("threshold")
    stages["threshold_window_evaluation"] = {
        "status": "succeeded",
        "rule_parameters": rule_config["parameters"],
        "rule_active": rule_config["active"],
        "matched": matching_alert is not None,
        "evaluated_window_minutes": window_minutes,
        "observed_value_label": observed_value_label,
        "observed_value": observed_value,
        "configured_threshold": threshold,
        "evidence_available": evidence_available,
        "existing_open_alert_for_rule": existing_open_alert,
        "blended_with_real_history": blended_with_real_history,
        "note": (
            "An open alert already exists for this source and rule; production "
            "dedup logic suppresses a new alert even if this rule's threshold "
            "was met by this simulation, so an exact observed value could not "
            "be evaluated without bypassing that same dedup guard."
            if existing_open_alert and matching_alert is None
            else None
        ),
    }

    if matching_alert is None:
        stages["alert_preview"] = {
            "status": "succeeded",
            "alert": None,
            "reason": "no_alert_created_for_selected_rule",
        }
        stages["mitre_mapping"] = {"status": "skipped", "reason": "no_alert_created_for_selected_rule"}
        stages["soar_preview"] = {"status": "skipped", "reason": "no_alert_created_for_selected_rule"}
        return

    enriched_alert = enrich_alert_with_mitre(dict(matching_alert))
    enriched_alert = enrich_alert_with_correlation_context(enriched_alert)
    stages["alert_preview"] = {"status": "succeeded", "alert": enriched_alert}
    stages["mitre_mapping"] = {
        "status": "succeeded",
        "mitre_technique_id": enriched_alert.get("mitre_technique_id"),
        "mitre_technique_name": enriched_alert.get("mitre_technique_name"),
        "mitre_tactic": enriched_alert.get("mitre_tactic"),
    }

    # SOAR preview: reuses match_playbooks() read-only, against the alert row
    # this same (uncommitted) transaction just inserted. No queue row, no
    # playbook_execution row, and no integration adapter is ever invoked here.
    matched_playbooks = match_playbooks(conn, matching_alert["id"])
    soar_preview_playbooks = []
    for playbook in matched_playbooks:
        steps = playbook.get("steps") or []
        approval_steps = [
            step for step in steps if isinstance(step, dict) and step.get("action") == "require_approval"
        ]
        soar_preview_playbooks.append(
            {
                "playbook_id": playbook.get("id"),
                "name": playbook.get("name"),
                "approval_required": bool(approval_steps),
                "approval_risk_levels": [step.get("risk_level", "high") for step in approval_steps],
            }
        )

    stages["soar_preview"] = {
        "status": "succeeded",
        "matched_playbooks": soar_preview_playbooks,
        "no_playbook_match": len(soar_preview_playbooks) == 0,
        "selected_response_action": enriched_alert.get("response_action"),
        "response_action_basis": (
            "computed from a stubbed simulated reputation score; not the source IP's real reputation"
        ),
    }
