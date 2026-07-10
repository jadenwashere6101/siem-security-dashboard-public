"""Classifier report for unsupported_action dead-letter handoff."""

from scripts.classify_unsupported_action_dead_letters import classify_action


def test_classify_bare_notify_and_enrich_context():
    notify = classify_action("notify")
    assert notify["cohort"] == "ambiguous_notify"
    assert "Do not retry bare notify" in notify["hint"]

    enrich = classify_action("enrich_context")
    assert enrich["cohort"] == "misrouted_enrich_context"
    assert "playbook" in enrich["hint"].lower()


def test_classify_provider_notify_canary_hint():
    slack = classify_action("notify_slack")
    assert slack["cohort"] == "provider_notify"
    assert slack["disposition"] == "canary_retry_if_idempotent"
