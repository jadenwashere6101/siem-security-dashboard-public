import json

from flask import current_app

from core.db import get_db_connection
from engines.detection_applicability import get_rule_applicability_metadata
from engines.detection_rule_catalog import (
    APP_INSIGHTS_UNAUTHORIZED_ACCESS_THRESHOLD,
    APP_INSIGHTS_UNAUTHORIZED_ACCESS_WINDOW_MINUTES,
    APPLICATION_EXCEPTION_THRESHOLD,
    APPLICATION_EXCEPTION_WINDOW_MINUTES,
    CORRELATION_WINDOW_MINUTES,
    FAILED_LOGIN_THRESHOLD,
    FAILED_LOGIN_WINDOW_MINUTES,
    HIGH_REQUEST_RATE_THRESHOLD,
    HIGH_REQUEST_RATE_WINDOW_MINUTES,
    HTTP_ERROR_THRESHOLD,
    HTTP_ERROR_WINDOW_MINUTES,
    HONEYPOT_ADMIN_PROBE_THRESHOLD,
    HONEYPOT_ADMIN_PROBE_WINDOW_MINUTES,
    HONEYPOT_CREDENTIAL_STUFFING_THRESHOLD,
    HONEYPOT_CREDENTIAL_STUFFING_WINDOW_MINUTES,
    HONEYPOT_ENV_PROBE_THRESHOLD,
    HONEYPOT_ENV_PROBE_WINDOW_MINUTES,
    HONEYPOT_SCANNER_DETECTED_THRESHOLD,
    HONEYPOT_SCANNER_DETECTED_WINDOW_MINUTES,
    PASSWORD_SPRAY_THRESHOLD,
    PASSWORD_SPRAY_WINDOW_MINUTES,
    PFSENSE_ALLOW_AFTER_DENY_MIN_DENY_THRESHOLD,
    PFSENSE_ALLOW_AFTER_DENY_WINDOW_MINUTES,
    PFSENSE_NOISY_SOURCE_THRESHOLD,
    PFSENSE_NOISY_SOURCE_WINDOW_MINUTES,
    PFSENSE_PORT_SCAN_HOST_THRESHOLD,
    PFSENSE_PORT_SCAN_THRESHOLD,
    PFSENSE_PORT_SCAN_WINDOW_MINUTES,
    PFSENSE_REPEATED_DENY_THRESHOLD,
    PFSENSE_REPEATED_DENY_WINDOW_MINUTES,
    PFSENSE_SUSPICIOUS_ALLOW_DISTINCT_PORT_ESCALATION_THRESHOLD,
    PFSENSE_SUSPICIOUS_ALLOW_HIGH_CONFIDENCE_REPEAT_THRESHOLD,
    PFSENSE_SUSPICIOUS_ALLOW_THRESHOLD,
    PFSENSE_SUSPICIOUS_ALLOW_WINDOW_MINUTES,
    PORT_SCAN_THRESHOLD,
    PORT_SCAN_WINDOW_MINUTES,
    SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES,
    SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES,
    SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES,
    SUCCESS_AFTER_SPRAY_THRESHOLD,
    get_base_rule_catalog_records,
    get_rule_parameter_defaults,
)


# Minutes after a pfSense alert for a given (source_ip, alert_type) is resolved
# during which an equal-or-lower-severity recurrence is suppressed rather than
# regenerated. A strictly higher-severity recurrence always breaks through.
PFSENSE_ALERT_COOLDOWN_MINUTES = 60

# Sensitive/management-style destination ports. A `firewall_allow` event that lets
# inbound traffic reach one of these ports is contextually risky even though a
# single allow is not inherently malicious (see pfsense-firewall-detections-soar spec).
# Escalation multiplier: repeated-deny/port-scan alerts escalate from medium to
# high severity when observed volume/breadth reaches this multiple of the
# configured threshold, independent of reputation-based escalation.
PFSENSE_SEVERITY_ESCALATION_MULTIPLIER = 3

# Reputation score at/above which a pfSense alert can strengthen already-meaningful evidence.
PFSENSE_HIGH_REPUTATION_SCORE = 70

# Shared validation bounds for admin-configurable detector settings.
DETECTION_THRESHOLD_MIN = 1
DETECTION_THRESHOLD_MAX = 100
DETECTION_WINDOW_MINUTES_MIN = 1
DETECTION_WINDOW_MINUTES_MAX = 1440


def get_detection_rule_defaults():
    return {
        record.rule_id: {
            "rule_id": record.rule_id,
            "display_name": record.display_name,
            "parameters": get_rule_parameter_defaults(record.rule_id),
            "active": True,
            "description": record.description,
        }
        for record in get_base_rule_catalog_records()
        if record.implementation_state == "implemented"
    }


