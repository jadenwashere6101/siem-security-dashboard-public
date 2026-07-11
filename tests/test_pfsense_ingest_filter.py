from unittest.mock import MagicMock

import pytest

from engines.pfsense_ingest_filter import (
    DEFAULT_SENSITIVE_PORTS,
    default_effective_policy,
    evaluate_event,
    load_effective_policy,
    upsert_config_override,
    validate_config_entry,
    validate_sensitive_ports,
)


def event(action="pass", protocol="tcp", direction="out", destination_port=443):
    return {"raw_payload": {"action": action, "protocol": protocol, "direction": direction, "destination_port": destination_port}}


def test_safe_defaults_and_deterministic_precedence():
    policy = default_effective_policy()
    assert evaluate_event(event(action="block"), policy).reason == "blocked_traffic"
    assert evaluate_event(event(direction="in", destination_port=22), policy).reason == "inbound_sensitive_port"
    assert evaluate_event(event(destination_port=53), policy).retain is False
    assert evaluate_event(event(protocol="icmp", destination_port=None), policy).retain is False


def test_enabled_categories_retain_dns_icmp_and_all_allows():
    policy = default_effective_policy()
    policy["categories"]["dns_traffic"]["enabled"] = True
    assert evaluate_event(event(protocol="udp", destination_port=53), policy).reason == "allowed_port_53"
    policy["categories"]["icmp_traffic"]["enabled"] = True
    assert evaluate_event(event(protocol="icmp", destination_port=None), policy).reason == "allowed_icmp"
    policy["categories"]["all_allow_events"]["enabled"] = True
    assert evaluate_event(event(), policy).reason == "all_allowed_traffic"


@pytest.mark.parametrize("ports", [[22, 22], [True], [0], [65536], ["22"], [], list(range(1, 66))])
def test_sensitive_port_validation_rejects_invalid_values(ports):
    with pytest.raises(ValueError):
        validate_sensitive_ports(ports)


def test_config_validation_rejects_unknowns_and_normalizes_ports():
    with pytest.raises(ValueError):
        validate_config_entry("unknown", True, {})
    with pytest.raises(ValueError):
        validate_config_entry("block_events", 1, {})
    with pytest.raises(ValueError):
        validate_config_entry("block_events", True, {"extra": True})
    result = validate_config_entry("inbound_sensitive_port_allows", True, {"sensitive_ports": [443, 22]})
    assert result["parameters"]["sensitive_ports"] == [22, 443]


def test_config_lookup_failure_rolls_back_savepoint_and_uses_safe_defaults():
    cur = MagicMock()
    cur.execute.side_effect = [None, RuntimeError("database unavailable"), None, None]

    policy = load_effective_policy(cur)

    assert policy["status"] == "unavailable"
    assert policy["categories"]["block_events"]["enabled"] is True
    assert policy["categories"]["all_allow_events"]["enabled"] is False
    assert tuple(policy["categories"]["inbound_sensitive_port_allows"]["parameters"]["sensitive_ports"]) == DEFAULT_SENSITIVE_PORTS


def test_invalid_database_override_uses_safe_defaults_with_invalid_status():
    cur = MagicMock()
    cur.fetchall.return_value = [("all_allow_events", True, {"unexpected": True})]

    policy = load_effective_policy(cur)

    assert policy["status"] == "invalid"
    assert policy["categories"]["all_allow_events"]["enabled"] is False


def test_upsert_validates_before_staging_atomic_override():
    cur = MagicMock()
    with pytest.raises(ValueError):
        upsert_config_override(cur, "all_allow_events", "yes", {}, "admin")
    cur.execute.assert_not_called()

    result = upsert_config_override(
        cur,
        "inbound_sensitive_port_allows",
        True,
        {"sensitive_ports": [443, 22]},
        "admin",
    )

    assert result == {"enabled": True, "parameters": {"sensitive_ports": [22, 443]}}
    assert cur.execute.call_count == 1
