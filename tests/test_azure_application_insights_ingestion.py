from __future__ import annotations

import importlib.util
import json
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from adapters.azure_insights_adapter import normalize_azure_insights_telemetry


def _load_function_app_module():
    module_name = "tests.siem_azure_function_app"
    if module_name in sys.modules:
        return sys.modules[module_name]

    azure_module = types.ModuleType("azure")
    functions_module = types.ModuleType("azure.functions")
    identity_module = types.ModuleType("azure.identity")
    monitor_module = types.ModuleType("azure.monitor")
    query_module = types.ModuleType("azure.monitor.query")

    class _FunctionApp:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            return lambda func: func

        def timer_trigger(self, *args, **kwargs):
            return lambda func: func

    class _AuthLevel:
        FUNCTION = "function"

    class _HttpResponse:
        def __init__(self, body, status_code=200, mimetype="application/json"):
            self.body = body
            self.status_code = status_code
            self.mimetype = mimetype

    functions_module.FunctionApp = _FunctionApp
    functions_module.AuthLevel = _AuthLevel
    functions_module.HttpResponse = _HttpResponse
    functions_module.HttpRequest = object
    functions_module.TimerRequest = object
    identity_module.DefaultAzureCredential = object
    query_module.LogsQueryClient = object

    sys.modules.setdefault("azure", azure_module)
    sys.modules["azure.functions"] = functions_module
    sys.modules["azure.identity"] = identity_module
    sys.modules["azure.monitor"] = monitor_module
    sys.modules["azure.monitor.query"] = query_module

    module_path = (
        Path(__file__).resolve().parent.parent / "siem-azure-function" / "function_app.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        "os.environ",
        {
            "SIEM_AZURE_INGEST_URL": "https://siem.example/api/ingest/azure",
            "AZURE_INGEST_API_KEY": "azure-key",
            "LOG_ANALYTICS_WORKSPACE_ID": "workspace-id",
        },
        clear=False,
    ):
        assert spec.loader is not None
        spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


def _request_telemetry(*, response_code):
    return {
        "client_IP": "198.51.100.50",
        "baseType": "RequestData",
        "time": "2026-07-14T12:00:00+00:00",
        "cloud_RoleName": "orders-api",
        "operationName": "GET /api/orders",
        "data": {
            "baseData": {
                "name": "GET /api/orders",
                "message": "GET /api/orders",
                "responseCode": str(response_code),
            }
        },
    }


def test_unauthorized_request_classification_matches_function_and_backend():
    function_app = _load_function_app_module()
    row = {
        "itemType": "request",
        "resultCode": "401",
        "client_IP": "198.51.100.50",
        "timestamp": datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        "operation_Name": "GET /api/orders",
        "name": "GET /api/orders",
        "message": "GET /api/orders",
        "cloud_RoleName": "orders-api",
        "customDimensions": {},
    }

    assert function_app._classify_telemetry_row(row) == {
        "status": "mapped",
        "event_type": "unauthorized_access",
        "response_code": 401,
    }
    normalized = normalize_azure_insights_telemetry(_request_telemetry(response_code=401))
    assert normalized["event_type"] == "unauthorized_access"
    assert normalized["severity"] == "medium"


def test_dependency_and_availability_failures_classify_consistently():
    function_app = _load_function_app_module()
    dependency_row = {
        "itemType": "dependency",
        "resultCode": "0",
        "success": False,
        "client_IP": "198.51.100.60",
        "timestamp": datetime(2026, 7, 14, 12, 5, tzinfo=timezone.utc),
        "operation_Name": "sql-call",
        "name": "sql-call",
        "message": "sql-call",
        "cloud_RoleName": "orders-api",
        "customDimensions": {},
    }
    availability_row = {
        "itemType": "availability",
        "success": False,
        "client_IP": "198.51.100.61",
        "timestamp": datetime(2026, 7, 14, 12, 6, tzinfo=timezone.utc),
        "operation_Name": "home-page-check",
        "name": "home-page-check",
        "message": "health check failed",
        "cloud_RoleName": "orders-api",
        "customDimensions": {},
    }

    assert function_app._classify_telemetry_row(dependency_row)["event_type"] == "dependency_failure"
    assert function_app._classify_telemetry_row(availability_row)["event_type"] == "availability_failure"

    normalized_dependency = normalize_azure_insights_telemetry(
        {
            "client_IP": "198.51.100.60",
            "baseType": "RemoteDependencyData",
            "time": "2026-07-14T12:05:00+00:00",
            "cloud_RoleName": "orders-api",
            "operationName": "sql-call",
            "success": False,
            "data": {"baseData": {"name": "sql-call", "message": "sql-call", "success": False}},
        }
    )
    assert normalized_dependency["event_type"] == "dependency_failure"

    normalized_availability = normalize_azure_insights_telemetry(
        {
            "client_IP": "198.51.100.61",
            "baseType": "AvailabilityData",
            "time": "2026-07-14T12:06:00+00:00",
            "cloud_RoleName": "orders-api",
            "data": {
                "baseData": {
                    "name": "home-page-check",
                    "message": "health check failed",
                    "success": False,
                }
            },
        }
    )
    assert normalized_availability["event_type"] == "availability_failure"


