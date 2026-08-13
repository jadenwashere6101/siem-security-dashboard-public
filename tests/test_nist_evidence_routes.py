from contextlib import contextmanager
import json
from unittest.mock import MagicMock, patch

from werkzeug.security import generate_password_hash


ADMIN_USER = "testadmin"
ADMIN_PASS = "testpassword123!"
ROLE_SECRET = "nist-role-fixture"


class RouteSafeConnection:
    def __init__(self):
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()


class ActualRouteSafeConnection:
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


def _login_admin(client):
    with patch("core.audit_helpers.get_db_connection"):
        response = client.post("/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert response.status_code == 200


@contextmanager
def _logged_in_role(client, role):
    user = {
        "username": f"nist_{role}",
        "password_hash": generate_password_hash(ROLE_SECRET, method="pbkdf2:sha256"),
        "role": role,
        "is_active": True,
    }
    with patch("routes.auth_routes.get_user_by_username", return_value=user), patch(
        "core.auth.get_user_by_username", return_value=user
    ), patch("core.audit_helpers.get_db_connection"):
        response = client.post(
            "/login", json={"username": user["username"], "password": ROLE_SECRET}
        )
        assert response.status_code == 200
        yield


def _boundary():
    return {
        "id": 7,
        "name": "Declared enclave",
        "description": "Assessment input",
        "selected_sources": ["azure_insights", "nginx"],
        "selected_source_types": ["cloud_api", "web_log"],
        "environments": ["prod"],
        "default_window_hours": 24,
        "is_active": True,
        "scope_declaration": "Assessment scope is declared by an authorized user.",
        "created_by": "admin",
        "updated_by": "admin",
        "created_at": "2026-08-12T10:00:00+00:00",
        "updated_at": "2026-08-12T10:00:00+00:00",
    }


def _run():
    return {
        "id": 11,
        "boundary_id": 7,
        "framework_id": "nist_sp_800_171",
        "framework_version": "rev3",
        "catalog_version": "v1",
        "catalog_hash": "a" * 64,
        "collector_version": "v1",
        "requested_window_start": "2026-08-12T09:00:00+00:00",
        "requested_window_end": "2026-08-12T10:00:00+00:00",
        "status": "completed_with_partial_evidence",
        "source_health_snapshot": {"sources": []},
        "actor_username": "admin",
        "summary_counts": {"requirement_count": 12},
        "started_at": "2026-08-12T10:00:00+00:00",
        "completed_at": "2026-08-12T10:00:01+00:00",
        "created_at": "2026-08-12T10:00:00+00:00",
    }


def _result():
    return {
        "id": 20,
        "run_id": 11,
        "requirement_id": "03.03.01",
        "requirement_name": "Event Logging",
        "mapping_strength": "partial_siem_evidence",
        "evidence_status": "partial_evidence",
        "collection_confidence": "unknown",
        "reason_code": "collection_unknown",
        "limitation": "Other evidence is required.",
        "evidence_count": 1,
        "omitted_count": 0,
        "evaluated_at": "2026-08-12T10:00:00+00:00",
        "catalog_version": "v1",
        "catalog_hash": "a" * 64,
        "collector_version": "v1",
    }


def test_nist_routes_require_authentication(client):
    assert client.get("/nist/evidence/catalog").status_code == 401
    assert client.post("/nist/evidence/boundaries", json={}).status_code == 401


def test_analyst_can_read_catalog_but_cannot_mutate_boundary(client):
    with _logged_in_role(client, "analyst"):
        catalog = client.get("/nist/evidence/catalog")
        denied = client.post("/nist/evidence/boundaries", json={})
    assert catalog.status_code == 200
    assert len(catalog.get_json()["mappings"]) == 12
    assert denied.status_code == 403


def test_viewer_cannot_read_nist_evidence(client):
    with _logged_in_role(client, "viewer"):
        response = client.get("/nist/evidence/catalog")
    assert response.status_code == 403


def test_super_admin_boundary_create_normalizes_and_audits(client):
    _login_admin(client)
    conn = RouteSafeConnection()
    boundary = _boundary()
    with patch("routes.nist_evidence_routes.get_db_connection", return_value=conn), patch(
        "routes.nist_evidence_routes.create_boundary", return_value=boundary
    ) as create_mock, patch("routes.nist_evidence_routes.log_audit_event") as audit_mock:
        response = client.post(
            "/nist/evidence/boundaries",
            json={"name": "Declared enclave", "selected_sources": ["azure", "web_log"]},
        )
    assert response.status_code == 201
    create_mock.assert_called_once()
    conn.commit.assert_called_once()
    audit_mock.assert_called_once()
    assert audit_mock.call_args.args[0] == "NIST_EVIDENCE_BOUNDARY_CREATED"
    assert audit_mock.call_args.kwargs["details"] == {"boundary_id": 7}


def test_super_admin_run_creation_is_audited_without_evidence_payload(client):
    _login_admin(client)
    conn = RouteSafeConnection()
    with patch("routes.nist_evidence_routes.get_db_connection", return_value=conn), patch(
        "routes.nist_evidence_routes.execute_assessment_run", return_value=11
    ), patch("routes.nist_evidence_routes.get_run", return_value=_run()), patch(
        "routes.nist_evidence_routes.log_audit_event"
    ) as audit_mock:
        response = client.post("/nist/evidence/boundaries/7/runs", json={})
    assert response.status_code == 201
    details = audit_mock.call_args.kwargs["details"]
    assert details == {"boundary_id": 7, "run_id": 11}
    assert "evidence" not in json.dumps(details).lower()


def test_json_export_includes_provenance_shape_and_no_overclaim_fields(client):
    _login_admin(client)
    conn = RouteSafeConnection()
    evidence = {
        "items": [{
            "id": 31, "requirement_id": "03.03.01", "evidence_category": "event_types",
            "evidence_type": "normalized_event", "canonical_source": "azure_insights",
            "source_type": "cloud_api", "source_health_state": "healthy",
            "entity_type": "event", "entity_id": "99",
            "occurrence_timestamp": "2026-08-12T09:30:00+00:00",
            "ingestion_timestamp": "2026-08-12T09:30:01+00:00",
            "collection_timestamp": "2026-08-12T10:00:00+00:00",
            "query_window_start": "2026-08-12T09:00:00+00:00",
            "query_window_end": "2026-08-12T10:00:00+00:00",
            "query_hash": "b" * 64, "operational_classification": "real",
            "is_truncated": False, "omitted_count": 0, "catalog_version": "v1",
            "mapping_version": "v1", "collector_version": "v1",
            "evidence_summary": "event type=failed_login",
            "reference_metadata": {"occurrence_timestamp_available": True},
        }],
        "total": 1, "limit": 100, "offset": 0,
    }
    with patch("routes.nist_evidence_routes.get_db_connection", return_value=conn), patch(
        "routes.nist_evidence_routes.get_run", return_value=_run()
    ), patch("routes.nist_evidence_routes.get_boundary", return_value=_boundary()), patch(
        "routes.nist_evidence_routes.list_requirement_results", return_value=[_result()]
    ), patch("routes.nist_evidence_routes.list_evidence_references", return_value=evidence), patch(
        "routes.nist_evidence_routes.log_audit_event"
    ):
        response = client.get("/nist/evidence/runs/11/export?format=json")
    assert response.status_code == 200
    payload = json.loads(response.get_data(as_text=True))
    assert payload["requirement_results"][0]["evidence_references"][0]["entity_id"] == "99"
    serialized = json.dumps(payload).lower()
    for forbidden in (
        '"compliant"', '"compliance_status"', '"passed"',
        '"failed_control"', '"certification_status"', '"raw_payload"',
    ):
        assert forbidden not in serialized


def test_csv_export_has_deterministic_evidence_columns_and_no_overall_score(client):
    _login_admin(client)
    conn = RouteSafeConnection()
    with patch("routes.nist_evidence_routes.get_db_connection", return_value=conn), patch(
        "routes.nist_evidence_routes.get_run", return_value=_run()
    ), patch("routes.nist_evidence_routes.get_boundary", return_value=_boundary()), patch(
        "routes.nist_evidence_routes.list_requirement_results", return_value=[_result()]
    ), patch(
        "routes.nist_evidence_routes.list_evidence_references",
        return_value={"items": [], "total": 0, "limit": 100, "offset": 0},
    ), patch("routes.nist_evidence_routes.log_audit_event"):
        response = client.get("/nist/evidence/runs/11/export?format=csv")
    assert response.status_code == 200
    header = response.get_data(as_text=True).splitlines()[0]
    assert "mapping_strength,evidence_status,collection_confidence" in header
    assert "compliance" not in header.lower()
    assert "overall" not in header.lower()


def test_postgres_boundary_run_results_evidence_and_audit_end_to_end(client, postgres_db):
    conn, cur = postgres_db
    cur.execute(
        """
        INSERT INTO ingestion_checkpoints (
            connector_name, last_processed_at, last_poll_status, last_poll_counts, updated_at
        ) VALUES
            ('bank_app', NOW(), 'success', '{}'::jsonb, NOW()),
            ('pfsense', NOW(), 'success', '{}'::jsonb, NOW())
        """
    )
    cur.execute(
        """
        INSERT INTO events (
            event_type, severity, source_ip, source, source_type, event_timestamp,
            message, app_name, environment, raw_payload, created_at
        ) VALUES
            ('failed_login', 'high', '8.8.4.4', 'bank_app', 'custom', NOW() - INTERVAL '5 minutes',
             'failed login', 'bank', 'prod', '{}'::jsonb, NOW() - INTERVAL '4 minutes'),
            ('firewall_deny', 'medium', '8.8.4.5', 'pfsense', 'firewall', NOW() - INTERVAL '3 minutes',
             'firewall deny', 'pfsense', 'prod', '{}'::jsonb, NOW() - INTERVAL '2 minutes')
        """
    )
    cur.execute(
        """
        INSERT INTO alerts (
            alert_type, severity, source_ip, source, source_type, message, status, context
        ) VALUES
            ('failed_login_threshold', 'high', '8.8.4.4', 'bank_app', 'custom',
             'authentication threshold', 'open', '{}'::jsonb),
            ('firewall_rule_match', 'medium', '8.8.4.5', 'pfsense', 'firewall',
             'firewall finding', 'open', '{}'::jsonb)
        """
    )
    conn.commit()
    wrapper = ActualRouteSafeConnection(conn)
    _login_admin(client)
    with patch("routes.nist_evidence_routes.get_db_connection", return_value=wrapper), patch(
        "core.audit_helpers.get_db_connection", return_value=wrapper
    ):
        boundary_response = client.post(
            "/nist/evidence/boundaries",
            json={
                "name": "PostgreSQL boundary",
                "selected_sources": ["bank_app", "pfsense"],
                "environments": ["prod"],
                "default_window_hours": 1,
            },
        )
        assert boundary_response.status_code == 201, boundary_response.get_json()
        boundary = boundary_response.get_json()
        run_response = client.post(f"/nist/evidence/boundaries/{boundary['id']}/runs", json={})
        assert run_response.status_code == 201, run_response.get_json()
        run = run_response.get_json()
        results_response = client.get(f"/nist/evidence/runs/{run['id']}/results")
        evidence_response = client.get(
            f"/nist/evidence/runs/{run['id']}/results/03.01.08/evidence"
        )

    assert run["status"] == "completed_with_partial_evidence"
    assert run["summary_counts"]["requirement_count"] == 12
    results = results_response.get_json()["items"]
    assert len(results) == 12
    assert {item["requirement_id"] for item in results} == {
        "03.03.01", "03.03.02", "03.03.03", "03.03.04", "03.03.05",
        "03.03.06", "03.03.07", "03.06.01", "03.06.02", "03.14.06",
        "03.13.01", "03.01.08",
    }
    evidence = evidence_response.get_json()["items"]
    assert {item["canonical_source"] for item in evidence} == {"bank_app"}
    assert all("raw_payload" not in json.dumps(item).lower() for item in evidence)
    cur.execute(
        """
        SELECT event_type, details
        FROM audit_log
        WHERE event_type IN ('NIST_EVIDENCE_BOUNDARY_CREATED', 'NIST_EVIDENCE_RUN_CREATED')
        ORDER BY id
        """
    )
    audit_rows = cur.fetchall()
    assert [row[0] for row in audit_rows] == [
        "NIST_EVIDENCE_BOUNDARY_CREATED", "NIST_EVIDENCE_RUN_CREATED"
    ]
    assert all("raw_payload" not in json.dumps(row[1]).lower() for row in audit_rows)
