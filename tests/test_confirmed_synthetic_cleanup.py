from pathlib import Path

import pytest

from scripts import cleanup_confirmed_synthetic_dashboard_data as cleanup_script
from core.synthetic_data_policy import CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS
from scripts.cleanup_confirmed_synthetic_dashboard_data import (
    CONFIRMATION_TOKEN,
    build_cleanup_report,
    execute_cleanup,
)


REVIEWED_SYNTHETIC_IPS = tuple(sorted(CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS))


def test_cleanup_script_imports_and_displays_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["cleanup_confirmed_synthetic_dashboard_data.py", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        cleanup_script.main()

    assert exc_info.value.code == 0
    assert "Dry-run or execute cleanup" in capsys.readouterr().out


def _insert_alert(
    cur,
    alert_id,
    source_ip,
    message,
    *,
    alert_type="legacy_synthetic",
    source="bank_app",
    source_type="custom",
    context="'{}'::jsonb",
    created_at="NOW()",
):
    cur.execute(
        f"""
        INSERT INTO alerts (
            id, alert_type, severity, source_ip, source, source_type, message, status, context, created_at
        )
        VALUES (%s, %s, 'medium', %s, %s, %s, %s, 'open', {context}, {created_at})
        """,
        (alert_id, alert_type, source_ip, source, source_type, message),
    )


def _insert_event(cur, source_ip, *, source, source_type, app_name, environment, message, raw_payload):
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type, message, app_name, environment, raw_payload
        )
        VALUES ('failed_login', 'medium', %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (source_ip, source, source_type, message, app_name, environment, raw_payload),
    )
    return cur.fetchone()[0]


def test_cleanup_report_selects_reviewed_synthetic_alerts_and_preserves_production_alerts(postgres_db):
    conn, cur = postgres_db
    for source_ip in REVIEWED_SYNTHETIC_IPS:
        _insert_event(
            cur,
            source_ip,
            source="demo",
            source_type="custom",
            app_name="simulator",
            environment="dev",
            message="Reviewed synthetic event batch",
            raw_payload='{"data_provenance":"synthetic"}',
        )
    selected_ids = []
    for index in range(44):
        source_ip = REVIEWED_SYNTHETIC_IPS[index % len(REVIEWED_SYNTHETIC_IPS)]
        alert_id = 1000 + index
        selected_ids.append(alert_id)
        if index % 4 == 0:
            _insert_alert(cur, alert_id, source_ip, f"seeded synthetic alert user{index}")
        elif index % 4 == 1:
            _insert_alert(cur, alert_id, source_ip, "explicit source=demo batch", source="demo")
        elif index % 4 == 2:
            _insert_alert(
                cur,
                alert_id,
                source_ip,
                "Azure smoke test alert",
                source="azure_insights",
                source_type="cloud_api",
            )
        else:
            _insert_alert(
                cur,
                alert_id,
                source_ip,
                "canonical provenance alert",
                context="'{\"data_provenance\":\"synthetic\"}'::jsonb",
            )

    _insert_alert(
        cur,
        9001,
        "1.1.1.1",
        "legitimate pfSense telemetry",
        alert_type="pfsense_firewall_repeated_deny",
        source="pfsense",
        source_type="firewall",
        created_at="NOW() - INTERVAL '5 days'",
    )
    _insert_alert(
        cur,
        9002,
        "8.8.8.8",
        "legitimate bank-app traffic",
        alert_type="failed_login_threshold",
        created_at="NOW() - INTERVAL '5 days'",
    )
    _insert_alert(
        cur,
        9003,
        "198.51.100.10",
        "documentation sample should not be cleanup-selected",
        alert_type="failed_login_threshold",
    )
    conn.commit()

    report = build_cleanup_report(conn)

    assert {row["id"] for row in report["selected_alerts"]} == set(selected_ids)
    assert all(row["id"] not in {9001, 9002, 9003} for row in report["selected_alerts"])
    assert report["would_delete"]["alerts"] == 44
    assert report["would_delete"]["events"] == len(REVIEWED_SYNTHETIC_IPS)
    assert report["refusal_reasons"] == []


