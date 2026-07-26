from scripts.cleanup_confirmed_synthetic_dashboard_data import build_cleanup_report


def _insert_alert(cur, alert_id, source_ip, message):
    cur.execute(
        """
        INSERT INTO alerts (id, alert_type, severity, source_ip, source, source_type, message, status)
        VALUES (%s, 'legacy_synthetic', 'medium', %s, 'bank_app', 'custom', %s, 'open')
        """,
        (alert_id, source_ip, message),
    )


def _insert_event(cur, source_ip, *, source, source_type, app_name, environment, message, raw_payload):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type, message, app_name, environment, raw_payload
        )
        VALUES ('failed_login', 'medium', %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (source_ip, source, source_type, message, app_name, environment, raw_payload),
    )


def test_cleanup_report_selects_only_confirmed_alert_ids_and_synthetic_event_evidence(postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, 16, "103.103.103.103", "confirmed legacy synthetic")
    _insert_alert(cur, 17, "107.107.107.107", "confirmed legacy synthetic")
    _insert_alert(cur, 99, "103.103.103.103", "same IP but not confirmed alert id")
    _insert_alert(cur, 100, "1.1.1.1", "legitimate pfSense telemetry")
    _insert_event(
        cur,
        "103.103.103.103",
        source="simulator",
        source_type="simulator",
        app_name="simulator",
        environment="dev",
        message="Simulated failed login",
        raw_payload='{"data_provenance":"synthetic"}',
    )
    _insert_event(
        cur,
        "103.103.103.103",
        source="pfsense",
        source_type="firewall",
        app_name="pfsense_filterlog",
        environment="prod",
        message="Production-like event sharing a confirmed IP",
        raw_payload='{"data_provenance":"operational"}',
    )
    _insert_event(
        cur,
        "1.1.1.1",
        source="pfsense",
        source_type="firewall",
        app_name="pfsense_filterlog",
        environment="prod",
        message="Legitimate pfSense event",
        raw_payload='{"data_provenance":"operational"}',
    )
    conn.commit()

    report = build_cleanup_report(
        conn,
        alert_ids=(16, 17),
        source_ips=("103.103.103.103", "107.107.107.107"),
    )

    assert [row["id"] for row in report["selected_alerts"]] == [16, 17]
    assert {str(row["source_ip"]) for row in report["selected_alerts"]} == {
        "103.103.103.103",
        "107.107.107.107",
    }
    assert len(report["selected_events"]) == 1
    assert str(report["selected_events"][0]["source_ip"]) == "103.103.103.103"
    assert all(str(row.get("source_ip")) != "1.1.1.1" for row in report["selected_events"])
    assert report["would_delete"] == {"alerts": 2, "events": 1}
    assert report["refusal_reasons"] == []


def test_cleanup_report_refuses_unexpected_alert_dependencies(postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, 16, "103.103.103.103", "confirmed legacy synthetic")
    cur.execute(
        """
        INSERT INTO alert_notes (alert_id, author, note_text)
        VALUES (16, 'analyst', 'do not delete without review')
        """
    )
    conn.commit()

    report = build_cleanup_report(
        conn,
        alert_ids=(16,),
        source_ips=("103.103.103.103",),
    )

    assert report["dependency_counts"]["alert_notes"] == 1
    assert report["refusal_reasons"] == [
        {
            "code": "unexpected_dependencies",
            "counts": {"alert_notes": 1},
        }
    ]
