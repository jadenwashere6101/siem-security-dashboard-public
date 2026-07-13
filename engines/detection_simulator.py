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
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
from core.ip_helpers import determine_response_action
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
from helpers.enrichment_helpers import (
    MITRE_ATTACK_MAPPINGS,
    enrich_alert_with_correlation_context,
    enrich_alert_with_mitre,
)
from helpers.ingest_normalizers import (
    HONEYPOT_EVENT_TYPES,
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
MAX_TEMP_EVENT_COUNT = 100
MAX_TEMP_TOTAL_INPUT_BYTES = 256 * 1024
MAX_TEMP_EVENT_BYTES = 8 * 1024
MAX_TEMP_STRING_LENGTH = 256
MAX_TEMP_EVENT_TYPE_LENGTH = 64
MAX_TEMP_IN_LIST_SIZE = 20
MAX_TEMP_GROUP_RESULTS = 50

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

SIMULATION_MODE_EXISTING_PRODUCTION_RULE = "existing_production_rule"
SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE = "temporary_playground_rule"
TEMPORARY_PLAYGROUND_ALERT_TYPE = "temporary_playground_rule"
TEMPORARY_RULE_MITRE_PATTERN = re.compile(r"^T\d{4}(?:\.\d{3})?$")
TEMPORARY_RULE_NUMERIC_FIELDS = frozenset({"destination_port", "http_status"})
TEMPORARY_RULE_STRING_FIELDS = frozenset(
    {
        "source_ip",
        "destination_ip",
        "username",
        "event_type",
        "event_outcome",
        "action",
        "severity",
    }
)
TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE = {
    "honeypot": frozenset({"source_ip", "username", "event_type", "severity"}),
    "bank_app": frozenset({"source_ip", "username", "event_type", "event_outcome", "severity"}),
    "pfsense": frozenset(
        {"source_ip", "destination_ip", "destination_port", "event_type", "action", "severity"}
    ),
    "nginx": frozenset({"source_ip", "event_type", "http_status", "severity"}),
    "azure_insights": frozenset(
        {"source_ip", "username", "event_type", "event_outcome", "http_status", "severity"}
    ),
    "opentelemetry": frozenset({"source_ip", "event_type", "http_status", "severity"}),
}
TEMPORARY_RULE_GROUPABLE_FIELDS_BY_SOURCE = {
    "honeypot": frozenset({"source_ip", "username"}),
    "bank_app": frozenset({"source_ip", "username"}),
    "pfsense": frozenset({"source_ip", "destination_ip", "destination_port"}),
    "nginx": frozenset({"source_ip"}),
    "azure_insights": frozenset({"source_ip", "username"}),
    "opentelemetry": frozenset({"source_ip"}),
}
TEMPORARY_RULE_SUPPORTED_INPUT_FORMATS = {
    "honeypot": frozenset({"json_lines", "json_array"}),
    "bank_app": frozenset({"json_lines", "json_array"}),
    "pfsense": frozenset({"raw_text", "json_lines", "json_array"}),
    "nginx": frozenset({"raw_text"}),
    "azure_insights": frozenset({"json_lines", "json_array"}),
    "opentelemetry": frozenset({"json_lines", "json_array"}),
}
TEMPORARY_RULE_ALLOWED_EVENT_TYPES_BY_SOURCE = {
    "honeypot": HONEYPOT_EVENT_TYPES,
    "bank_app": frozenset(VALID_EVENT_TYPES),
    "pfsense": frozenset({"firewall_block", "firewall_allow"}),
    "nginx": frozenset({"unauthorized_access", "http_error", "normal_activity"}),
    "azure_insights": frozenset(
        {"failed_login", "successful_login", "application_exception", "availability_failure", "http_error", "normal_activity"}
    ),
    "opentelemetry": frozenset({"unauthorized_access", "http_error", "application_exception", "normal_activity"}),
}
TEMPORARY_RULE_ALLOWED_OPERATORS = frozenset(
    {
        "equals",
        "not_equals",
        "contains",
        "starts_with",
        "ends_with",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "in_list",
    }
)
TEMPORARY_RULE_STRING_OPERATORS = frozenset(
    {"equals", "not_equals", "contains", "starts_with", "ends_with", "in_list"}
)
TEMPORARY_RULE_NUMERIC_OPERATORS = frozenset(
    {
        "equals",
        "not_equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "in_list",
    }
)
TEMPORARY_RULE_FORBIDDEN_REQUEST_KEYS = frozenset(
    {"history_mode", "draft_id", "saved_rule_id", "use_production_history", "persist_draft", "save_rule"}
)
TEMPORARY_RULE_MITRE_TECHNIQUES = {}
for _mitre_data in MITRE_ATTACK_MAPPINGS.values():
    technique_id = _mitre_data.get("mitre_technique_id")
    if not technique_id or technique_id in TEMPORARY_RULE_MITRE_TECHNIQUES:
        continue
    TEMPORARY_RULE_MITRE_TECHNIQUES[technique_id] = {
        "mitre_technique_id": technique_id,
        "mitre_technique_name": _mitre_data.get("mitre_technique_name"),
        "mitre_tactic": _mitre_data.get("mitre_tactic"),
    }


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


def _finalize(*, source, stages, simulation_mode, rule_id=None, temporary_rule=None):
    payload = {
        "simulated": True,
        "simulation_mode": simulation_mode,
        "source": source,
        "stages": stages,
    }
    if rule_id is not None:
        payload["rule_id"] = rule_id
    if temporary_rule is not None:
        payload["temporary_rule"] = temporary_rule
    return payload


def _normalize_simulation_mode(simulation_mode, rule_id, temporary_rule):
    if simulation_mode is None:
        if temporary_rule is not None and rule_id is None:
            return SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE
        return SIMULATION_MODE_EXISTING_PRODUCTION_RULE
    if simulation_mode not in {
        SIMULATION_MODE_EXISTING_PRODUCTION_RULE,
        SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
    }:
        raise SimulationValidationError("Unsupported simulation_mode")
    if simulation_mode == SIMULATION_MODE_EXISTING_PRODUCTION_RULE and temporary_rule is not None:
        raise SimulationValidationError(
            "temporary_rule is only allowed for simulation_mode='temporary_playground_rule'"
        )
    if simulation_mode == SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE and rule_id is not None:
        raise SimulationValidationError(
            "rule_id is not allowed for simulation_mode='temporary_playground_rule'"
        )
    return simulation_mode


def _validate_non_empty_string(value, field_name, *, max_length=MAX_TEMP_STRING_LENGTH):
    if not isinstance(value, str):
        raise SimulationValidationError(f"{field_name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise SimulationValidationError(f"{field_name} must be a non-empty string")
    if len(trimmed) > max_length:
        raise SimulationValidationError(f"{field_name} exceeds maximum length of {max_length}")
    return trimmed


def _validate_bounded_int(value, field_name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise SimulationValidationError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise SimulationValidationError(f"{field_name} must be between {minimum} and {maximum}")
    return value


def _validate_temporary_rule_value(field_name, operator, value):
    is_numeric = field_name in TEMPORARY_RULE_NUMERIC_FIELDS
    allowed_operators = (
        TEMPORARY_RULE_NUMERIC_OPERATORS if is_numeric else TEMPORARY_RULE_STRING_OPERATORS
    )
    if operator not in allowed_operators:
        raise SimulationValidationError(
            f"Operator '{operator}' is not allowed for condition.field '{field_name}'"
        )

    if operator == "in_list":
        if not isinstance(value, list):
            raise SimulationValidationError("condition.value must be a list for operator 'in_list'")
        if not value or len(value) > MAX_TEMP_IN_LIST_SIZE:
            raise SimulationValidationError(
                f"condition.value list must contain between 1 and {MAX_TEMP_IN_LIST_SIZE} items"
            )
        normalized_values = []
        seen_type = None
        for item in value:
            normalized_item = (
                _validate_bounded_int(item, "condition.value item", -65535, 65535)
                if is_numeric
                else _validate_non_empty_string(item, "condition.value item")
            )
            item_type = type(normalized_item)
            if seen_type is None:
                seen_type = item_type
            elif item_type is not seen_type:
                raise SimulationValidationError("condition.value list items must have the same type")
            normalized_values.append(normalized_item)
        return normalized_values

    if is_numeric:
        return _validate_bounded_int(value, "condition.value", -65535, 65535)
    return _validate_non_empty_string(value, "condition.value")


def _validate_temporary_rule_contract(temporary_rule):
    if not isinstance(temporary_rule, dict):
        raise SimulationValidationError("temporary_rule must be an object")

    allowed_keys = {
        "source",
        "source_type",
        "input_format",
        "event_type",
        "condition",
        "aggregation",
        "threshold",
        "window_minutes",
        "severity",
        "mitre_technique_id",
    }
    unexpected_keys = sorted(set(temporary_rule) - allowed_keys)
    if unexpected_keys:
        raise SimulationValidationError(
            f"temporary_rule contains unsupported fields: {', '.join(unexpected_keys)}"
        )

    source = _validate_non_empty_string(temporary_rule.get("source"), "temporary_rule.source", max_length=64)
    if source not in SOURCE_TYPE_BY_SOURCE:
        raise SimulationValidationError("Unknown temporary_rule.source")

    source_type = _validate_non_empty_string(
        temporary_rule.get("source_type"), "temporary_rule.source_type", max_length=64
    )
    if SOURCE_TYPE_BY_SOURCE[source] != source_type:
        raise SimulationValidationError("temporary_rule.source_type does not match the canonical source type")

    input_format = _validate_non_empty_string(
        temporary_rule.get("input_format"), "temporary_rule.input_format", max_length=32
    )
    if input_format not in TEMPORARY_RULE_SUPPORTED_INPUT_FORMATS[source]:
        raise SimulationValidationError(
            f"Source '{source}' does not support temporary_rule.input_format '{input_format}'"
        )

    event_type = temporary_rule.get("event_type")
    if event_type is not None:
        event_type = _validate_non_empty_string(
            event_type, "temporary_rule.event_type", max_length=MAX_TEMP_EVENT_TYPE_LENGTH
        )
        if event_type not in TEMPORARY_RULE_ALLOWED_EVENT_TYPES_BY_SOURCE[source]:
            raise SimulationValidationError(
                f"temporary_rule.event_type '{event_type}' is not supported for source '{source}'"
            )

    condition = temporary_rule.get("condition")
    if not isinstance(condition, dict):
        raise SimulationValidationError("temporary_rule.condition must be an object")
    if set(condition) != {"field", "operator", "value"}:
        raise SimulationValidationError(
            "temporary_rule.condition must contain exactly field, operator, and value"
        )
    condition_field = _validate_non_empty_string(condition.get("field"), "temporary_rule.condition.field")
    if condition_field not in TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE[source]:
        raise SimulationValidationError(
            f"temporary_rule.condition.field '{condition_field}' is not supported for source '{source}'"
        )
    condition_operator = _validate_non_empty_string(
        condition.get("operator"), "temporary_rule.condition.operator", max_length=32
    )
    if condition_operator not in TEMPORARY_RULE_ALLOWED_OPERATORS:
        raise SimulationValidationError("temporary_rule.condition.operator is unsupported")
    condition_value = _validate_temporary_rule_value(condition_field, condition_operator, condition.get("value"))

    aggregation = temporary_rule.get("aggregation")
    if not isinstance(aggregation, dict):
        raise SimulationValidationError("temporary_rule.aggregation must be an object")
    if set(aggregation) != {"type", "group_by_field"}:
        raise SimulationValidationError(
            "temporary_rule.aggregation must contain exactly type and group_by_field"
        )
    aggregation_type = _validate_non_empty_string(
        aggregation.get("type"), "temporary_rule.aggregation.type", max_length=32
    )
    if aggregation_type != "count":
        raise SimulationValidationError("temporary_rule.aggregation.type must be 'count'")
    group_by_field = _validate_non_empty_string(
        aggregation.get("group_by_field"), "temporary_rule.aggregation.group_by_field"
    )
    if group_by_field not in TEMPORARY_RULE_GROUPABLE_FIELDS_BY_SOURCE[source]:
        raise SimulationValidationError(
            f"temporary_rule.aggregation.group_by_field '{group_by_field}' is not supported for source '{source}'"
        )

    threshold = _validate_bounded_int(temporary_rule.get("threshold"), "temporary_rule.threshold", 1, 100)
    window_minutes = _validate_bounded_int(
        temporary_rule.get("window_minutes"), "temporary_rule.window_minutes", 1, 1440
    )
    severity = _validate_non_empty_string(temporary_rule.get("severity"), "temporary_rule.severity", max_length=16)
    if severity not in VALID_SEVERITIES:
        raise SimulationValidationError("temporary_rule.severity is unsupported")

    mitre_technique_id = temporary_rule.get("mitre_technique_id")
    if mitre_technique_id is not None:
        mitre_technique_id = _validate_non_empty_string(
            mitre_technique_id, "temporary_rule.mitre_technique_id", max_length=16
        )
        if not TEMPORARY_RULE_MITRE_PATTERN.match(mitre_technique_id):
            raise SimulationValidationError("temporary_rule.mitre_technique_id must match Txxxx or Txxxx.xxx")
        if mitre_technique_id not in TEMPORARY_RULE_MITRE_TECHNIQUES:
            raise SimulationValidationError("temporary_rule.mitre_technique_id is unsupported")

    return {
        "source": source,
        "source_type": source_type,
        "input_format": input_format,
        "event_type": event_type,
        "condition": {
            "field": condition_field,
            "operator": condition_operator,
            "value": condition_value,
        },
        "aggregation": {"type": aggregation_type, "group_by_field": group_by_field},
        "threshold": threshold,
        "window_minutes": window_minutes,
        "severity": severity,
        "mitre_technique_id": mitre_technique_id,
    }


def _coerce_temp_text_items(input_format, input_text):
    if not isinstance(input_text, str) or not input_text.strip():
        raise SimulationValidationError("input_text must be a non-empty string")
    encoded = input_text.encode("utf-8")
    if len(encoded) > MAX_TEMP_TOTAL_INPUT_BYTES:
        raise SimulationValidationError(
            f"Temporary playground input exceeds maximum size of {MAX_TEMP_TOTAL_INPUT_BYTES} bytes"
        )

    if input_format == "raw_text":
        items = [line for line in input_text.splitlines() if isinstance(line, str) and line.strip()]
    elif input_format == "json_lines":
        items = []
        for line in input_text.splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise SimulationValidationError(f"Invalid JSON line: {error.msg}") from error
            if not isinstance(parsed, dict):
                raise SimulationValidationError("Each json_lines item must decode to an object")
            items.append(parsed)
    else:
        try:
            parsed = json.loads(input_text)
        except json.JSONDecodeError as error:
            raise SimulationValidationError(f"Invalid JSON array payload: {error.msg}") from error
        if not isinstance(parsed, list) or not parsed:
            raise SimulationValidationError("json_array input must decode to a non-empty array of objects")
        if not all(isinstance(item, dict) for item in parsed):
            raise SimulationValidationError("json_array input must contain only objects")
        items = parsed

    if not items:
        raise SimulationValidationError("Temporary playground input must contain at least one event")
    if len(items) > MAX_TEMP_EVENT_COUNT:
        raise SimulationValidationError(
            f"Temporary playground input exceeds maximum event count of {MAX_TEMP_EVENT_COUNT}"
        )
    return items


def _coerce_temp_sample_events(sample_events):
    if not isinstance(sample_events, list) or not sample_events:
        raise SimulationValidationError("sample_events must be a non-empty list")
    if len(sample_events) > MAX_TEMP_EVENT_COUNT:
        raise SimulationValidationError(
            f"Temporary playground input exceeds maximum event count of {MAX_TEMP_EVENT_COUNT}"
        )
    if not all(isinstance(item, dict) for item in sample_events):
        raise SimulationValidationError("sample_events must contain only objects")
    encoded = json.dumps(sample_events).encode("utf-8")
    if len(encoded) > MAX_TEMP_TOTAL_INPUT_BYTES:
        raise SimulationValidationError(
            f"Temporary playground input exceeds maximum size of {MAX_TEMP_TOTAL_INPUT_BYTES} bytes"
        )
    return sample_events


def _validate_temp_event_size(raw_item, index):
    if isinstance(raw_item, str):
        encoded = raw_item.encode("utf-8")
    else:
        encoded = json.dumps(raw_item).encode("utf-8")
    if len(encoded) > MAX_TEMP_EVENT_BYTES:
        raise SimulationValidationError(
            f"Temporary playground event {index} exceeds maximum size of {MAX_TEMP_EVENT_BYTES} bytes"
        )


def _parse_iso_timestamp(value):
    if not value:
        return None
    if not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _temporary_rule_event_outcome(event_type):
    if event_type in {"failed_login", "login_failure"}:
        return "failure"
    if event_type == "successful_login":
        return "success"
    return None


def _extract_temporary_rule_field(event_dict, field_name):
    raw_payload = event_dict.get("raw_payload") if isinstance(event_dict.get("raw_payload"), dict) else {}
    if field_name == "source_ip":
        return event_dict.get("source_ip")
    if field_name == "destination_ip":
        return event_dict.get("destination_ip") or raw_payload.get("destination_ip")
    if field_name == "destination_port":
        value = event_dict.get("destination_port") or raw_payload.get("destination_port")
        if value in (None, "") or isinstance(value, bool):
            return None
        return int(value) if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()) else None
    if field_name == "username":
        return event_dict.get("username") or raw_payload.get("username") or raw_payload.get("userPrincipalName")
    if field_name == "event_type":
        return event_dict.get("event_type")
    if field_name == "event_outcome":
        return _temporary_rule_event_outcome(event_dict.get("event_type"))
    if field_name == "http_status":
        candidates = (
            raw_payload.get("status"),
            raw_payload.get("status_code"),
            raw_payload.get("statusCode"),
            raw_payload.get("responseCode"),
            raw_payload.get("resultCode"),
        )
        for candidate in candidates:
            if isinstance(candidate, bool) or candidate in (None, ""):
                continue
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str) and candidate.strip().isdigit():
                return int(candidate.strip())
        return None
    if field_name == "action":
        return raw_payload.get("action")
    if field_name == "severity":
        return event_dict.get("severity")
    return None


def _temporary_rule_value_matches(operator, expected, actual):
    if actual is None:
        return False
    if isinstance(expected, list):
        if isinstance(actual, str):
            actual = actual.strip().lower()
            expected = [item.strip().lower() if isinstance(item, str) else item for item in expected]
        return actual in expected
    if isinstance(expected, int):
        if not isinstance(actual, int):
            return False
        if operator == "equals":
            return actual == expected
        if operator == "not_equals":
            return actual != expected
        if operator == "greater_than":
            return actual > expected
        if operator == "greater_than_or_equal":
            return actual >= expected
        if operator == "less_than":
            return actual < expected
        if operator == "less_than_or_equal":
            return actual <= expected
        return False

    actual_text = str(actual).strip().lower()
    expected_text = str(expected).strip().lower()
    if operator == "equals":
        return actual_text == expected_text
    if operator == "not_equals":
        return actual_text != expected_text
    if operator == "contains":
        return expected_text in actual_text
    if operator == "starts_with":
        return actual_text.startswith(expected_text)
    if operator == "ends_with":
        return actual_text.endswith(expected_text)
    return False


def _apply_temporary_rule_mitre_selection(alert_dict, mitre_technique_id):
    mitre = TEMPORARY_RULE_MITRE_TECHNIQUES.get(mitre_technique_id)
    alert_dict["mitre_technique_id"] = mitre["mitre_technique_id"] if mitre else None
    alert_dict["mitre_technique_name"] = mitre.get("mitre_technique_name") if mitre else None
    alert_dict["mitre_tactic"] = mitre.get("mitre_tactic") if mitre else None
    return alert_dict


def _build_temporary_alert_message(temporary_rule, matched_group, observed_value):
    event_type = temporary_rule.get("event_type") or "any event type"
    return (
        f"Temporary playground rule matched {observed_value} event(s) for "
        f"{temporary_rule['aggregation']['group_by_field']}={matched_group} "
        f"within {temporary_rule['window_minutes']} minute(s) on {event_type}."
    )


def _insert_temporary_alert_preview(cur, temporary_rule, matched_group, observed_value, source_ip):
    response_action = determine_response_action(SIMULATED_REPUTATION["reputation_score"])
    cur.execute(
        """
        INSERT INTO alerts (
            source_ip,
            alert_type,
            severity,
            source,
            source_type,
            message,
            status,
            response_action,
            response_status,
            reputation_score,
            reputation_label,
            reputation_source,
            reputation_summary,
            context
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, 'not_executed', %s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            source_ip,
            TEMPORARY_PLAYGROUND_ALERT_TYPE,
            temporary_rule["severity"],
            temporary_rule["source"],
            temporary_rule["source_type"],
            _build_temporary_alert_message(temporary_rule, matched_group, observed_value),
            response_action,
            SIMULATED_REPUTATION["reputation_score"],
            SIMULATED_REPUTATION["reputation_label"],
            SIMULATED_REPUTATION["reputation_source"],
            SIMULATED_REPUTATION["reputation_summary"],
            json.dumps(
                {
                    "simulation_mode": SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
                    "group_by_field": temporary_rule["aggregation"]["group_by_field"],
                    "matched_group": matched_group,
                    "observed_value": observed_value,
                    "configured_threshold": temporary_rule["threshold"],
                    "evaluated_window_minutes": temporary_rule["window_minutes"],
                }
            ),
        ),
    )
    return cur.fetchone()[0]


def _build_temporary_soar_preview(conn, alert_row):
    matched_playbooks = match_playbooks(conn, alert_row["id"])
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
    return {
        "status": "succeeded",
        "matched_playbooks": soar_preview_playbooks,
        "no_playbook_match": len(soar_preview_playbooks) == 0,
        "selected_response_action": alert_row.get("response_action"),
        "response_action_basis": (
            "computed from a stubbed simulated reputation score; not the source IP's real reputation"
        ),
    }


def run_detection_simulation(
    *,
    source=None,
    rule_id=None,
    input_format=None,
    raw_lines=None,
    json_events=None,
    environment="prod",
    simulation_mode=None,
    temporary_rule=None,
    input_text=None,
    sample_events=None,
):
    mode = _normalize_simulation_mode(simulation_mode, rule_id, temporary_rule)
    if mode == SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE:
        return _run_temporary_rule_simulation(
            temporary_rule=temporary_rule,
            input_text=input_text,
            sample_events=sample_events,
            json_events=json_events,
            environment=environment,
        )
    return _run_existing_detection_simulation(
        source=source,
        rule_id=rule_id,
        input_format=input_format,
        raw_lines=raw_lines,
        json_events=json_events,
        environment=environment,
    )


def _run_existing_detection_simulation(
    *,
    source,
    rule_id,
    input_format,
    raw_lines=None,
    json_events=None,
    environment="prod",
):
    """Version 1 production-rule simulator entry point.

    Validates the request, parses/normalizes input, then runs the rollback-only
    transaction. Raises SimulationValidationError for request-shape problems;
    never touches the database for those.
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
        return _finalize(
            source=source,
            rule_id=rule_id,
            stages=stages,
            simulation_mode=SIMULATION_MODE_EXISTING_PRODUCTION_RULE,
        )

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
        return _finalize(
            source=source,
            rule_id=rule_id,
            stages=stages,
            simulation_mode=SIMULATION_MODE_EXISTING_PRODUCTION_RULE,
        )

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

    return _finalize(
        source=source,
        rule_id=rule_id,
        stages=stages,
        simulation_mode=SIMULATION_MODE_EXISTING_PRODUCTION_RULE,
    )


def _run_temporary_rule_simulation(
    *,
    temporary_rule,
    input_text=None,
    sample_events=None,
    json_events=None,
    environment="prod",
):
    if not isinstance(environment, str) or not environment.strip():
        raise SimulationValidationError("environment must be a non-empty string")
    validated_rule = _validate_temporary_rule_contract(temporary_rule)
    source = validated_rule["source"]
    input_format = validated_rule["input_format"]

    if input_text is not None and sample_events is not None:
        raise SimulationValidationError("Provide either input_text or sample_events, not both")

    if input_text is not None:
        items = _coerce_temp_text_items(input_format, input_text)
    elif sample_events is not None:
        items = _coerce_temp_sample_events(sample_events)
    elif json_events is not None:
        items = _coerce_temp_sample_events(json_events)
    else:
        raise SimulationValidationError("Temporary playground requests require input_text or sample_events")

    for index, raw_item in enumerate(items):
        _validate_temp_event_size(raw_item, index)

    stages = _new_stages()
    stages["raw_input"] = {
        "status": "succeeded",
        "input_count": len(items),
        "input_format": input_format,
    }

    parse_key = {
        "raw_text": "raw",
        "json_lines": "json",
        "json_array": "json",
    }[input_format]
    handler = PARSE_DISPATCH[(source, parse_key)]

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
                "[DETECTION SIMULATOR] unexpected temporary-rule parser failure source=%s index=%s",
                source,
                index,
            )
            parser_results.append({"index": index, "status": "failed", "error": "Unexpected parser error"})

    any_parsed = len(normalized_events) > 0
    stages["parser"] = {"status": "succeeded" if any_parsed else "failed", "results": parser_results}
    if not any_parsed:
        _skip_from(stages, "normalized_event", "parser_failed")
        return _finalize(
            source=source,
            stages=stages,
            simulation_mode=SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
            temporary_rule=validated_rule,
        )

    stages["normalized_event"] = {"status": "succeeded", "events": normalized_events}
    stages["detection_applicability"] = {
        "status": "succeeded",
        "source": source,
        "source_type": validated_rule["source_type"],
        "event_type_filter": validated_rule["event_type"],
        "allowed_condition_fields": sorted(TEMPORARY_RULE_ALLOWED_FIELDS_BY_SOURCE[source]),
        "allowed_group_by_fields": sorted(TEMPORARY_RULE_GROUPABLE_FIELDS_BY_SOURCE[source]),
    }

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            _run_temporary_pipeline(
                conn=conn,
                cur=cur,
                temporary_rule=validated_rule,
                normalized_events=normalized_events,
                stages=stages,
            )
        finally:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()

    return _finalize(
        source=source,
        stages=stages,
        simulation_mode=SIMULATION_MODE_TEMPORARY_PLAYGROUND_RULE,
        temporary_rule=validated_rule,
    )


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


def _run_temporary_pipeline(*, conn, cur, temporary_rule, normalized_events, stages):
    candidate_events = normalized_events
    if temporary_rule.get("event_type"):
        candidate_events = [
            event for event in normalized_events if event.get("event_type") == temporary_rule["event_type"]
        ]

    condition_field = temporary_rule["condition"]["field"]
    condition_operator = temporary_rule["condition"]["operator"]
    condition_value = temporary_rule["condition"]["value"]
    group_by_field = temporary_rule["aggregation"]["group_by_field"]

    matching_events = []
    grouped_events = defaultdict(list)
    for event in candidate_events:
        actual_value = _extract_temporary_rule_field(event, condition_field)
        if not _temporary_rule_value_matches(condition_operator, condition_value, actual_value):
            continue
        group_value = _extract_temporary_rule_field(event, group_by_field)
        if group_value in (None, ""):
            continue
        matching_events.append(event)
        grouped_events[group_value].append(event)

    stages["detection_evaluation"] = {
        "status": "succeeded",
        "candidate_event_count": len(candidate_events),
        "matching_event_count": len(matching_events),
        "event_type_filter_applied": temporary_rule.get("event_type"),
        "condition": temporary_rule["condition"],
    }

    grouped_results = []
    for group_value, events in grouped_events.items():
        parsed_timestamps = [_parse_iso_timestamp(event.get("event_timestamp")) for event in events]
        use_timestamp_window = bool(events) and all(timestamp is not None for timestamp in parsed_timestamps)
        if use_timestamp_window:
            window_end = max(parsed_timestamps)
            window_start = window_end - timedelta(minutes=temporary_rule["window_minutes"])
            events_in_window = [
                event
                for event, parsed_timestamp in zip(events, parsed_timestamps)
                if parsed_timestamp is not None and parsed_timestamp >= window_start
            ]
            window_basis = "event_timestamps"
        else:
            events_in_window = list(events)
            window_basis = "request_scope_without_timestamps"

        grouped_results.append(
            {
                "group_value": str(group_value),
                "match_count": len(events_in_window),
                "window_basis": window_basis,
                "sample_source_ip": next(
                    (event.get("source_ip") for event in events_in_window if event.get("source_ip")),
                    None,
                ),
            }
        )

    grouped_results.sort(key=lambda item: (-item["match_count"], item["group_value"]))
    grouped_results = grouped_results[:MAX_TEMP_GROUP_RESULTS]

    top_group = grouped_results[0] if grouped_results else None
    matched = bool(top_group and top_group["match_count"] >= temporary_rule["threshold"])
    matched_group = top_group["group_value"] if top_group else None
    observed_value = top_group["match_count"] if top_group else 0

    stages["threshold_window_evaluation"] = {
        "status": "succeeded",
        "matched": matched,
        "matched_group": matched_group,
        "observed_value_label": "count",
        "observed_value": observed_value,
        "configured_threshold": temporary_rule["threshold"],
        "evaluated_window_minutes": temporary_rule["window_minutes"],
        "window_basis": top_group["window_basis"] if top_group else "request_scope_without_timestamps",
        "group_by_field": group_by_field,
        "grouped_results": grouped_results,
        "evidence_available": top_group is not None,
        "pasted_event_only": True,
        "nothing_persisted": True,
        "nothing_executed": True,
    }

    if not matched:
        stages["alert_preview"] = {
            "status": "succeeded",
            "alert": None,
            "reason": "temporary_rule_threshold_not_reached",
        }
        stages["mitre_mapping"] = (
            {
                "status": "succeeded",
                "mitre_technique_id": None,
                "mitre_technique_name": None,
                "mitre_tactic": None,
                "reason": "no_temporary_rule_mitre_selected",
            }
            if temporary_rule.get("mitre_technique_id") is None
            else {
                "status": "skipped",
                "reason": "no_alert_created_for_temporary_rule",
            }
        )
        stages["soar_preview"] = {"status": "skipped", "reason": "no_alert_created_for_temporary_rule"}
        return

    matched_group_events = grouped_events[matched_group]
    preview_source_ip = next(
        (event.get("source_ip") for event in matched_group_events if event.get("source_ip")),
        None,
    )
    alert_id = _insert_temporary_alert_preview(
        cur,
        temporary_rule,
        matched_group,
        observed_value,
        preview_source_ip,
    )
    alert_row = _fetch_alert_rows(cur, [alert_id])[0]
    alert_row = _apply_temporary_rule_mitre_selection(alert_row, temporary_rule.get("mitre_technique_id"))

    stages["alert_preview"] = {
        "status": "succeeded",
        "alert": alert_row,
        "temporary_rule_semantics": True,
        "persistence": "request_scoped_rollback_only",
    }
    stages["mitre_mapping"] = {
        "status": "succeeded",
        "mitre_technique_id": alert_row.get("mitre_technique_id"),
        "mitre_technique_name": alert_row.get("mitre_technique_name"),
        "mitre_tactic": alert_row.get("mitre_tactic"),
        "reason": (
            "temporary_rule_selected_mitre_technique"
            if temporary_rule.get("mitre_technique_id")
            else "no_temporary_rule_mitre_selected"
        ),
    }
    stages["soar_preview"] = _build_temporary_soar_preview(conn, alert_row)
