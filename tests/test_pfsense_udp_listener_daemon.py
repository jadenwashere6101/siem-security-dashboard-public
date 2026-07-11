import importlib.util
import inspect
import logging
import socket
import threading
import time
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import urllib.error

from adapters.pfsense_filterlog_adapter import MAX_PACKET_BYTES
from engines.pfsense_syslog_listener import (
    DEFAULT_BIND_PORT,
    PfSenseListenerConfig,
    PfSenseListenerShutdown,
    PfSenseListenerStats,
    RateLimiter,
    create_udp_socket,
    forward_normalized_event,
    load_config_from_environ,
    process_datagram,
    run_pfsense_syslog_listener,
    validate_config,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

TCP_BLOCK = (
    "<134>Jul  7 12:00:01 fw filterlog[12345]: "
    "1000000103,,,1777758297,igb1,match,block,in,4,0x0,,64,25432,0,DF,6,tcp,60,"
    "198.51.100.10,203.0.113.20,54321,443,0,S,123456,0,65535,,mss"
)

VALID_API_KEY = "test-ingest-api-key"


def make_config(**overrides):
    defaults = {
        "bind_host": "127.0.0.1",
        "bind_port": DEFAULT_BIND_PORT,
        "allowed_source_ips": frozenset({"127.0.0.1", "198.51.100.10"}),
        "backend_url": "http://127.0.0.1:5051/ingest/pfsense",
        "api_key": VALID_API_KEY,
        "max_packet_bytes": MAX_PACKET_BYTES,
        "global_rate_limit": 100,
        "per_source_rate_limit": 50,
        "rate_limit_window_seconds": 60.0,
        "backend_timeout_seconds": 1.0,
        "recv_timeout_seconds": 0.2,
        "environment": "test",
        "max_packets": 1,
    }
    defaults.update(overrides)
    return PfSenseListenerConfig(**defaults)


def test_default_port_is_5514():
    config = load_config_from_environ({})
    assert config.bind_port == 5514


def test_create_udp_socket_binds_configured_host_and_port():
    sock = create_udp_socket("127.0.0.1", 0, recv_timeout_seconds=0.1)
    host, port = sock.getsockname()

    assert host == "127.0.0.1"
    assert port > 0
    sock.close()


def test_listener_binds_and_processes_configured_port():
    sock = create_udp_socket("127.0.0.1", 0, recv_timeout_seconds=0.2)
    _host, port = sock.getsockname()
    forwarded = []
    config = make_config(bind_port=port, max_packets=1)

    def fake_forward(event, **_kwargs):
        forwarded.append(event)
        return True, 201, None

    shutdown = PfSenseListenerShutdown()

    def run_listener():
        run_pfsense_syslog_listener(
            config=config,
            shutdown=shutdown,
            sock=sock,
            forwarder=fake_forward,
        )

    thread = threading.Thread(target=run_listener)
    thread.start()
    time.sleep(0.05)

    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        client.sendto(TCP_BLOCK.encode("utf-8"), ("127.0.0.1", port))
        thread.join(timeout=2.0)
    finally:
        client.close()
        shutdown.request("test_complete")
        thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert len(forwarded) == 1
    assert forwarded[0]["event_type"] == "firewall_block"
    assert forwarded[0]["source"] == "pfsense"


def test_unauthorized_source_is_rejected_before_forward():
    stats = PfSenseListenerStats()
    forward_mock = MagicMock(return_value=(True, 201, None))
    config = make_config(allowed_source_ips=frozenset({"203.0.113.9"}))

    outcome = process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=config,
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=forward_mock,
    )

    assert outcome == "rejected_source"
    assert stats.rejected_source == 1
    forward_mock.assert_not_called()


