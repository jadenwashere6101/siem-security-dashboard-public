from contextlib import contextmanager
from unittest.mock import patch

from helpers.query_helpers import build_alert_csv_query


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"


class _RouteSafeConnection:
    """Wraps postgres_db connection; ignores close(), delegates commit/rollback."""

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


@contextmanager
def _patched_app_db(conn):
    """Patch route-level, reporting blueprint, and audit-helper DB connections to use the test conn."""
    wrapper = _RouteSafeConnection(conn)
    with patch("core.audit_helpers.get_db_connection", return_value=wrapper), patch(
        "routes.reporting_routes.get_db_connection", return_value=wrapper
    ):
        yield


@contextmanager
def _patched_route_db_only(conn):
    """Patch route-level DB only — for routes that do not call log_audit_event."""
    wrapper = _RouteSafeConnection(conn)
    with patch("routes.reporting_routes.get_db_connection", return_value=wrapper):
        yield


def _login_super_admin(client):
    resp = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert resp.status_code == 200


def _insert_alert(
    cur,
    *,
    source_ip="198.51.100.250",
    message="Reporting contract alert",
    alert_type="failed_login_threshold",
    severity="high",
    status="open",
    source="bank_app",
    source_type="custom",
):
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (alert_type, severity, source_ip, source, source_type, message, status),
    )
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# GET /alerts/<id>/report  (text/plain single-alert report)
# ---------------------------------------------------------------------------


def test_single_alert_txt_report_without_session_returns_401(client):
    resp = client.get("/alerts/1/report")
    assert resp.status_code == 401


