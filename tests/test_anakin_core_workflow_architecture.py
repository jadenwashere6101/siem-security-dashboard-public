from __future__ import annotations

import json

import pytest

from core.ai.draft_schemas import DRAFT_STATUS_SUCCESS
from core.ai.drafting_service import create_draft
from core.ai.explainer_service import AiServiceResult
from core.ai.models import AI_STATUS_SUCCESS, AiGatewayRequest, AiGatewayResponse, AiRequestMetadata
from core.ai.workflow_orchestrator import (
    DEEP_INVESTIGATE_LIFECYCLE_STAGES,
    WORKFLOW_AUTO,
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_GENERATE_ARTIFACT,
    WORKFLOW_QUICK_EXPLAIN,
    WORKFLOW_REPO_ASSISTANT,
    WORKFLOW_SOC_BRIEFING,
    WorkflowValidationError,
    classify_workflow,
    legacy_explain_context,
    run_workflow,
)
from tests.test_ai_drafting_assistant import _config, _context_payload, _valid_payload


class SequenceGateway:
    def __init__(self, contents):
        self.contents = list(contents)
        self.requests: list[AiGatewayRequest] = []

    def generate(self, request: AiGatewayRequest) -> AiGatewayResponse:
        self.requests.append(request)
        content = self.contents.pop(0)
        return AiGatewayResponse(
            status=AI_STATUS_SUCCESS,
            content=content,
            error=None,
            metadata=AiRequestMetadata(
                provider="local",
                model="llama3.1:8b",
                mode="local_only",
                status=AI_STATUS_SUCCESS,
                local_request=True,
                paid_request=False,
                profile=request.profile,
            ),
        )


def test_auto_classification_is_auditable_and_conservative_for_privileged_workflows():
    decision = classify_workflow(
        {
            "workflow": WORKFLOW_AUTO,
            "prompt": "Should I block or monitor this source?",
            "context_type": "alert",
        }
    )
    assert decision.classified_workflow == WORKFLOW_DECISION_SUPPORT
    assert decision.confidence == "high"
    assert "recommendation" in decision.reason.lower() or "decision" in decision.reason.lower()
    assert classify_workflow(
        {
            "workflow": WORKFLOW_AUTO,
            "prompt": "Should I block this source?",
            "context_type": "alert",
        }
    ).classified_workflow == WORKFLOW_DECISION_SUPPORT

    privileged = classify_workflow(
        {
            "workflow": WORKFLOW_AUTO,
            "prompt": "Generate a SOC briefing and ask the repo assistant to confirm deployment.",
            "context_type": "dashboard",
        }
    )
    assert privileged.classified_workflow == WORKFLOW_QUICK_EXPLAIN
    assert privileged.confidence == "low"
    assert privileged.chooser_required is True
    assert WORKFLOW_SOC_BRIEFING not in privileged.allowed_workflows
    assert WORKFLOW_REPO_ASSISTANT not in privileged.allowed_workflows


def test_explicit_privileged_workflow_is_not_available_from_normal_orchestrator_route():
    with pytest.raises(WorkflowValidationError) as error:
        run_workflow({"workflow": WORKFLOW_REPO_ASSISTANT, "prompt": "Where is the worker?", "context_type": "general"})

    assert error.value.status_code == 403


