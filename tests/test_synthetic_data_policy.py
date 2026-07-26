from engines.ingest_engine import _build_synthetic_provenance_context


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