def test_cleanup_report_selects_synthetic_events_without_capturing_real_one_dot_one(postgres_db):
    conn, cur = postgres_db
    selected_event_id = _insert_event(
        cur,
        "1.1.1.1",
        source="bank_app",
        source_type="custom",
        app_name="simulator",
        environment="dev",
        message="Simulated failed login",
        raw_payload='{"data_provenance":"synthetic"}',
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
    _insert_event(
        cur,
        "8.8.8.8",
        source="bank_app",
        source_type="custom",
        app_name="bank_api",
        environment="prod",
        message="Legitimate bank-app event",
        raw_payload='{"data_provenance":"operational"}',
    )
    conn.commit()

    report = build_cleanup_report(conn)

    assert [row["id"] for row in report["selected_events"]] == [selected_event_id]
    assert all(row["message"] != "Legitimate pfSense event" for row in report["selected_events"])


def test_cleanup_report_allows_benign_monitor_only_dependencies(postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, 16, "103.103.103.103", "confirmed legacy synthetic")
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
    cur.execute(
        """
        INSERT INTO response_actions_queue (idempotency_key, alert_id, source_ip, action, status)
        VALUES ('monitor-only-16', 16, '103.103.103.103', 'monitor', 'pending')
        """
    )
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (16, '103.103.103.103', 'monitor', 'success', 'monitor-only')
        """
    )
    conn.commit()

    report = build_cleanup_report(conn, alert_ids=(16,), source_ips=("103.103.103.103",))

    assert report["dependency_counts"]["response_actions_queue"] == 1
    assert report["dependency_counts"]["response_actions_log"] == 1
    assert report["benign_monitor_dependency_counts"] == {
        "response_actions_queue": 1,
        "response_actions_log": 1,
    }
    assert report["refusal_reasons"] == []


def test_cleanup_report_allows_reviewed_synthetic_note_and_simulated_escalation(postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, 16, "103.103.103.103", "confirmed legacy synthetic")
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
    cur.execute(
        """
        INSERT INTO alert_notes (alert_id, author, note_text)
        VALUES (16, 'admin', 'this is a test note from synthetic cleanup verification')
        """
    )
    cur.execute(
        """
        INSERT INTO response_actions_log (alert_id, source_ip, action, status, details)
        VALUES (16, '103.103.103.103', 'escalate', 'success', 'simulated escalation test artifact')
        """
    )
    conn.commit()

    report = build_cleanup_report(conn, alert_ids=(16,), source_ips=("103.103.103.103",))

    assert report["dependency_counts"]["alert_notes"] == 1
    assert report["dependency_counts"]["response_actions_log"] == 1
    assert report["benign_monitor_dependency_counts"] == {
        "alert_notes": 1,
        "response_actions_log": 1,
    }
    assert report["refusal_reasons"] == []


def test_cleanup_report_blocks_unexpected_dependencies(postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, 16, "103.103.103.103", "confirmed legacy synthetic")
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
    cur.execute(
        """
        INSERT INTO alert_notes (alert_id, author, note_text)
        VALUES (16, 'analyst', 'do not delete without review')
        """
    )
    conn.commit()

    report = build_cleanup_report(conn, alert_ids=(16,), source_ips=("103.103.103.103",))

    assert report["dependency_counts"]["alert_notes"] == 1
    assert report["refusal_reasons"] == [
        {
            "code": "unexpected_dependencies",
            "counts": {"alert_notes": 1},
        }
    ]


def test_cleanup_dry_run_confirmation_backup_and_execution_remove_no_orphaned_events(postgres_db, tmp_path):
    conn, cur = postgres_db
    _insert_alert(cur, 16, "103.103.103.103", "confirmed legacy synthetic")
    event_id = _insert_event(
        cur,
        "103.103.103.103",
        source="simulator",
        source_type="simulator",
        app_name="simulator",
        environment="dev",
        message="Simulated failed login",
        raw_payload='{"data_provenance":"synthetic"}',
    )
    cur.execute(
        """
        INSERT INTO response_actions_queue (idempotency_key, alert_id, source_ip, action, status)
        VALUES ('execution-monitor-16', 16, '103.103.103.103', 'monitor', 'pending')
        """
    )
    conn.commit()

    dry_run = execute_cleanup(conn)
    assert dry_run["mode"] == "dry_run"
    cur.execute("SELECT COUNT(*) FROM alerts WHERE id = 16")
    assert cur.fetchone()[0] == 1

    refused = execute_cleanup(conn, execute=True, confirm="wrong-token", backup_dir=tmp_path)
    assert refused["mode"] == "refused"
    assert refused["refusal_reasons"] == [{"code": "missing_confirmation_token"}]
    assert list(Path(tmp_path).glob("*.json")) == []

    executed = execute_cleanup(conn, execute=True, confirm=CONFIRMATION_TOKEN, backup_dir=tmp_path)
    assert executed["mode"] == "executed"
    assert executed["deleted"] == {"alerts": 1, "events": 1}
    assert Path(executed["backup_path"]).exists()
    assert list(Path(tmp_path).glob("confirmed_synthetic_dashboard_cleanup_*.json"))

    cur.execute("SELECT COUNT(*) FROM alerts WHERE id = 16")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM events WHERE id = %s", (event_id,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT alert_id FROM response_actions_queue WHERE idempotency_key = 'execution-monitor-16'")
    assert cur.fetchone()[0] is None
    cur.execute(
        """
        SELECT COUNT(*)
        FROM alerts a
        WHERE a.source_ip = '103.103.103.103'::inet
          AND a.created_at >= NOW() - INTERVAL '24 hours'
        """
    )
    assert cur.fetchone()[0] == 0
