from adapters.pfsense_filterlog_adapter import (
    MAX_PACKET_BYTES,
    parse_pfsense_filterlog_packet,
)


TCP_BLOCK = (
    "<134>Jul  7 12:00:01 fw filterlog[12345]: "
    "1000000103,,,1777758297,igb1,match,block,in,4,0x0,,64,25432,0,DF,6,tcp,60,"
    "198.51.100.10,203.0.113.20,54321,443,0,S,123456,0,65535,,mss"
)

UDP_PASS = (
    "<134>Jul  7 12:00:02 fw filterlog: "
    "1000000104,,,1777758298,igb0,match,pass,out,4,0x0,,64,4921,0,none,17,udp,60,"
    "10.0.0.5,8.8.8.8,5353,53,28"
)


def test_valid_ipv4_tcp_block_line_parses_and_normalizes():
    result = parse_pfsense_filterlog_packet(TCP_BLOCK.encode("utf-8"), environment="test")

    assert result["ok"] is True
    parsed = result["parsed"]
    assert parsed["action"] == "block"
    assert parsed["interface"] == "igb1"
    assert parsed["direction"] == "in"
    assert parsed["ip_version"] == "4"
    assert parsed["protocol"] == "tcp"
    assert parsed["source_ip"] == "198.51.100.10"
    assert parsed["destination_ip"] == "203.0.113.20"
    assert parsed["source_port"] == 54321
    assert parsed["destination_port"] == 443
    assert parsed["rule_id"] == "1000000103"
    assert parsed["tracker"] == "1777758297"

    event = result["event"]
    assert event["event_type"] == "firewall_block"
    assert event["severity"] == "medium"
    assert event["source_ip"] == "198.51.100.10"
    assert event["source"] == "pfsense"
    assert event["source_type"] == "firewall"
    assert event["app_name"] == "pfsense_filterlog"
    assert event["environment"] == "test"
    assert event["raw_payload"]["event_type_candidate"] == "firewall_block"
    assert event["raw_payload"]["destination_port"] == 443


def test_valid_ipv4_udp_pass_line_parses_and_normalizes():
    result = parse_pfsense_filterlog_packet(UDP_PASS)

    assert result["ok"] is True
    parsed = result["parsed"]
    assert parsed["action"] == "pass"
    assert parsed["interface"] == "igb0"
    assert parsed["direction"] == "out"
    assert parsed["ip_version"] == "4"
    assert parsed["protocol"] == "udp"
    assert parsed["source_ip"] == "10.0.0.5"
    assert parsed["destination_ip"] == "8.8.8.8"
    assert parsed["source_port"] == 5353
    assert parsed["destination_port"] == 53

    event = result["event"]
    assert event["event_type"] == "firewall_allow"
    assert event["severity"] == "low"
    assert event["raw_payload"]["event_type_candidate"] == "firewall_allow"


def test_malformed_input_does_not_crash_and_returns_bounded_telemetry():
    result = parse_pfsense_filterlog_packet("not syslog and not filterlog")

    assert result["ok"] is False
    assert result["error"]["stage"] == "syslog"
    assert result["error"]["reason"] == "missing_filterlog_payload"
    assert len(result["error"]["summary"]) <= 160


def test_oversized_input_rejected_before_parse():
    result = parse_pfsense_filterlog_packet(b"x" * (MAX_PACKET_BYTES + 1))

    assert result["ok"] is False
    assert result["error"]["stage"] == "size"
    assert result["error"]["reason"] == "packet_too_large"
    assert result["error"]["input_byte_length"] == MAX_PACKET_BYTES + 1
    assert result["error"]["summary"] is None


def test_invalid_utf8_is_handled_safely_without_crashing():
    result = parse_pfsense_filterlog_packet(TCP_BLOCK.encode("utf-8") + b"\xff")

    assert result["ok"] is True
    assert result["telemetry"]["utf8_replaced"] is True
    assert result["event"]["raw_payload"]["utf8_replaced"] is True


def test_control_characters_are_stripped_from_output():
    dirty = TCP_BLOCK.replace("filterlog", "filterlog\x00\x1f")

    result = parse_pfsense_filterlog_packet(dirty)

    assert result["ok"] is True
    summary = result["event"]["raw_payload"]["sanitized_summary"]
    assert "\x00" not in summary
    assert "\x1f" not in summary


def test_raw_log_preserves_full_untruncated_filterlog_text_beyond_summary_bound():
    long_suffix = "," + ("a" * 200)
    long_line = TCP_BLOCK + long_suffix

    result = parse_pfsense_filterlog_packet(long_line.encode("utf-8"))

    assert result["ok"] is True
    raw_payload = result["event"]["raw_payload"]
    assert len(raw_payload["sanitized_summary"]) == 160
    assert len(raw_payload["raw_log"]) > 160
    assert raw_payload["raw_log"].startswith(raw_payload["sanitized_summary"])
    assert raw_payload["raw_log"].endswith("a" * 200)


def test_raw_log_matches_sanitized_summary_when_line_is_short():
    result = parse_pfsense_filterlog_packet(UDP_PASS)

    assert result["ok"] is True
    raw_payload = result["event"]["raw_payload"]
    assert raw_payload["raw_log"] == raw_payload["sanitized_summary"]


def test_ipv6_or_unknown_variant_is_handled_safely():
    ipv6_line = (
        "<134>Jul  7 12:00:03 fw filterlog: "
        "1000000105,,,1777758299,igb1,match,block,in,6,0x0,,64,0,0,none,6,tcp,60,"
        "2001:db8::1,2001:db8::2,12345,443,0"
    )

    result = parse_pfsense_filterlog_packet(ipv6_line)

    assert result["ok"] is False
    assert result["error"]["stage"] == "filterlog"
    assert result["error"]["reason"] == "unsupported_ip_version"


def test_normalized_output_matches_unified_shape_and_is_runtime_isolated():
    result = parse_pfsense_filterlog_packet(UDP_PASS.encode("utf-8"), sender_ip="192.0.2.9")

    assert result["ok"] is True
    event = result["event"]
    assert set(event) == {
        "event_type",
        "severity",
        "source_ip",
        "source",
        "source_type",
        "event_timestamp",
        "message",
        "app_name",
        "environment",
        "raw_payload",
    }
    assert event["source"] == "pfsense"
    assert event["source_type"] == "firewall"
    assert event["raw_payload"]["pfsense_sender_ip"] == "192.0.2.9"
