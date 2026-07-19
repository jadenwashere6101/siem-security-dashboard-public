from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from core.ai.config import AI_MODE_DISABLED, AI_MODE_LOCAL_ONLY, AiGatewayConfig
from core.ai.context_builder import AiContextPayload, AiContextSource
from core.ai.draft_schemas import (
    DEFAULT_DRAFT_LABELS,
    DRAFT_DEFINITIONS,
    DRAFT_STATUS_PARSE_FAILED,
    DRAFT_STATUS_SUCCESS,
    DRAFT_STATUS_VALIDATION_FAILED,
    SUPPORTED_DRAFT_TYPES,
    validate_draft_payload,
)
from core.ai.drafting_service import create_draft
from core.ai.models import AI_STATUS_DISABLED, AI_STATUS_SUCCESS, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata
from core.ai.soc_tools import SocToolExecutionSummary, SocToolResult, SocToolSource


class RecordingGateway:
    def __init__(self, content: str | None = None, status: str = AI_STATUS_SUCCESS, error: str | None = None):
        self.content = content or json.dumps(_valid_payload("incident_note"))
        self.status = status
        self.error = error
        self.requests: list[AiGatewayRequest] = []

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        self.requests.append(request)
        return AiGatewayResponse(
            status=self.status,
            content=self.content if self.status == AI_STATUS_SUCCESS else None,
            error=self.error,
            metadata=AiRequestMetadata(
                provider="local",
                model="qwen3:4b-instruct",
                mode=AI_MODE_LOCAL_ONLY,
                status=self.status,
                latency_ms=12,
                estimated_prompt_tokens=10,
                estimated_completion_tokens=20,
                estimated_cost_usd=0,
                local_request=True,
                paid_request=False,
            ),
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


def _context_payload(context_type: str = "incident", *, insufficient: bool = False) -> AiContextPayload:
    return AiContextPayload(
        context_type=context_type,
        data={
            "incident": {"id": 7, "title": "Suspicious scan"},
            "api_key": "sk-secret-value",
        },
        sources=[AiContextSource(context_type, f"/{context_type}/7", [7], "2026-01-01T00:00:00+00:00")],
        insufficient_context=insufficient,
        insufficient_reason="No incident evidence." if insufficient else None,
    )


def _valid_payload(draft_type: str) -> dict:
    payloads = {
        "detection_rule_change": {
            "title": "Tune port scan threshold",
            "rationale": "Repeated scan evidence supports a threshold review.",
            "target_rule": "pfsense_firewall_port_scan",
            "suggested_condition": "Increase confidence when one source probes many ports.",
            "severity": "high",
            "false_positive_notes": "Validate against known scanners.",
            "test_ideas": ["Replay representative pfSense events."],
            "rollback_notes": "Restore previous threshold if false positives spike.",
            "source_references": ["/alerts/7"],
        },
        "playbook_draft": {
            "name": "Review suspicious scanner",
            "trigger_context": "High severity scan alert",
            "steps": ["Collect alert detail", "Check source-IP history"],
            "approval_gates": ["Analyst approval before enforcement"],
            "simulation_real_caveats": "Keep enforcement disabled until reviewed.",
            "required_integrations": ["firewall"],
            "risks": ["False positive scanner may be internal"],
            "source_references": ["/source-ip-context"],
        },
        "incident_note": {
            "summary": "Suspicious scan activity observed.",
            "evidence": ["Alert #7 fired"],
            "uncertainty": "Ownership of source IP is unknown.",
            "recommended_next_steps": ["Review related events"],
            "attribution": ["/incidents/7"],
        },
        "escalation_summary": {
            "audience": "SOC lead",
            "urgency": "High",
            "business_or_security_impact": "Potential recon against exposed services.",
            "evidence": ["Multiple related alerts"],
            "asks": ["Confirm blocking policy"],
            "next_update_criteria": "Update after related-event review.",
            "source_references": ["/incidents/7/timeline"],
        },
        "response_recommendation": {
            "recommended_action_class": "Monitor and investigate",
            "prerequisites": ["Confirm source history"],
            "expected_outcome": "Better confidence before enforcement.",
            "approval_need": "Required before blocking.",
            "risk": "Premature blocking may affect benign scanning.",
            "alternatives": ["Escalate to network owner"],
            "source_references": ["/response-registry/7"],
        },
        "investigation_checklist": {
            "title": "Investigate suspicious scanner",
            "checks": ["Review alert detail", "Check source-IP context"],
            "data_sources": ["alerts", "events"],
            "expected_findings": ["Related scan events"],
            "stop_conditions": ["No related evidence found"],
            "source_references": ["/alerts/7"],
        },
    }
    return payloads[draft_type]


def _fake_user(username: str, password: str, role: str):
    return {
        "username": username,
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }


def _login_role(client, *, role: str):
    username = f"{role}_draft_user"
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


def test_draft_contract_defines_all_supported_types_and_review_only_labels():
    assert SUPPORTED_DRAFT_TYPES == {
        "detection_rule_change",
        "playbook_draft",
        "incident_note",
        "escalation_summary",
        "response_recommendation",
        "investigation_checklist",
    }
    assert DEFAULT_DRAFT_LABELS == {
        "ai_generated": True,
        "read_only": True,
        "persisted": False,
        "applied": False,
        "approval_required_before_apply": True,
    }
    for draft_type, definition in DRAFT_DEFINITIONS.items():
        assert definition.draft_type == draft_type
        assert definition.allowed_context_types
        assert validate_draft_payload(draft_type, _valid_payload(draft_type)).valid is True


def test_draft_schema_rejects_malformed_and_mutation_like_payloads():
    result = validate_draft_payload("incident_note", {"summary": "x", "applied": True})
    assert result.valid is False
    assert any("applied" in error for error in result.errors)

    result = validate_draft_payload("playbook_draft", {**_valid_payload("playbook_draft"), "steps": ["x"] * 20})
    assert result.valid is False
    assert any("steps" in error for error in result.errors)


def test_create_draft_reuses_context_gateway_and_redacts_secrets(monkeypatch):
    gateway = RecordingGateway(json.dumps(_valid_payload("incident_note")))
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("incident"))

    result = create_draft(
        {
            "draft_type": "incident_note",
            "instruction": "Draft a note.",
            "context_type": "incident",
            "context": {"incident_id": 7},
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.status_code == 200
    assert result.payload["status"] == DRAFT_STATUS_SUCCESS
    assert result.payload["draft"]["labels"] == DEFAULT_DRAFT_LABELS
    assert result.payload["draft"]["validation"]["valid"] is True
    assert result.payload["metadata"]["local_request"] is True
    assert gateway.requests[0].metadata == {
        "context_type": "incident",
        "action": "draft",
        "draft_type": "incident_note",
        "read_only": True,
        "persisted": False,
        "applied": False,
    }
    assert "sk-secret-value" not in gateway.requests[0].prompt
    assert "sk-secret-value" not in str(result.payload)
    assert "[REDACTED]" in gateway.requests[0].prompt


def test_create_draft_can_use_read_tool_evidence_without_repo_assistant(monkeypatch):
    gateway = RecordingGateway(json.dumps(_valid_payload("response_recommendation")))
    tool_result = SocToolResult(
        tool_name="get_source_ip_context",
        status="success",
        data={"source_ip": "198.51.100.10"},
        sources=[
            SocToolSource(
                tool_name="get_source_ip_context",
                source_type="source_ip",
                source_path="/source-ip-context",
                source_helper="core.ai.context_builder",
            )
        ],
    )
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("source_ip"))
    monkeypatch.setattr(
        "core.ai.drafting_service.execute_tool_plan",
        lambda *_args, **_kwargs: SocToolExecutionSummary(used=True, calls=[tool_result], sources=tool_result.sources),
    )
    monkeypatch.setattr(
        "core.ai.drafting_service.build_deterministic_tool_plan",
        lambda **_kwargs: [{"tool_name": "get_source_ip_context", "arguments": {"source_ip": "198.51.100.10"}}],
    )
    monkeypatch.setattr(
        "core.ai.repo_assistant_service.answer_repo_question",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("repo assistant must not run")),
    )

    result = create_draft(
        {
            "draft_type": "response_recommendation",
            "instruction": "Draft a response recommendation for 198.51.100.10.",
            "context_type": "source_ip",
            "context": {"source_ip": "198.51.100.10"},
            "use_tools": True,
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.payload["status"] == DRAFT_STATUS_SUCCESS
    assert result.payload["tools"]["used"] is True
    assert result.payload["tools"]["read_only"] is True
    assert "Read-only SOC tool evidence" in gateway.requests[0].prompt


def test_create_draft_returns_insufficient_context_without_gateway(monkeypatch):
    gateway = RecordingGateway()
    monkeypatch.setattr(
        "core.ai.drafting_service.build_ai_context",
        lambda **_kwargs: _context_payload("incident", insufficient=True),
    )

    result = create_draft(
        {
            "draft_type": "incident_note",
            "instruction": "Draft a note.",
            "context_type": "incident",
            "context": {"incident_id": 7},
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.payload["status"] == "insufficient_context"
    assert result.payload["draft"]["validation"]["valid"] is False
    assert gateway.requests == []


def test_create_draft_preserves_gateway_disabled_state(monkeypatch):
    gateway = RecordingGateway(status=AI_STATUS_DISABLED, error="AI gateway is disabled.")
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("incident"))

    result = create_draft(
        {
            "draft_type": "incident_note",
            "instruction": "Draft a note.",
            "context_type": "incident",
            "context": {"incident_id": 7},
        },
        gateway=gateway,
        config=_config(mode=AI_MODE_DISABLED, configured_mode=AI_MODE_DISABLED),
    )

    assert result.payload["status"] == AI_STATUS_DISABLED
    assert result.payload["draft"]["labels"]["applied"] is False
    assert result.payload["error"] == "AI gateway is disabled."


def test_create_draft_rejects_malformed_provider_output(monkeypatch):
    gateway = RecordingGateway("this is not json")
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("incident"))

    result = create_draft(
        {
            "draft_type": "incident_note",
            "instruction": "Draft a note.",
            "context_type": "incident",
            "context": {"incident_id": 7},
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.payload["status"] == DRAFT_STATUS_PARSE_FAILED
    assert result.payload["draft"]["payload"] == {}


def test_create_draft_rejects_schema_invalid_provider_output(monkeypatch):
    gateway = RecordingGateway(json.dumps({"summary": "Only one field"}))
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("incident"))

    result = create_draft(
        {
            "draft_type": "incident_note",
            "instruction": "Draft a note.",
            "context_type": "incident",
            "context": {"incident_id": 7},
        },
        gateway=gateway,
        config=_config(),
    )

    assert result.payload["status"] == DRAFT_STATUS_VALIDATION_FAILED
    assert result.payload["draft"]["payload"] == {}
    assert result.payload["draft"]["validation"]["errors"]


def test_draft_route_auth_rbac_and_validation(client, mock_db, monkeypatch):
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("incident"))
    monkeypatch.setattr("core.ai.drafting_service.load_ai_gateway_config", lambda: _config())
    monkeypatch.setattr(
        "core.ai.drafting_service.AiGateway",
        lambda config=None: RecordingGateway(json.dumps(_valid_payload("incident_note"))),
    )

    unauthenticated = client.post("/ai/drafts", json={"draft_type": "incident_note"})
    assert unauthenticated.status_code in (302, 401)

    viewer_patchers = _login_role(client, role="viewer")
    try:
        forbidden = client.post("/ai/drafts", json={"draft_type": "incident_note"})
    finally:
        _stop_patchers(viewer_patchers)
    assert forbidden.status_code == 403

    analyst_patchers = _login_role(client, role="analyst")
    try:
        invalid = client.post("/ai/drafts", json={"draft_type": "execute_playbook", "instruction": "run", "context_type": "incident"})
        success = client.post(
            "/ai/drafts",
            json={
                "draft_type": "incident_note",
                "instruction": "Draft a note.",
                "context_type": "incident",
                "context": {"incident_id": 7},
            },
        )
    finally:
        _stop_patchers(analyst_patchers)

    assert invalid.status_code == 400
    assert invalid.get_json()["status"] == "unsupported_draft_type"
    assert success.status_code == 200
    assert success.get_json()["draft"]["labels"]["persisted"] is False


def test_draft_generation_does_not_call_representative_mutation_helpers(monkeypatch):
    gateway = RecordingGateway(json.dumps(_valid_payload("playbook_draft")))
    monkeypatch.setattr("core.ai.drafting_service.build_ai_context", lambda **_kwargs: _context_payload("alert"))
    mutation_targets = [
        "core.playbook_store.create_playbook_definition",
        "core.playbook_store.update_playbook_definition",
        "core.playbook_store.create_playbook_execution",
        "core.playbook_store.create_retry_execution",
        "core.playbook_store.mark_playbook_execution_permanently_failed",
        "core.ip_helpers.execute_response_action",
    ]
    patchers = [
        patch(target, side_effect=AssertionError(f"{target} must not be called"))
        for target in mutation_targets
    ]
    for patcher in patchers:
        patcher.start()
    try:
        result = create_draft(
            {
                "draft_type": "playbook_draft",
                "instruction": "Draft a playbook proposal only.",
                "context_type": "alert",
                "context": {"alert_id": 7},
            },
            gateway=gateway,
            config=_config(),
        )
    finally:
        for patcher in reversed(patchers):
            patcher.stop()

    assert result.payload["status"] == DRAFT_STATUS_SUCCESS
    assert result.payload["draft"]["labels"]["applied"] is False
