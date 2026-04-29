import ipaddress


def _first_non_empty_value(*values):
    for value in values:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        elif value not in (None, ""):
            return value
    return None


def _safe_get(obj, *path):
    current = obj
    for key in path:
        if isinstance(key, int):
            if not isinstance(current, list) or key >= len(current) or key < 0:
                return None
            current = current[key]
        else:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
            if current is None:
                return None
    return current


def _extract_source_ip(telemetry):
    source_ip = _first_non_empty_value(
        telemetry.get("source_ip"),
        telemetry.get("sourceIp"),
        telemetry.get("client_ip"),
        telemetry.get("client_IP"),
        telemetry.get("clientIp"),
        telemetry.get("clientIP"),
        _safe_get(telemetry, "context", "client", "ip"),
        _safe_get(telemetry, "context", "client", "ipAddress"),
        _safe_get(telemetry, "context", "location", "clientIp"),
        _safe_get(telemetry, "context", "location", "clientip"),
        _safe_get(telemetry, "client", "ip"),
        _safe_get(telemetry, "client", "ipAddress"),
        _safe_get(telemetry, "properties", "clientIp"),
        _safe_get(telemetry, "customDimensions", "clientIp"),
        _safe_get(telemetry, "tags", "ai.location.ip"),
    )

    if source_ip is None:
        raise ValueError("Missing valid source/client IP")

    try:
        return str(ipaddress.ip_address(str(source_ip).strip()))
    except ValueError as error:
        raise ValueError("Missing valid source/client IP") from error


def _normalize_status_code(value):
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        digits = value.strip()
        if digits.isdigit():
            return int(digits)

    return None


def _build_exception_message(base_data, telemetry, operation_name):
    return _first_non_empty_value(
        base_data.get("message"),
        telemetry.get("message"),
        _safe_get(base_data, "exceptions", 0, "message"),
        _safe_get(base_data, "exceptions", 0, "typeName"),
        operation_name,
        "Azure application exception detected",
    )


def _build_availability_message(base_data, telemetry, operation_name):
    return _first_non_empty_value(
        base_data.get("message"),
        telemetry.get("message"),
        operation_name,
        "Azure availability failure detected",
    )


def _build_http_error_message(base_data, telemetry, operation_name, result_code):
    return _first_non_empty_value(
        base_data.get("message"),
        telemetry.get("message"),
        operation_name,
        f"Azure HTTP error telemetry detected: status {result_code}",
        "Azure HTTP error telemetry detected",
    )


def _build_request_message(base_data, telemetry, operation_name):
    return _first_non_empty_value(
        base_data.get("message"),
        telemetry.get("message"),
        operation_name,
        "Azure request telemetry observed",
    )


def _build_trace_message(base_data, telemetry, operation_name):
    return _first_non_empty_value(
        base_data.get("message"),
        telemetry.get("message"),
        operation_name,
        "Azure trace telemetry observed",
    )


def _extract_identity_source_ip(telemetry):
    source_ip = _first_non_empty_value(
        telemetry.get("sourceIp"),
        telemetry.get("source_ip"),
        telemetry.get("client_IP"),
        telemetry.get("clientIp"),
    )

    if source_ip is None:
        raise ValueError("Missing valid source/client IP")

    try:
        return str(ipaddress.ip_address(str(source_ip).strip()))
    except ValueError as error:
        raise ValueError("Missing valid source/client IP") from error


def _extract_identity_username(telemetry):
    username = _first_non_empty_value(
        telemetry.get("userPrincipalName"),
        telemetry.get("username"),
        telemetry.get("upn"),
    )
    if username is None:
        raise ValueError("Missing username")
    return str(username).strip()


def _normalize_identity_result(telemetry):
    result_value = _first_non_empty_value(
        telemetry.get("result"),
        telemetry.get("resultType"),
    )

    if result_value is None:
        raise ValueError("Missing or unrecognized login result")

    result_text = str(result_value).strip().lower()
    if not result_text:
        raise ValueError("Missing or unrecognized login result")

    if result_text in {"success", "0"}:
        return "successful_login", "low"

    if result_text == "failure":
        return "failed_login", "medium"

    if result_text.isdigit() and result_text != "0":
        return "failed_login", "medium"

    raise ValueError("Missing or unrecognized login result")


