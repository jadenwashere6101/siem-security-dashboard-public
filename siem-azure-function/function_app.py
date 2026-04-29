import json
import logging
import os
import urllib.request
import urllib.error
from datetime import timedelta

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

SIEM_AZURE_INGEST_URL = os.environ["SIEM_AZURE_INGEST_URL"]
AZURE_INGEST_API_KEY = os.environ["AZURE_INGEST_API_KEY"]
LOG_ANALYTICS_WORKSPACE_ID = os.environ["LOG_ANALYTICS_WORKSPACE_ID"]
QUERY_WINDOW_MINUTES = 5
MAX_RECORDS = 25
UNKNOWN_AZURE_SERVICE = "unknown_azure_service"

APP_INSIGHTS_QUERY = f"""
let exceptionRows = AppExceptions
| where TimeGenerated >= ago({QUERY_WINDOW_MINUTES}m)
| project
    itemType = "exception",
    timestamp = TimeGenerated,
    operation_Name = OperationName,
    name = "",
    message = Message,
    client_IP = ClientIP,
    resultCode = "",
    cloud_RoleName = AppRoleName,
    severityLevel = SeverityLevel;
let requestRows = AppRequests
| where TimeGenerated >= ago({QUERY_WINDOW_MINUTES}m)
| where toint(ResultCode) in (401, 403) or toint(ResultCode) >= 500
| project
    itemType = "request",
    timestamp = TimeGenerated,
    operation_Name = OperationName,
    name = Name,
    message = Name,
    client_IP = ClientIP,
    resultCode = ResultCode,
    cloud_RoleName = AppRoleName,
    severityLevel = int(null);
union isfuzzy=true exceptionRows, requestRows
| where isnotempty(client_IP)
| order by timestamp asc
| take {MAX_RECORDS}
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

    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


def _query_recent_telemetry():
    credential = DefaultAzureCredential()
    client = LogsQueryClient(credential)
    result = client.query_workspace(
        workspace_id=LOG_ANALYTICS_WORKSPACE_ID,
        query=APP_INSIGHTS_QUERY,
        timespan=timedelta(minutes=QUERY_WINDOW_MINUTES),
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

    return {
        "status": "unmapped",
        "reason": "unsupported_item_type",
    }


def _row_to_siem_telemetry(row: dict, mapping: dict) -> dict:
    client_ip = row.get("client_IP")
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
        "baseType": "RequestData",
        "time": timestamp_text,
        "data": {
            "baseData": {
                "name": operation_name or request_name or message,
                "message": message,
                "responseCode": str(result_code),
            }
        }
    }


def _has_valid_client_ip(row: dict) -> bool:
    client_ip = row.get("client_IP")
    if client_ip is None:
        return False

    normalized = str(client_ip).strip()
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


@app.timer_trigger(schedule="0 */5 * * * *", arg_name="timer", run_on_startup=False)
def poll_application_insights(timer: func.TimerRequest) -> None:
    try:
        rows = _query_recent_telemetry()
    except Exception:
        logging.exception("Failed to query Application Insights telemetry")
        return

    mapping_counts = {
        "application_exception": 0,
        "unauthorized_access": 0,
        "http_error": 0,
    }
    forwarded = 0
    skipped_invalid_ip = 0
    unmapped_telemetry = 0
    missing_critical_fields = 0
    failures = 0
    sample_skipped_reason = None
    sample_skipped_row = None

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
            forward_telemetry_to_siem(telemetry)
            mapping_counts[mapping["event_type"]] += 1
            forwarded += 1
        except Exception:
            failures += 1
            logging.exception("Failed to forward Application Insights telemetry row")

    logging.info(
        "Application Insights mapping decisions: application_exception=%d unauthorized_access=%d http_error=%d unmapped_telemetry=%d missing_critical_fields=%d",
        mapping_counts["application_exception"],
        mapping_counts["unauthorized_access"],
        mapping_counts["http_error"],
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
        "Application Insights polling complete: returned=%d forwarded=%d skipped_invalid_ip=%d failures=%d unmapped_telemetry=%d missing_critical_fields=%d query_window_minutes=%d max_records=%d",
        len(rows),
        forwarded,
        skipped_invalid_ip,
        failures,
        unmapped_telemetry,
        missing_critical_fields,
        QUERY_WINDOW_MINUTES,
        MAX_RECORDS,
    )
