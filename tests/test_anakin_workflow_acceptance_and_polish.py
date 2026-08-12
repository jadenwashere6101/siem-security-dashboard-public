from __future__ import annotations

from core.ai.acceptance_harness import (
    APPROVED_SURFACE_CONTROL_MATRIX,
    CANONICAL_ACCEPTANCE_WORKFLOWS,
    REMOVED_FRONTEND_ACTION_IDS,
    REMOVED_FRONTEND_AI_LABELS,
    build_acceptance_cases,
    build_complete_ai_inventory,
    build_frontend_realistic_request,
    build_golden_reasoning_cases,
    build_production_like_alert_checklist_fixture,
    build_workflow_acceptance_summary,
    build_workflow_representative_fixtures,
    evaluate_golden_reasoning_answer,
    removed_frontend_ai_controls_present,
    run_offline_contract_tier,
)
from core.ai.config import AiGatewayConfig
from core.ai.drafting_service import _build_draft_prompt
from core.ai.explainer_service import AiServiceResult
from core.ai.workflow_orchestrator import (
    DEEP_INVESTIGATE_LIFECYCLE_STAGES,
    WORKFLOW_AUTO,
    WORKFLOW_DEEP_INVESTIGATE,
    WORKFLOW_DECISION_SUPPORT,
    WORKFLOW_GENERATE_ARTIFACT,
    WORKFLOW_QUICK_EXPLAIN,
    WORKFLOW_REPO_ASSISTANT,
    WORKFLOW_SOC_BRIEFING,
    run_workflow,
)


def test_final_workflow_acceptance_summary_has_zero_offline_failures_and_all_controls_mapped():
    summary = build_workflow_acceptance_summary()

    assert set(summary["workflows"]) == set(CANONICAL_ACCEPTANCE_WORKFLOWS)
    assert all(summary["workflows"][workflow] > 0 for workflow in CANONICAL_ACCEPTANCE_WORKFLOWS)
    assert summary["actions_discovered"] == summary["actions_covered"]
    assert summary["offline_failures"] == 0
    assert summary["failures_by_root_cause"] == {}
    assert summary["unmapped"] == []
    assert summary["obsolete_frontend_controls"] == {"labels": [], "action_ids": []}
    assert summary["legacy_adapter_count"] > 0
    assert summary["canonical_frontend_count"] > 0


def test_approved_surface_control_matrix_is_small_and_exact():
    assert APPROVED_SURFACE_CONTROL_MATRIX == {
        "Dashboard": ("Ask Anakin", "Quick Explain", "Deep Investigate"),
        "Alert Details": ("Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact"),
        "Source IP": ("Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact"),
        "Incident": ("Deep Investigate", "Decision Support", "Generate Artifact"),
        "SOC Command Center / Recon": ("Deep Investigate", "Decision Support", "Generate Artifact"),
        "Response Registry": ("Decision Support", "Deep Investigate", "Generate Artifact"),
        "Analyst Workspace": ("Deep Investigate", "Decision Support", "Generate Artifact"),
        "Global Anakin": ("Ask Anakin", "Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact"),
        "Command Palette": ("Quick Explain", "Deep Investigate", "Decision Support", "Generate Artifact", "SOC Briefing", "Repo Assistant"),
        "SOC Briefings": ("Generate/Run Briefing",),
        "Repo Assistant": ("Dedicated assistant",),
    }
    assert max(len(controls) for controls in APPROVED_SURFACE_CONTROL_MATRIX.values()) <= 6


def test_removed_legacy_frontend_controls_and_action_ids_are_absent_from_component_sources():
    obsolete = removed_frontend_ai_controls_present()

    assert obsolete == {"labels": [], "action_ids": []}
    assert "Explain this alert" not in REMOVED_FRONTEND_AI_LABELS
    assert "suggestedactions" in REMOVED_FRONTEND_ACTION_IDS


def test_representative_workflow_fixtures_cover_every_canonical_workflow_with_safe_contracts():
    fixtures = build_workflow_representative_fixtures()

    assert {fixture["workflow"] for fixture in fixtures} == set(CANONICAL_ACCEPTANCE_WORKFLOWS)
    for fixture in fixtures:
        assert fixture["prompt"]
        if fixture["workflow"] == WORKFLOW_QUICK_EXPLAIN:
            assert fixture["expected_route"] == "POST /ai/workflows"
        if fixture["workflow"] in {WORKFLOW_DEEP_INVESTIGATE, WORKFLOW_DECISION_SUPPORT, WORKFLOW_GENERATE_ARTIFACT}:
            assert fixture["expected_route"] == "POST /ai/workflows/requests"
        if fixture["workflow"] == WORKFLOW_GENERATE_ARTIFACT:
            assert fixture["non_persistent"] is True
        if fixture["workflow"] == WORKFLOW_SOC_BRIEFING:
            assert fixture["status_only"] is True
        if fixture["workflow"] == WORKFLOW_REPO_ASSISTANT:
            assert fixture["citations_backend_owned"] is True


def test_acceptance_harness_includes_production_like_alert_checklist_fixture_under_limit():
    fixture = build_production_like_alert_checklist_fixture()
    prompt = _build_draft_prompt(
        fixture["request"],
        fixture["ai_context"],
        fixture["tools"],
        config=AiGatewayConfig(mode="disabled", max_prompt_chars=14000),
        profile_max_prompt_chars=fixture["profile_max_prompt_chars"],
    )

    assert fixture["request"].draft_type == "investigation_checklist"
    assert fixture["request"].context_type == "alert"
    assert len(prompt) < fixture["profile_max_prompt_chars"]
    assert '"related_events":500' in prompt


