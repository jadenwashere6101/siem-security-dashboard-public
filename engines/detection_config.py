import json

from flask import current_app

from core.db import get_db_connection


# Detector defaults.
FAILED_LOGIN_THRESHOLD = 3
FAILED_LOGIN_WINDOW_MINUTES = 15

PORT_SCAN_THRESHOLD = 2
PORT_SCAN_WINDOW_MINUTES = 15

PASSWORD_SPRAY_THRESHOLD = 5
PASSWORD_SPRAY_WINDOW_MINUTES = 15

HTTP_ERROR_THRESHOLD = 5
HTTP_ERROR_WINDOW_MINUTES = 15
APPLICATION_EXCEPTION_THRESHOLD = 3
APPLICATION_EXCEPTION_WINDOW_MINUTES = 10

HIGH_REQUEST_RATE_THRESHOLD = 20
HIGH_REQUEST_RATE_WINDOW_MINUTES = 5
CORRELATION_WINDOW_MINUTES = 10

SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES = 15
SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES = 30
SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES = 15
SUCCESS_AFTER_SPRAY_THRESHOLD = 5

# Shared validation bounds for admin-configurable detector settings.
DETECTION_THRESHOLD_MIN = 1
DETECTION_THRESHOLD_MAX = 100
DETECTION_WINDOW_MINUTES_MIN = 1
DETECTION_WINDOW_MINUTES_MAX = 1440


def get_detection_rule_defaults():
    return {
        "failed_login_threshold": {
            "rule_id": "failed_login_threshold",
            "display_name": "Failed Login Threshold",
            "parameters": {
                "threshold": FAILED_LOGIN_THRESHOLD,
                "window_minutes": FAILED_LOGIN_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when multiple failed login attempts occur within a time window.",
        },
        "port_scan_threshold": {
            "rule_id": "port_scan_threshold",
            "display_name": "Port Scan Threshold",
            "parameters": {
                "threshold": PORT_SCAN_THRESHOLD,
                "window_minutes": PORT_SCAN_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when repeated port scan events occur from the same source within a time window.",
        },
        "password_spraying_threshold": {
            "rule_id": "password_spraying_threshold",
            "display_name": "Password Spraying Threshold",
            "parameters": {
                "threshold": PASSWORD_SPRAY_THRESHOLD,
                "window_minutes": PASSWORD_SPRAY_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when failed logins target multiple distinct usernames from the same source within a time window.",
        },
        "http_error_threshold": {
            "rule_id": "http_error_threshold",
            "display_name": "HTTP Error Threshold",
            "parameters": {
                "threshold": HTTP_ERROR_THRESHOLD,
                "window_minutes": HTTP_ERROR_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when repeated HTTP error events occur from the same source within a time window.",
        },
        "application_exception_threshold": {
            "rule_id": "application_exception_threshold",
            "display_name": "Application Exception Threshold",
            "parameters": {
                "threshold": APPLICATION_EXCEPTION_THRESHOLD,
                "window_minutes": APPLICATION_EXCEPTION_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when repeated application exception events occur from the same source within a time window.",
        },
        "high_request_rate_threshold": {
            "rule_id": "high_request_rate_threshold",
            "display_name": "High Request Rate Threshold",
            "parameters": {
                "threshold": HIGH_REQUEST_RATE_THRESHOLD,
                "window_minutes": HIGH_REQUEST_RATE_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when high request volume occurs from the same source within a time window.",
        },
        "successful_login_after_spray": {
            "rule_id": "successful_login_after_spray",
            "display_name": "Successful Login After Spray",
            "parameters": {
                "threshold": SUCCESS_AFTER_SPRAY_THRESHOLD,
                "success_window_minutes": SUCCESS_AFTER_SPRAY_SUCCESS_WINDOW_MINUTES,
                "failed_lookback_minutes": SUCCESS_AFTER_SPRAY_FAILED_LOOKBACK_MINUTES,
                "correlation_window_minutes": SUCCESS_AFTER_SPRAY_CORRELATION_WINDOW_MINUTES,
            },
            "active": True,
            "description": "Triggers when password spraying activity is followed by a successful login from the same source.",
        },
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
            }
            for rule_defaults in defaults.values()
        ]
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