def test_oversized_packet_is_rejected_before_parser():
    stats = PfSenseListenerStats()
    parser_mock = MagicMock()
    forward_mock = MagicMock()
    config = make_config()

    outcome = process_datagram(
        b"x" * (MAX_PACKET_BYTES + 1),
        "127.0.0.1",
        config=config,
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=forward_mock,
        parser=parser_mock,
    )

    assert outcome == "oversized"
    assert stats.oversized == 1
    parser_mock.assert_not_called()
    forward_mock.assert_not_called()


def test_malformed_packet_does_not_crash_listener():
    stats = PfSenseListenerStats()
    forward_mock = MagicMock()
    config = make_config()

    outcome = process_datagram(
        b"not syslog",
        "127.0.0.1",
        config=config,
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=forward_mock,
    )

    assert outcome == "parse_failed"
    forward_mock.assert_not_called()


def test_malformed_utf8_does_not_crash_listener():
    stats = PfSenseListenerStats()
    forward_mock = MagicMock(return_value=(True, 201, None))
    config = make_config()

    outcome = process_datagram(
        TCP_BLOCK.encode("utf-8") + b"\xff",
        "127.0.0.1",
        config=config,
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=forward_mock,
    )

    assert outcome == "ingested"
    assert stats.accepted == 1


def test_valid_packet_forwards_normalized_event_to_backend_route():
    stats = PfSenseListenerStats()
    forwarded = []

    def fake_forward(event, **_kwargs):
        forwarded.append(event)
        return True, 201, None

    outcome = process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=make_config(),
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=fake_forward,
    )

    assert outcome == "ingested"
    assert stats.forwarded == 1
    assert stats.ingested == 1
    assert forwarded[0]["source_type"] == "firewall"
    assert forwarded[0]["raw_payload"]["protocol"] == "tcp"


def test_filtered_backend_response_is_counted_without_ingested_increment():
    stats = PfSenseListenerStats()

    outcome = process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=make_config(),
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=MagicMock(return_value=(True, 202, None)),
    )

    assert outcome == "filtered"
    assert stats.forwarded == 1
    assert stats.filtered == 1
    assert stats.ingested == 0
    assert stats.backend_failed == 0


@pytest.mark.parametrize(
    "forward_result,expected_outcome",
    [
        ((False, 400, "http_error"), "rejected"),
        ((False, 500, "http_error"), "backend_failed"),
        ((False, None, "network_error"), "backend_failed"),
        ((False, None, "timeout"), "backend_failed"),
    ],
)
def test_backend_failures_are_logged_safely(
    caplog,
    forward_result,
    expected_outcome,
):
    caplog.set_level(logging.INFO)
    stats = PfSenseListenerStats()

    outcome = process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=make_config(),
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=MagicMock(return_value=forward_result),
    )

    assert outcome == expected_outcome
    if expected_outcome == "rejected":
        assert stats.rejected == 1
        assert stats.backend_failed == 0
    else:
        assert stats.backend_failed == 1
    assert VALID_API_KEY not in caplog.text
    assert TCP_BLOCK not in caplog.text


def test_malformed_packet_does_not_reach_backend():
    forward_mock = MagicMock()
    stats = PfSenseListenerStats()

    process_datagram(
        b"garbage",
        "127.0.0.1",
        config=make_config(),
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=forward_mock,
    )

    forward_mock.assert_not_called()


def test_rate_limit_behavior_is_deterministic():
    limiter = RateLimiter(
        global_limit=1,
        per_source_limit=1,
        window_seconds=60.0,
        monotonic_fn=lambda: 100.0,
    )

    assert limiter.allow("127.0.0.1") is True
    assert limiter.allow("127.0.0.1") is False

    stats = PfSenseListenerStats()
    config = make_config(global_rate_limit=1, per_source_rate_limit=1, rate_limit_window_seconds=60.0)
    limiter = RateLimiter(
        global_limit=config.global_rate_limit,
        per_source_limit=config.per_source_rate_limit,
        window_seconds=config.rate_limit_window_seconds,
        monotonic_fn=lambda: 200.0,
    )

    first = process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=config,
        stats=stats,
        rate_limiter=limiter,
        forwarder=MagicMock(return_value=(True, 201, None)),
    )
    second = process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=config,
        stats=stats,
        rate_limiter=limiter,
        forwarder=MagicMock(return_value=(True, 201, None)),
    )

    assert first == "ingested"
    assert second == "rate_limited"
    assert stats.rate_limited == 1


