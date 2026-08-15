from engines.ingest_engine import _build_synthetic_provenance_context
from core.synthetic_data_policy import (
    CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS,
    CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS,
    load_synthetic_source_ip_exclusions,
    is_synthetic_json_payload,
    synthetic_json_provenance_value,
)


def test_one_dot_one_is_cleanup_eligible_but_not_globally_excluded_from_dashboard(monkeypatch):
    monkeypatch.delenv("SIEM_SYNTHETIC_SOURCE_IP_EXCLUSIONS", raising=False)
    monkeypatch.delenv("SYNTHETIC_SOURCE_IP_EXCLUSIONS", raising=False)
    exclusions, _ = load_synthetic_source_ip_exclusions()

    assert "1.1.1.1" in CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS
    assert "1.1.1.1" not in CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS
    assert "1.1.1.1" not in exclusions


def test_ingest_event_with_canonical_synthetic_provenance_marks_alert_context():
    context = _build_synthetic_provenance_context(
        {
            "source": "bank_app",
            "source_type": "custom",
            "app_name": "simulator",
            "raw_payload": {
                "data_provenance": "synthetic",
                "provenance": {
                    "classification": "synthetic",
                    "origin": "simulate_attacks.py",
                },
            },
        }
    )

    assert context == {
        "data_provenance": "synthetic",
        "provenance": {
            "classification": "synthetic",
            "origin": "simulate_attacks.py",
        },
    }


def test_operational_event_without_synthetic_markers_has_no_synthetic_context():
    context = _build_synthetic_provenance_context(
        {
            "source": "pfsense",
            "source_type": "firewall",
            "app_name": "pfsense_filterlog",
            "raw_payload": {"data_provenance": "operational"},
        }
    )

    assert context is None


def test_canonical_json_classifier_uses_ordered_supported_paths():
    assert is_synthetic_json_payload({"data_provenance": "synthetic"}) is True
    assert is_synthetic_json_payload(
        {"provenance": {"classification": "demo"}}
    ) is True
    assert is_synthetic_json_payload(
        {"metadata": {"provenance": "manual_test"}}
    ) is True
    assert synthetic_json_provenance_value(
        {
            "data_provenance": "operational",
            "provenance": {"classification": "synthetic"},
        }
    ) == "operational"
    assert is_synthetic_json_payload(
        {
            "data_provenance": "operational",
            "provenance": {"classification": "synthetic"},
        }
    ) is False
