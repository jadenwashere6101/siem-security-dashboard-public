from __future__ import annotations

from dataclasses import replace
import inspect
import json
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.ai.config import AI_MODE_DISABLED, AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.context_builder import AiContextPayload, AiContextSource
from core.ai.investigation_models import (
    MAX_TOOL_CALLS_PER_PASS,
    MAX_WORKFLOW_STEPS,
    STEP_EXECUTE_READ_TOOL,
    STEP_VALIDATE_EVIDENCE,
)
from core.ai.investigation_planner import (
    build_investigation_plan,
    classify_routing_profile,
    select_automatic_draft,
    validate_tool_evidence,
    validate_workflow_steps,
)
import core.ai.investigation_planner as investigation_planner_module
import core.ai.investigation_service as investigation_service_module
from core.ai.investigation_service import run_investigation
from core.ai.models import AI_STATUS_FALLBACK_BLOCKED, AI_STATUS_SUCCESS, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata
from core.ai.soc_tools import (
    TOOL_STATUS_FORBIDDEN,
    TOOL_STATUS_SUCCESS,
    SocToolExecutionSummary,
    SocToolResult,
    SocToolSource,
)


class RecordingGateway:
    def __init__(self, *, status: str = AI_STATUS_SUCCESS, content: str = "Summary\n\nKey evidence: /alerts/7"):
        self.status = status
        self.content = content
        self.requests: list[AiGatewayRequest] = []

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        self.requests.append(request)
        return AiGatewayResponse(
            status=self.status,
            content=self.content if self.status == AI_STATUS_SUCCESS else None,
            error=None if self.status == AI_STATUS_SUCCESS else self.status,
            metadata=AiRequestMetadata(
                provider="local",
                model="qwen3:4b-instruct",
                mode=AI_MODE_LOCAL_ONLY,
                status=self.status,
                latency_ms=11,
                estimated_prompt_tokens=20,
                estimated_completion_tokens=10,
                estimated_cost_usd=0,
                local_request=True,
                paid_request=False,
                fallback_attempted=self.status == AI_STATUS_FALLBACK_BLOCKED,
                fallback_reason="provider_timeout" if self.status == AI_STATUS_FALLBACK_BLOCKED else None,
            ),
        )


class FakeDraftResult:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code


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


def _context_payload(context_type: str = "alert", *, severity: str = "high", insufficient: bool = False) -> AiContextPayload:
    return AiContextPayload(
        context_type=context_type,
        data={
            context_type: {"id": 7, "severity": severity, "source_ip": "198.51.100.10"},
            "incident": {"id": 3, "severity": severity} if context_type in {"alert", "incident"} else None,
            "api_key": "sk-secret-value",
        },
        sources=[AiContextSource(context_type, f"/{context_type}/7", [7], "2026-07-19T00:00:00+00:00")],
        insufficient_context=insufficient,
        insufficient_reason="No evidence" if insufficient else None,
    )


def _tool_result(name="get_alert_detail", *, status=TOOL_STATUS_SUCCESS, record_ids=None, source_path="/alerts/7", data=None):
    record_ids = [7] if record_ids is None else record_ids
    return SocToolResult(
        tool_name=name,
        status=status,
        data=data if data is not None else {"id": 7, "source_ip": "198.51.100.10", "token": "secret-token"},
        sources=[
            SocToolSource(
                tool_name=name,
                source_type="alert",
                source_path=source_path,
                source_helper="test.helper",
                record_ids=record_ids,
            )
        ],
    )


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, role: str):
    username = f"{role}_advanced_ai_user"
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


def test_planner_enforces_allowed_steps_depth_and_mutation_tool_rejection():
    assert len(validate_workflow_steps(["build_context", "plan_read_tools"])) == 2

    try:
        validate_workflow_steps(["build_context"] * (MAX_WORKFLOW_STEPS + 1))
    except Exception as error:
        assert error.error_code == "workflow_depth_exceeded"
    else:
        raise AssertionError("workflow depth was not enforced")

    try:
        validate_workflow_steps(["execute_playbook"])
    except Exception as error:
        assert error.error_code == "unsupported_step"
    else:
        raise AssertionError("unsupported workflow step was accepted")

    try:
        build_investigation_plan(
            context_type="alert",
            context={"alert_id": 7},
            question="investigate",
            tool_policy={"tool_requests": [{"tool_name": "block_ip", "arguments": {"source_ip": "198.51.100.10"}}]},
        )
    except Exception as error:
        assert "Unsupported SOC read tool" in str(error)
    else:
        raise AssertionError("mutation-like tool request was accepted")


