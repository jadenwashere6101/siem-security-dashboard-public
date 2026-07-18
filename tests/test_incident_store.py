import pytest
from psycopg2 import IntegrityError
from psycopg2.extras import Json

import siem_backend
from core import playbook_store
from core.incident_store import (
    auto_close_resolved_p3_incidents_for_alert,
    create_incident,
    find_open_incident_by_source_ip,
    get_incident_detail,
    link_alert_to_incident,
    list_incidents,
    maybe_create_or_link_incident,
    update_incident_status,
)


def _insert_alert(conn, cur, source_ip: str = "203.0.113.10") -> int:
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, message, status)
        VALUES ('test_alert', 'HIGH', %s::inet, 'test message', 'open')
        RETURNING id
        """,
        (source_ip,),
    )
    (aid,) = cur.fetchone()
    conn.commit()
    return aid


def _insert_custom_alert(
    conn,
    cur,
    *,
    source_ip: str,
    alert_type: str,
    severity: str = "HIGH",
    source: str = "bank_app",
    source_type: str = "custom",
    message: str = "test message",
    context=None,
) -> int:
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, context)
        VALUES (%s, %s, %s::inet, %s, %s, %s, 'open', %s)
        RETURNING id
        """,
        (alert_type, severity, source_ip, source, source_type, message, Json(context or {})),
    )
    (aid,) = cur.fetchone()
    conn.commit()
    return aid


def _count_incidents(cur):
    cur.execute("SELECT COUNT(*) FROM incidents")
    return cur.fetchone()[0]


def _count_links(cur):
    cur.execute("SELECT COUNT(*) FROM incident_alerts")
    return cur.fetchone()[0]


def _count_escalation_audits(cur):
    cur.execute(
        "SELECT COUNT(*) FROM audit_log WHERE event_type = 'incident_severity_escalated'"
    )
    return cur.fetchone()[0]


def _count_auto_close_audits(cur):
    cur.execute(
        "SELECT COUNT(*) FROM audit_log WHERE event_type = 'incident_auto_closed'"
    )
    return cur.fetchone()[0]


def _insert_queue_row(cur, *, alert_id: int, source_ip: str, status: str) -> int:
    cur.execute(
        """
        INSERT INTO response_actions_queue (idempotency_key, alert_id, source_ip, action, status)
        VALUES (md5(random()::text), %s, %s::inet, 'block_ip', %s)
        RETURNING id
        """,
        (alert_id, source_ip, status),
    )
    return cur.fetchone()[0]


def _insert_playbook_execution(cur, *, alert_id: int, incident_id: int, status: str) -> int:
    conn = cur.connection
    if playbook_store.get_playbook_definition(conn, "auto_close_pb") is None:
        playbook_store.create_playbook_definition(
            conn,
            "auto_close_pb",
            "Auto Close PB",
            steps=[{"action": "monitor", "params": {}}],
        )
    execution_id = playbook_store.create_playbook_execution(
        conn,
        "auto_close_pb",
        alert_id=alert_id,
        incident_id=incident_id,
    )
    playbook_store.update_execution_status(conn, execution_id, status)
    return execution_id


def _insert_pending_approval(cur, *, incident_id: int) -> int:
    cur.execute(
        """
        INSERT INTO approval_requests (incident_id, status, action, expires_at)
        VALUES (%s, 'pending', 'playbook.require_approval', NOW() + INTERVAL '1 hour')
        RETURNING id
        """,
        (incident_id,),
    )
    return cur.fetchone()[0]


def _insert_user(cur, *, user_id: int, username: str) -> int:
    cur.execute(
        """
        INSERT INTO users (id, username, password_hash, role, is_active)
        VALUES (%s, %s, 'test-hash', 'analyst', TRUE)
        """,
        (user_id, username),
    )
    return user_id


class _AuditSafeConnection:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return None


def test_schema_tables_exist(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name IN ('incidents', 'incident_alerts')
        ORDER BY table_name
        """
    )
    names = [r[0] for r in cur.fetchall()]
    assert names == ["incident_alerts", "incidents"]


def test_schema_status_check_rejects_unknown(postgres_db):
    conn, cur = postgres_db
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES ('t', 'HIGH', 'P2', 'unknown', '198.51.100.1'::inet)
            """
        )