def test_single_alert_txt_report_nonexistent_id_returns_404(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/alerts/999999/report")

    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_single_alert_txt_report_authenticated_returns_text_download(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.30", message="TXT report contract")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/report")

    assert resp.status_code == 200
    assert "text/plain" in resp.content_type
    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert f"incident-report-alert-{alert_id}.txt" in disposition
    assert len(resp.data) > 0


# ---------------------------------------------------------------------------
# GET /alerts/<id>/report/pdf  (PDF single-alert report)
# ---------------------------------------------------------------------------


def test_single_alert_pdf_report_without_session_returns_401(client):
    resp = client.get("/alerts/1/report/pdf")
    assert resp.status_code == 401


def test_single_alert_pdf_report_nonexistent_id_returns_404(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/alerts/999999/report/pdf")

    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_single_alert_pdf_report_authenticated_returns_pdf_download(client, postgres_db):
    conn, cur = postgres_db
    alert_id = _insert_alert(cur, source_ip="198.51.100.31", message="PDF report contract")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get(f"/alerts/{alert_id}/report/pdf")

    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert f"incident-report-alert-{alert_id}.pdf" in disposition
    # Minimal PDF magic-bytes check — confirms ReportLab produced a real PDF.
    assert resp.data[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# GET /alerts/report  (text/plain multi-alert report)
# ---------------------------------------------------------------------------


def test_multi_alert_txt_report_without_session_returns_401(client):
    resp = client.get("/alerts/report")
    assert resp.status_code == 401


def test_multi_alert_txt_report_authenticated_returns_text_download(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/alerts/report")

    assert resp.status_code == 200
    assert "text/plain" in resp.content_type
    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert "incident-report-alerts.txt" in disposition
    assert len(resp.data) > 0


def test_multi_alert_txt_report_includes_seeded_alert(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(cur, source_ip="198.51.100.32", message="Multi-alert TXT contract marker")
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/alerts/report")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="replace")
    assert "ALERT 1" in body


# ---------------------------------------------------------------------------
# GET /alerts/report/pdf  (PDF multi-alert report)
# ---------------------------------------------------------------------------


def test_multi_alert_pdf_report_without_session_returns_401(client):
    resp = client.get("/alerts/report/pdf")
    assert resp.status_code == 401


def test_multi_alert_pdf_report_authenticated_returns_pdf_download(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    with _patched_app_db(conn):
        resp = client.get("/alerts/report/pdf")

    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert "incident-report-alerts.pdf" in disposition
    assert resp.data[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# GET /alerts/export/csv  (CSV export, requires analyst_or_super_admin)
# ---------------------------------------------------------------------------


def test_csv_export_without_session_returns_401(client):
    resp = client.get("/alerts/export/csv")
    assert resp.status_code == 401


def test_csv_export_authenticated_returns_csv_with_header_row(client, postgres_db):
    conn, cur = postgres_db
    conn.commit()

    _login_super_admin(client)
    # CSV export does not call log_audit_event — only route-level DB needed.
    with _patched_route_db_only(conn):
        resp = client.get("/alerts/export/csv")

    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    disposition = resp.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    body = resp.data.decode("utf-8", errors="replace")
    first_line = body.splitlines()[0]
    assert first_line == "id,alert_type,severity,source_ip,status,created_at,environment,message"


def test_filtered_exports_honor_rule_id_and_existing_filters(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        source_ip="8.8.4.40",
        message="filtered export match",
        alert_type="failed_login_threshold",
        severity="high",
        status="open",
        source="bank_app",
    )
    _insert_alert(
        cur,
        source_ip="8.8.4.41",
        message="filtered export wrong rule",
        alert_type="port_scan_threshold",
        severity="high",
        status="open",
        source="bank_app",
    )
    _insert_alert(
        cur,
        source_ip="8.8.4.42",
        message="filtered export wrong severity",
        alert_type="failed_login_threshold",
        severity="low",
        status="open",
        source="bank_app",
    )
    conn.commit()

    _login_super_admin(client)
    query = "rule_id=failed_login_threshold&severity=high&source=bank_app&search=filtered%20export"
    with _patched_app_db(conn):
        txt_resp = client.get(f"/alerts/report?{query}")
    assert txt_resp.status_code == 200
    txt_body = txt_resp.data.decode("utf-8", errors="replace")
    assert "filtered export match" in txt_body
    assert "filtered export wrong rule" not in txt_body
    assert "filtered export wrong severity" not in txt_body

    with _patched_route_db_only(conn):
        csv_resp = client.get(f"/alerts/export/csv?{query}")
    assert csv_resp.status_code == 200
    csv_body = csv_resp.data.decode("utf-8", errors="replace")
    assert "filtered export match" in csv_body
    assert "filtered export wrong rule" not in csv_body
    assert "filtered export wrong severity" not in csv_body


def test_csv_export_preserves_latest_environment_lookup(client, postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        source_ip="8.8.4.55",
        message="csv environment lookup",
        alert_type="failed_login_threshold",
        severity="high",
        status="open",
        source="bank_app",
    )
    cur.execute(
        """
        INSERT INTO events (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            app_name,
            environment,
            raw_payload,
            created_at
        )
        VALUES
            ('login_failure', 'medium', '8.8.4.55', 'bank_app', 'custom', 'old event', 'auth', 'dev', '{}'::jsonb, NOW() - INTERVAL '2 hours'),
            ('login_failure', 'medium', '8.8.4.55', 'bank_app', 'custom', 'new event', 'auth', 'prod', '{}'::jsonb, NOW() - INTERVAL '1 minute')
        """
    )
    conn.commit()

    _login_super_admin(client)
    with _patched_route_db_only(conn):
        resp = client.get("/alerts/export/csv?rule_id=failed_login_threshold&search=csv%20environment")

    assert resp.status_code == 200
    body = resp.data.decode("utf-8", errors="replace")
    assert "csv environment lookup" in body
    assert ",prod," in body


def test_csv_export_query_is_bounded_by_distinct_filtered_sources():
    query, params = build_alert_csv_query(
        {
            "rule_id": "failed_login_threshold",
            "severity": "high",
            "search": "export",
            "operational_scope": "all_history",
        }
    )

    assert "FROM alerts a\n        LEFT JOIN LATERAL" not in query
    assert "distinct_alert_sources" in query
    assert "SELECT DISTINCT source_ip" in query
    assert "FROM distinct_alert_sources das" in query
    assert "LEFT JOIN LATERAL" in query
    assert "ORDER BY e.created_at DESC, e.id DESC" in query
    assert params == ["%export%", "%export%", "%export%", "failed_login_threshold", "high"]


def test_csv_export_query_plan_uses_latest_environment_index(postgres_db):
    conn, cur = postgres_db
    _insert_alert(
        cur,
        source_ip="8.8.4.60",
        message="csv plan alert",
        alert_type="failed_login_threshold",
        severity="high",
        status="open",
        source="bank_app",
    )
    cur.execute(
        """
        INSERT INTO events (
            event_type,
            severity,
            source_ip,
            source,
            source_type,
            message,
            app_name,
            environment,
            raw_payload,
            created_at
        )
        SELECT
            'login_failure',
            'medium',
            '8.8.4.60'::inet,
            'bank_app',
            'custom',
            'csv plan event ' || gs,
            'auth',
            CASE WHEN gs = 600 THEN 'prod' ELSE 'dev' END,
            '{}'::jsonb,
            NOW() - (gs || ' seconds')::interval
        FROM generate_series(1, 600) AS gs
        """
    )
    cur.execute("ANALYZE alerts")
    cur.execute("ANALYZE events")
    cur.execute("SET LOCAL enable_seqscan = off")
    query, params = build_alert_csv_query(
        {
            "rule_id": "failed_login_threshold",
            "search": "csv plan alert",
            "operational_scope": "all_history",
        }
    )
    cur.execute(f"EXPLAIN (FORMAT TEXT, COSTS OFF) {query}", tuple(params))
    plan = "\n".join(row[0] for row in cur.fetchall())

    assert "idx_events_source_ip_created_at_latest" in plan
