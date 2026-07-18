from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import core.ai.context_builder as context_builder
from core.ai.config import AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.context_builder import AiContextPayload, AiContextSource, build_ai_context
from core.ai.explainer_service import chat_about_siem, explain_context
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata

ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class FakeCursor:
    def __init__(self, row=None):
        self.row = row
        self.closed = False
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeConnection:
    def __init__(self, row=None):
        self.cursor_obj = FakeCursor(row=row)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def _alert_row(alert_id=42, context=None):
    row = [None] * 20
    row[0] = alert_id
    row[1] = "pfsense_firewall_port_scan"
    row[2] = "high"
    row[3] = "Port scan detected"
    row[17] = "pfsense"
    row[18] = "firewall"
    row[19] = context or {"related_event_filter": {"source_ip": "198.51.100.10"}}
    return tuple(row)


class RecordingGateway:
    def __init__(self):
        self.requests: list[AiGatewayRequest] = []

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        self.requests.append(request)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content="AI explanation",
            error=None,
            metadata=AiRequestMetadata(
                provider="local",
                model="llama3",
                mode=AI_MODE_LOCAL_ONLY,
                status=AI_STATUS_SUCCESS,
                latency_ms=12,
                estimated_prompt_tokens=5,
                estimated_completion_tokens=7,
                estimated_cost_usd=0,
                local_request=True,
                paid_request=False,
            ),
        )


def _config(**overrides) -> AiGatewayConfig:
    base = AiGatewayConfig(
        mode=AI_MODE_LOCAL_ONLY,
        configured_mode=AI_MODE_LOCAL_ONLY,
        local_provider="local",
        local_base_url="http://127.0.0.1:11434",
        local_model="llama3",
        max_prompt_chars=12000,
    )
    return replace(base, **overrides)


