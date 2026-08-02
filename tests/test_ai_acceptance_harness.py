from __future__ import annotations

from dataclasses import replace

from core.ai.acceptance_harness import (
    LIVE_SWEEP_VM_COMMAND,
    ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH,
    ROOT_CAUSE_INVALID_RESPONSE,
    build_production_safe_live_sweep_matrix,
    build_complete_ai_inventory,
    build_frontend_realistic_request,
    build_acceptance_cases,
    discover_frontend_ai_options,
    render_markdown_report,
    run_acceptance_harness,
    run_live_backend_sweep,
    run_offline_contract_tier,
    run_optional_live_smoke_tier,
)
from core.ai.config import default_ai_profiles
from core.ai.profile_registry import AI_INVOCATION_INVENTORY, AI_PROFILE_FAST_TRIAGE
from core.ai.acceptance_harness import _select_live_representative_cases
from core.ai.workflow_orchestrator import CANONICAL_WORKFLOWS, WORKFLOW_AUTO


def test_acceptance_harness_covers_every_inventory_action_without_manual_button_list():
    cases = build_acceptance_cases()
    complete_inventory, _frontend_options = build_complete_ai_inventory()
    complete_keys = {entry.key for entry in complete_inventory}

    assert set(cases) == complete_keys
    for legacy in AI_INVOCATION_INVENTORY:
        assert any(
            entry.backend_path == legacy.backend_path and entry.profile == legacy.profile
            for entry in complete_inventory
        )
    assert len(complete_keys) > len(AI_INVOCATION_INVENTORY)
    assert "frontend.alert.artifact.checklist" in complete_keys
    assert "frontend.recon.artifact.response_recommendation" in complete_keys
    assert "frontend.dashboard.ask_anakin" in complete_keys
    assert all(entry.workflow in CANONICAL_WORKFLOWS for entry in complete_inventory)
    assert all(entry.workflow for entry in complete_inventory)

    report = run_offline_contract_tier()

    assert report.actions_discovered == len(complete_inventory)
    assert report.actions_covered == len(complete_inventory)
    assert report.failures_by_root_cause == {}
    assert all(result.success for result in report.results)


def test_acceptance_rows_include_required_product_debug_fields():
    report = run_offline_contract_tier()

    required_routes = {
        "POST /ai/explain",
        "POST /ai/chat",
        "POST /ai/drafts",
        "POST /ai/investigations",
        "POST /ai/workflows",
        "POST /ai/workflows/requests",
        "POST /ai/repo/requests",
        "soc_briefing_worker",
    }
    assert required_routes.issubset({result.backend_route for result in report.results})

    for result in report.results:
        assert result.action_button_name
        assert result.frontend_action_id
        assert result.backend_route
        assert result.context_type
        assert result.selected_profile
        assert result.selected_model
        assert result.prompt_size >= 0
        assert result.prompt_limit >= 0
        assert result.response_time_ms >= 0
        assert result.stale_state_result
        assert all(result.response_usefulness_checks.values())


def test_manual_briefing_lifecycle_acceptance_reaches_visible_terminal_state():
    report = run_offline_contract_tier()
    manual = next(result for result in report.results if result.frontend_action_id == "worker.soc_briefing.manual_run_now")

    assert manual.backend_route == "soc_briefing_worker"
    assert manual.selected_profile == "deep_briefing"
    assert manual.stale_state_result == "manual_lifecycle_visible_terminal:completed"
    assert manual.success is True


def test_frontend_realistic_contracts_are_discovered_from_component_sources():
    options = discover_frontend_ai_options()

    assert options["frontend.command_registry.quick_explain"]["workflow"] == "quick_explain"
    assert options["frontend.command_registry.deep_investigate"]["workflow"] == "deep_investigate"
    assert options["frontend.command_registry.decision_support"]["workflow"] == "decision_support"
    assert options["frontend.command_registry.generate_artifact"]["artifactType"] == "investigation_checklist"