def test_successful_dependency_and_demo_trace_are_not_supported():
    function_app = _load_function_app_module()
    successful_dependency = {
        "itemType": "dependency",
        "resultCode": "200",
        "success": True,
        "client_IP": "198.51.100.70",
        "timestamp": datetime(2026, 7, 14, 12, 10, tzinfo=timezone.utc),
        "operation_Name": "redis-call",
        "name": "redis-call",
        "message": "redis-call",
        "cloud_RoleName": "orders-api",
        "customDimensions": {},
    }

    assert function_app._classify_telemetry_row(successful_dependency)["status"] == "unmapped"
    with pytest.raises(ValueError, match="Unsupported Azure telemetry type"):
        normalize_azure_insights_telemetry(
            {
                "client_IP": "198.51.100.71",
                "baseType": "TraceData",
                "time": "2026-07-14T12:11:00+00:00",
                "message": "HTTP request received: demo",
                "data": {"baseData": {"message": "HTTP request received: demo"}},
            }
        )


def test_query_includes_dependencies_and_availability_and_excludes_demo_traces():
    function_app = _load_function_app_module()
    query = function_app._build_app_insights_query(
        datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 14, 12, 10, tzinfo=timezone.utc),
    )

    assert "AppDependencies" in query
    assert "AppAvailabilityResults" in query
    assert "AppTraces" not in query
    assert "HTTP request received" not in query


def test_polling_pages_updates_checkpoint_and_avoids_gap_loss():
    function_app = _load_function_app_module()
    start = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    second = start + timedelta(minutes=1)
    third = start + timedelta(minutes=2)

    page_one = [
        {
            "itemType": "request",
            "resultCode": "401",
            "client_IP": "198.51.100.80",
            "timestamp": start,
            "operation_Name": "GET /api/orders",
            "name": "GET /api/orders",
            "message": "GET /api/orders",
            "cloud_RoleName": "orders-api",
            "customDimensions": {},
        },
        {
            "itemType": "request",
            "resultCode": "403",
            "client_IP": "198.51.100.80",
            "timestamp": second,
            "operation_Name": "GET /api/orders",
            "name": "GET /api/orders",
            "message": "GET /api/orders",
            "cloud_RoleName": "orders-api",
            "customDimensions": {},
        },
    ]
    page_two = [
        {
            "itemType": "exception",
            "client_IP": "198.51.100.80",
            "timestamp": third,
            "operation_Name": "GET /api/orders",
            "name": "",
            "message": "boom",
            "cloud_RoleName": "orders-api",
            "customDimensions": {},
            "severityLevel": 3,
        }
    ]
    query_calls = []
    persisted = {}
    forwarded = []

    def fake_query(lower_bound, upper_bound):
        query_calls.append((lower_bound, upper_bound))
        if len(query_calls) == 1:
            return page_one
        if len(query_calls) == 2:
            assert lower_bound == second
            return page_two
        assert lower_bound == third
        return []

    with patch.object(function_app, "PAGE_SIZE", 2), patch.object(
        function_app, "MAX_POLL_PAGES", 3
    ), patch.object(function_app, "_fetch_checkpoint", return_value=start - timedelta(minutes=1)), patch.object(
        function_app, "_query_recent_telemetry", side_effect=fake_query
    ), patch.object(
        function_app, "_persist_checkpoint", side_effect=lambda ts, status, counts: persisted.update(
            {"timestamp": ts, "status": status, "counts": counts}
        )
    ), patch.object(
        function_app, "forward_telemetry_to_siem", side_effect=lambda payload: forwarded.append(payload)
    ):
        function_app.poll_application_insights(None)

    assert len(forwarded) == 3
    assert persisted["timestamp"] == third
    assert persisted["status"] == "success"
    assert persisted["counts"]["pages_processed"] == 2
    assert query_calls[0][0] == start - timedelta(minutes=1)


