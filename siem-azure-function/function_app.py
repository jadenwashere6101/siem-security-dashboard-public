import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

SIEM_AZURE_INGEST_URL = os.environ["SIEM_AZURE_INGEST_URL"]
AZURE_INGEST_API_KEY = os.environ["AZURE_INGEST_API_KEY"]
LOG_ANALYTICS_WORKSPACE_ID = os.environ["LOG_ANALYTICS_WORKSPACE_ID"]
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "25"))
MAX_POLL_PAGES = int(os.getenv("MAX_POLL_PAGES", "10"))
QUERY_RETRY_ATTEMPTS = int(os.getenv("QUERY_RETRY_ATTEMPTS", "3"))
FORWARD_RETRY_ATTEMPTS = int(os.getenv("FORWARD_RETRY_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "1"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
CHECKPOINT_ENDPOINT_URL = (
    SIEM_AZURE_INGEST_URL.rstrip("/") + "/checkpoint"
    if SIEM_AZURE_INGEST_URL.rstrip("/").endswith("/ingest/azure")
    else SIEM_AZURE_INGEST_URL.rstrip("/") + "/ingest/azure/checkpoint"
)
CHECKPOINT_FALLBACK_MINUTES = 15
CHECKPOINT_FALLBACK_MAX_MINUTES = 60
UNKNOWN_AZURE_SERVICE = "unknown_azure_service"


def _utc_now():
    return datetime.now(timezone.utc)


def _format_kql_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _fallback_checkpoint():
    now = _utc_now()
    return now - timedelta(
        minutes=max(CHECKPOINT_FALLBACK_MINUTES, min(CHECKPOINT_FALLBACK_MAX_MINUTES, 60))
    )


def _build_app_insights_query(lower_bound, upper_bound):
    lower_text = _format_kql_datetime(lower_bound)
    upper_text = _format_kql_datetime(upper_bound)
    return f"""
let exceptionRows = AppExceptions
| where TimeGenerated > datetime({lower_text}) and TimeGenerated <= datetime({upper_text})
| project
    itemType = "exception",
    timestamp = TimeGenerated,
    operation_Name = OperationName,
    name = "",
    message = Message,
    client_IP = ClientIP,
    resultCode = "",
    cloud_RoleName = AppRoleName,
    severityLevel = SeverityLevel,
    success = bool(null),
    customDimensions = Properties;
let requestRows = AppRequests
| where TimeGenerated > datetime({lower_text}) and TimeGenerated <= datetime({upper_text})
| where isnotempty(ClientIP)
| project
    itemType = "request",
    timestamp = TimeGenerated,
    operation_Name = OperationName,
    name = Name,
    message = Name,
    client_IP = ClientIP,
    resultCode = ResultCode,
    cloud_RoleName = AppRoleName,
    severityLevel = int(null),
    success = bool(null),
    customDimensions = Properties;
let dependencyRows = AppDependencies
| where TimeGenerated > datetime({lower_text}) and TimeGenerated <= datetime({upper_text})
| where Success == false
| project
    itemType = "dependency",
    timestamp = TimeGenerated,
    operation_Name = OperationName,
    name = Name,
    message = Name,
    client_IP = ClientIP,
    resultCode = ResultCode,
    cloud_RoleName = AppRoleName,
    severityLevel = int(null),
    success = Success,
    customDimensions = Properties;
let availabilityRows = AppAvailabilityResults
| where TimeGenerated > datetime({lower_text}) and TimeGenerated <= datetime({upper_text})
| where Success == false
| project
    itemType = "availability",
    timestamp = TimeGenerated,
    operation_Name = Name,
    name = Name,
    message = Message,
    client_IP = ClientIP,
    resultCode = "",
    cloud_RoleName = AppRoleName,
    severityLevel = int(null),
    success = Success,
    customDimensions = Properties;
union isfuzzy=true exceptionRows, requestRows, dependencyRows, availabilityRows
| order by timestamp asc
| take {PAGE_SIZE}
""".strip()


def forward_telemetry_to_siem(telemetry: dict):
    body = json.dumps(telemetry).encode("utf-8")

    req = urllib.request.Request(
        SIEM_AZURE_INGEST_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": AZURE_INGEST_API_KEY,
        },
    )

    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return resp.status, resp.read().decode("utf-8")


def _fetch_checkpoint():
    req = urllib.request.Request(
        CHECKPOINT_ENDPOINT_URL,
        method="GET",
        headers={"X-API-Key": AZURE_INGEST_API_KEY},
    )

    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    raw_value = payload.get("last_processed_at")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return _fallback_checkpoint()

    normalized = raw_value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return _fallback_checkpoint()
    return parsed.astimezone(timezone.utc)


def _persist_checkpoint(last_processed_at, poll_status, poll_counts):
    body = json.dumps(
        {
            "last_processed_at": last_processed_at.isoformat() if last_processed_at else None,
            "last_poll_status": poll_status,
            "last_poll_counts": poll_counts,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        CHECKPOINT_ENDPOINT_URL,
        data=body,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": AZURE_INGEST_API_KEY,
        },
    )

    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return resp.status, resp.read().decode("utf-8")


def _retry(operation, *, attempts, backoff_seconds, operation_name):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt >= attempts:
                break
            logging.warning(
                "%s attempt %d/%d failed: %s",
                operation_name,
                attempt,
                attempts,
                error,
            )
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    raise last_error


def _query_recent_telemetry(lower_bound, upper_bound):
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)
    query = _build_app_insights_query(lower_bound, upper_bound)
    result = client.query_workspace(
        workspace_id=LOG_ANALYTICS_WORKSPACE_ID,
        query=query,
        timespan=max(upper_bound - lower_bound, timedelta(minutes=1)),
    )

    tables = getattr(result, "tables", None) or []
    if not tables:
        return []

    table = tables[0]
    column_names = table.columns

    return [dict(zip(column_names, row)) for row in table.rows]