def test_floating_anakin_builds_auto_workflow_payload_contract():
    payload, route = build_frontend_realistic_request(
        {
            "route": "POST /ai/workflows/requests",
            "workflow": "auto",
            "question": "What should I inspect first?",
            "contextType": "general",
            "context": {"active_section": "dashboard", "recent_alerts": [{"id": 1}]},
        }
    )

    assert route == "POST /ai/workflows/requests"
    assert payload["workflow"] == "auto"
    assert payload["prompt"] == "What should I inspect first?"
    assert payload["context_type"] == "general"
    assert "action" not in payload
    assert "model" not in payload
    assert "profile" not in payload


def test_repo_architecture_chat_builds_message_based_payload_contract():
    payload, route = build_frontend_realistic_request(
        {
            "route": "POST /ai/repo/requests",
            "message": "Where is the SOAR worker implemented?",
            "client_history": [{"role": "assistant", "content": "prior"}],
            "refresh": True,
        }
    )

    assert route == "POST /ai/repo/requests"
    assert payload == {
        "message": "Where is the SOAR worker implemented?",
        "client_history": [{"role": "assistant", "content": "prior"}],
        "refresh": True,
    }
    assert "context_type" not in payload
    assert "action" not in payload
    assert "context" not in payload


def test_invalid_context_with_timeout_seconds_metadata_is_not_provider_timeout():
    from core.ai.acceptance_harness import _root_cause_from_live

    root_cause = _root_cause_from_live(
        status="invalid_context",
        error="Unsupported context_type: analyst_workspace",
        http_status=400,
        body={"metadata": {"timeout_seconds": 90}, "status": "invalid_context"},
    )

    assert root_cause == ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH


def test_acceptance_harness_groups_failures_by_root_cause(monkeypatch):
    monkeypatch.setattr("core.ai.acceptance_harness._sample_response_for_case", lambda _entry, _case: "continue monitoring.")

    report = run_offline_contract_tier()

    assert ROOT_CAUSE_INVALID_RESPONSE in report.failures_by_root_cause
    assert len(report.failures_by_root_cause[ROOT_CAUSE_INVALID_RESPONSE]) >= 1
    assert all(not result.success for result in report.results)


def test_soc_briefing_acceptance_rejects_internal_pipeline_terms(monkeypatch):
    from core.ai.acceptance_harness import _sample_response_for_case as original_sample

    def fake_sample(entry, case):
        if entry.backend_path == "soc_briefing_worker":
            return "Assessment: 2 selected candidate(s) and 1 bounded evidence reference(s) were reviewed from /alerts/1 with get_alert_detail."
        return original_sample(entry, case)

    monkeypatch.setattr("core.ai.acceptance_harness._sample_response_for_case", fake_sample)

    report = run_offline_contract_tier()
    failed = [result for result in report.results if result.backend_route == "soc_briefing_worker"]

    assert failed
    assert all(not result.success for result in failed)
    assert ROOT_CAUSE_INVALID_RESPONSE in report.failures_by_root_cause


def test_acceptance_harness_detects_unexpected_profile_prompt_limit_regression():
    from core.ai.acceptance_harness import _acceptance_config

    config = _acceptance_config()
    profiles = dict(default_ai_profiles(local_model="llama3.1:8b", local_timeout_seconds=30))
    profiles[AI_PROFILE_FAST_TRIAGE] = replace(profiles[AI_PROFILE_FAST_TRIAGE], max_prompt_chars=10)
    config = replace(config, profiles=profiles)

    report = run_offline_contract_tier(config=config)

    assert "prompt_too_large" in report.failures_by_root_cause
    assert any(result.error_code == "prompt_exceeded_profile_limit" for result in report.results)


def test_optional_live_smoke_tier_is_disabled_without_explicit_flag(monkeypatch):
    monkeypatch.delenv("AI_ACCEPTANCE_LIVE_OLLAMA", raising=False)

    smoke = run_optional_live_smoke_tier()

    assert smoke == [
        {
            "enabled": False,
            "reason": "Set AI_ACCEPTANCE_LIVE_OLLAMA=1 to run one live local Ollama smoke request per profile.",
        }
    ]


