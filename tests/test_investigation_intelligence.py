from core.investigation_intelligence import (
    build_investigation_value,
    build_local_evidence_override_reasons,
    build_returning_attacker_context,
)


def test_many_alerts_within_one_minute_are_repeated_activity_not_returning():
    context = build_returning_attacker_context(
        {
            "observed_at": [
                "2026-07-10T10:00:00Z",
                "2026-07-10T10:00:20Z",
                "2026-07-10T10:00:45Z",
            ],
            "previous_incidents": 2,
            "previous_responses": 1,
        }
    )

    assert context["is_returning"] is False
    assert context["headline"] == "Repeated activity"
    assert context["summary"] == "Repeated activity within one continuous burst"


def test_separate_observation_windows_are_returning():
    context = build_returning_attacker_context(
        {
            "observed_at": [
                "2026-07-10T10:00:00Z",
                "2026-07-10T10:05:00Z",
                "2026-07-10T18:30:00Z",
            ],
        }
    )

    assert context["is_returning"] is True
    assert context["headline"] == "Returning attacker"
    assert context["observation_window_count"] == 2
    assert context["returned_after_hours"] >= 8


def test_separate_calendar_days_are_returning():
    context = build_returning_attacker_context(
        {
            "observed_at": [
                "2026-07-10T23:00:00Z",
                "2026-07-11T01:00:00Z",
            ],
        }
    )

    assert context["is_returning"] is True
    assert context["distinct_observation_days"] == 2
    assert context["summary"] == "Seen on 2 distinct days"


def test_invalid_timestamps_fall_back_to_no_prior_history():
    context = build_returning_attacker_context({"observed_at": ["invalid"]})

    assert context["is_returning"] is False
    assert context["headline"] == "No prior history"
    assert context["summary"] == "No prior history for this source"


def test_shadow_mode_is_default_and_does_not_change_investigation_value(monkeypatch):
    monkeypatch.delenv("INTERNET_NOISE_POLICY_MODE", raising=False)

    investigation = build_investigation_value(
        alert_type="port_scan_threshold",
        severity="high",
        response_history_present=True,
        internet_noise_assessment={
            "provider": "GreyNoise",
            "assessment": "commodity",
            "explanation": "Known commodity internet scanner.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
        internet_noise_override_reasons=[],
    )

    assert investigation["level"] == "medium"
    assert investigation["internet_noise"]["policy_mode"] == "shadow"
    assert investigation["internet_noise"]["effect"] == "shadow_observation"
    assert investigation["internet_noise"]["applied_to_investigation"] is False
    assert "shadow mode recorded" in investigation["summary"].lower()


def test_policy_mode_can_lower_investigation_urgency(monkeypatch):
    monkeypatch.setenv("INTERNET_NOISE_POLICY_MODE", "policy")

    investigation = build_investigation_value(
        alert_type="port_scan_threshold",
        severity="high",
        response_history_present=True,
        internet_noise_assessment={
            "provider": "GreyNoise",
            "assessment": "commodity",
            "explanation": "Known commodity internet scanner.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
        internet_noise_override_reasons=[],
    )

    assert investigation["level"] == "low"
    assert investigation["internet_noise"]["effect"] == "reduced_urgency"
    assert investigation["internet_noise"]["applied_to_investigation"] is True
    assert "normal internet noise" in investigation["summary"]


def test_malicious_internet_noise_never_lowers_investigation_urgency():
    investigation = build_investigation_value(
        alert_type="port_scan_threshold",
        severity="high",
        internet_noise_assessment={
            "provider": "GreyNoise",
            "assessment": "malicious",
            "explanation": "Known malicious internet activity.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
    )

    assert investigation["summary"] == "High severity raises review priority"
    assert investigation["internet_noise"]["effect"] == "neutral"


def test_local_evidence_override_preserves_urgency_for_benign_internet_noise():
    overrides = build_local_evidence_override_reasons(
        alert_type="pfsense_firewall_allow_after_deny",
        progression_observed=True,
        corroborating_detection_count=2,
        repeated_destination=True,
        destination_important=True,
    )
    investigation = build_investigation_value(
        alert_type="pfsense_firewall_allow_after_deny",
        severity="high",
        progression_observed=True,
        corroborating_detection_count=2,
        repeated_destination=True,
        destination_important=True,
        internet_noise_assessment={
            "provider": "GreyNoise",
            "assessment": "commodity",
            "explanation": "Known commodity internet scanner.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
        internet_noise_override_reasons=overrides,
    )

    assert investigation["internet_noise"]["effect"] == "local_evidence_override"
    assert investigation["level"] in {"medium", "high"}
    assert "overrides the internet-noise assessment" in investigation["summary"]