def _normalize_result_code(value):
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    value_text = str(value).strip()
    return int(value_text) if value_text.isdigit() else None


def _serialize_log_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _sample_row_for_logging(row: dict) -> dict:
    return {key: _serialize_log_value(value) for key, value in row.items()}


def _normalize_custom_dimensions(value):
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    return {}


def _extract_real_client_ip(row: dict) -> str:
    custom_dimensions = _normalize_custom_dimensions(row.get("customDimensions"))
    candidate = custom_dimensions.get("client_IP")
    if candidate in (None, ""):
        candidate = custom_dimensions.get("x-forwarded-for")
    if candidate in (None, ""):
        candidate = row.get("client_IP")
    if candidate in (None, ""):
        message = str(row.get("message") or "")
        marker = "real_ip="
        if marker in message:
            candidate = message.split(marker, 1)[1].split(",", 1)[0].strip()

    candidate_text = str(candidate).split(",")[0].strip() if candidate not in (None, "") else ""
    if candidate_text.count(":") == 1:
        host, port = candidate_text.rsplit(":", 1)
        if port.isdigit():
            candidate_text = host.strip()
    return candidate_text


def _classify_telemetry_row(row: dict) -> dict:
    item_type = str(row.get("itemType") or "").strip().lower()

    if item_type == "exception":
        return {
            "status": "mapped",
            "event_type": "application_exception",
        }

    if item_type == "request":
        result_code = _normalize_result_code(row.get("resultCode"))
        if result_code is None:
            return {
                "status": "missing_critical",
                "reason": "missing_result_code",
            }

        if result_code in {401, 403}:
            return {
                "status": "mapped",
                "event_type": "unauthorized_access",
                "response_code": result_code,
            }

        if result_code >= 500:
            return {
                "status": "mapped",
                "event_type": "http_error",
                "response_code": result_code,
            }

        return {
            "status": "unmapped",
            "reason": "unsupported_request_result_code",
        }

    if item_type == "dependency":
        result_code = _normalize_result_code(row.get("resultCode"))
        success_value = row.get("success")
        success_text = str(success_value).strip().lower() if success_value is not None else ""
        if result_code in {401, 403}:
            return {
                "status": "mapped",
                "event_type": "unauthorized_access",
                "response_code": result_code,
            }
        if result_code is not None and result_code >= 500:
            return {
                "status": "mapped",
                "event_type": "http_error",
                "response_code": result_code,
            }
        if success_text == "false":
            return {
                "status": "mapped",
                "event_type": "dependency_failure",
                "response_code": result_code,
            }
        return {
            "status": "unmapped",
            "reason": "unsupported_dependency_result",
        }

    if item_type == "availability":
        return {
            "status": "mapped",
            "event_type": "availability_failure",
        }

    return {
        "status": "unmapped",
        "reason": "unsupported_item_type",
    }