def test_live_backend_sweep_is_disabled_without_explicit_gate(monkeypatch):
    monkeypatch.delenv("AI_ACCEPTANCE_LIVE_BACKEND_SWEEP", raising=False)

    sweep = run_live_backend_sweep()

    assert sweep["enabled"] is False
    assert "AI_ACCEPTANCE_LIVE_BACKEND_SWEEP=1" in sweep["reason"]


def test_live_backend_sweep_requires_authenticated_cookie_when_enabled(monkeypatch):
    monkeypatch.setenv("AI_ACCEPTANCE_LIVE_BACKEND_SWEEP", "1")
    monkeypatch.delenv("AI_ACCEPTANCE_SESSION_COOKIE", raising=False)

    sweep = run_live_backend_sweep(session_cookie="")

    assert sweep["enabled"] is True
    assert sweep["status"] == "blocked"
    assert "AI_ACCEPTANCE_SESSION_COOKIE" in sweep["error"]


def test_live_representative_plan_uses_unique_safe_backend_paths():
    inventory, _frontend_options = build_complete_ai_inventory()
    cases = build_acceptance_cases()

    plan = _select_live_representative_cases(inventory, cases)
    matrix = [(entry.backend_path, entry.profile, entry.key) for entry, _case in plan]
    expected_keys = {row["key"] for row in build_production_safe_live_sweep_matrix() if row["key"].startswith(("frontend.", "worker."))}

    assert {key for _path, _profile, key in matrix} == expected_keys
    assert len(plan) == 10
    assert ("POST /ai/workflows", "fast_triage", "frontend.dashboard.quick_explain") in matrix
    assert ("POST /ai/workflows/requests", "guided_analysis", "frontend.alert.deep_investigate") in matrix
    assert ("POST /ai/workflows/requests", "guided_analysis", "frontend.alert.decision_support") in matrix
    assert ("POST /ai/workflows/requests", "guided_analysis", "frontend.alert.artifact.checklist") in matrix
    assert ("POST /ai/workflows/requests", "fast_triage", "frontend.floating_anakin.ask") in matrix
    assert ("POST /ai/workflows/requests", "fast_triage", "frontend.floating_anakin.low_confidence_chooser") in matrix
    assert ("POST /ai/repo/requests", "developer_assistant", "frontend.repo_architecture.chat.factual") in matrix
    assert ("POST /ai/repo/requests", "developer_assistant", "frontend.repo_architecture.chat.evaluative") in matrix
    assert ("POST /ai/actions/preview", "guided_analysis", "frontend.ai_action.preview.add_incident_note") in matrix
    assert ("soc_briefing_worker", "deep_briefing", "worker.soc_briefing.manual_run_now") in matrix
    assert all(path != "POST /ai/actions/confirm" for path, _profile, _key in matrix)


