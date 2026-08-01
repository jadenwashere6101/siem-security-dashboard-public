from __future__ import annotations

from dataclasses import replace

from core.ai.acceptance_harness import (
    ROOT_CAUSE_INVALID_RESPONSE,
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


def test_acceptance_harness_covers_every_inventory_action_without_manual_button_list():
    cases = build_acceptance_cases()
    inventory_keys = {entry.key for entry in AI_INVOCATION_INVENTORY}

    assert set(cases) == inventory_keys

    report = run_offline_contract_tier()

    assert report.actions_discovered == len(AI_INVOCATION_INVENTORY)
    assert report.actions_covered == len(AI_INVOCATION_INVENTORY)
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
    manual = next(result for result in report.results if result.frontend_action_id == "worker.soc_briefing.manual_and_scheduled")

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


def test_acceptance_report_renders_grouped_markdown_summary():
    report = run_acceptance_harness(include_live_smoke=True)
    markdown = render_markdown_report(report)

    assert "Actions discovered" in markdown
    assert "Failures By Root Cause" in markdown
    assert "Live Smoke" in markdown
    assert "frontend.dashboard.metrics.ask_dashboard" in markdown