def _row_to_siem_telemetry(row: dict, mapping: dict) -> dict:
    client_ip = _extract_real_client_ip(row)
    timestamp = row.get("timestamp")
    timestamp_text = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
    operation_name = str(row.get("operation_Name") or "").strip()
    request_name = str(row.get("name") or "").strip()
    app_name = str(row.get("cloud_RoleName") or "").strip() or UNKNOWN_AZURE_SERVICE
    default_message = "Azure Application Insights event"
    message = (
        str(row.get("message") or "").strip()
        or operation_name
        or request_name
        or default_message
    )
    severity_level = row.get("severityLevel")
    result_code = mapping.get("response_code")
    event_type = mapping["event_type"]

    if event_type == "application_exception":
        return {
            "client_IP": client_ip,
            "source_ip": client_ip,
            "event_type": event_type,
            "message": message,
            "app_name": app_name,
            "timestamp": timestamp_text,
            "severity": severity_level,
            "raw_payload": _sample_row_for_logging(row),
            "cloud_RoleName": row.get("cloud_RoleName"),
            "operationName": operation_name,
            "baseType": "ExceptionData",
            "time": timestamp_text,
            "data": {
                "baseData": {
                    "message": message,
                    "name": operation_name or request_name,
                }
            }
        }

    if event_type == "availability_failure":
        return {
            "client_IP": client_ip,
            "source_ip": client_ip,
            "event_type": event_type,
            "message": message,
            "app_name": app_name,
            "timestamp": timestamp_text,
            "raw_payload": _sample_row_for_logging(row),
            "cloud_RoleName": row.get("cloud_RoleName"),
            "operationName": operation_name,
            "success": False,
            "baseType": "AvailabilityData",
            "time": timestamp_text,
            "data": {
                "baseData": {
                    "name": operation_name or request_name or message,
                    "message": message,
                    "success": False,
                }
            },
        }

    return {
        "client_IP": client_ip,
        "source_ip": client_ip,
        "event_type": event_type,
        "message": message,
        "app_name": app_name,
        "response_code": str(result_code),
        "timestamp": timestamp_text,
        "raw_payload": _sample_row_for_logging(row),
        "cloud_RoleName": row.get("cloud_RoleName"),
        "operationName": operation_name,
        "success": bool(False) if event_type == "dependency_failure" else row.get("success"),
        "baseType": "RemoteDependencyData" if event_type == "dependency_failure" else "RequestData",
        "time": timestamp_text,
        "data": {
            "baseData": {
                "name": operation_name or request_name or message,
                "message": message,
                "responseCode": str(result_code),
                "success": False if event_type == "dependency_failure" else row.get("success"),
            }
        }
    }


def _has_valid_client_ip(row: dict) -> bool:
    normalized = _extract_real_client_ip(row)
    return bool(normalized) and normalized != "0.0.0.0"


@app.route(route="forward_one", methods=["POST"])
def forward_one(req: func.HttpRequest) -> func.HttpResponse:
    try:
        telemetry = req.get_json()

        status, response = forward_telemetry_to_siem(telemetry)

        return func.HttpResponse(
            json.dumps({
                "message": "Forwarded to SIEM",
                "siem_status": status,
                "siem_response": response
            }),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.exception("Error forwarding telemetry")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="test_endpoint", methods=["GET"])
def test_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    forwarded_for = req.headers.get("X-Forwarded-For", "")
    real_ip = forwarded_for.split(",")[0].strip() if forwarded_for else ""
    if not real_ip:
        real_ip = req.headers.get("X-Client-IP", "").strip()
    if not real_ip:
        real_ip = "unknown"

    logging.info(
        "HTTP request received: real_ip=%s, user_agent=%s, path=%s",
        real_ip,
        req.headers.get("User-Agent"),
        req.url,
    )
    return func.HttpResponse(
        json.dumps({"status": "ok"}),
        status_code=200,
        mimetype="application/json",
    )


