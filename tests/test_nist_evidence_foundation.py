from datetime import datetime, timedelta, timezone
import json

import pytest

from core.nist_evidence_catalog import (
    CATALOG_HASH,
    PARTIAL_SIEM_EVIDENCE,
    STRONG_SIEM_EVIDENCE,
    V1_MAPPINGS,
    catalog_document,
)
from core.nist_evidence_collectors import CollectorContext, collect_all_categories
from core.nist_evidence_engine import (
    CONFIDENCE_DEGRADED,
    CONFIDENCE_HEALTHY,
    CONFIDENCE_UNKNOWN,
    EVIDENCE_AVAILABLE,
    NO_EVIDENCE_FOUND,
    NOT_ASSESSABLE_BY_SIEM,
    PARTIAL_EVIDENCE,
    EvidenceBundle,
    classify_operational_record,
    classify_soar_outcome,
    collection_confidence_for_sources,
    evaluate_requirement,
)
from core.source_health import aggregate_source_health
from core.source_inventory import normalize_source_id


NOW = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
START = NOW - timedelta(hours=1)


def _mapping(requirement_id):
    return next(item for item in V1_MAPPINGS if item.requirement_id == requirement_id)


def _health(status="healthy", *, updated_at=NOW):
    entry = {
        "source": "bank_app",
        "health_status": status,
        "latest_ingestion_at": updated_at.isoformat(),
    }
    return {"generated_at": NOW.isoformat(), "sources": [entry]}


def test_v1_catalog_has_exactly_the_approved_12_mappings_and_strengths():
    assert [(item.requirement_id, item.requirement_name) for item in V1_MAPPINGS] == [
        ("03.03.01", "Event Logging"),
        ("03.03.02", "Audit Record Content"),
        ("03.03.03", "Audit Record Generation"),
        ("03.03.04", "Response to Audit Logging Process Failures"),
        ("03.03.05", "Audit Record Review, Analysis, and Reporting"),
        ("03.03.06", "Audit Record Reduction and Report Generation"),
        ("03.03.07", "Time Stamps"),
        ("03.06.01", "Incident Handling"),
        ("03.06.02", "Incident Monitoring, Reporting, and Response Assistance"),
        ("03.14.06", "System Monitoring"),
        ("03.13.01", "Boundary Protection"),
        ("03.01.08", "Unsuccessful Logon Attempts"),
    ]
    strengths = {item.requirement_id: item.mapping_strength for item in V1_MAPPINGS}
    assert sum(value == STRONG_SIEM_EVIDENCE for value in strengths.values()) == 5
    assert sum(value == PARTIAL_SIEM_EVIDENCE for value in strengths.values()) == 7
    assert len(CATALOG_HASH) == 64
    assert catalog_document()["catalog_hash"] == CATALOG_HASH


def test_catalog_uses_canonical_source_names_and_contains_no_outcome_claim_fields():
    document = catalog_document()
    source_ids = {source for item in V1_MAPPINGS for source in item.source_requirements}
    assert {"azure_insights", "opentelemetry", "nginx"}.issubset(source_ids)
    assert not {"azure", "otlp", "web_log"} & source_ids
    assert normalize_source_id("azure") == "azure_insights"
    assert normalize_source_id("otlp") == "opentelemetry"
    assert normalize_source_id("web_log") == "nginx"
    serialized = json.dumps(document).lower()
    for forbidden_field in (
        '"compliant"', '"compliance_status"', '"passed"',
        '"failed_control"', '"certification_status"',
    ):
        assert forbidden_field not in serialized


def test_status_engine_keeps_mapping_strength_status_and_confidence_separate():
    mapping = _mapping("03.03.01")
    bundles = [EvidenceBundle(category, 1) for category in mapping.evidence_categories]
    result = evaluate_requirement(
        mapping, bundles, collection_confidence=CONFIDENCE_HEALTHY,
        window_start=START, window_end=NOW,
    )
    assert mapping.mapping_strength == PARTIAL_SIEM_EVIDENCE
    assert result.evidence_status == EVIDENCE_AVAILABLE
    assert result.collection_confidence == CONFIDENCE_HEALTHY