def test_schema_priority_check_rejects_p5(postgres_db):
    conn, cur = postgres_db
    with pytest.raises(IntegrityError):
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES ('t', 'HIGH', 'P5', 'open', '198.51.100.1'::inet)
            """
        )


def test_schema_duplicate_primary_incident_alerts_raises(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(conn, cur)
    inc = create_incident(conn, "t", "HIGH", "203.0.113.1")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
        (iid, aid),
    )
    with pytest.raises(IntegrityError):
        cur.execute(
            "INSERT INTO incident_alerts (incident_id, alert_id) VALUES (%s, %s)",
            (iid, aid),
        )


def test_create_incident_returns_expected_fields(postgres_db):
    conn, _cur = postgres_db
    row = create_incident(conn, "My title", "HIGH", "203.0.113.5")
    conn.commit()
    assert row["title"] == "My title"
    assert row["severity"] == "HIGH"
    assert row["priority"] == "P2"
    assert row["status"] == "open"
    assert row["source_ip"] == "203.0.113.5"
    assert row["assigned_to"] is None
    assert row["resolved_at"] is None
    assert isinstance(row["id"], int)
    assert row["created_at"]


def test_create_incident_critical_maps_priority_p1(postgres_db):
    conn, _cur = postgres_db
    row = create_incident(conn, "c", "CRITICAL", "203.0.113.6")
    conn.commit()
    assert row["priority"] == "P1"


def test_link_alert_to_incident_idempotent(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(conn, cur)
    inc = create_incident(conn, "t", "HIGH", "203.0.113.7")
    conn.commit()
    iid = inc["id"]
    link_alert_to_incident(conn, iid, aid)
    conn.commit()
    link_alert_to_incident(conn, iid, aid)
    conn.commit()
    cur.execute(
        "SELECT COUNT(*) FROM incident_alerts WHERE incident_id = %s AND alert_id = %s",
        (iid, aid),
    )
    assert cur.fetchone()[0] == 1


def test_find_open_returns_none_when_empty(postgres_db):
    conn, _cur = postgres_db
    assert find_open_incident_by_source_ip(conn, "203.0.113.20") is None


def test_find_open_ignores_resolved_within_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.21")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET status = 'resolved' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    assert find_open_incident_by_source_ip(conn, "203.0.113.21", 60) is None


def test_find_open_ignores_closed_within_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.22")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET status = 'closed' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    assert find_open_incident_by_source_ip(conn, "203.0.113.22", 60) is None


def test_find_open_finds_open_within_window(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.23")
    conn.commit()
    found = find_open_incident_by_source_ip(conn, "203.0.113.23", 60)
    assert found is not None
    assert found["id"] == inc["id"]


def test_find_open_finds_investigating_within_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "t", "HIGH", "203.0.113.24")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET status = 'investigating' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    found = find_open_incident_by_source_ip(conn, "203.0.113.24", 60)
    assert found is not None
    assert found["id"] == iid


def test_find_open_returns_none_outside_window(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "old", "HIGH", "203.0.113.25")
    conn.commit()
    iid = inc["id"]
    cur.execute(
        "UPDATE incidents SET created_at = NOW() - INTERVAL '2 hours' WHERE id = %s",
        (iid,),
    )
    conn.commit()
    assert find_open_incident_by_source_ip(conn, "203.0.113.25", 60) is None


def test_find_open_most_recent_when_multiple_open_same_ip(postgres_db):
    conn, cur = postgres_db
    older = create_incident(conn, "a", "HIGH", "203.0.113.26")
    conn.commit()
    cur.execute(
        "UPDATE incidents SET created_at = NOW() - INTERVAL '30 minutes' WHERE id = %s",
        (older["id"],),
    )
    conn.commit()
    newer = create_incident(conn, "b", "HIGH", "203.0.113.26")
    conn.commit()
    found = find_open_incident_by_source_ip(conn, "203.0.113.26", 120)
    assert found is not None
    assert found["id"] == newer["id"]


def test_maybe_create_returns_none_for_medium_and_low(postgres_db):
    conn, cur = postgres_db
    aid_hi = _insert_alert(conn, cur, "203.0.113.30")
    assert maybe_create_or_link_incident(conn, aid_hi, "MEDIUM", "203.0.113.30") is None
    conn.commit()
    assert _count_incidents(cur) == 0

    aid_lo = _insert_alert(conn, cur, "203.0.113.31")
    assert maybe_create_or_link_incident(conn, aid_lo, "LOW", "203.0.113.31") is None
    conn.commit()
    assert _count_incidents(cur) == 0


def test_maybe_create_high_creates_and_links(postgres_db):
    conn, cur = postgres_db
    aid = _insert_alert(conn, cur, "203.0.113.32")
    inc = maybe_create_or_link_incident(conn, aid, "HIGH", "203.0.113.32")
    conn.commit()
    assert inc is not None
    assert inc["severity"] == "HIGH"
    assert _count_incidents(cur) == 1
    assert _count_links(cur) == 1
    cur.execute(
        "SELECT incident_id FROM incident_alerts WHERE alert_id = %s",
        (aid,),
    )
    assert cur.fetchone()[0] == inc["id"]
    assert inc["priority"] == "P3"


def test_shadow_mode_is_default_and_keeps_incident_policy_neutral(
    postgres_db, monkeypatch
):
    monkeypatch.delenv("INTERNET_NOISE_POLICY_MODE", raising=False)
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.132",
        alert_type="port_scan_threshold",
        severity="HIGH",
        context={},
    )
    monkeypatch.setattr(
        "core.incident_store.get_internet_noise_assessment",
        lambda *_args, **_kwargs: {
            "provider": "GreyNoise",
            "assessment": "commodity",
            "explanation": "Known commodity internet scanner.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "HIGH",
        "203.0.113.132",
        alert_type="port_scan_threshold",
        context={},
    )
    conn.commit()

    assert incident is not None
    assert incident["severity"] == "HIGH"
    assert _count_incidents(cur) == 1


def test_policy_mode_can_keep_high_alert_visible_without_incident(
    postgres_db, monkeypatch
):
    monkeypatch.setenv("INTERNET_NOISE_POLICY_MODE", "policy")
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.134",
        alert_type="port_scan_threshold",
        severity="HIGH",
        context={},
    )
    monkeypatch.setattr(
        "core.incident_store.get_internet_noise_assessment",
        lambda *_args, **_kwargs: {
            "provider": "GreyNoise",
            "assessment": "commodity",
            "explanation": "Known commodity internet scanner.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "HIGH",
        "203.0.113.134",
        alert_type="port_scan_threshold",
        context={},
    )
    conn.commit()

    assert incident is None
    assert _count_incidents(cur) == 0


def test_local_progression_overrides_commodity_internet_noise_for_incident_creation(
    postgres_db, monkeypatch
):
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.133",
        alert_type="pfsense_firewall_allow_after_deny",
        severity="HIGH",
        source="pfsense",
        source_type="firewall",
        context={
            "progression_observed": True,
            "corroborating_detection_count": 2,
            "operational_flags": {"incident_eligible": True},
            "target_context": {"distinct_destination_count": 1, "distinct_port_count": 1},
        },
    )
    monkeypatch.setattr(
        "core.incident_store.get_internet_noise_assessment",
        lambda *_args, **_kwargs: {
            "provider": "GreyNoise",
            "assessment": "commodity",
            "explanation": "Known commodity internet scanner.",
            "confidence": "high",
            "last_checked": "2026-07-18T12:00:00+00:00",
            "cached": True,
            "lookup_status": "succeeded",
            "provider_metadata": {},
        },
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "HIGH",
        "203.0.113.133",
        alert_type="pfsense_firewall_allow_after_deny",
        context={
            "progression_observed": True,
            "corroborating_detection_count": 2,
            "operational_flags": {"incident_eligible": True},
            "target_context": {"distinct_destination_count": 1, "distinct_port_count": 1},
        },
    )
    conn.commit()

    assert incident is not None
    assert incident["priority"] in {"P2", "P3"}


def test_maybe_create_links_existing_open_in_window(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.33")
    first = maybe_create_or_link_incident(conn, aid1, "HIGH", "203.0.113.33")
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.33")
    second = maybe_create_or_link_incident(conn, aid2, "HIGH", "203.0.113.33")
    conn.commit()
    assert second["id"] == first["id"]
    assert _count_incidents(cur) == 1
    assert _count_links(cur) == 2


def test_maybe_create_new_when_outside_dedup_window(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.34")
    first = maybe_create_or_link_incident(conn, aid1, "HIGH", "203.0.113.34")
    conn.commit()
    cur.execute(
        "UPDATE incidents SET created_at = NOW() - INTERVAL '3 hours' WHERE id = %s",
        (first["id"],),
    )
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.34")
    second = maybe_create_or_link_incident(conn, aid2, "HIGH", "203.0.113.34")
    conn.commit()
    assert second["id"] != first["id"]
    assert _count_incidents(cur) == 2


def test_maybe_create_new_when_existing_resolved(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.35")
    prev = maybe_create_or_link_incident(conn, aid1, "HIGH", "203.0.113.35")
    conn.commit()
    update_incident_status(conn, prev["id"], "resolved", "u1")
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.35")
    nxt = maybe_create_or_link_incident(conn, aid2, "HIGH", "203.0.113.35")
    conn.commit()
    assert nxt["id"] != prev["id"]
    assert _count_incidents(cur) == 2


def test_maybe_create_critical_dedup_same_as_high(postgres_db):
    conn, cur = postgres_db
    aid1 = _insert_alert(conn, cur, "203.0.113.36")
    one = maybe_create_or_link_incident(conn, aid1, "CRITICAL", "203.0.113.36")
    conn.commit()
    aid2 = _insert_alert(conn, cur, "203.0.113.36")
    two = maybe_create_or_link_incident(conn, aid2, "CRITICAL", "203.0.113.36")
    conn.commit()
    assert two["id"] == one["id"]


def test_honeypot_scanner_detected_stays_alert_only(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.70",
        alert_type="honeypot_scanner_detected",
        severity="MEDIUM",
        source="honeypot",
        source_type="honeypot",
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "MEDIUM",
        "203.0.113.70",
        alert_type="honeypot_scanner_detected",
        context={},
    )
    conn.commit()

    assert incident is None
    assert _count_incidents(cur) == 0


def test_honeypot_admin_probe_stays_alert_only(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.71",
        alert_type="honeypot_admin_probe_threshold",
        severity="MEDIUM",
        source="honeypot",
        source_type="honeypot",
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "MEDIUM",
        "203.0.113.71",
        alert_type="honeypot_admin_probe_threshold",
        context={},
    )
    conn.commit()

    assert incident is None
    assert _count_incidents(cur) == 0


def test_honeypot_env_probe_is_alert_first_without_stronger_evidence(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.72",
        alert_type="honeypot_env_probe_threshold",
        severity="HIGH",
        source="honeypot",
        source_type="honeypot",
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "HIGH",
        "203.0.113.72",
        alert_type="honeypot_env_probe_threshold",
        context={},
    )
    conn.commit()

    assert incident is None
    assert _count_incidents(cur) == 0


def test_honeypot_env_probe_can_escalate_with_stronger_evidence(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.73",
        alert_type="honeypot_env_probe_threshold",
        severity="HIGH",
        source="honeypot",
        source_type="honeypot",
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "HIGH",
        "203.0.113.73",
        alert_type="honeypot_env_probe_threshold",
        context={"corroborating_detection_count": 2, "repeated_sensitive_path_probe": True},
    )
    conn.commit()

    assert incident is not None
    assert incident["priority"] == "P3"
    assert _count_incidents(cur) == 1


def test_honeypot_credential_stuffing_remains_incident_eligible_as_p3(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="203.0.113.74",
        alert_type="honeypot_credential_stuffing_threshold",
        severity="HIGH",
        source="honeypot",
        source_type="honeypot",
    )

    incident = maybe_create_or_link_incident(
        conn,
        alert_id,
        "HIGH",
        "203.0.113.74",
        alert_type="honeypot_credential_stuffing_threshold",
        context={},
    )
    conn.commit()

    assert incident is not None
    assert incident["priority"] == "P3"


def test_grouped_recon_incident_reuses_recon_activity_owner(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO recon_activities (
            activity_type, source, source_type, status, severity, coordination_status,
            protected_range_key, service_signature, first_seen, last_seen, assessment_text, membership_evidence, summary
        )
        VALUES (
            'distributed_internet_reconnaissance', 'pfsense', 'firewall', 'monitoring', 'high', 'possible',
            '203.0.113.0/24', '[1194]'::jsonb, NOW() - INTERVAL '10 minutes', NOW(),
            'Repeated VPN recon', '{}'::jsonb, '{"source_ip_count": 3, "destination_ip_count": 1, "distinct_service_count": 1}'
        )
        RETURNING id
        """
    )
    recon_activity_id = cur.fetchone()[0]
    conn.commit()

    first_alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="198.51.100.90",
        alert_type="pfsense_firewall_port_scan",
        severity="HIGH",
        source="pfsense",
        source_type="firewall",
        context={
            "operational_flags": {"incident_eligible": True},
            "recon_activity": {"id": recon_activity_id, "source_ip_count": 3},
            "target_context": {"primary_destination_ip": "203.0.113.20", "distinct_destination_count": 1, "distinct_port_count": 1},
        },
    )
    second_alert_id = _insert_custom_alert(
        conn,
        cur,
        source_ip="198.51.100.91",
        alert_type="pfsense_firewall_port_scan",
        severity="HIGH",
        source="pfsense",
        source_type="firewall",
        context={
            "operational_flags": {"incident_eligible": True},
            "recon_activity": {"id": recon_activity_id, "source_ip_count": 3},
            "target_context": {"primary_destination_ip": "203.0.113.20", "distinct_destination_count": 1, "distinct_port_count": 1},
        },
    )

    first = maybe_create_or_link_incident(
        conn,
        first_alert_id,
        "HIGH",
        "198.51.100.90",
        alert_type="pfsense_firewall_port_scan",
        context={
            "operational_flags": {"incident_eligible": True},
            "recon_activity": {"id": recon_activity_id, "source_ip_count": 3},
            "target_context": {"primary_destination_ip": "203.0.113.20", "distinct_destination_count": 1, "distinct_port_count": 1},
        },
    )
    second = maybe_create_or_link_incident(
        conn,
        second_alert_id,
        "HIGH",
        "198.51.100.91",
        alert_type="pfsense_firewall_port_scan",
        context={
            "operational_flags": {"incident_eligible": True},
            "recon_activity": {"id": recon_activity_id, "source_ip_count": 3},
            "target_context": {"primary_destination_ip": "203.0.113.20", "distinct_destination_count": 1, "distinct_port_count": 1},
        },
    )
    conn.commit()

    assert first is not None
    assert second is not None
    assert first["id"] == second["id"]
    assert first["priority"] == "P3"
    cur.execute("SELECT related_incident_id FROM recon_activities WHERE id = %s", (recon_activity_id,))
    assert cur.fetchone()[0] == first["id"]
    assert _count_incidents(cur) == 1
    assert _count_links(cur) == 2


