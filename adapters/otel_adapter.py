import ipaddress
from datetime import datetime, timezone

# OpenTelemetry JSON normalization helpers.
# Scope is intentionally narrow and maps only the approved subset of HTTP/error/
# exception-style telemetry used by the current SIEM ingestion path.

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


def _flatten_any_value(value):
    if isinstance(value, dict):
        for key in (
            "stringValue",
            "intValue",
            "doubleValue",
            "boolValue",
            "bytesValue",
        ):
            if key in value:
                return value[key]
        if "arrayValue" in value and isinstance(value["arrayValue"], dict):
            values = value["arrayValue"].get("values")
            if isinstance(values, list):
                return [_flatten_any_value(item) for item in values]
        if "kvlistValue" in value and isinstance(value["kvlistValue"], dict):
            return _normalize_attribute_container(value["kvlistValue"].get("values"))
    return value


def _normalize_attribute_container(attributes):
    if isinstance(attributes, dict):
        return attributes

    if not isinstance(attributes, list):
        return {}

    normalized = {}
    for item in attributes:
        if not isinstance(item, dict):
            continue

        key = item.get("key")
        if not isinstance(key, str) or not key:
            continue

        normalized[key] = _flatten_any_value(item.get("value"))

    return normalized


def _collect_attribute_maps(telemetry):
    maps = []
    for candidate in (
        telemetry.get("attributes"),
        _safe_get(telemetry, "resource", "attributes"),
        _safe_get(telemetry, "span", "attributes"),
        _safe_get(telemetry, "logRecord", "attributes"),
    ):
        normalized = _normalize_attribute_container(candidate)
        if normalized:
            maps.append(normalized)
    return maps


def _extract_attribute_value(telemetry, *keys):
    attribute_maps = _collect_attribute_maps(telemetry)
    for key in keys:
        direct_value = telemetry.get(key)
        if direct_value not in (None, ""):
            return direct_value

        for attribute_map in attribute_maps:
            value = attribute_map.get(key)
            if value not in (None, ""):
                return value

    return None


def _extract_source_ip(telemetry):
    source_ip = _first_non_empty_value(
        telemetry.get("source_ip"),
        telemetry.get("sourceIp"),
        _extract_attribute_value(telemetry, "source_ip", "net.peer.ip", "client.address", "http.client_ip"),
    )

    if source_ip is None:
        raise ValueError("Missing valid source/client IP")

    try:
        return str(ipaddress.ip_address(str(source_ip).strip()))
    except ValueError as error:
        raise ValueError("Missing valid source/client IP") from error


def _extract_app_name(telemetry):
    return _first_non_empty_value(
        _extract_attribute_value(telemetry, "service.name"),
    )


def _normalize_status_code(value):
    if value in (None, "") or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        digits = value.strip()
        if digits.isdigit():
            return int(digits)

    return None


def _normalize_event_timestamp(value):
    if value in (None, ""):
        return None

    if isinstance(value, str):
        digits = value.strip()
        if digits.isdigit():
            value = int(digits)
        else:
            return value

    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value / 1_000_000_000, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None

    return None


def normalize_otel_telemetry(telemetry):
    # Expects JSON-style OTEL payloads already accepted by the /ingest/otlp
    # route. This adapter is not intended to implement full OTLP coverage.
    if not isinstance(telemetry, dict) or not telemetry:
        raise ValueError("Telemetry item must be an object")

    source_ip = _extract_source_ip(telemetry)
    status_code = _normalize_status_code(
        _first_non_empty_value(
            telemetry.get("status_code"),
            telemetry.get("statusCode"),
            _extract_attribute_value(telemetry, "http.status_code", "status_code", "statusCode"),
        )
    )

    event_timestamp = _normalize_event_timestamp(
        _first_non_empty_value(
            telemetry.get("timeUnixNano"),
            telemetry.get("observedTimeUnixNano"),
            telemetry.get("startTimeUnixNano"),
            telemetry.get("timestamp"),
            telemetry.get("time"),
            _safe_get(telemetry, "span", "startTimeUnixNano"),
            _safe_get(telemetry, "logRecord", "timeUnixNano"),
        )
    )

    operation_name = _first_non_empty_value(
        telemetry.get("name"),
        telemetry.get("message"),
        _extract_attribute_value(telemetry, "http.target", "url.path", "http.route"),
        "OpenTelemetry event",
    )
    body = telemetry.get("body")
    body_text = body if isinstance(body, str) else None
    message = _first_non_empty_value(
        body_text,
        telemetry.get("message"),
        _extract_attribute_value(telemetry, "exception.message"),
    )
    app_name = _extract_app_name(telemetry)

    if status_code in {401, 403}:
        result = {
            "event_type": "unauthorized_access",
            "severity": "medium",
            "source_ip": source_ip,
            "message": message or f"Unauthorized HTTP telemetry detected: status {status_code} for {operation_name}",
            "event_timestamp": event_timestamp,
        }
        if app_name:
            result["app_name"] = app_name
        return result

    if status_code is not None and status_code >= 500:
        result = {
            "event_type": "http_error",
            "severity": "medium",
            "source_ip": source_ip,
            "message": message or f"HTTP error telemetry detected: status {status_code} for {operation_name}",
            "event_timestamp": event_timestamp,
        }
        if app_name:
            result["app_name"] = app_name
        return result

    status_value = _first_non_empty_value(
        _safe_get(telemetry, "status", "code"),
        telemetry.get("status"),
        _extract_attribute_value(telemetry, "otel.status_code"),
    )
    status_text = str(status_value).strip().lower() if status_value is not None else ""
    exception_type = _extract_attribute_value(telemetry, "exception.type")

    if exception_type or status_text in {"error", "2"}:
        result = {
            "event_type": "application_exception",
            "severity": "high",
            "source_ip": source_ip,
            "message": message or f"Application exception telemetry detected: {operation_name}",
            "event_timestamp": event_timestamp,
        }
        if app_name:
            result["app_name"] = app_name
        return result

    if status_code is not None:
        result = {
            "event_type": "normal_activity",
            "severity": "low",
            "source_ip": source_ip,
            "message": message or f"Successful HTTP telemetry observed: {operation_name}",
            "event_timestamp": event_timestamp,
        }
        if app_name:
            result["app_name"] = app_name
        return result

    result = {
        "event_type": "normal_activity",
        "severity": "low",
        "source_ip": source_ip,
        "message": message or f"OpenTelemetry event observed: {operation_name}",
        "event_timestamp": event_timestamp,
    }
    if app_name:
        result["app_name"] = app_name
    return result