def test_plan_is_bounded_to_one_non_recursive_tool_pass():
    plan = build_investigation_plan(
        context_type="source_ip",
        context={"source_ip": "198.51.100.10"},
        question="Show me everything tied to this source IP and response history",
    )

    assert len(plan.steps) <= MAX_WORKFLOW_STEPS
    assert len(plan.tool_calls) <= MAX_TOOL_CALLS_PER_PASS
    assert plan.bounds["max_planning_passes"] == 1
    assert plan.bounds["max_generation_calls"] == 2
    assert all(call["tool_name"] in {
        "search_alerts",
        "get_alert_detail",
        "get_related_events",
        "get_source_ip_context",
        "search_incidents",
        "get_incident_timeline",
        "list_playbook_executions",
        "read_audit_log",
        "get_response_registry_context",
    } for call in plan.tool_calls)


def test_evidence_validation_rejects_forbidden_mismatched_and_unsourced_results():
    accepted = _tool_result()
    forbidden = _tool_result("read_audit_log", status=TOOL_STATUS_FORBIDDEN)
    mismatched = _tool_result("get_alert_detail", record_ids=[99], source_path="/alerts/99")
    unsourced = SocToolResult(tool_name="search_alerts", status=TOOL_STATUS_SUCCESS, data={"items": [1]}, sources=[])
    summary = SocToolExecutionSummary(used=True, calls=[accepted, forbidden, mismatched, unsourced], sources=accepted.sources)

    validated, metadata = validate_tool_evidence(
        summary,
        context_snapshot={"alert_id": 7},
        prompt_budget_chars=10000,
    )

    assert [call.tool_name for call in validated.calls] == ["get_alert_detail"]
    assert metadata["rejected_count"] == 3
    assert "secret-token" not in str(validated.as_dict())
    assert "[REDACTED]" in str(validated.as_dict())


def test_automatic_draft_policy_is_narrow_and_review_only():
    plan = build_investigation_plan(context_type="incident", context={"incident_id": 7}, question="investigate")
    decision = select_automatic_draft(
        plan=plan,
        ai_context=_context_payload("incident", severity="high"),
        validated_tools=SocToolExecutionSummary(used=True, calls=[_tool_result("get_incident_timeline")], sources=_tool_result("get_incident_timeline").sources),
        gateway_status="success",
    )

    assert decision["decision"] == "generate"
    assert decision["selected_type"] == "incident_note"
    assert decision["labels"]["persisted"] is False
    assert decision["labels"]["applied"] is False
    assert "detection_rule_change" not in decision["allowed_types"]
    assert "playbook_draft" not in decision["allowed_types"]


def test_routing_profile_records_complexity_and_fallback_inputs():
    profile = classify_routing_profile(
        workflow_type="alert_investigation",
        context_type="alert",
        context_payload=_context_payload(),
        planned_tool_calls=5,
        successful_sources=4,
        failed_sources=1,
        truncated=True,
        draft_decision={"decision": "generate"},
        config=_config(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
        remaining_timeout_seconds=10.5,
    )

    assert profile.profile == "advanced"
    assert profile.inputs["planned_tool_call_count"] == 5
    assert profile.inputs["fallback_mode"] == AI_MODE_DISABLED
    assert profile.inputs["draft_requested"] is True


def test_investigation_service_orchestrates_read_only_partial_fallback_metadata(monkeypatch):
    gateway = RecordingGateway(status=AI_STATUS_FALLBACK_BLOCKED)
    monkeypatch.setattr("core.ai.investigation_service.build_ai_context", lambda **_kwargs: _context_payload("alert"))
    monkeypatch.setattr(
        "core.ai.investigation_service.execute_tool_plan",
        lambda *_args, **_kwargs: SocToolExecutionSummary(
            used=True,
            calls=[_tool_result("get_alert_detail")],
            sources=_tool_result("get_alert_detail").sources,
        ),
    )
    monkeypatch.setattr(
        "core.ai.investigation_service.create_draft",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("draft should not run after fallback failure")),
    )

    result = run_investigation(
        {
            "context_type": "alert",
            "question": "Investigate alert",
            "context": {"alert_id": 7, "source_ip": "198.51.100.10"},
            "client_request_id": "advanced-test",
        },
        gateway=gateway,
        config=_config(),
    )

    investigation = result.payload["investigation"]
    assert result.status_code == 200
    assert investigation["status"] == "partial"
    assert investigation["labels"]["read_only"] is True
    assert investigation["labels"]["writes_performed"] is False
    assert investigation["observability"]["provider_responses"][0]["status"] == AI_STATUS_FALLBACK_BLOCKED
    assert investigation["observability"]["aggregate_estimated_cost_usd"] == 0
    assert any(step["step_type"] == STEP_EXECUTE_READ_TOOL for step in investigation["steps"])
    assert any(step["step_type"] == STEP_VALIDATE_EVIDENCE for step in investigation["steps"])
    assert len(gateway.requests) == 1
    assert gateway.requests[0].metadata["read_only"] is True
    assert "sk-secret-value" not in gateway.requests[0].prompt


