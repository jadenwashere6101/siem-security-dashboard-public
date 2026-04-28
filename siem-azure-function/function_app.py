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
SIEM_AZURE_INGEST_API_KEY = os.environ["SIEM_AZURE_INGEST_API_KEY"]
LOG_ANALYTICS_WORKSPACE_ID = os.environ["LOG_ANALYTICS_WORKSPACE_ID"]

APP_INSIGHTS_QUERY = """
union isfuzzy=true
(
    exceptions
    | where timestamp >= ago(5m)
    | project
        itemType = "exception",
        timestamp,
        operation_Name,
        message,
        client_IP,
        resultCode = ""
),
(
    requests
    | where timestamp >= ago(5m)
    | where toint(resultCode) in (401, 403) or toint(resultCode) >= 500
    | project
        itemType = "request",
        timestamp,
        operation_Name,
        message = name,
        client_IP,
        resultCode
)
| where isnotempty(client_IP)
| order by timestamp asc
| take 25
""".strip()


def forward_telemetry_to_siem(telemetry: dict):
    body = json.dumps(telemetry).encode("utf-8")

    req = urllib.request.Request(
        SIEM_AZURE_INGEST_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": SIEM_AZURE_INGEST_API_KEY,
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
        timespan=timedelta(minutes=5),
    )

    tables = getattr(result, "tables", None) or []
    if not tables:
        return []

    table = tables[0]
    column_names = [column.name for column in table.columns]

    return [dict(zip(column_names, row)) for row in table.rows]


def _row_to_siem_telemetry(row: dict) -> dict:
    item_type = row.get("itemType")
    client_ip = row.get("client_IP")
    timestamp = row.get("timestamp")
    operation_name = row.get("operation_Name") or ""
    message = row.get("message") or operation_name or "Azure Application Insights event"
    result_code = str(row.get("resultCode") or "")

    if item_type == "exception":
        return {
            "client_IP": client_ip,
            "baseType": "ExceptionData",
            "time": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
            "data": {
                "baseData": {
                    "message": message,
                }
            },
        }

    return {
        "client_IP": client_ip,
        "baseType": "RequestData",
        "time": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
        "data": {
            "baseData": {
                "name": operation_name or message,
                "message": message,
                "responseCode": result_code,
            }
        },
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

    forwarded = 0
    skipped_invalid_ip = 0
    failures = 0

    for row in rows:
        if not _has_valid_client_ip(row):
            skipped_invalid_ip += 1
            continue

        try:
            telemetry = _row_to_siem_telemetry(row)
            forward_telemetry_to_siem(telemetry)
            forwarded += 1
        except Exception:
            failures += 1
            logging.exception("Failed to forward Application Insights telemetry row")

    logging.info(
        "Application Insights polling complete: returned=%d forwarded=%d skipped_invalid_ip=%d failures=%d",
        len(rows),
        forwarded,
        skipped_invalid_ip,
        failures,
    )