@pytest.mark.parametrize(
    ("bundles", "confidence", "expected"),
    [
        ((EvidenceBundle("event_types", 1),), CONFIDENCE_HEALTHY, PARTIAL_EVIDENCE),
        ((), CONFIDENCE_DEGRADED, PARTIAL_EVIDENCE),
        ((), CONFIDENCE_UNKNOWN, PARTIAL_EVIDENCE),
        (
            (EvidenceBundle("event_types", 0), EvidenceBundle("detection_configuration", 0)),
            CONFIDENCE_HEALTHY,
            NO_EVIDENCE_FOUND,
        ),
    ],
)
def test_status_engine_partial_and_empty_rules(bundles, confidence, expected):
    result = evaluate_requirement(
        _mapping("03.03.01"), bundles, collection_confidence=confidence,
        window_start=START, window_end=NOW,
    )
    assert result.evidence_status == expected


def test_status_engine_supports_explicit_non_siem_requirement():
    source = _mapping("03.03.07")
    outside = type(source)(
        requirement_id="example", requirement_name="External Evidence",
        mapping_strength=source.mapping_strength, evidence_categories=(),
        source_requirements=(), limitation="External evidence required.",
        assessable_by_siem=False, not_assessable_rationale="Configuration inspection required.",
    )
    result = evaluate_requirement(
        outside, (), collection_confidence=CONFIDENCE_UNKNOWN,
        window_start=START, window_end=NOW,
    )
    assert result.evidence_status == NOT_ASSESSABLE_BY_SIEM
    assert result.reason_code == "outside_siem_visibility"


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (_health("healthy"), CONFIDENCE_HEALTHY),
        (_health("degraded"), CONFIDENCE_DEGRADED),
        (_health("unknown"), CONFIDENCE_UNKNOWN),
    ],
)
def test_collection_confidence_handles_canonical_health_states(snapshot, expected):
    assert collection_confidence_for_sources(snapshot, ("bank_app",), observed_at=NOW) == expected


def test_collection_confidence_preserves_legacy_checkpoint_snapshot_compatibility():
    snapshot = {
        "sources": [{
            "source": "azure_insights",
            "connector_status": "healthy",
            "last_poll_at": (NOW - timedelta(hours=3)).isoformat(),
        }]
    }
    assert collection_confidence_for_sources(
        snapshot, ("azure_insights",), observed_at=NOW
    ) == CONFIDENCE_DEGRADED


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("healthy", "healthy"), CONFIDENCE_HEALTHY),
        (("healthy", "degraded"), CONFIDENCE_DEGRADED),
        (("healthy", "unknown"), CONFIDENCE_UNKNOWN),
    ],
)
def test_collection_confidence_mixed_boundary_precedence(states, expected):
    snapshot = {
        "sources": [
            {"source": "pfsense", "health_status": states[0]},
            {"source": "azure_insights", "health_status": states[1]},
        ]
    }
    assert collection_confidence_for_sources(
        snapshot, ("pfsense", "azure_insights"), observed_at=NOW
    ) == expected


def test_production_push_source_without_checkpoint_can_reach_evidence_available(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type, event_timestamp,
            message, app_name, environment, raw_payload, created_at
        ) VALUES (
            'firewall_deny', 'medium', '9.9.9.9', 'pfsense', 'firewall', %s,
            'recent real firewall evidence', 'pfsense', 'prod', '{}'::jsonb, %s
        )
        """,
        (NOW - timedelta(minutes=2), NOW - timedelta(minutes=1)),
    )
    cur.execute(
        """
        INSERT INTO source_ingestion_health_state (
            source, latest_event_at, latest_qualifying_real_ingestion_at
        ) VALUES ('pfsense', %s, %s)
        """,
        (NOW - timedelta(minutes=1), NOW - timedelta(minutes=1)),
    )
    conn.commit()

    snapshot = aggregate_source_health(conn, generated_at=NOW)
    confidence = collection_confidence_for_sources(
        snapshot, ("pfsense",), observed_at=NOW
    )
    mapping = _mapping("03.13.01")
    result = evaluate_requirement(
        mapping,
        [EvidenceBundle(category, 1) for category in mapping.evidence_categories],
        collection_confidence=confidence,
        window_start=START,
        window_end=NOW,
    )

    assert confidence == CONFIDENCE_HEALTHY
    assert result.evidence_status == EVIDENCE_AVAILABLE


def test_stale_and_never_seen_push_health_propagate_to_nist_confidence(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type,
            message, app_name, environment, raw_payload, created_at
        ) VALUES (
            'firewall_deny', 'medium', '9.9.9.9', 'pfsense', 'firewall',
            'stale real firewall evidence', 'pfsense', 'prod', '{}'::jsonb, %s
        )
        """,
        (NOW - timedelta(hours=1),),
    )
    cur.execute(
        """
        INSERT INTO source_ingestion_health_state (
            source, latest_event_at, latest_qualifying_real_ingestion_at
        ) VALUES ('pfsense', %s, %s)
        """,
        (NOW - timedelta(hours=1), NOW - timedelta(hours=1)),
    )
    conn.commit()

    snapshot = aggregate_source_health(conn, generated_at=NOW)

    assert collection_confidence_for_sources(
        snapshot, ("pfsense",), observed_at=NOW
    ) == CONFIDENCE_DEGRADED
    assert collection_confidence_for_sources(
        snapshot, ("opentelemetry",), observed_at=NOW
    ) == CONFIDENCE_UNKNOWN