def test_investigation_service_reports_request_cancellation_before_tool_execution(monkeypatch):
    monkeypatch.setattr(
        "core.ai.investigation_service.build_ai_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("context should not build after cancellation")),
    )

    result = run_investigation(
        {
            "context_type": "alert",
            "question": "Investigate alert",
            "context": {"alert_id": 7, "source_ip": "198.51.100.10"},
        },
        gateway=RecordingGateway(),
        config=_config(),
        is_cancelled=lambda: True,
    )

    investigation = result.payload["investigation"]
    assert result.status_code == 200
    assert investigation["status"] == "cancelled"
    assert investigation["observability"]["cancelled"] is True
    assert investigation["observability"]["timed_out"] is False
    assert investigation["steps"][-1]["status"] == "cancelled"
    assert investigation["labels"]["read_only"] is True
    assert investigation["labels"]["writes_performed"] is False


def test_investigation_planner_and_service_do_not_import_mutation_paths():
    combined_source = "\n".join(
        [
            inspect.getsource(investigation_planner_module),
            inspect.getsource(investigation_service_module),
        ]
    )

    assert "core.ai.action_service" not in combined_source
    assert "confirm_ai_action" not in combined_source
    assert "preview_ai_action" not in combined_source
    assert "subprocess" not in combined_source
    assert "os.system" not in combined_source


def test_investigation_route_requires_existing_rbac_and_preserves_action_boundary(client, mock_db, monkeypatch):
    patchers = _login_role(client, role="analyst")
    gateway = RecordingGateway()
    monkeypatch.setattr("core.ai.investigation_service.build_ai_context", lambda **_kwargs: _context_payload("incident"))
    monkeypatch.setattr("core.ai.investigation_service.load_ai_gateway_config", lambda: _config())
    monkeypatch.setattr("core.ai.investigation_service.AiGateway", lambda config=None: gateway)
    monkeypatch.setattr(
        "core.ai.investigation_service.execute_tool_plan",
        lambda *_args, **_kwargs: SocToolExecutionSummary(used=True, calls=[_tool_result("get_incident_timeline")], sources=_tool_result("get_incident_timeline").sources),
    )
    monkeypatch.setattr(
        "core.ai.investigation_service.create_draft",
        lambda *_args, **_kwargs: FakeDraftResult(
            {
                "status": "success",
                "draft": {
                    "draft_type": "incident_note",
                    "title": "Incident note draft",
                    "payload": {"summary": "x", "evidence": [], "uncertainty": "", "recommended_next_steps": [], "attribution": []},
                    "validation": {"valid": True, "errors": []},
                    "labels": {"ai_generated": True, "read_only": True, "persisted": False, "applied": False, "approval_required_before_apply": True},
                },
                "metadata": {"status": "success", "estimated_prompt_tokens": 1, "estimated_completion_tokens": 1, "estimated_cost_usd": 0},
                "context": {"sources": []},
            }
        ),
    )
    with patch("core.ai.action_service.confirm_ai_action") as confirm:
        try:
            response = client.post(
                "/ai/investigations",
                json={"context_type": "incident", "context": {"incident_id": 7}, "question": "Investigate"},
            )
        finally:
            _stop_patchers(patchers)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["investigation"]["drafts"][0]["draft"]["labels"]["persisted"] is False
    assert payload["investigation"]["drafts"][0]["draft"]["labels"]["applied"] is False
    assert confirm.call_count == 0


def test_investigation_route_rejects_viewer_before_tool_execution(client, mock_db, monkeypatch):
    patchers = _login_role(client, role="viewer")
    monkeypatch.setattr(
        "core.ai.investigation_service.execute_tool_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tool execution should not run")),
    )
    try:
        response = client.post("/ai/investigations", json={"context_type": "alert", "context": {"alert_id": 1}})
    finally:
        _stop_patchers(patchers)

    assert response.status_code == 403
