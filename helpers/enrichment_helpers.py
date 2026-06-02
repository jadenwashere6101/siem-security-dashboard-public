import json

MITRE_ATTACK_MAPPINGS = {
    "failed_login_threshold": {
        "mitre_technique_id": "T1110",
        "mitre_technique_name": "Brute Force",
        "mitre_tactic": "Credential Access",
    },
    "port_scan_threshold": {
        "mitre_technique_id": "T1046",
        "mitre_technique_name": "Network Service Discovery",
        "mitre_tactic": "Discovery",
    },
    "suspicious_ip_reputation": {
        "mitre_technique_id": "T1595",
        "mitre_technique_name": "Active Scanning",
        "mitre_tactic": "Reconnaissance",
    },
    "password_spraying_threshold": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
    "successful_login_after_spray": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
    "spray_then_success_pattern": {
        "mitre_technique_id": "T1110.003",
        "mitre_technique_name": "Password Spraying",
        "mitre_tactic": "Credential Access",
    },
}

# These alert types intentionally keep null MITRE fields. Their current
# semantics are too broad to map to a specific ATT&CK technique confidently.
INTENTIONALLY_UNMAPPED_MITRE_ALERT_TYPES = {
    "http_error_threshold",
    "application_exception_threshold",
    "high_request_rate_threshold",
    "correlated_activity",
    "web_to_app_attack_pattern",
    "cloud_app_error_pattern",
}

CORRELATION_ALERT_TYPES = frozenset(
    {
        "correlated_activity",
        "web_to_app_attack_pattern",
        "spray_then_success_pattern",
        "cloud_app_error_pattern",
    }
)

CORRELATION_CONTEXT_RESPONSE_KEYS = (
    "correlation_type",
    "matched_rule_id",
    "matched_window_minutes",
    "matched_alert_count",
    "matched_groups",
    "contributing_alert_ids",
    "contributing_alert_types",
    "contributing_sources",
    "contributing_source_types",
)


def enrich_alert_with_mitre(alert_dict):
    alert_type = alert_dict.get("alert_type")
    mitre_data = MITRE_ATTACK_MAPPINGS.get(alert_type, {})

    alert_dict["mitre_technique_id"] = mitre_data.get("mitre_technique_id")
    alert_dict["mitre_technique_name"] = mitre_data.get("mitre_technique_name")
    alert_dict["mitre_tactic"] = mitre_data.get("mitre_tactic")

    return alert_dict


def _parse_correlated_activity_message(message):
    marker = "involving:"
    marker_index = message.lower().find(marker)
    if marker_index == -1:
        return []
    return [
        item.strip()
        for item in message[marker_index + len(marker) :].split(",")
        if item.strip()
    ]


def _normalize_alert_context(context):
    if context is None:
        return {}
    if isinstance(context, dict):
        return context
    if isinstance(context, str):
        try:
            parsed = json.loads(context)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_scalar_list(values):
    if not isinstance(values, list):
        return None
    safe_values = []
    for value in values:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, str)):
            safe_values.append(value)
            continue
        if isinstance(value, float) and value.is_integer():
            safe_values.append(int(value))
            continue
        return None
    return safe_values


def _safe_correlation_context(context):
    normalized = _normalize_alert_context(context)
    if not normalized:
        return None

    safe_context = {}
    for key in CORRELATION_CONTEXT_RESPONSE_KEYS:
        if key not in normalized:
            continue
        value = normalized[key]
        if key in {
            "correlation_type",
            "matched_rule_id",
        }:
            if isinstance(value, str) and value:
                safe_context[key] = value
            continue
        if key == "matched_window_minutes":
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                safe_context[key] = value
            elif isinstance(value, float) and value.is_integer():
                safe_context[key] = int(value)
            continue
        if key == "matched_alert_count":
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                safe_context[key] = value
            elif isinstance(value, float) and value.is_integer():
                safe_context[key] = int(value)
            continue
        safe_list = _safe_scalar_list(value)
        if safe_list is not None:
            safe_context[key] = safe_list

    if not safe_context.get("contributing_alert_types") and not safe_context.get("matched_rule_id"):
        return None
    return safe_context


def enrich_alert_with_correlation_context(alert_dict):
    alert_type = alert_dict.get("alert_type")
    if alert_type not in CORRELATION_ALERT_TYPES:
        return alert_dict

    safe_context = _safe_correlation_context(alert_dict.get("context"))
    if safe_context:
        contributing_types = safe_context.get("contributing_alert_types") or []
        alert_dict["is_correlation_alert"] = True
        alert_dict["correlated_alert_types"] = list(contributing_types)
        matched_count = safe_context.get("matched_alert_count")
        if isinstance(matched_count, int):
            alert_dict["correlated_alert_count"] = matched_count
        else:
            alert_dict["correlated_alert_count"] = len(contributing_types)
        alert_dict["correlation_context"] = {
            key: safe_context[key]
            for key in CORRELATION_CONTEXT_RESPONSE_KEYS
            if key in safe_context
        }
        return alert_dict

    if alert_type != "correlated_activity":
        return alert_dict

    correlated_alert_types = _parse_correlated_activity_message(str(alert_dict.get("message") or ""))
    if not correlated_alert_types:
        return alert_dict

    alert_dict["is_correlation_alert"] = True
    alert_dict["correlated_alert_types"] = correlated_alert_types
    alert_dict["correlated_alert_count"] = len(correlated_alert_types)
    return alert_dict