def test_critical_alert_upgrades_existing_high_incident_and_audits(postgres_db):
    conn, cur = postgres_db
    audit_conn = _AuditSafeConnection(conn)
    first_alert_id = _insert_alert(conn, cur, "203.0.113.37")
    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        incident = maybe_create_or_link_incident(conn, first_alert_id, "HIGH", "203.0.113.37")
    conn.commit()

    second_alert_id = _insert_alert(conn, cur, "203.0.113.37")
    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        linked = maybe_create_or_link_incident(conn, second_alert_id, "CRITICAL", "203.0.113.37")
    conn.commit()

    assert linked["id"] == incident["id"]
    cur.execute("SELECT severity, priority FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone() == ("CRITICAL", "P1")
    assert _count_incidents(cur) == 1
    assert _count_escalation_audits(cur) == 1
    cur.execute(
        """
        SELECT details
        FROM audit_log
        WHERE event_type = 'incident_severity_escalated'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    audit = cur.fetchone()[0]
    assert audit["incident_id"] == incident["id"]
    assert audit["from_severity"] == "HIGH"
    assert audit["to_severity"] == "CRITICAL"
    assert audit["from_priority"] == "P3"
    assert audit["to_priority"] == "P1"


def test_critical_alert_link_to_existing_critical_incident_is_noop(postgres_db):
    conn, cur = postgres_db
    audit_conn = _AuditSafeConnection(conn)
    first_alert_id = _insert_alert(conn, cur, "203.0.113.38")
    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        incident = maybe_create_or_link_incident(conn, first_alert_id, "CRITICAL", "203.0.113.38")
    conn.commit()

    second_alert_id = _insert_alert(conn, cur, "203.0.113.38")
    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        linked = maybe_create_or_link_incident(conn, second_alert_id, "CRITICAL", "203.0.113.38")
    conn.commit()

    assert linked["id"] == incident["id"]
    assert _count_incidents(cur) == 1
    assert _count_escalation_audits(cur) == 0


def test_high_alert_never_downgrades_existing_critical_incident(postgres_db):
    conn, cur = postgres_db
    audit_conn = _AuditSafeConnection(conn)
    first_alert_id = _insert_alert(conn, cur, "203.0.113.39")
    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        incident = maybe_create_or_link_incident(conn, first_alert_id, "CRITICAL", "203.0.113.39")
    conn.commit()

    second_alert_id = _insert_alert(conn, cur, "203.0.113.39")
    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        linked = maybe_create_or_link_incident(conn, second_alert_id, "HIGH", "203.0.113.39")
    conn.commit()

    assert linked["id"] == incident["id"]
    cur.execute("SELECT severity, priority FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone() == ("CRITICAL", "P1")
    assert _count_escalation_audits(cur) == 0


def test_list_incidents_ordered_and_filters(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, created_at)
        VALUES
          ('a', 'MEDIUM', 'P2', 'open', '198.51.100.1'::inet, NOW() - INTERVAL '3 hours'),
          ('b', 'CRITICAL', 'P1', 'resolved', '198.51.100.2'::inet, NOW() - INTERVAL '2 hours'),
          ('c', 'CRITICAL', 'P1', 'open', '198.51.100.3'::inet, NOW() - INTERVAL '1 hour')
        """
    )
    conn.commit()
    rows = list_incidents(conn)
    titles = [r["title"] for r in rows]
    assert titles == ["c", "b", "a"]
    open_only = list_incidents(conn, status="open")
    assert len(open_only) == 2
    crit = list_incidents(conn, severity="CRITICAL")
    assert len(crit) == 2


def test_list_incidents_limit_clamped(postgres_db):
    conn, cur = postgres_db
    for n in range(110):
        cur.execute(
            """
            INSERT INTO incidents (title, severity, priority, status, source_ip)
            VALUES (%s, 'LOW', 'P2', 'closed', '198.51.100.10'::inet)
            """,
            (f"bulk-{n}",),
        )
    conn.commit()
    assert len(list_incidents(conn, status="closed", limit=200)) == 100


def test_list_incidents_empty(postgres_db):
    conn, _cur = postgres_db
    assert list_incidents(conn) == []


def test_list_incidents_offset(postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO incidents (title, severity, priority, status, source_ip, created_at)
        VALUES
          ('x1', 'HIGH', 'P2', 'open', '198.51.100.20'::inet, NOW() - INTERVAL '20 minutes'),
          ('x2', 'HIGH', 'P2', 'open', '198.51.100.21'::inet, NOW() - INTERVAL '10 minutes'),
          ('x3', 'HIGH', 'P2', 'open', '198.51.100.22'::inet, NOW())
        """
    )
    conn.commit()
    page = list_incidents(conn, limit=1, offset=1)
    assert len(page) == 1
    assert page[0]["title"] == "x2"


def test_list_incidents_since_tuning_excludes_legacy_only_pfsense_incidents(postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", "2026-06-01T00:00:00Z")
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, created_at)
        VALUES
          ('pfsense_firewall_repeated_deny', 'HIGH', '198.51.100.40'::inet, 'pfsense', 'firewall', 'legacy', 'open', '2026-05-01T00:00:00+00:00'),
          ('pfsense_firewall_port_scan', 'HIGH', '198.51.100.41'::inet, 'pfsense', 'firewall', 'current', 'open', '2026-06-15T00:00:00+00:00'),
          ('failed_login_threshold', 'HIGH', '198.51.100.42'::inet, 'bank_app', 'custom', 'non-pfsense', 'open', '2026-05-01T00:00:00+00:00')
        RETURNING id
        """
    )
    legacy_alert_id, current_alert_id, non_pfsense_alert_id = [row[0] for row in cur.fetchall()]
    legacy_incident = create_incident(conn, "legacy", "HIGH", "198.51.100.40")
    current_incident = create_incident(conn, "current", "HIGH", "198.51.100.41")
    non_pfsense_incident = create_incident(conn, "other", "HIGH", "198.51.100.42")
    link_alert_to_incident(conn, legacy_incident["id"], legacy_alert_id)
    link_alert_to_incident(conn, current_incident["id"], current_alert_id)
    link_alert_to_incident(conn, non_pfsense_incident["id"], non_pfsense_alert_id)
    conn.commit()

    rows = list_incidents(conn, operational_scope="since_tuning")
    titles = {row["title"] for row in rows}

    assert titles == {"current", "other"}


def test_get_incident_detail_marks_pre_tuning_pfsense_incident(postgres_db, monkeypatch):
    conn, cur = postgres_db
    monkeypatch.setenv("SIEM_PFSENSE_TUNING_BASELINE", "2026-06-01T00:00:00Z")
    cur.execute(
        """
        INSERT INTO alerts (alert_type, severity, source_ip, source, source_type, message, status, created_at)
        VALUES ('pfsense_firewall_repeated_deny', 'HIGH', '198.51.100.43'::inet, 'pfsense', 'firewall', 'legacy', 'open', '2026-05-01T00:00:00+00:00')
        RETURNING id
        """
    )
    alert_id = cur.fetchone()[0]
    incident = create_incident(conn, "legacy detail", "HIGH", "198.51.100.43")
    link_alert_to_incident(conn, incident["id"], alert_id)
    conn.commit()

    detail = get_incident_detail(conn, incident["id"])

    assert detail["operational_history"]["is_pre_tuning"] is True
    assert detail["alerts"][0]["operational_history"]["is_pre_tuning"] is True


def test_get_incident_unknown_returns_none(postgres_db):
    conn, _cur = postgres_db
    assert get_incident_detail(conn, 999999) is None


def test_get_incident_detail_with_alerts(postgres_db):
    conn, cur = postgres_db
    inc = create_incident(conn, "detail", "HIGH", "203.0.113.40")
    conn.commit()
    aid = _insert_alert(conn, cur, "203.0.113.40")
    link_alert_to_incident(conn, inc["id"], aid)
    conn.commit()
    detail = get_incident_detail(conn, inc["id"])
    assert detail["id"] == inc["id"]
    assert len(detail["alerts"]) == 1
    a0 = detail["alerts"][0]
    assert a0["alert_id"] == aid
    assert a0["alert_type"] == "test_alert"
    assert a0["linked_at"]


def test_get_incident_no_links_empty_alerts(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "solo", "HIGH", "203.0.113.41")
    conn.commit()
    detail = get_incident_detail(conn, inc["id"])
    assert detail["alerts"] == []


def test_update_open_to_investigating(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.50")
    conn.commit()
    out = update_incident_status(conn, inc["id"], "investigating", "alice")
    conn.commit()
    assert out["status"] == "investigating"
    assert out["resolved_at"] is None


def test_update_open_to_resolved_sets_resolved_at(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.51")
    conn.commit()
    out = update_incident_status(conn, inc["id"], "resolved", "alice")
    conn.commit()
    assert out["status"] == "resolved"
    assert out["resolved_at"] is not None


def test_update_resolved_to_open_keeps_resolved_at(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.52")
    conn.commit()
    r1 = update_incident_status(conn, inc["id"], "resolved", "alice")
    conn.commit()
    ts = r1["resolved_at"]
    r2 = update_incident_status(conn, inc["id"], "open", "alice")
    conn.commit()
    assert r2["status"] == "open"
    assert r2["resolved_at"] == ts


def test_update_closed_to_open_raises(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.53")
    conn.commit()
    update_incident_status(conn, inc["id"], "resolved", "alice")
    conn.commit()
    update_incident_status(conn, inc["id"], "closed", "alice")
    conn.commit()
    with pytest.raises(ValueError, match="invalid status transition"):
        update_incident_status(conn, inc["id"], "open", "alice")


def test_update_unknown_status_raises(postgres_db):
    conn, _cur = postgres_db
    inc = create_incident(conn, "st", "HIGH", "203.0.113.54")
    conn.commit()
    with pytest.raises(ValueError, match="invalid status transition"):
        update_incident_status(conn, inc["id"], "bogus", "alice")


def test_update_unknown_incident_raises(postgres_db):
    conn, _cur = postgres_db
    with pytest.raises(ValueError, match="incident not found"):
        update_incident_status(conn, 999999, "investigating", "alice")


def test_auto_close_resolved_p3_incident_closes_only_when_all_linked_alerts_resolved_and_audits(postgres_db):
    conn, cur = postgres_db
    audit_conn = _AuditSafeConnection(conn)
    alert_id = _insert_alert(conn, cur, "203.0.113.210")
    incident = create_incident(conn, "auto close", "HIGH", "203.0.113.210", priority="P3")
    link_alert_to_incident(conn, incident["id"], alert_id)
    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    conn.commit()

    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        closed = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
    conn.commit()

    assert closed == [incident["id"]]
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone()[0] == "closed"
    assert _count_auto_close_audits(cur) == 1
    cur.execute(
        """
        SELECT details
        FROM audit_log
        WHERE event_type = 'incident_auto_closed'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    details = cur.fetchone()[0]
    assert details["incident_id"] == incident["id"]
    assert details["closure_policy"] == "p3_resolved_autoclose"
    assert "All linked alerts resolved" in details["reason"]


def test_auto_close_resolved_p3_incident_skips_when_any_linked_alert_open(postgres_db):
    conn, cur = postgres_db
    first_alert_id = _insert_alert(conn, cur, "203.0.113.211")
    second_alert_id = _insert_alert(conn, cur, "203.0.113.211")
    incident = create_incident(conn, "skip open linked", "HIGH", "203.0.113.211", priority="P3")
    link_alert_to_incident(conn, incident["id"], first_alert_id)
    link_alert_to_incident(conn, incident["id"], second_alert_id)
    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (first_alert_id,))
    conn.commit()

    closed = auto_close_resolved_p3_incidents_for_alert(conn, first_alert_id)
    conn.commit()

    assert closed == []
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone()[0] == "open"


def test_auto_close_resolved_p3_incident_skips_pending_approval(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(conn, cur, "203.0.113.212")
    incident = create_incident(conn, "skip approval", "HIGH", "203.0.113.212", priority="P3")
    link_alert_to_incident(conn, incident["id"], alert_id)
    _insert_pending_approval(cur, incident_id=incident["id"])
    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    conn.commit()

    closed = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
    conn.commit()

    assert closed == []
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone()[0] == "open"


def test_auto_close_resolved_p3_incident_skips_active_queue_or_playbook(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(conn, cur, "203.0.113.213")
    incident = create_incident(conn, "skip active work", "HIGH", "203.0.113.213", priority="P3")
    link_alert_to_incident(conn, incident["id"], alert_id)
    _insert_queue_row(cur, alert_id=alert_id, source_ip="203.0.113.213", status="running")
    _insert_playbook_execution(cur, alert_id=alert_id, incident_id=incident["id"], status="awaiting_approval")
    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    conn.commit()

    closed = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
    conn.commit()

    assert closed == []
    cur.execute("SELECT status FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone()[0] == "open"


def test_auto_close_resolved_p3_incident_skips_investigating_or_assigned(postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(conn, cur, "203.0.113.214")
    incident = create_incident(conn, "skip analyst review", "HIGH", "203.0.113.214", priority="P3")
    link_alert_to_incident(conn, incident["id"], alert_id)
    _insert_user(cur, user_id=1, username="autoclose-analyst")
    cur.execute(
        "UPDATE incidents SET status = 'investigating', assigned_to = 1 WHERE id = %s",
        (incident["id"],),
    )
    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    conn.commit()

    closed = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
    conn.commit()

    assert closed == []
    cur.execute("SELECT status, assigned_to FROM incidents WHERE id = %s", (incident["id"],))
    assert cur.fetchone() == ("investigating", 1)


def test_auto_close_resolved_p3_incident_is_idempotent(postgres_db):
    conn, cur = postgres_db
    audit_conn = _AuditSafeConnection(conn)
    alert_id = _insert_alert(conn, cur, "203.0.113.215")
    incident = create_incident(conn, "idempotent close", "HIGH", "203.0.113.215", priority="P3")
    link_alert_to_incident(conn, incident["id"], alert_id)
    cur.execute("UPDATE alerts SET status = 'resolved' WHERE id = %s", (alert_id,))
    conn.commit()

    with siem_backend.app.app_context(), pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.audit_helpers.get_db_connection", lambda: audit_conn)
        first = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
        second = auto_close_resolved_p3_incidents_for_alert(conn, alert_id)
    conn.commit()

    assert first == [incident["id"]]
    assert second == []
    assert _count_auto_close_audits(cur) == 1