def normalize_azure_identity_telemetry(telemetry):
    if not isinstance(telemetry, dict) or not telemetry:
        raise ValueError("Telemetry item must be an object")

    source_ip = _extract_identity_source_ip(telemetry)
    username = _extract_identity_username(telemetry)
    event_type, severity = _normalize_identity_result(telemetry)

    message = _first_non_empty_value(
        telemetry.get("message"),
        telemetry.get("resultDescription"),
    )
    if message is None:
        if event_type == "failed_login":
            message = f"Azure login failure for {username} from {source_ip}"
        else:
            message = f"Azure login success for {username} from {source_ip}"

    event_timestamp = _first_non_empty_value(
        telemetry.get("timestamp"),
        telemetry.get("time"),
        telemetry.get("createdDateTime"),
    )

    return {
        "event_type": event_type,
        "severity": severity,
        "source_ip": source_ip,
        "username": username,
        "message": message,
        "event_timestamp": event_timestamp,
    }


def normalize_azure_insights_telemetry(telemetry):
    if not isinstance(telemetry, dict) or not telemetry:
        raise ValueError("Telemetry item must be an object")

    source_ip = _extract_source_ip(telemetry)

    data = telemetry.get("data")
    base_type = _first_non_empty_value(
        telemetry.get("baseType"),
        _safe_get(data, "baseType"),
    )
    base_data = data.get("baseData") if isinstance(data, dict) and isinstance(data.get("baseData"), dict) else {}
    telemetry_name = _first_non_empty_value(telemetry.get("name"), telemetry.get("telemetryType"), base_type)
    telemetry_name_lower = str(telemetry_name or "").lower()
    base_type_lower = str(base_type or "").lower()

    success_value = _first_non_empty_value(
        base_data.get("success"),
        telemetry.get("success"),
    )
    result_code = _normalize_status_code(
        _first_non_empty_value(
            base_data.get("responseCode"),
            base_data.get("resultCode"),
            telemetry.get("responseCode"),
            telemetry.get("resultCode"),
            telemetry.get("statusCode"),
        )
    )

    event_timestamp = _first_non_empty_value(
        telemetry.get("timestamp"),
        telemetry.get("time"),
        base_data.get("timestamp"),
    )

    operation_name = _first_non_empty_value(
        base_data.get("name"),
        telemetry.get("operationName"),
        telemetry.get("name"),
        "Azure telemetry event",
    )

    if "exception" in base_type_lower or "exception" in telemetry_name_lower:
        message = _build_exception_message(base_data, telemetry, operation_name)
        return {
            "event_type": "application_exception",
            "severity": "high",
            "source_ip": source_ip,
            "message": message,
            "event_timestamp": event_timestamp,
        }

    if "availability" in base_type_lower or "availability" in telemetry_name_lower:
        availability_success = base_data.get("success")
        if availability_success is False or str(availability_success).strip().lower() == "false":
            message = _build_availability_message(base_data, telemetry, operation_name)
            return {
                "event_type": "availability_failure",
                "severity": "high",
                "source_ip": source_ip,
                "message": message,
                "event_timestamp": event_timestamp,
            }

    if "request" in base_type_lower or "request" in telemetry_name_lower or "dependency" in base_type_lower or "dependency" in telemetry_name_lower:
        if result_code is not None and 500 <= result_code <= 599:
            message = _build_http_error_message(base_data, telemetry, operation_name, result_code)
            return {
                "event_type": "http_error",
                "severity": "medium",
                "source_ip": source_ip,
                "message": message,
                "event_timestamp": event_timestamp,
            }

        success_str = str(success_value).strip().lower() if success_value is not None else ""
        if result_code is not None or success_str in {"true", "false"}:
            message = _build_request_message(base_data, telemetry, operation_name)
            return {
                "event_type": "normal_activity",
                "severity": "low",
                "source_ip": source_ip,
                "message": message,
                "event_timestamp": event_timestamp,
            }

    if "trace" in base_type_lower or "trace" in telemetry_name_lower or "log" in base_type_lower or "log" in telemetry_name_lower:
        message = _build_trace_message(base_data, telemetry, operation_name)
        return {
            "event_type": "normal_activity",
            "severity": "low",
            "source_ip": source_ip,
            "message": message,
            "event_timestamp": event_timestamp,
        }

    raise ValueError("Unsupported Azure telemetry type")