@pytest.mark.parametrize("health_status", (CONFIDENCE_DEGRADED, CONFIDENCE_UNKNOWN))
def test_unhealthy_collection_cannot_produce_no_evidence_found(health_status):
    mapping = _mapping("03.13.01")
    result = evaluate_requirement(
        mapping,
        [EvidenceBundle(category, 0) for category in mapping.evidence_categories],
        collection_confidence=health_status,
        window_start=START,
        window_end=NOW,
    )

    assert result.evidence_status == PARTIAL_EVIDENCE
    assert result.evidence_status != NO_EVIDENCE_FOUND


def test_soar_and_synthetic_classification_is_conservative():
    assert classify_soar_outcome(
        execution_mode="real", execution_state="succeeded", external_executed=True
    ) == "real"
    assert classify_soar_outcome(
        execution_mode="simulation", execution_state="succeeded", external_executed=False,
        simulated=True,
    ) == "simulated"
    assert classify_soar_outcome(
        execution_mode="tracking_only", execution_state="succeeded", external_executed=False,
        tracking_recorded=True,
    ) == "tracking_only"
    assert classify_soar_outcome(
        execution_mode="real", execution_state="blocked", external_executed=False
    ) == "blocked"
    assert classify_operational_record(provenance="demo") == "synthetic"
    assert classify_operational_record(source_ip="203.0.113.77") == "synthetic"
    assert classify_operational_record(source_ip="8.8.4.4") == "real"


def _seed_collector_records(conn, cur):
    for source, source_type in (
        ("bank_app", "custom"), ("pfsense", "firewall"),
        ("nginx", "web_log"), ("azure_insights", "cloud_api"),
        ("opentelemetry", "telemetry"),
    ):
        cur.execute(
            """
            INSERT INTO ingestion_checkpoints (
                connector_name, last_processed_at, last_poll_status, last_poll_counts, updated_at
            ) VALUES (%s, %s, 'success', '{}'::jsonb, %s)
            """,
            (source, NOW, NOW),
        )
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type, event_timestamp,
            message, app_name, environment, raw_payload, created_at
        ) VALUES
            ('failed_login', 'high', '8.8.4.4', 'bank_app', 'custom', %s,
             'failed login evidence', 'bank', 'prod', '{}'::jsonb, %s),
            ('firewall_deny', 'medium', '8.8.4.5', 'pfsense', 'firewall', %s,
             'firewall deny evidence', 'pfsense', 'prod', '{}'::jsonb, %s)
        """,
        (NOW - timedelta(minutes=20), NOW - timedelta(minutes=19),
         NOW - timedelta(minutes=15), NOW - timedelta(minutes=14)),
    )
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, context, created_at
        ) VALUES
            ('failed_login_threshold', 'high', '8.8.4.4', 'bank_app', 'custom',
             'authentication threshold evidence', 'open', '{}'::jsonb, %s),
            ('firewall_rule_match', 'medium', '8.8.4.5', 'pfsense', 'firewall',
             'firewall finding evidence', 'open', '{}'::jsonb, %s)
        RETURNING id
        """,
        (NOW - timedelta(minutes=18), NOW - timedelta(minutes=13)),
    )
    alert_ids = [row[0] for row in cur.fetchall()]
    cur.execute(
        """
        INSERT INTO detection_config (rule_id, parameters, active, updated_by, updated_at)
        VALUES ('failed_login_threshold', '{}'::jsonb, TRUE, 'tester', %s)
        """,
        (NOW,),
    )
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, created_at)
        VALUES ('Collector incident', 'high', 'P2', 'investigating', '8.8.4.4', %s)
        RETURNING id
        """,
        (NOW - timedelta(minutes=12),),
    )
    incident_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO incident_alerts (incident_id, alert_id, linked_at) VALUES (%s, %s, %s)",
        (incident_id, alert_ids[0], NOW - timedelta(minutes=11)),
    )
    cur.execute(
        "INSERT INTO incident_notes (incident_id, author, note_text, created_at) VALUES (%s, 'analyst', 'bounded note', %s)",
        (incident_id, NOW - timedelta(minutes=10)),
    )
    cur.execute(
        """
        INSERT INTO approval_requests (
            incident_id, status, action, risk_level, request_reason, created_at, expires_at
        ) VALUES (%s, 'pending', 'block_ip', 'high', 'bounded approval', %s, %s)
        """,
        (incident_id, NOW - timedelta(minutes=8), NOW + timedelta(hours=1)),
    )
    cur.execute(
        """
        INSERT INTO analyst_workspaces (owner_username, name)
        VALUES ('analyst', 'NIST collector') RETURNING id
        """
    )
    workspace_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO evidence_references (
            owner_username, workspace_id, referenced_object_type, referenced_object_id,
            label, source, rationale, relationship_type, created_at
        ) VALUES ('analyst', %s, 'alert', %s, 'bounded alert reference', 'bank_app',
                  'collector fixture', 'supports', %s)
        """,
        (workspace_id, str(alert_ids[0]), NOW - timedelta(minutes=9)),
    )
    conn.commit()


