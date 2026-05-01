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
