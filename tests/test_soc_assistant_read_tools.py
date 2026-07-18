from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.ai.config import AI_MODE_DISABLED, AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.context_builder import AiContextPayload, AiContextSource
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata
from core.ai.soc_tool_executor import (
    build_deterministic_tool_plan,
    execute_tool,
    execute_tool_plan,
    should_skip_tools_for_gateway,
    tool_summary_for_prompt,
)
from core.ai.soc_tools import (
    SUPPORTED_TOOL_NAMES,
    TOOL_DEFINITIONS,
    TOOL_STATUS_FORBIDDEN,
    TOOL_STATUS_SUCCESS,
    TOOL_STATUS_UNSUPPORTED,
    SocToolResult,
    SocToolExecutionSummary,
    SocToolSource,
    validate_tool_args,
    validate_tool_name,
)


def _config(**overrides) -> AiGatewayConfig:
    return replace(
        AiGatewayConfig(
            mode=AI_MODE_LOCAL_ONLY,
            configured_mode=AI_MODE_LOCAL_ONLY,
            local_provider="local",
            local_base_url="http://127.0.0.1:11434",
            local_model="qwen3:4b-instruct",
            max_prompt_chars=12000,
        ),
        **overrides,
    )


class RecordingGateway:
    def __init__(self):
        self.requests: list[AiGatewayRequest] = []

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        self.requests.append(request)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content="Tool-grounded answer",
            error=None,
            metadata=AiRequestMetadata(
                provider="local",
                model="qwen3:4b-instruct",
                mode=AI_MODE_LOCAL_ONLY,
                status=AI_STATUS_SUCCESS,
                estimated_cost_usd=0,
                local_request=True,
                paid_request=False,
            ),
        )


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, role: str):
    username = f"{role}_user"
    password = "testpassword123!"
    user = _fake_user(username, password, role)
    patchers = [
        patch("routes.auth_routes.get_user_by_username", return_value=user),
        patch("core.auth.get_user_by_username", return_value=user),
    ]
    for patcher in patchers:
        patcher.start()
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return patchers


def _stop_patchers(patchers):
    for patcher in reversed(patchers):
        patcher.stop()


def test_tool_contract_lists_exact_supported_read_tools_and_canonical_sources():
    assert SUPPORTED_TOOL_NAMES == {
        "search_alerts",
        "get_alert_detail",
        "get_related_events",
        "get_source_ip_context",
        "search_incidents",
        "get_incident_timeline",
        "list_playbook_executions",
        "read_audit_log",
        "get_response_registry_context",
    }
    for name, definition in TOOL_DEFINITIONS.items():
        assert definition.name == name
        assert definition.source_path
        assert definition.source_helper
        assert definition.max_results <= 25


def test_tool_validation_rejects_unsupported_mutation_and_bad_arguments():
    try:
        validate_tool_name("execute_playbook")
    except Exception as error:
        assert error.error_code == "mutation_tool_rejected"
    else:
        raise AssertionError("mutation-like tool was accepted")

    try:
        validate_tool_name("unknown_lookup")
    except Exception as error:
        assert error.error_code == TOOL_STATUS_UNSUPPORTED
    else:
        raise AssertionError("unknown tool was accepted")

    try:
        validate_tool_args("get_source_ip_context", {"source_ip": "not-an-ip"})
    except Exception as error:
        assert "source_ip is invalid" in str(error)
    else:
        raise AssertionError("invalid IP was accepted")

    args = validate_tool_args("search_alerts", {"source_ip": "198.51.100.10", "limit": 1000})
    assert args["source_ip"] == "198.51.100.10"
    assert args["limit"] == 25


def test_executor_dispatches_supported_tools_and_enforces_rbac(monkeypatch):
    called = []

    def fake_execute(tool_name, args, *, config, started):
        called.append((tool_name, args))
        return SocToolResult(
            tool_name=tool_name,
            status=TOOL_STATUS_SUCCESS,
            data={"api_key": "secret-value", "count": 1},
            sources=[
                SocToolSource(
                    tool_name=tool_name,
                    source_type="test",
                    source_path=TOOL_DEFINITIONS[tool_name].source_path,
                    source_helper=TOOL_DEFINITIONS[tool_name].source_helper,
                )
            ],
        )

    monkeypatch.setattr("core.ai.soc_tool_executor._execute_validated_tool", fake_execute)

    for name in SUPPORTED_TOOL_NAMES - {"read_audit_log"}:
        args = {
            "search_alerts": {},
            "get_alert_detail": {"alert_id": 1},
            "get_related_events": {"source_ip": "198.51.100.10"},
            "get_source_ip_context": {"source_ip": "198.51.100.10"},
            "search_incidents": {},
            "get_incident_timeline": {"incident_id": 2},
            "list_playbook_executions": {},
            "get_response_registry_context": {"registry_id": 3},
        }[name]
        result = execute_tool({"tool_name": name, "arguments": args}, actor_role="analyst", config=_config())
        assert result.status == TOOL_STATUS_SUCCESS
        assert result.as_dict()["data"]["api_key"] == "[REDACTED]"

    audit_result = execute_tool({"tool_name": "read_audit_log", "arguments": {}}, actor_role="analyst", config=_config())
    assert audit_result.status == TOOL_STATUS_FORBIDDEN
    assert any(name == "search_alerts" for name, _args in called)