@app.timer_trigger(schedule="0 */5 * * * *", arg_name="timer", run_on_startup=False)
def poll_application_insights(timer: func.TimerRequest) -> None:
    try:
        checkpoint = _fetch_checkpoint()
    except Exception:
        logging.exception("Failed to read Application Insights checkpoint; using bounded fallback")
        checkpoint = _fallback_checkpoint()

    poll_upper_bound = _utc_now()
    watermark = checkpoint

    mapping_counts = {
        "application_exception": 0,
        "unauthorized_access": 0,
        "http_error": 0,
        "dependency_failure": 0,
        "availability_failure": 0,
    }
    returned = 0
    forwarded = 0
    skipped_invalid_ip = 0
    unmapped_telemetry = 0
    missing_critical_fields = 0
    failures = 0
    pages_processed = 0
    sample_skipped_reason = None
    sample_skipped_row = None
    poll_status = "success"

    for _page in range(MAX_POLL_PAGES):
        try:
            rows = _retry(
                lambda: _query_recent_telemetry(watermark, poll_upper_bound),
                attempts=QUERY_RETRY_ATTEMPTS,
                backoff_seconds=RETRY_BACKOFF_SECONDS,
                operation_name="Application Insights query",
            )
        except Exception:
            poll_status = "failure" if pages_processed == 0 else "partial"
            failures += 1
            logging.exception("Failed to query Application Insights telemetry after retries")
            break

        if not rows:
            break

        returned += len(rows)
        pages_processed += 1
        page_failed = False

        for row in rows:
            if not _has_valid_client_ip(row):
                skipped_invalid_ip += 1
                continue

            mapping = _classify_telemetry_row(row)
            if mapping["status"] == "missing_critical":
                missing_critical_fields += 1
                if sample_skipped_row is None:
                    sample_skipped_reason = mapping["reason"]
                    sample_skipped_row = _sample_row_for_logging(row)
                continue

            if mapping["status"] == "unmapped":
                unmapped_telemetry += 1
                if sample_skipped_row is None:
                    sample_skipped_reason = mapping["reason"]
                    sample_skipped_row = _sample_row_for_logging(row)
                continue

            try:
                telemetry = _row_to_siem_telemetry(row, mapping)
                _retry(
                    lambda telemetry=telemetry: forward_telemetry_to_siem(telemetry),
                    attempts=FORWARD_RETRY_ATTEMPTS,
                    backoff_seconds=RETRY_BACKOFF_SECONDS,
                    operation_name="Application Insights forward",
                )
                mapping_counts[mapping["event_type"]] += 1
                forwarded += 1
            except Exception:
                failures += 1
                page_failed = True
                logging.exception("Failed to forward Application Insights telemetry row after retries")
                break

        if page_failed:
            poll_status = "failure" if pages_processed == 1 else "partial"
            break

        last_timestamp = rows[-1].get("timestamp")
        if isinstance(last_timestamp, datetime):
            watermark = last_timestamp.astimezone(timezone.utc)

        if len(rows) < PAGE_SIZE:
            break

    poll_counts = {
        "returned": returned,
        "forwarded": forwarded,
        "skipped_invalid_ip": skipped_invalid_ip,
        "failures": failures,
        "unmapped_telemetry": unmapped_telemetry,
        "missing_critical_fields": missing_critical_fields,
        "pages_processed": pages_processed,
        "page_size": PAGE_SIZE,
        "max_poll_pages": MAX_POLL_PAGES,
    }

    try:
        _persist_checkpoint(watermark, poll_status, poll_counts)
    except Exception:
        logging.exception("Failed to persist Application Insights checkpoint")

    logging.info(
        "Application Insights mapping decisions: application_exception=%d unauthorized_access=%d http_error=%d dependency_failure=%d availability_failure=%d unmapped_telemetry=%d missing_critical_fields=%d",
        mapping_counts["application_exception"],
        mapping_counts["unauthorized_access"],
        mapping_counts["http_error"],
        mapping_counts["dependency_failure"],
        mapping_counts["availability_failure"],
        unmapped_telemetry,
        missing_critical_fields,
    )

    if sample_skipped_row is not None:
        logging.warning(
            "Application Insights skipped sample: reason=%s sample_row=%s",
            sample_skipped_reason,
            json.dumps(sample_skipped_row, default=str),
        )

    logging.info(
        "Application Insights polling complete: status=%s returned=%d forwarded=%d skipped_invalid_ip=%d failures=%d unmapped_telemetry=%d missing_critical_fields=%d pages_processed=%d page_size=%d max_poll_pages=%d checkpoint=%s poll_upper_bound=%s",
        poll_status,
        returned,
        forwarded,
        skipped_invalid_ip,
        failures,
        unmapped_telemetry,
        missing_critical_fields,
        pages_processed,
        PAGE_SIZE,
        MAX_POLL_PAGES,
        watermark.isoformat() if watermark else None,
        poll_upper_bound.isoformat(),
    )
