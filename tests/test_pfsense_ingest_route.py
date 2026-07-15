import ast
import inspect
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from adapters.pfsense_filterlog_adapter import MAX_PFSENSE_INGEST_BYTES


VALID_API_KEY = "test-ingest-api-key"


class ConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


def valid_pfsense_block_payload(**overrides):
    payload = {
        "event_type": "firewall_block",
        "severity": "medium",
        "source_ip": "198.51.100.10",
        "source": "pfsense",
        "source_type": "firewall",
        "message": "pfSense TCP traffic blocked from 198.51.100.10 to 203.0.113.20:443",
        "app_name": "pfsense_filterlog",
        "environment": "prod",
        "raw_payload": {
            "action": "block",
            "interface": "igb1",
            "direction": "in",
            "ip_version": "4",
            "protocol": "tcp",
            "source_ip": "198.51.100.10",
            "destination_ip": "203.0.113.20",
            "source_port": 54321,
            "destination_port": 443,
            "rule_id": "1000000103",
            "tracker": "1777758297",
            "event_type_candidate": "firewall_block",
        },
    }
    payload.update(overrides)
    return payload


def valid_pfsense_allow_payload(**overrides):
    payload = {
        "event_type": "firewall_allow",
        "severity": "low",
        "source_ip": "10.0.0.5",
        "source": "pfsense",
        "source_type": "firewall",
        "message": "pfSense UDP traffic allowed from 10.0.0.5 to 8.8.8.8:53",
        "app_name": "pfsense_filterlog",
        "environment": "prod",
        "raw_payload": {
            "action": "pass",
            "interface": "igb1",
            "direction": "in",
            "ip_version": "4",
            "protocol": "udp",
            "source_ip": "10.0.0.5",
            "destination_ip": "203.0.113.22",
            "source_port": 5353,
            "destination_port": 22,
            "event_type_candidate": "firewall_allow",
        },
    }
    payload.update(overrides)
    return payload


def install_route_db(monkeypatch, postgres_db):
    conn, _cur = postgres_db
    import routes.ingest_routes as ingest_routes

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: ConnectionProxy(conn))
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", lambda _ip: {})
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ingest_routes,
        "_create_playbook_executions_for_alerts",
        lambda *_args, **_kwargs: {"summary": {"created": 0}, "results": []},
    )