def test_tool_plan_is_bounded_non_recursive_and_redacts_prompt_evidence(monkeypatch):
    calls = [
        {"tool_name": "search_alerts", "arguments": {"source_ip": "198.51.100.10"}},
        {"tool_name": "get_source_ip_context", "arguments": {"source_ip": "198.51.100.10"}},
        {"tool_name": "list_playbook_executions", "arguments": {}},
        {"tool_name": "search_incidents", "arguments": {}},
        {"tool_name": "read_audit_log", "arguments": {}},
        {"tool_name": "get_related_events", "arguments": {"source_ip": "198.51.100.10"}},
    ]

    def fake_execute(raw_call, *, actor_role, config):
        return SocToolResult(
            tool_name=raw_call["tool_name"],
            status=TOOL_STATUS_SUCCESS,
            data={"token": "secret-token", "ok": True},
        )

    monkeypatch.setattr("core.ai.soc_tool_executor.execute_tool", fake_execute)
    summary = execute_tool_plan(calls, actor_role="super_admin", config=_config(), tool_policy={"max_tool_calls": 5})

    assert len(summary.calls) == 5
    assert summary.truncated is True
    prompt_payload = tool_summary_for_prompt(summary, max_chars=10000)
    assert "secret-token" not in str(prompt_payload)
    assert "[REDACTED]" in str(prompt_payload)


def test_deterministic_plan_uses_existing_siem_context_without_repo_tools():
    plan = build_deterministic_tool_plan(
        question="Show me everything tied to 85.11.167.228 in the last 24 hours",
        context_type="general",
        context={"active_section": "dashboard"},
    )
    names = [call["tool_name"] for call in plan.calls]
    assert "get_source_ip_context" in names
    assert "search_alerts" in names
    assert "get_related_events" in names
    assert all(not name.startswith("repo") for name in names)


def test_gateway_disabled_skips_tools_before_execution():
    disabled = _config(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED)
    assert should_skip_tools_for_gateway(disabled) is True


def test_chat_route_runs_tool_assisted_flow_and_preserves_read_only_metadata(client, mock_db, monkeypatch):
    patchers = _login_role(client, role="analyst")
    gateway = RecordingGateway()
    tool_result = SocToolResult(
        tool_name="get_source_ip_context",
        status=TOOL_STATUS_SUCCESS,
        data={"source_ip": "198.51.100.10", "alerts": {"count": 2}},
        sources=[
            SocToolSource(
                tool_name="get_source_ip_context",
                source_type="source_ip",
                source_path="/source-ip-context",
                source_helper="core.ai.context_builder",
                record_ids=["198.51.100.10"],
            )
        ],
    )

    monkeypatch.setattr(
        "core.ai.explainer_service.build_ai_context",
        lambda **_kwargs: AiContextPayload(
            context_type="general",
            data={"visible_context": {"active_section": "dashboard"}},
            sources=[AiContextSource("visible_context", "frontend_visible_context")],
        ),
    )
    monkeypatch.setattr("core.ai.explainer_service.load_ai_gateway_config", lambda: _config())
    monkeypatch.setattr("core.ai.explainer_service.AiGateway", lambda config=None: gateway)
    monkeypatch.setattr(
        "core.ai.explainer_service.execute_tool_plan",
        lambda *_args, **_kwargs: SocToolExecutionSummary(
            used=True,
            calls=[tool_result],
            sources=tool_result.sources,
        ),
    )

    try:
        response = client.post(
            "/ai/chat",
            json={
                "message": "Explain 198.51.100.10",
                "visible_context": {"active_section": "dashboard"},
                "use_tools": True,
            },
        )
    finally:
        _stop_patchers(patchers)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == AI_STATUS_SUCCESS
    assert payload["tools"]["used"] is True
    assert payload["tools"]["read_only"] is True
    assert payload["tools"]["calls"][0]["tool_name"] == "get_source_ip_context"
    assert payload["metadata"]["local_request"] is True
    assert len(gateway.requests) == 1
    assert "Read-only SOC tool evidence" in gateway.requests[0].prompt


def test_tool_assisted_route_rejects_viewer_before_tool_execution(client, mock_db, monkeypatch):
    patchers = _login_role(client, role="viewer")
    monkeypatch.setattr(
        "core.ai.explainer_service.execute_tool_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tool execution should not run")),
    )
    try:
        response = client.post("/ai/chat", json={"message": "Use tools", "use_tools": True})
    finally:
        _stop_patchers(patchers)

    assert response.status_code == 403