def test_listener_has_no_database_access():
    source = inspect.getsource(importlib.import_module("engines.pfsense_syslog_listener"))
    forbidden = ("psycopg2", "get_db_connection", "ingest_normalized_event", "INSERT INTO events")
    for token in forbidden:
        assert token not in source


def test_structured_logs_exclude_raw_packets_and_api_keys(caplog):
    caplog.set_level(logging.INFO)
    stats = PfSenseListenerStats()

    process_datagram(
        TCP_BLOCK.encode("utf-8"),
        "127.0.0.1",
        config=make_config(),
        stats=stats,
        rate_limiter=RateLimiter(global_limit=10, per_source_limit=10, window_seconds=60.0),
        forwarder=MagicMock(return_value=(False, 500, "http_error")),
    )

    assert VALID_API_KEY not in caplog.text
    assert TCP_BLOCK not in caplog.text
    assert "pfsense_listener_event" in caplog.text


def test_forward_normalized_event_handles_http_error():
    def fake_opener(_request, timeout=0):
        raise urllib.error.HTTPError(
            url="http://example.test/ingest/pfsense",
            code=422,
            msg="Unprocessable",
            hdrs=None,
            fp=BytesIO(b'{"error":"Invalid raw_payload"}'),
        )

    ok, status, error = forward_normalized_event(
        {"event_type": "firewall_block"},
        backend_url="http://example.test/ingest/pfsense",
        api_key=VALID_API_KEY,
        api_key_header="X-API-Key",
        timeout_seconds=1.0,
        opener=fake_opener,
    )

    assert ok is False
    assert status == 422
    assert error == "http_error"


def test_pfsense_systemd_unit_follows_daemon_pattern():
    service = (REPO_ROOT / "deploy/systemd/pfsense-syslog-listener.service").read_text()

    assert "Type=simple" in service
    assert "Restart=on-failure" in service
    assert "StandardOutput=journal" in service
    assert "pfsense_syslog_listener_daemon.py" in service
    assert "PFSENSE_LISTENER_PORT=5514" in service
    assert "PFSENSE_MAX_PACKET_BYTES=4096" in service


def test_install_helper_does_not_auto_start_by_default():
    helper = (REPO_ROOT / "scripts/install_pfsense_syslog_listener_service.sh").read_text()

    assert "pfsense-syslog-listener.service" in helper
    assert "Service is not started unless --start was passed" in helper
    assert "--enable" in helper
    assert "--rollback" in helper
    assert "Azure NSG" in helper


def test_listener_scope_excludes_exposure_and_detection():
    source = inspect.getsource(importlib.import_module("engines.pfsense_syslog_listener"))
    forbidden = (
        "ingest_normalized_event",
        "create_pending_executions",
        "enqueue_committed_alerts",
        "azure",
        "ufw",
        "iptables",
        "nsg",
    )
    lowered = source.lower()
    for token in forbidden:
        assert token not in lowered


def test_listener_and_daemon_import_cleanly():
    import engines.pfsense_syslog_listener as listener

    assert listener.DEFAULT_BIND_PORT == 5514

    daemon_path = REPO_ROOT / "scripts/pfsense_syslog_listener_daemon.py"
    spec = importlib.util.spec_from_file_location("pfsense_syslog_listener_daemon", daemon_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_validate_config_requires_allow_list_and_api_key():
    with pytest.raises(ValueError, match="PFSENSE_ALLOWED_SOURCE_IPS"):
        validate_config(make_config(allowed_source_ips=frozenset(), api_key=VALID_API_KEY))

    with pytest.raises(ValueError, match="PFSENSE_INGEST_API_KEY"):
        validate_config(make_config(api_key=""))