def test_live_backend_sweep_runs_status_checks_and_representative_plan_only(monkeypatch):
    monkeypatch.setenv("AI_ACCEPTANCE_LIVE_BACKEND_SWEEP", "1")
    monkeypatch.setenv("AI_ACCEPTANCE_SESSION_COOKIE", "session=test")
    monkeypatch.setattr("core.ai.acceptance_harness._discover_live_entities", lambda _base_url, _cookie: {"incident_id": 2002})
    monkeypatch.setattr("core.ai.acceptance_harness.time.sleep", lambda _seconds: None)

    status_paths = []
    representative_paths = []

    def fake_status(_base_url, _cookie, path, frontend_action_id, _config):
        status_paths.append(path)
        return {
            "frontend_action_id": frontend_action_id,
            "execution_path": f"GET {path}",
            "route": path,
            "profile": "fast_triage",
            "model": "llama3.1:8b",
            "prompt_size": 0,
            "prompt_limit": 8000,
            "latency_ms": 1,
            "http_status": 200,
            "provider_status": "success",
            "success": True,
        }

    def fake_action(_base_url, _cookie, entry, case, _ids, _config):
        representative_paths.append(entry.backend_path)
        return {
            "frontend_action_id": entry.key,
            "execution_path": entry.backend_path,
            "route": entry.backend_path,
            "profile": entry.profile,
            "model": "llama3.1:8b",
            "prompt_size": 10,
            "prompt_limit": 14000,
            "latency_ms": 1,
            "http_status": 200,
            "provider_status": "success",
            "success": True,
        }

    def fake_briefing(_base_url, _cookie, entry, *, create_manual_briefing_job):
        assert create_manual_briefing_job is False
        representative_paths.append(entry.backend_path)
        return {
            "frontend_action_id": entry.key,
            "execution_path": "GET /soc-briefings/control",
            "route": "/soc-briefings/control",
            "profile": entry.profile,
            "model": None,
            "prompt_size": None,
            "prompt_limit": None,
            "latency_ms": 1,
            "http_status": 200,
            "provider_status": "status_only",
            "success": True,
        }

    monkeypatch.setattr("core.ai.acceptance_harness._live_status_check", fake_status)
    monkeypatch.setattr("core.ai.acceptance_harness._live_ai_action_check", fake_action)
    monkeypatch.setattr("core.ai.acceptance_harness._live_manual_briefing_check", fake_briefing)

    sweep = run_live_backend_sweep(throttle_seconds=0)

    assert sweep["offline_actions_covered"] == len(build_acceptance_cases())
    assert sweep["representative_calls_planned"] == len(build_production_safe_live_sweep_matrix())
    assert sweep["actions_invoked"] == len(build_production_safe_live_sweep_matrix())
    assert status_paths == ["/ai/status", "/ai/repo/status"]
    assert representative_paths.count("POST /ai/workflows") == 1
    assert representative_paths.count("POST /ai/workflows/requests") == 5
    assert representative_paths.count("POST /ai/repo/requests") == 2
    assert "POST /ai/actions/preview" in representative_paths
    assert "soc_briefing_worker" in representative_paths
    assert "POST /ai/explain" not in representative_paths
    assert "POST /ai/drafts" not in representative_paths
    assert "POST /ai/investigations" not in representative_paths
    assert "POST /ai/actions/confirm" not in representative_paths
    assert sweep["safety"]["live_strategy"] == "representative_unique_backend_execution_paths"
    assert sweep["safety"]["actions_confirm_route_skipped"] is True


def test_production_safe_live_sweep_matrix_is_workflow_based_and_non_mutating():
    matrix = build_production_safe_live_sweep_matrix()

    assert {row["key"] for row in matrix} == {
        "status.ai_gateway",
        "status.repo_assistant",
        "frontend.dashboard.quick_explain",
        "frontend.alert.deep_investigate",
        "frontend.alert.decision_support",
        "frontend.alert.artifact.checklist",
        "frontend.floating_anakin.ask",
        "frontend.floating_anakin.low_confidence_chooser",
        "frontend.repo_architecture.chat.factual",
        "frontend.repo_architecture.chat.evaluative",
        "worker.soc_briefing.manual_run_now",
        "frontend.ai_action.preview.add_incident_note",
    }
    assert all(row["mutation"] is False for row in matrix)
    assert any(row["workflow"] == WORKFLOW_AUTO for row in matrix)
    assert any(row.get("expected_status") == "chooser_required" for row in matrix)
    assert any(row.get("non_persistent") is True for row in matrix)
    assert any(row.get("status_only_default") is True for row in matrix)
    assert any(row.get("confirmation_skipped") is True for row in matrix)
    assert all("confirm" not in row["route"] for row in matrix)
    assert "AI_ACCEPTANCE_LIVE_BACKEND_SWEEP=1" in LIVE_SWEEP_VM_COMMAND
    assert "/ai/actions/confirm" not in LIVE_SWEEP_VM_COMMAND


def test_acceptance_report_renders_grouped_markdown_summary():
    report = run_acceptance_harness(include_live_smoke=True)
    markdown = render_markdown_report(report)

    assert "Actions discovered" in markdown
    assert "Failures By Root Cause" in markdown
    assert "Live Smoke" in markdown
    assert "frontend.dashboard.ask_anakin" in markdown