def test_collectors_cover_every_v1_mapping_with_bounded_canonical_references(postgres_db):
    conn, cur = postgres_db
    _seed_collector_records(conn, cur)
    snapshot = {
        "generated_at": NOW.isoformat(),
        "sources": [
            {"source": source, "health_status": "healthy"}
            for source in ("bank_app", "pfsense", "nginx", "azure_insights", "opentelemetry")
        ],
    }
    bundles = collect_all_categories(
        cur,
        CollectorContext(
            source_ids=("bank_app", "pfsense", "nginx", "azure_insights", "opentelemetry"),
            environments=("prod",), window_start=START, window_end=NOW,
            collected_at=NOW, source_health_snapshot=snapshot, reference_limit=1,
        ),
    )
    for mapping in V1_MAPPINGS:
        assert set(mapping.evidence_categories).issubset(bundles), mapping.requirement_id
        result = evaluate_requirement(
            mapping, (bundles[category] for category in mapping.evidence_categories),
            collection_confidence=CONFIDENCE_HEALTHY, window_start=START, window_end=NOW,
        )
        assert result.requirement_id == mapping.requirement_id
        assert result.evidence_status in {EVIDENCE_AVAILABLE, PARTIAL_EVIDENCE, NO_EVIDENCE_FOUND}

    event_ref = bundles["failed_logons"].references[0]
    assert event_ref.canonical_source == "bank_app"
    assert event_ref.occurrence_timestamp != event_ref.ingestion_timestamp
    assert len(event_ref.query_hash) == 64
    assert "raw_payload" not in json.dumps(event_ref.as_dict()).lower()
    assert bundles["monitored_events"].omitted_count >= 1
    approval_ref = next(
        item for item in bundles["response_workflow"].references
        if item.evidence_type == "approval_workflow"
    )
    assert approval_ref.operational_classification == "approval_only"
    assert approval_ref.operational_classification != "real"


def test_synthetic_only_event_is_excluded_from_operational_collector_count(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type, event_timestamp,
            message, app_name, environment, raw_payload, created_at
        ) VALUES ('failed_login', 'high', '203.0.113.77', 'bank_app', 'custom', %s,
                  'synthetic event', 'bank', 'prod', '{"data_provenance":"demo"}'::jsonb, %s)
        """,
        (NOW - timedelta(minutes=10), NOW - timedelta(minutes=9)),
    )
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, created_at)
        VALUES ('Synthetic incident', 'high', 'P2', 'open', '203.0.113.77', %s)
        RETURNING id
        """,
        (NOW - timedelta(minutes=8),),
    )
    incident_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO incident_notes (incident_id, author, note_text, created_at) VALUES (%s, 'test', 'demo note', %s)",
        (incident_id, NOW - timedelta(minutes=7)),
    )
    conn.commit()
    bundles = collect_all_categories(
        cur,
        CollectorContext(
            source_ids=("bank_app",), environments=("prod",), window_start=START,
            window_end=NOW, collected_at=NOW, source_health_snapshot=_health(),
        ),
    )
    assert bundles["failed_logons"].evidence_count == 0
    assert bundles["failed_logons"].references == ()
    assert bundles["incidents"].evidence_count == 0
    assert bundles["incident_documentation"].evidence_count == 0
