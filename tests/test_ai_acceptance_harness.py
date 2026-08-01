from __future__ import annotations

from dataclasses import replace

from core.ai.acceptance_harness import (
    ROOT_CAUSE_FRONTEND_CONTRACT_MISMATCH,
    ROOT_CAUSE_INVALID_RESPONSE,
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
    assert "frontend.alert.investigation_checklist.draft.line_264" in complete_keys
    assert "frontend.recon.response_recommendation.draft.line_1114" in complete_keys

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
        "POST /ai/repo/chat",
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

    assert options["frontend.recon.explain_recon_activity"]["contextType"] == "recon_activity"
    assert options["frontend.source_ip.explain_ip"]["context"] == {"source_ip": "203.0.113.77"}
    assert options["frontend.incident.summarize_incident"]["context"] == {"incident_id": 2002}
    assert options["frontend.response_registry.explain_response"]["context"] == {"registry_id": 4004}


def test_floating_anakin_chat_builds_message_based_payload_contract():
    payload, route = build_frontend_realistic_request(
        {
            "route": "POST /ai/chat",
            "message": "What should I inspect first?",
            "visible_context": {"active_section": "dashboard", "recent_alerts": [{"id": 1}]},
            "client_history": [{"role": "user", "content": "previous"}],
        }
    )

    assert route == "POST /ai/chat"
    assert payload == {
        "message": "What should I inspect first?",
        "visible_context": {"active_section": "dashboard", "recent_alerts": [{"id": 1}]},
        "client_history": [{"role": "user", "content": "previous"}],
        "use_tools": True,
        "tool_policy": {"max_tool_calls": 5, "time_window_hours": 24},
    }
    assert "context_type" not in payload
    assert "action" not in payload
    assert "context" not in payload


def test_repo_architecture_chat_builds_message_based_payload_contract():
    payload, route = build_frontend_realistic_request(
        {
            "route": "POST /ai/repo/chat",
            "message": "Where is the SOAR worker implemented?",
            "client_history": [{"role": "assistant", "content": "prior"}],
            "refresh": True,
        }
    )

    assert route == "POST /ai/repo/chat"
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

    assert len(plan) == 9
    assert ("POST /ai/explain", "fast_triage", "frontend.alert.explain_alert.line_184") in matrix
    assert any(path == "POST /ai/explain" and profile == "guided_analysis" for path, profile, _key in matrix)
    assert any(path == "POST /ai/drafts" for path, _profile, _key in matrix)
    assert any(path == "POST /ai/investigations" for path, _profile, _key in matrix)
    assert ("POST /ai/chat", "fast_triage", "frontend.floating_chat.general") in matrix
    assert ("POST /ai/repo/chat", "developer_assistant", "frontend.repo_architecture.chat.factual") in matrix
    assert ("POST /ai/repo/chat", "developer_assistant", "frontend.repo_architecture.chat.evaluative") in matrix
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

    assert sweep["offline_actions_covered"] == 43
    assert sweep["representative_calls_planned"] == 11
    assert sweep["actions_invoked"] == 11
    assert status_paths == ["/ai/status", "/ai/repo/status"]
    assert representative_paths.count("POST /ai/explain") == 2
    assert "POST /ai/drafts" in representative_paths
    assert "POST /ai/investigations" in representative_paths
    assert "POST /ai/chat" in representative_paths
    assert representative_paths.count("POST /ai/repo/chat") == 2
    assert "POST /ai/actions/preview" in representative_paths
    assert "soc_briefing_worker" in representative_paths
    assert "POST /ai/actions/confirm" not in representative_paths
    assert sweep["safety"]["live_strategy"] == "representative_unique_backend_execution_paths"
    assert sweep["safety"]["actions_confirm_route_skipped"] is True


def test_acceptance_report_renders_grouped_markdown_summary():
    report = run_acceptance_harness(include_live_smoke=True)
    markdown = render_markdown_report(report)

    assert "Actions discovered" in markdown
    assert "Failures By Root Cause" in markdown
    assert "Live Smoke" in markdown
    assert "frontend.dashboard.metrics.ask_dashboard" in markdown
