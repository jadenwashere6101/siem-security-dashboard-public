# spec: SPEC-INGEST-001
# spec: SPEC-NORM-001
HONEYPOT_EVENT_TYPES = frozenset({
    "env_probe",
    "admin_probe",
    "scanner_detected",
    "credential_stuffing",
    "http_error",
})

RAW_PASSWORD_FIELD_NAMES = frozenset({
    "password",
    "passwd",
    "pwd",
    "user_password",
})


def reject_raw_password_fields(event_dict):
    event_type = event_dict.get("event_type")
    if event_type not in HONEYPOT_EVENT_TYPES:
        return

    _reject_raw_password_fields_recursive(event_dict)


def _reject_raw_password_fields_recursive(value, path="payload"):
    if isinstance(value, dict):
        for key, child_value in value.items():
            key_text = str(key).strip().lower()
            child_path = f"{path}.{key}" if path else str(key)
            if key_text in RAW_PASSWORD_FIELD_NAMES:
                raise ValueError(f"Raw password field '{child_path}' is not allowed")
            _reject_raw_password_fields_recursive(child_value, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_raw_password_fields_recursive(item, f"{path}[{index}]")


def _safe_non_empty_string(value):
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def _get_azure_app_name(telemetry_item):
    if not isinstance(telemetry_item, dict):
        return "azure_application_insights"

    return _safe_non_empty_string(telemetry_item.get("cloud_RoleName")) or "azure_application_insights"


def _is_azure_identity_payload(telemetry_item):
    if not isinstance(telemetry_item, dict):
        return False

    return str(telemetry_item.get("baseType") or "").strip() in {"SignInData", "SignInLog"}


def has_valid_location(location):
    if not isinstance(location, dict):
        return False

    lat = location.get("lat")
    lon = location.get("lon")
    return lat not in (None, "") and lon not in (None, "")


def _get_azure_identity_app_name(telemetry_item):
    if not isinstance(telemetry_item, dict):
        return "azure_identity"

    return (
        _safe_non_empty_string(telemetry_item.get("appDisplayName"))
        or _safe_non_empty_string(telemetry_item.get("app_name"))
        or "azure_identity"
    )


def _get_otel_app_name(normalized_telemetry, telemetry_item):
    normalized_name = _safe_non_empty_string(
        normalized_telemetry.get("app_name") if isinstance(normalized_telemetry, dict) else None
    )
    if normalized_name:
        return normalized_name

    payload_name = _safe_non_empty_string(
        telemetry_item.get("serviceName") if isinstance(telemetry_item, dict) else None
    )
    if payload_name:
        return payload_name

    return "opentelemetry"