def test_offline_inventory_maps_every_remaining_ai_control_to_one_canonical_workflow():
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()
    report = run_offline_contract_tier()

    assert set(cases) == {entry.key for entry in inventory}
    assert all(entry.workflow in CANONICAL_ACCEPTANCE_WORKFLOWS for entry in inventory)
    assert all(result.success for result in report.results)


def test_all_approved_generate_artifact_types_are_covered_by_acceptance_inventory():
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()
    artifact_types = set()
    for entry in inventory:
        case = cases[entry.key]
        if entry.workflow != WORKFLOW_GENERATE_ARTIFACT:
            continue
        artifact = case.request_payload.get("artifact") if isinstance(case.request_payload.get("artifact"), dict) else {}
        draft_type = case.request_payload.get("draft_type") or artifact.get("type")
        if draft_type:
            artifact_types.add(draft_type)

    assert artifact_types >= {
        "incident_note",
        "investigation_checklist",
        "escalation_summary",
        "playbook_draft",
        "detection_rule_change",
        "response_recommendation",
    }


def test_auto_routing_low_confidence_chooser_cannot_reach_restricted_workflows_or_mutating_paths():
    payload, route = build_frontend_realistic_request(
        {
            "route": "POST /ai/workflows",
            "workflow": WORKFLOW_AUTO,
            "question": "run briefing, repo deploy, and approve the action",
            "contextType": "general",
            "context": {"active_section": "dashboard"},
        }
    )

    result = run_workflow(payload)

    assert route == "POST /ai/workflows/requests"
    assert result.status_code == 200
    assert result.payload["status"] == "chooser_required"
    assert result.payload["classification"]["confidence"] == "low"
    assert WORKFLOW_SOC_BRIEFING not in result.payload["result"]["allowed_workflows"]
    assert WORKFLOW_REPO_ASSISTANT not in result.payload["result"]["allowed_workflows"]
    assert "confirm" not in str(result.payload).lower()


def test_quick_explain_request_is_bounded_tool_free_and_ignores_client_model_selection(monkeypatch):
    captured = {}

    def fake_explain(payload, **_kwargs):
        captured.update(payload)
        return AiServiceResult(
            {
                "status": "success",
                "answer": "Most important: no successful follow-up is visible. Next check: inspect auth outcomes.",
                "metadata": {"profile": "fast_triage", "model": "llama3.1:8b"},
                "context": {},
                "tools": {"used": False},
                "error": None,
            },
            200,
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = run_workflow(
        {
            "workflow": WORKFLOW_QUICK_EXPLAIN,
            "prompt": "What matters?",
            "context_type": "alert",
            "context": {"alert_id": 7},
            "model": "client-model",
            "profile": "client-profile",
            "timeout": 1,
        }
    )

    assert result.payload["workflow"] == WORKFLOW_QUICK_EXPLAIN
    assert captured["use_tools"] is False
    assert captured["tool_policy"] is None
    assert "model" not in captured
    assert "profile" not in captured
    assert "timeout" not in captured


def test_decision_support_is_recommendation_only_and_never_enters_artifact_contract(monkeypatch):
    captured = {}

    def fake_explain(payload, **_kwargs):
        captured.update(payload)
        return AiServiceResult(
            {
                "status": "success",
                "answer": "Primary recommendation: gather more evidence before blocking.",
                "metadata": {"profile": "guided_analysis"},
                "context": {},
                "tools": {"used": False},
                "error": None,
            },
            200,
        )

    monkeypatch.setattr("core.ai.workflow_orchestrator.explain_context", fake_explain)

    result = run_workflow(
        {
            "workflow": WORKFLOW_DECISION_SUPPORT,
            "prompt": "Should I block or escalate?",
            "context_type": "source_ip",
            "context": {"source_ip": "203.0.113.77"},
        }
    )

    assert result.payload["workflow"] == WORKFLOW_DECISION_SUPPORT
    assert result.payload["result"]["decision_support"]["read_only"] is True
    assert result.payload["result"]["decision_support"]["artifacts_generated"] is False
    assert result.payload["result"]["decision_support"]["actions_taken"] is False
    assert "do not draft artifacts" in captured["question"].lower()


def test_deep_investigate_lifecycle_uses_truthful_backend_stage_names(monkeypatch):
    def fake_investigation(payload, **_kwargs):
        assert payload["allow_automatic_draft"] is False
        return type(
            "Result",
            (),
            {
                "status_code": 200,
                "payload": {
                    "status": "success",
                    "investigation": {"steps": [{"step_type": "build_context", "status": "success"}]},
                    "metadata": {"profile": "guided_analysis"},
                    "error": None,
                },
            },
        )()

    monkeypatch.setattr("core.ai.workflow_orchestrator.run_investigation", fake_investigation)

    result = run_workflow({"workflow": WORKFLOW_DEEP_INVESTIGATE, "prompt": "Investigate.", "context_type": "alert", "context": {"alert_id": 7}})

    assert result.payload["lifecycle"]["mode"] == "polling"
    assert [stage["stage"] for stage in result.payload["lifecycle"]["stages"]] == list(DEEP_INVESTIGATE_LIFECYCLE_STAGES)
    assert "job_id" not in result.payload["lifecycle"]


def test_response_quality_acceptance_checks_properties_not_exact_wording():
    for case in build_golden_reasoning_cases():
        checks = evaluate_golden_reasoning_answer(case, case.expected_answer)
        assert all(checks.values()), (case.key, checks)