def test_polling_retries_query_and_forward_failures_before_succeeding():
    function_app = _load_function_app_module()
    row_time = datetime(2026, 7, 14, 12, 15, tzinfo=timezone.utc)
    row = {
        "itemType": "request",
        "resultCode": "401",
        "client_IP": "198.51.100.90",
        "timestamp": row_time,
        "operation_Name": "GET /api/orders",
        "name": "GET /api/orders",
        "message": "GET /api/orders",
        "cloud_RoleName": "orders-api",
        "customDimensions": {},
    }
    query_attempts = {"count": 0}
    forward_attempts = {"count": 0}
    persisted = {}

    def flaky_query(lower_bound, upper_bound):
        query_attempts["count"] += 1
        if query_attempts["count"] == 1:
            raise RuntimeError("transient query failure")
        if query_attempts["count"] == 2:
            return [row]
        return []

    def flaky_forward(payload):
        forward_attempts["count"] += 1
        if forward_attempts["count"] < 3:
            raise RuntimeError("transient forward failure")
        return 201, json.dumps({"ok": True})

    with patch.object(function_app, "PAGE_SIZE", 5), patch.object(
        function_app, "_fetch_checkpoint", return_value=row_time - timedelta(minutes=1)
    ), patch.object(
        function_app, "_query_recent_telemetry", side_effect=flaky_query
    ), patch.object(
        function_app, "forward_telemetry_to_siem", side_effect=flaky_forward
    ), patch.object(
        function_app, "_persist_checkpoint", side_effect=lambda ts, status, counts: persisted.update(
            {"timestamp": ts, "status": status, "counts": counts}
        )
    ), patch.object(function_app.time, "sleep", return_value=None):
        function_app.poll_application_insights(None)

    assert query_attempts["count"] >= 2
    assert forward_attempts["count"] == 3
    assert persisted["status"] == "success"
    assert persisted["timestamp"] == row_time


def test_polling_does_not_advance_checkpoint_past_failed_page():
    function_app = _load_function_app_module()
    first = datetime(2026, 7, 14, 12, 20, tzinfo=timezone.utc)
    second = first + timedelta(minutes=1)
    query_rows = [
        {
            "itemType": "request",
            "resultCode": "401",
            "client_IP": "198.51.100.91",
            "timestamp": first,
            "operation_Name": "GET /api/orders",
            "name": "GET /api/orders",
            "message": "GET /api/orders",
            "cloud_RoleName": "orders-api",
            "customDimensions": {},
        },
        {
            "itemType": "exception",
            "client_IP": "198.51.100.91",
            "timestamp": second,
            "operation_Name": "GET /api/orders",
            "name": "",
            "message": "boom",
            "cloud_RoleName": "orders-api",
            "customDimensions": {},
            "severityLevel": 3,
        },
    ]
    persisted = {}

    def always_fail_forward(payload):
        if payload["event_type"] == "application_exception":
            raise RuntimeError("permanent forward failure")
        return 201, json.dumps({"ok": True})

    with patch.object(function_app, "_fetch_checkpoint", return_value=first - timedelta(minutes=1)), patch.object(
        function_app, "_query_recent_telemetry", side_effect=[query_rows]
    ), patch.object(
        function_app, "forward_telemetry_to_siem", side_effect=always_fail_forward
    ), patch.object(
        function_app, "_persist_checkpoint", side_effect=lambda ts, status, counts: persisted.update(
            {"timestamp": ts, "status": status, "counts": counts}
        )
    ), patch.object(function_app.time, "sleep", return_value=None):
        function_app.poll_application_insights(None)

    assert persisted["status"] in {"failure", "partial"}
    assert persisted["timestamp"] == first - timedelta(minutes=1)