def _context_payload(context_type: str = "alert", *, insufficient: bool = False) -> AiContextPayload:
    return AiContextPayload(
        context_type=context_type,
        data={
            "alert": {"id": 42, "message": "Blocked inbound scan"},
            "api_token": "sk-secret-value",
        },
        sources=[AiContextSource(context_type, f"/{context_type}/42", [42], "2026-01-01T00:00:00+00:00")],
        insufficient_context=insufficient,
        insufficient_reason="No visible SIEM context was supplied." if insufficient else None,
    )


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, username: str, password: str, role: str):
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def test_explain_context_uses_gateway_read_only_metadata_and_redacts_secrets(monkeypatch):
    gateway = RecordingGateway()
    monkeypatch.setattr(
        "core.ai.explainer_service.build_ai_context",
        lambda **_kwargs: _context_payload(),
    )

    result = explain_context(
        {
            "context_type": "alert",
            "action": "explain_alert",
            "question": "What happened?",
            "context": {"alert_id": 42},
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.status_code == 200
    assert result.payload["status"] == AI_STATUS_SUCCESS
    assert result.payload["answer"] == "AI explanation"
    assert result.payload["metadata"]["local_request"] is True
    assert result.payload["metadata"]["estimated_cost_usd"] == 0
    assert gateway.requests[0].capability == "text_generation"
    assert gateway.requests[0].metadata == {
        "context_type": "alert",
        "action": "explain_alert",
        "read_only": True,
    }
    assert "sk-secret-value" not in gateway.requests[0].prompt
    assert "sk-secret-value" not in str(result.payload)
    assert "[REDACTED]" in gateway.requests[0].prompt


def test_chat_context_uses_visible_context_and_client_owned_history(monkeypatch):
    gateway = RecordingGateway()

    def fake_builder(**kwargs):
        assert kwargs["context_type"] == "general"
        assert kwargs["question"] == "What am I seeing?"
        assert kwargs["client_history"] == [{"role": "user", "content": "previous"}]
        assert kwargs["context"] == {"active_section": "dashboard"}
        return _context_payload("general")

    monkeypatch.setattr("core.ai.explainer_service.build_ai_context", fake_builder)

    result = chat_about_siem(
        {
            "message": "What am I seeing?",
            "visible_context": {"active_section": "dashboard"},
            "client_history": [{"role": "user", "content": "previous"}],
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.status_code == 200
    assert result.payload["context"]["context_type"] == "general"
    assert gateway.requests[0].metadata["action"] == "general_chat"


def test_insufficient_context_returns_safe_answer_without_provider_call(monkeypatch):
    gateway = RecordingGateway()
    monkeypatch.setattr(
        "core.ai.explainer_service.build_ai_context",
        lambda **_kwargs: _context_payload("general", insufficient=True),
    )

    result = chat_about_siem(
        {"message": "Explain this", "visible_context": {}},
        gateway=gateway,
        config=_config(),
    )

    assert result.status_code == 200
    assert result.payload["status"] == "insufficient_context"
    assert result.payload["insufficient_context"] is True
    assert result.payload["metadata"]["estimated_prompt_tokens"] == 0
    assert gateway.requests == []


def test_context_builder_rejects_unsupported_context_type_safely():
    try:
        build_ai_context(context_type="shell", context={}, config=_config())
    except Exception as error:
        assert error.error_code == "invalid_context"
        assert "Unsupported context_type" in str(error)
    else:
        raise AssertionError("unsupported context_type was accepted")


def test_context_builder_uses_canonical_alert_paths(monkeypatch):
    conn = FakeConnection(row=_alert_row())
    monkeypatch.setattr(context_builder, "get_db_connection", lambda: conn)
    monkeypatch.setattr(context_builder, "_fetch_latest_resolved_audits", lambda _cur, _ids: {42: {"cooldown": False}})
    monkeypatch.setattr(context_builder, "_fetch_alert_intelligence", lambda _conn, _rows: {42: {"summary": "intel"}})
    monkeypatch.setattr(
        context_builder,
        "_build_alert_payload",
        lambda *_args, **_kwargs: {"id": 42, "message": "Port scan detected"},
    )
    monkeypatch.setattr(context_builder, "_build_pfsense_why_fired_payload", lambda *_args: {"summary": "threshold"})
    monkeypatch.setattr(context_builder, "_query_related_pfsense_events", lambda *_args, **_kwargs: [{"id": 1}])

    payload = build_ai_context(context_type="alert", context={"alert_id": 42}, config=_config())

    assert payload.context_type == "alert"
    assert payload.data["alert"]["id"] == 42
    assert payload.data["why_fired"]["summary"] == "threshold"
    assert payload.data["related_events"] == [{"id": 1}]
    assert [source.source_path for source in payload.sources] == [
        "/alerts/42",
        "/alerts/42/why-fired",
        "/alerts/42/related-events",
    ]
    assert conn.closed is True


def test_context_builder_uses_canonical_incident_paths(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(context_builder, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        context_builder,
        "get_incident_detail",
        lambda _conn, incident_id: {"id": incident_id, "title": "Credential incident"},
    )
    monkeypatch.setattr(
        context_builder,
        "build_readonly_incident_timeline",
        lambda _conn, _incident_id: {"timeline": [{"event_type": f"event-{index}"} for index in range(35)]},
    )

    payload = build_ai_context(context_type="incident", context={"incident_id": 7}, config=_config())

    assert payload.context_type == "incident"
    assert payload.data["incident"]["id"] == 7
    assert len(payload.data["timeline"]) == context_builder.SECTION_LIMITS["timeline"]
    assert payload.metadata()["truncated"] is True
    assert [source.source_path for source in payload.sources[:2]] == ["/incidents/7", "/incidents/7/timeline"]


def test_context_builder_uses_canonical_source_ip_aggregation(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(context_builder, "get_db_connection", lambda: conn)
    monkeypatch.setattr(context_builder, "_fetch_alert_context", lambda _cur, _ip: ({"recent": [{"id": 42}]}, [42]))
    monkeypatch.setattr(context_builder, "_fetch_incident_context", lambda _cur, _ip, _alert_ids: ({"recent": [{"id": 7}]}, [7]))
    monkeypatch.setattr(context_builder, "_fetch_queue_context", lambda _cur, _ip: {"recent": [{"id": 3}]})
    monkeypatch.setattr(context_builder, "_fetch_blocklist_context", lambda _cur, _ip: {"entries": [{"id": 4}]})
    monkeypatch.setattr(
        context_builder,
        "get_ip_reputation",
        lambda _ip, cur=None: {
            "reputation_score": 10,
            "reputation_label": "Suspicious",
            "reputation_summary": "Repeated activity",
            "contributing_signals": [],
        },
    )
    monkeypatch.setattr(context_builder, "_fetch_external_reputation_snapshots", lambda _cur, _ip: {"latest_external": None})
    monkeypatch.setattr(context_builder, "_fetch_playbook_execution_context", lambda _cur, _alerts, _incidents: {"recent": [{"id": 5}]})
    monkeypatch.setattr(context_builder, "_fetch_returning_attacker_context", lambda _cur, _ip: {"previous_responses": 1, "repeated_destinations": 1, "days_observed": 2})
    monkeypatch.setattr(context_builder, "_fetch_campaign_memberships", lambda _cur, _ip: {"count": 1, "recent": [{"campaign_intelligence": {"summary": "campaign"}}]})
    monkeypatch.setattr(context_builder, "get_internet_noise_assessment", lambda _ip: {"assessment": "neutral"})
    monkeypatch.setattr(context_builder, "build_local_evidence_override_reasons", lambda **_kwargs: ["local evidence"])
    monkeypatch.setattr(context_builder, "build_internet_noise_decision", lambda assessment, override_reasons=None: {"assessment": assessment["assessment"], "override_reasons": override_reasons})
    monkeypatch.setattr(context_builder, "get_recent_outcomes_for_source_ip", lambda _conn, _ip, limit: [{"id": 6, "limit": limit}])
    monkeypatch.setattr(context_builder, "get_outcome_count_groups", lambda _conn, source_ip: {"succeeded": 1})

    payload = build_ai_context(context_type="source_ip", context={"source_ip": "198.51.100.10"}, config=_config())

    assert payload.context_type == "source_ip"
    assert payload.data["source_ip"] == "198.51.100.10"
    assert payload.data["alerts"]["recent"] == [{"id": 42}]
    assert payload.data["reputation"]["behavioral"]["label"] == "Suspicious"
    assert payload.data["response_outcomes"][0]["limit"] == context_builder.SECTION_LIMITS["source_ip_outcomes"]
    assert payload.sources[0].source_path == "/source-ip-context"


def test_context_builder_uses_canonical_recon_activity_paths(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(context_builder, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        context_builder,
        "get_recon_activity_detail",
        lambda _conn, activity_id: {
            "id": activity_id,
            "summary": {
                "representative_sources": ["198.51.100.10"],
                "target_context": {"sample_destination_ips": ["203.0.113.5"], "sample_destination_ports": [22]},
            },
            "first_seen": "2026-01-01T00:00:00Z",
            "last_seen": "2026-01-01T01:00:00Z",
        },
    )
    monkeypatch.setattr(context_builder, "_query_related_pfsense_events", lambda *_args, **_kwargs: [{"event_id": 1}])

    payload = build_ai_context(context_type="recon_activity", context={"activity_id": 90}, config=_config())

    assert payload.context_type == "recon_activity"
    assert payload.data["recon_activity"]["id"] == 90
    assert payload.data["related_events"] == [{"event_id": 1}]
    assert [source.source_path for source in payload.sources] == [
        "/recon-activities/90",
        "/recon-activities/90/related-events",
    ]


def test_context_builder_uses_visible_dashboard_state():
    payload = build_ai_context(
        context_type="dashboard",
        context={
            "visible_filters": {"severity": "high"},
            "dashboard_summary": {"totalAlerts": 3},
            "timeline": [{"bucket": index} for index in range(40)],
            "top_source_ips": [{"source_ip": str(index)} for index in range(12)],
            "map_markers": [{"source_ip": str(index)} for index in range(12)],
            "recent_alerts": [{"id": index} for index in range(12)],
        },
        config=_config(),
    )

    assert payload.context_type == "dashboard"
    assert payload.data["visible_filters"] == {"severity": "high"}
    assert len(payload.data["timeline"]) == context_builder.SECTION_LIMITS["timeline"]
    assert len(payload.data["top_source_ips"]) == context_builder.SECTION_LIMITS["recent_alerts"]
    assert payload.sources[0].source_path == "/alerts/summary"


def test_context_builder_uses_registry_detail_without_command_execution(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(context_builder, "get_db_connection", lambda: conn)
    monkeypatch.setattr(
        context_builder,
        "get_registry_detail",
        lambda _conn, registry_id: {"record": {"id": registry_id, "indicator_value": "198.51.100.10"}},
    )

    payload = build_ai_context(context_type="response_registry", context={"registry_id": 11}, config=_config())

    assert payload.context_type == "response_registry"
    assert payload.data["response_registry"]["record"]["id"] == 11
    assert payload.sources[0].source_path == "/response-registry/11"


def test_context_builder_uses_detection_sources(monkeypatch):
    conn = FakeConnection(row=_alert_row(alert_id=42, context={"rule": "scan"}))
    monkeypatch.setattr(context_builder, "get_db_connection", lambda: conn)
    monkeypatch.setattr(context_builder, "_fetch_latest_resolved_audits", lambda _cur, _ids: {})
    monkeypatch.setattr(context_builder, "_build_pfsense_why_fired_payload", lambda *_args: {"summary": "scan threshold"})
    monkeypatch.setattr(context_builder, "build_severity_response_matrix", lambda _conn: {"high": {"recommended": "review"}})

    payload = build_ai_context(context_type="detection", context={"alert_id": 42}, config=_config())

    assert payload.context_type == "detection"
    assert payload.data["why_fired"]["summary"] == "scan threshold"
    assert payload.data["alert_detection_metadata"]["alert_id"] == 42
    assert payload.data["severity_response_matrix"]["high"]["recommended"] == "review"
    assert [source.source_path for source in payload.sources] == [
        "/alerts/42/why-fired",
        "/api/severity-response-matrix",
    ]


def test_context_builder_uses_general_visible_context_and_bounded_history():
    payload = build_ai_context(
        context_type="general",
        context={"active_section": "dashboard"},
        config=_config(),
        question="What changed?",
        client_history=[{"role": "user", "content": f"message-{index}"} for index in range(12)],
    )

    assert payload.context_type == "general"
    assert payload.data["question"] == "What changed?"
    assert payload.data["visible_context"] == {"active_section": "dashboard"}
    assert len(payload.data["client_history"]) == context_builder.SECTION_LIMITS["chat_history"]
    assert payload.sources[0].source_path == "frontend_visible_context"


def test_ai_explain_route_requires_session(client):
    resp = client.post("/ai/explain", json={"context_type": "alert", "action": "explain_alert"})

    assert resp.status_code == 401


def test_ai_chat_route_rejects_viewer(client, mock_db):
    patchers = _login_role(client, username="ai_viewer_chat", password="p", role="viewer")
    try:
        resp = client.post("/ai/chat", json={"message": "Explain this"})
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 403


def test_ai_explain_route_allows_analyst_and_maps_service_response(client, mock_db, monkeypatch):
    patchers = _login_role(client, username="ai_analyst_explain", password="p", role="analyst")
    monkeypatch.setattr(
        "routes.ai_routes.explain_context",
        lambda _payload: type(
            "Result",
            (),
            {"payload": {"status": "success", "answer": "ok"}, "status_code": 200},
        )(),
    )
    try:
        resp = client.post(
            "/ai/explain",
            json={"context_type": "alert", "action": "explain_alert", "context": {"alert_id": 42}},
        )
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "success", "answer": "ok"}


def test_ai_explain_route_maps_missing_canonical_record_to_404(client, mock_db, monkeypatch):
    from core.ai.context_builder import AiContextNotFoundError

    patchers = _login_role(client, username="ai_analyst_missing", password="p", role="analyst")

    def raise_not_found(_payload):
        raise AiContextNotFoundError("Alert not found")

    monkeypatch.setattr("routes.ai_routes.explain_context", raise_not_found)
    try:
        resp = client.post(
            "/ai/explain",
            json={"context_type": "alert", "action": "explain_alert", "context": {"alert_id": 404}},
        )
    finally:
        _stop_patchers(patchers)

    assert resp.status_code == 404
    assert resp.get_json()["status"] == "context_not_found"


def test_ai_chat_route_rejects_invalid_json_for_super_admin(client):
    _login_super_admin(client)

    resp = client.post("/ai/chat", data="not-json", content_type="text/plain")

    assert resp.status_code == 400
    assert "JSON object body is required" in resp.get_json()["error"]