def parse_detection_rule_parameters(raw_parameters):
    if raw_parameters is None:
        return {}

    if isinstance(raw_parameters, str):
        try:
            raw_parameters = json.loads(raw_parameters)
        except json.JSONDecodeError as error:
            raise ValueError("Parameters must be valid JSON") from error

    if not isinstance(raw_parameters, dict):
        raise ValueError("Parameters must be an object")

    return raw_parameters


def validate_detection_rule_config(rule_id, parameters, active):
    defaults = get_detection_rule_defaults()
    rule_defaults = defaults.get(rule_id)

    if not rule_defaults:
        raise ValueError("Unknown rule_id")

    parameters = parse_detection_rule_parameters(parameters)

    if not isinstance(active, bool):
        raise ValueError("Active must be a boolean")

    allowed_parameters = set(rule_defaults["parameters"].keys())
    normalized_parameters = {}

    for key, value in parameters.items():
        if key not in allowed_parameters:
            raise ValueError(f"Unknown parameter key: {key}")

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Parameter {key} must be an integer")

        if key == "threshold":
            if not DETECTION_THRESHOLD_MIN <= value <= DETECTION_THRESHOLD_MAX:
                raise ValueError(f"Parameter {key} must be between {DETECTION_THRESHOLD_MIN} and {DETECTION_THRESHOLD_MAX}")
        else:
            if not DETECTION_WINDOW_MINUTES_MIN <= value <= DETECTION_WINDOW_MINUTES_MAX:
                raise ValueError(
                    f"Parameter {key} must be between {DETECTION_WINDOW_MINUTES_MIN} and {DETECTION_WINDOW_MINUTES_MAX}"
                )

        normalized_parameters[key] = value

    return {
        "parameters": normalized_parameters,
        "active": active,
    }


def get_effective_detection_rule(rule_id, cur=None):
    defaults = get_detection_rule_defaults()
    rule_defaults = defaults.get(rule_id)

    if not rule_defaults:
        raise ValueError("Unknown rule_id")

    effective_rule = {
        "rule_id": rule_defaults["rule_id"],
        "display_name": rule_defaults["display_name"],
        "parameters": dict(rule_defaults["parameters"]),
        "active": rule_defaults["active"],
        "description": rule_defaults["description"],
        "updated_by": None,
        "updated_at": None,
        "has_override": False,
        "override_status": "default",
        **get_rule_applicability_metadata(rule_id),
    }

    owns_connection = cur is None
    conn = None
    uses_savepoint = cur is not None

    try:
        if owns_connection:
            conn = get_db_connection()
            cur = conn.cursor()
            uses_savepoint = False

        if uses_savepoint:
            cur.execute("SAVEPOINT detection_config_lookup")

        cur.execute(
            """
            SELECT parameters, active, updated_by, updated_at
            FROM detection_config
            WHERE rule_id = %s
            """,
            (rule_id,),
        )
        row = cur.fetchone()

        if not row:
            return effective_rule

        effective_rule["has_override"] = True
        parameters = parse_detection_rule_parameters(row[0] if row[0] is not None else {})
        active = row[1]
        effective_rule["updated_by"] = row[2]
        effective_rule["updated_at"] = str(row[3]) if row[3] is not None else None

        validated = validate_detection_rule_config(rule_id, parameters, active)
        merged_parameters = dict(effective_rule["parameters"])
        merged_parameters.update(validated["parameters"])

        effective_rule["parameters"] = merged_parameters
        effective_rule["active"] = validated["active"]
        effective_rule["override_status"] = "applied"
        return effective_rule
    except ValueError as error:
        current_app.logger.warning("Invalid detection_config override for rule_id=%s: %s", rule_id, error)
        effective_rule["override_status"] = "invalid"
        return effective_rule
    except Exception as error:
        if uses_savepoint:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT detection_config_lookup")
            except Exception:
                pass
        current_app.logger.warning("Falling back to detection defaults for rule_id=%s: %s", rule_id, error)
        effective_rule["override_status"] = "unavailable"
        return effective_rule
    finally:
        if uses_savepoint:
            try:
                cur.execute("RELEASE SAVEPOINT detection_config_lookup")
            except Exception:
                pass
        if owns_connection:
            if cur:
                cur.close()
            if conn:
                conn.close()


def get_all_effective_detection_rules():
    defaults = get_detection_rule_defaults()
    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        return [get_effective_detection_rule(rule_id, cur=cur) for rule_id in defaults.keys()]
    except Exception as error:
        current_app.logger.warning("Falling back to detection defaults for admin detection rules list: %s", error)
        return [
            {
                **rule_defaults,
                "parameters": dict(rule_defaults["parameters"]),
                "has_override": False,
                "override_status": "unavailable",
                **get_rule_applicability_metadata(rule_defaults["rule_id"]),
            }
            for rule_defaults in defaults.values()
        ]
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
