from datetime import datetime, timedelta, timezone

from core.recon_activity_store import build_recon_intelligence_projection


BASE_TIME = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def _summary(
    *,
    alert_count=1,
    source_count=1,
    destination_count=1,
    service_count=1,
    alert_types=None,
    progression_observed=False,
):
    return {
        "underlying_alert_count": alert_count,
        "source_ip_count": source_count,
        "destination_ip_count": destination_count,
        "distinct_service_count": service_count,
        "alert_types": alert_types or ["pfsense_firewall_port_scan"],
        "progression_observed": progression_observed,
    }


def test_singleton_recon_is_candidate_and_hidden_from_primary_views():
    projection = build_recon_intelligence_projection(
        summary=_summary(),
        coordination_status="not_established",
        related_incident_id=None,
        first_seen=BASE_TIME,
        last_seen=BASE_TIME + timedelta(minutes=5),
    )

    assert projection["classification"] == "recon_candidate"
    assert projection["confidence"] == "low"
    assert projection["primary_view_visible"] is False


def test_several_related_alerts_from_one_source_form_recon_cluster():
    projection = build_recon_intelligence_projection(
        summary=_summary(alert_count=3, source_count=1, destination_count=2, service_count=1),
        coordination_status="not_established",
        related_incident_id=None,
        first_seen=BASE_TIME,
        last_seen=BASE_TIME + timedelta(minutes=20),
    )

    assert projection["classification"] == "recon_cluster"
    assert projection["confidence"] == "low"
    assert projection["primary_view_visible"] is True


def test_multiple_sources_with_service_overlap_become_possible_campaign():
    projection = build_recon_intelligence_projection(
        summary=_summary(alert_count=3, source_count=3, destination_count=2, service_count=1),
        coordination_status="possible",
        related_incident_id=None,
        first_seen=BASE_TIME,
        last_seen=BASE_TIME + timedelta(minutes=35),
    )

    assert projection["classification"] == "possible_campaign"
    assert projection["confidence"] == "medium"
    assert projection["primary_view_visible"] is True


def test_supported_progression_or_incident_correlation_promotes_campaign_recon():
    projection = build_recon_intelligence_projection(
        summary=_summary(
            alert_count=5,
            source_count=4,
            destination_count=3,
            service_count=2,
            alert_types=["pfsense_firewall_port_scan", "pfsense_firewall_allow_after_deny"],
            progression_observed=True,
        ),
        coordination_status="supported",
        related_incident_id=42,
        first_seen=BASE_TIME,
        last_seen=BASE_TIME + timedelta(minutes=90),
    )

    assert projection["classification"] == "campaign_recon"
    assert projection["confidence"] == "high"
    assert projection["primary_view_visible"] is True
