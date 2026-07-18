from core.investigation_intelligence import build_returning_attacker_context


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