def test_legacy_explain_route_maps_decision_actions_through_decision_support(monkeypatch):
    captured = {}

    def fake_explain(payload, **_kwargs):
        captured.update(payload)
        return AiServiceResult(
            {
                "status": "success",
                "answer": "Monitor first because evidence is incomplete.",
                "metadata": {"profile": "guided_analysis"},
                "context": {},
                "tools": {},
                "error": None,
            }
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = legacy_explain_context(
        {
            "context_type": "alert",
            "action": "recommend_next_steps",
            "question": "What should I do?",
            "context": {"alert_id": 7},
            "model": "client-selected-model",
            "profile": "client-selected-profile",
            "timeout": 1,
        }
    )

    assert result.payload["workflow"] == WORKFLOW_DECISION_SUPPORT
    assert result.payload["classification"]["classified_workflow"] == WORKFLOW_DECISION_SUPPORT
    assert result.payload["decision_support"]["artifacts_generated"] is False
    assert "model" not in captured
    assert "profile" not in captured
    assert "timeout" not in captured


def test_decision_support_rejects_artifact_and_mutation_fields():
    with pytest.raises(WorkflowValidationError) as error:
        run_workflow(
            {
                "workflow": WORKFLOW_DECISION_SUPPORT,
                "prompt": "What should I do?",
                "context_type": "alert",
                "artifact": {"type": "incident_note"},
            }
        )

    assert error.value.error_code == "decision_support_read_only"


def test_deep_investigate_exposes_truthful_polling_lifecycle(monkeypatch):
    def fake_run_investigation(payload, **_kwargs):
        assert payload["allow_automatic_draft"] is False
        return type(
            "Result",
            (),
            {
                "status_code": 200,
                "payload": {
                    "status": "success",
                    "investigation": {
                        "steps": [
                            {"step_type": "build_context", "status": "success"},
                            {"step_type": "plan_read_tools", "status": "success"},
                            {"step_type": "execute_read_tool", "status": "success"},
                            {"step_type": "validate_evidence", "status": "success"},
                            {"step_type": "suggest_response_plan", "status": "success"},
                            {"step_type": "finalize_summary", "status": "success"},
                        ],
                        "summary": "Evidence reviewed.",
                    },
                    "metadata": {},
                    "error": None,
                },
            },
        )()

    monkeypatch.setattr("core.ai.workflow_orchestrator.run_investigation", fake_run_investigation)

    result = run_workflow(
        {
            "workflow": WORKFLOW_DEEP_INVESTIGATE,
            "prompt": "Investigate this alert.",
            "context_type": "alert",
            "entity": {"alert_id": 7},
        }
    )

    assert result.payload["workflow"] == WORKFLOW_DEEP_INVESTIGATE
    assert result.payload["lifecycle"]["mode"] == "polling"
    assert [stage["stage"] for stage in result.payload["lifecycle"]["stages"]] == list(DEEP_INVESTIGATE_LIFECYCLE_STAGES)
    assert result.payload["lifecycle"]["stage"] == "complete"


def test_generate_artifact_keeps_one_bounded_repair_attempt(monkeypatch):
    invalid = json.dumps({"summary": "Only one field"})
    valid = json.dumps(_valid_payload("incident_note"))
    gateway = SequenceGateway([invalid, valid])
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

    assert result.payload["status"] == DRAFT_STATUS_SUCCESS
    assert result.payload["metadata"]["repair_attempted"] is True
    assert result.payload["metadata"]["repair_count"] == 1
    assert len(gateway.requests) == 2
    assert gateway.requests[1].metadata["action"] == "draft_repair"
    assert gateway.requests[1].profile == gateway.requests[0].profile


def test_canonical_workflow_route_ignores_client_model_profile_timeout(monkeypatch):
    captured = {}

    def fake_explain(payload, **_kwargs):
        captured.update(payload)
        return AiServiceResult(
            {
                "status": "success",
                "answer": "Short explanation.",
                "metadata": {"profile": "fast_triage"},
                "context": {},
                "tools": {},
                "error": None,
            }
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = run_workflow(
        {
            "workflow": WORKFLOW_QUICK_EXPLAIN,
            "prompt": "Explain this alert.",
            "context_type": "alert",
            "entity": {"alert_id": 7},
            "model": "not-allowed",
            "profile": "not-allowed",
            "timeout": 1,
        }
    )

    assert result.payload["classification"]["classified_workflow"] == WORKFLOW_QUICK_EXPLAIN
    assert "model" not in captured
    assert "profile" not in captured
    assert "timeout" not in captured