def fetch_event(cur, source_ip):
    cur.execute(
        """
        SELECT
            event_type,
            severity,
            host(source_ip),
            source,
            source_type,
            message,
            app_name,
            environment,
            raw_payload
        FROM events
        WHERE source_ip = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_ip,),
    )
    return cur.fetchone()


def post_pfsense(client, payload, api_key=VALID_API_KEY):
    headers = {"X-API-Key": api_key} if api_key is not None else {}
    return client.post("/ingest/pfsense", json=payload, headers=headers)


def test_pfsense_ingest_requires_api_key(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    ingest_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", ingest_mock)

    missing = post_pfsense(client, valid_pfsense_block_payload(), api_key=None)
    wrong = post_pfsense(client, valid_pfsense_block_payload(), api_key="wrong-key")

    assert missing.status_code == 401
    assert wrong.status_code == 401
    ingest_mock.assert_not_called()


def test_valid_firewall_block_ingests_successfully(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "198.51.100.10"

    response = post_pfsense(client, valid_pfsense_block_payload(source_ip=source_ip))

    assert response.status_code == 201
    assert response.get_json()["message"] == "pfSense event ingested successfully"
    event = fetch_event(cur, source_ip)
    assert event[0] == "firewall_block"
    assert event[1] == "medium"
    assert event[2] == source_ip
    assert event[3] == "pfsense"
    assert event[4] == "firewall"
    assert event[6] == "pfsense_filterlog"
    assert event[8]["action"] == "block"
    assert event[8]["destination_port"] == 443


def test_pfsense_event_timestamp_reaches_database_contract(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "198.51.100.111"
    event_timestamp = "2026-07-07T12:00:01+00:00"

    response = post_pfsense(
        client,
        valid_pfsense_block_payload(
            source_ip=source_ip,
            event_timestamp=event_timestamp,
        ),
    )

    assert response.status_code == 201
    cur.execute(
        "SELECT event_timestamp FROM events WHERE source_ip = %s ORDER BY id DESC LIMIT 1",
        (source_ip,),
    )
    assert cur.fetchone()[0] == datetime.fromisoformat(event_timestamp)


def test_textual_icmp_variant_reaches_existing_ingest_contract(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "198.51.100.112"
    raw_payload = {
        "action": "block",
        "interface": "igb1",
        "direction": "in",
        "ip_version": "4",
        "protocol": "icmp",
        "source_ip": source_ip,
        "destination_ip": "203.0.113.20",
        "icmp_type": "unreachport",
        "event_type_candidate": "firewall_block",
    }

    response = post_pfsense(
        client,
        valid_pfsense_block_payload(
            source_ip=source_ip,
            message=f"pfSense ICMP traffic blocked from {source_ip} to 203.0.113.20",
            raw_payload=raw_payload,
        ),
    )

    assert response.status_code == 201
    event = fetch_event(cur, source_ip)
    assert event[8]["protocol"] == "icmp"
    assert event[8]["icmp_type"] == "unreachport"


def test_valid_firewall_allow_ingests_successfully(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    _conn, cur = postgres_db
    source_ip = "10.0.0.5"

    response = post_pfsense(client, valid_pfsense_allow_payload(source_ip=source_ip))

    assert response.status_code == 201
    event = fetch_event(cur, source_ip)
    assert event[0] == "firewall_allow"
    assert event[1] == "low"
    assert event[8]["action"] == "pass"


def test_routine_allow_is_filtered_before_geolocation_or_ingest(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = []
    geo_mock = MagicMock()
    ingest_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", geo_mock)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", ingest_mock)
    payload = valid_pfsense_allow_payload()
    payload["raw_payload"] = dict(payload["raw_payload"], direction="out", destination_port=443)

    response = post_pfsense(client, payload)

    assert response.status_code == 202
    assert response.get_json() == {
        "status": "filtered",
        "category": "routine_allow",
        "reason": "no_enabled_retention_category",
    }
    geo_mock.assert_not_called()
    ingest_mock.assert_not_called()
    conn.rollback.assert_called_once()


def test_runtime_policy_matrix_retains_only_enabled_categories(client, monkeypatch, postgres_db):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    install_route_db(monkeypatch, postgres_db)
    conn, cur = postgres_db
    import routes.ingest_routes as ingest_routes

    geo_mock = MagicMock(return_value={})
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", geo_mock)
    cur.execute("SELECT COUNT(*) FROM events")
    before_count = cur.fetchone()[0]

    blocked = post_pfsense(client, valid_pfsense_block_payload(source_ip="198.51.100.31"))
    sensitive = post_pfsense(client, valid_pfsense_allow_payload(source_ip="198.51.100.32"))
    routine_payload = valid_pfsense_allow_payload(source_ip="198.51.100.33")
    routine_payload["raw_payload"] = dict(
        routine_payload["raw_payload"], direction="out", destination_port=443
    )
    routine = post_pfsense(client, routine_payload)

    assert [blocked.status_code, sensitive.status_code, routine.status_code] == [201, 201, 202]
    assert geo_mock.call_count == 2
    cur.execute("SELECT COUNT(*) FROM events")
    assert cur.fetchone()[0] == before_count + 2

    cur.execute("UPDATE pfsense_ingest_config SET enabled = TRUE WHERE category = 'dns_traffic'")
    conn.commit()
    dns_payload = valid_pfsense_allow_payload(source_ip="198.51.100.34")
    dns_payload["raw_payload"] = dict(
        dns_payload["raw_payload"], direction="out", protocol="udp", destination_port=53
    )
    assert post_pfsense(client, dns_payload).status_code == 201

    cur.execute("UPDATE pfsense_ingest_config SET enabled = TRUE WHERE category = 'icmp_traffic'")
    conn.commit()
    icmp_payload = valid_pfsense_allow_payload(source_ip="198.51.100.35")
    icmp_payload["raw_payload"] = {
        "action": "pass",
        "interface": "igb1",
        "direction": "in",
        "ip_version": "4",
        "protocol": "icmp",
        "source_ip": "198.51.100.35",
        "destination_ip": "203.0.113.35",
        "icmp_type": 8,
        "icmp_code": 0,
    }
    assert post_pfsense(client, icmp_payload).status_code == 201

    cur.execute("SELECT COUNT(*) FROM events")
    assert cur.fetchone()[0] == before_count + 4


@pytest.mark.parametrize(
    "payload,expected_error",
    [
        ({}, "Missing required fields"),
        ({"event_type": "firewall_block"}, "Missing required fields"),
        (
            {
                "event_type": "firewall_block",
                "severity": "medium",
                "source_ip": "not-an-ip",
                "source": "pfsense",
                "source_type": "firewall",
                "message": "blocked",
                "app_name": "pfsense_filterlog",
                "environment": "prod",
                "raw_payload": valid_pfsense_block_payload()["raw_payload"],
            },
            "Invalid source_ip",
        ),
        (
            valid_pfsense_block_payload(source="nginx"),
            "Invalid source fields",
        ),
        (
            valid_pfsense_block_payload(source_type="web_log"),
            "Invalid source fields",
        ),
        (
            valid_pfsense_block_payload(event_type="failed_login"),
            "Invalid event_type",
        ),
    ],
)
def test_missing_or_invalid_required_fields_are_rejected(client, monkeypatch, payload, expected_error):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    ingest_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", ingest_mock)

    response = post_pfsense(client, payload)

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error
    ingest_mock.assert_not_called()


def test_malformed_payload_is_rejected_without_echoing_attacker_content(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    ingest_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", ingest_mock)
    attacker_summary = "A" * 500 + "<script>alert(1)</script>"

    response = post_pfsense(
        client,
        {
            "event_type": "firewall_block",
            "severity": "medium",
            "source_ip": "198.51.100.10",
            "source": "pfsense",
            "source_type": "firewall",
            "message": attacker_summary,
            "app_name": "pfsense_filterlog",
            "environment": "prod",
            "raw_payload": {
                "action": "block",
                "interface": "igb1",
                "direction": "in",
                "ip_version": "4",
                "protocol": "tcp",
                "source_ip": "198.51.100.10",
                "destination_ip": "203.0.113.20",
                "destination_port": "not-a-port",
            },
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "Invalid raw_payload"
    assert attacker_summary not in str(body)
    ingest_mock.assert_not_called()


def test_raw_syslog_payload_is_rejected(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    ingest_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", ingest_mock)
    raw_syslog = (
        "<134>Jul  7 12:00:01 fw filterlog[12345]: "
        "1000000103,,,1777758297,igb1,match,block,in,4,0x0,,64,25432,0,DF,6,tcp,60,"
        "198.51.100.10,203.0.113.20,54321,443,0,S,123456,0,65535,,mss"
    )

    response = client.post(
        "/ingest/pfsense",
        data=f'"{raw_syslog}"',
        content_type="application/json",
        headers={"X-API-Key": VALID_API_KEY},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid JSON"
    assert raw_syslog not in response.get_data(as_text=True)
    ingest_mock.assert_not_called()


def test_route_calls_centralized_ingest_for_valid_payload(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    alerts_created = []
    ingest_calls = []

    def fake_ingest(event_dict, db_conn, db_cur):
        ingest_calls.append(event_dict)
        assert db_conn is conn
        assert db_cur is cur
        assert event_dict["source"] == "pfsense"
        assert event_dict["source_type"] == "firewall"
        return alerts_created

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", fake_ingest)
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", lambda _ip: {})
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ingest_routes,
        "_create_playbook_executions_for_alerts",
        lambda *_args, **_kwargs: {"summary": {"created": 0}, "results": []},
    )

    response = post_pfsense(client, valid_pfsense_block_payload())

    assert response.status_code == 201
    assert len(ingest_calls) == 1
    assert ingest_calls[0]["event_type"] == "firewall_block"


def test_route_does_not_directly_insert_events(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", lambda _ip: {})
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        ingest_routes,
        "_create_playbook_executions_for_alerts",
        lambda *_args, **_kwargs: {"summary": {"created": 0}, "results": []},
    )

    response = post_pfsense(client, valid_pfsense_allow_payload())

    assert response.status_code == 201
    executed_sql = [str(call.args[0]).upper() for call in cur.execute.call_args_list]
    assert not any("INSERT INTO EVENTS" in sql for sql in executed_sql)


def test_successful_ingest_preserves_downstream_orchestration(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    alerts_created = [
        {
            "alert_id": 789,
            "source_ip": "198.51.100.10",
            "response_action": "monitor",
            "severity": "HIGH",
        }
    ]

    monkeypatch.setattr(ingest_routes, "get_db_connection", lambda: conn)
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", lambda *_args, **_kwargs: alerts_created)
    monkeypatch.setattr(ingest_routes, "lookup_ip_location", lambda _ip: {})
    enqueue_mock = MagicMock(return_value=[])
    playbook_mock = MagicMock(return_value={"summary": {"created": 1}, "results": [{"alert_id": 789, "status": "created"}]})
    incident_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "enqueue_committed_alerts", enqueue_mock)
    monkeypatch.setattr(ingest_routes, "_create_playbook_executions_for_alerts", playbook_mock)
    monkeypatch.setattr(ingest_routes, "_create_incidents_for_alerts", incident_mock)

    response = post_pfsense(client, valid_pfsense_block_payload())

    assert response.status_code == 201
    assert response.get_json()["alerts_created"] == alerts_created
    playbook_mock.assert_called_once_with(alerts_created, conn)
    enqueue_mock.assert_called_once_with(alerts_created, conn, exclude_alert_ids={789})
    incident_mock.assert_called_once_with(alerts_created, conn)


def test_route_tests_do_not_depend_on_raw_syslog_parsing():
    import tests.test_pfsense_ingest_route as route_tests

    module_path = inspect.getfile(route_tests)
    with open(module_path, encoding="utf-8") as handle:
        module_source = handle.read()

    tree = ast.parse(module_source)
    parser_symbol = "parse_pfsense_filterlog_packet"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "adapters.pfsense_filterlog_adapter":
            imported_names = {alias.name for alias in node.names}
            assert parser_symbol not in imported_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != parser_symbol


def test_route_module_excludes_listener_deployment_and_detection_scope():
    import routes.ingest_routes as ingest_routes

    source = inspect.getsource(ingest_routes.add_pfsense_event)
    forbidden_tokens = (
        "socket",
        "systemd",
        "UDP",
        "nsg",
        "firewall_rule",
        "playbook_tuning",
        "deploy",
    )
    lowered = source.lower()
    for token in forbidden_tokens:
        assert token.lower() not in lowered


def test_oversized_request_is_rejected_safely(client, monkeypatch):
    monkeypatch.setenv("SIEM_INGEST_API_KEY", VALID_API_KEY)
    import routes.ingest_routes as ingest_routes

    ingest_mock = MagicMock()
    monkeypatch.setattr(ingest_routes, "ingest_normalized_event", ingest_mock)
    oversized_payload = valid_pfsense_block_payload()
    oversized_payload["raw_payload"]["sanitized_summary"] = "x" * (MAX_PFSENSE_INGEST_BYTES + 1)

    response = client.post(
        "/ingest/pfsense",
        json=oversized_payload,
        headers={"X-API-Key": VALID_API_KEY},
    )

    assert response.status_code == 413
    assert response.get_json()["error"] == "Payload too large"
    ingest_mock.assert_not_called()
