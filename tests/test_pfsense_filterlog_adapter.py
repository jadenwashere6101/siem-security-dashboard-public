from datetime import datetime, timezone

import pytest

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

ICMP_BLOCK = (
    "<134>Jul  7 12:00:03 fw filterlog: "
    "1000000105,,,1777758299,igb1,match,block,in,4,0x0,,64,0,0,none,1,icmp,84,"
    "198.51.100.11,203.0.113.21,8,0"
)

GENERIC_IPV4_PREFIX = (
    "<134>Jul  7 12:00:03 fw filterlog: "
    "1000000105,,,1777758299,igb1,match,block,in,4,0x0,,64,0,0,none,{protocol_id},{protocol},84,"
    "198.51.100.11,203.0.113.21"
)


def make_ipv4_protocol_line(protocol, protocol_id):
    return GENERIC_IPV4_PREFIX.format(protocol=protocol, protocol_id=protocol_id)


def make_icmp_line(*details):
    return make_ipv4_protocol_line("icmp", 1) + "," + ",".join(str(value) for value in details)


def test_valid_ipv4_tcp_block_line_parses_and_normalizes():
    result = parse_pfsense_filterlog_packet(
        TCP_BLOCK.encode("utf-8"),
        environment="test",
        received_at=datetime(2026, 7, 7, 12, 1, tzinfo=timezone.utc),
        syslog_timezone="America/New_York",
    )

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
    assert event["event_timestamp"] == "2026-07-07T12:00:01-04:00"
    assert event["raw_payload"]["event_type_candidate"] == "firewall_block"
    assert event["raw_payload"]["destination_port"] == 443
    assert event["raw_payload"]["raw_syslog"] == TCP_BLOCK


def test_single_digit_day_timestamp_parses_with_timezone_awareness():
    result = parse_pfsense_filterlog_packet(
        TCP_BLOCK,
        received_at=datetime(2026, 7, 7, 12, 1, tzinfo=timezone.utc),
        syslog_timezone="America/New_York",
    )

    assert result["ok"] is True
    assert result["event"]["event_timestamp"] == "2026-07-07T12:00:01-04:00"
    assert result["telemetry"]["timestamp_status"] == "parsed"


def test_year_boundary_infers_previous_year_without_future_timestamp():
    year_boundary = TCP_BLOCK.replace("Jul  7 12:00:01", "Dec 31 23:59:59")

    result = parse_pfsense_filterlog_packet(
        year_boundary,
        received_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        syslog_timezone="America/New_York",
    )

    assert result["ok"] is True
    assert result["event"]["event_timestamp"] == "2025-12-31T23:59:59-05:00"


def test_configured_iana_timezone_applies_dst_offset_for_summer_date(monkeypatch):
    monkeypatch.setenv("PFSENSE_SYSLOG_TIMEZONE", "America/New_York")

    result = parse_pfsense_filterlog_packet(
        TCP_BLOCK,
        received_at=datetime(2026, 7, 7, 16, 1, tzinfo=timezone.utc),
    )

    assert result["event"]["event_timestamp"] == "2026-07-07T12:00:01-04:00"


def test_iana_timezone_applies_standard_time_offset_for_winter_date():
    winter_line = TCP_BLOCK.replace("Jul  7 12:00:01", "Jan 15 12:00:01")

    result = parse_pfsense_filterlog_packet(
        winter_line,
        received_at=datetime(2026, 1, 15, 17, 1, tzinfo=timezone.utc),
        syslog_timezone="America/New_York",
    )

    assert result["event"]["event_timestamp"] == "2026-01-15T12:00:01-05:00"


def test_invalid_configured_timezone_fails_safe_without_vm_timezone_fallback():
    result = parse_pfsense_filterlog_packet(
        TCP_BLOCK,
        received_at=datetime(2026, 7, 7, 16, 1, tzinfo=timezone.utc),
        syslog_timezone="Not/A_Real_Zone",
    )

    assert result["ok"] is True
    assert result["event"]["event_timestamp"] is None
    assert result["telemetry"]["timestamp_status"] == "invalid"
    assert result["telemetry"]["timestamp_reason"] == "invalid_syslog_timezone"
    assert result["event"]["raw_payload"]["timestamp_parse_reason"] == "invalid_syslog_timezone"


def test_rfc5424_timestamp_preserves_explicit_timezone_offset():
    rfc5424_line = TCP_BLOCK.replace(
        "<134>Jul  7 12:00:01 fw filterlog[12345]: ",
        "<134>1 2026-07-07T08:00:01-04:00 fw filterlog 12345 - filterlog: ",
    )

    result = parse_pfsense_filterlog_packet(
        rfc5424_line,
        received_at=datetime(2026, 7, 7, 12, 1, tzinfo=timezone.utc),
        syslog_timezone="Not/A_Real_Zone",
    )

    assert result["ok"] is True
    assert result["event"]["event_timestamp"] == "2026-07-07T08:00:01-04:00"


def test_invalid_timestamp_keeps_valid_event_and_records_safe_diagnostic():
    invalid_timestamp = TCP_BLOCK.replace("Jul  7 12:00:01", "Jul 99 12:00:01")

    result = parse_pfsense_filterlog_packet(
        invalid_timestamp,
        received_at=datetime(2026, 7, 7, 12, 1, tzinfo=timezone.utc),
    )

    assert result["ok"] is True
    assert result["event"]["event_timestamp"] is None
    assert result["telemetry"]["timestamp_status"] == "invalid"
    assert result["telemetry"]["timestamp_reason"] == "invalid_bsd_timestamp"
    assert result["event"]["raw_payload"]["timestamp_parse_reason"] == "invalid_bsd_timestamp"
    assert invalid_timestamp not in str(result["telemetry"])


def test_missing_timestamp_keeps_valid_raw_filterlog_payload():
    raw_payload_only = TCP_BLOCK.split("filterlog[12345]: ", 1)[1]

    result = parse_pfsense_filterlog_packet(raw_payload_only)

    assert result["ok"] is True
    assert result["event"]["event_timestamp"] is None
    assert result["telemetry"]["timestamp_status"] == "missing"
    assert result["event"]["raw_payload"]["raw_log"] == raw_payload_only


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


def test_valid_ipv4_icmp_block_has_type_code_and_no_ports():
    result = parse_pfsense_filterlog_packet(ICMP_BLOCK)

    assert result["ok"] is True
    assert result["parsed"]["protocol"] == "icmp"
    assert result["parsed"]["icmp_type"] == 8
    assert result["parsed"]["icmp_code"] == 0
    assert result["event"]["raw_payload"]["icmp_type"] == 8
    assert "source_port" not in result["event"]["raw_payload"]
    assert "destination_port" not in result["event"]["raw_payload"]


@pytest.mark.parametrize(
    "protocol,protocol_id",
    [
        ("ah", 51),
        ("carp", 112),
        ("esp", 50),
        ("gre", 47),
        ("igmp", 2),
        ("ipencap", 4),
        ("ospf", 89),
        ("pfsync", 240),
        ("pim", 103),
        ("sctp", 132),
    ],
)
def test_common_ipv4_protocol_variants_parse_without_port_assumptions(protocol, protocol_id):
    result = parse_pfsense_filterlog_packet(make_ipv4_protocol_line(protocol, protocol_id))

    assert result["ok"] is True
    assert result["parsed"]["protocol"] == protocol
    assert result["parsed"]["source_port"] is None
    assert result["parsed"]["destination_port"] is None
    assert result["event"]["raw_payload"]["protocol"] == protocol


@pytest.mark.parametrize(
    "details,expected_type",
    [
        (("request", 123, 1), "request"),
        (("reply", 123, 1), "reply"),
        (("unreach", "host unreachable"), "unreach"),
        (("unreachport", "203.0.113.21", 17, 53), "unreachport"),
        (("unreachproto", "203.0.113.21", 47), "unreachproto"),
        (("needfrag", "203.0.113.21", 1400), "needfrag"),
        (("timexceed", "ttl exceeded"), "timexceed"),
        (("redirect", "host redirect"), "redirect"),
        (("paramprob", "invalid header"), "paramprob"),
        (("parameterprob", "invalid header"), "parameterprob"),
        (("maskreply", "255.255.255.0"), "maskreply"),
        (("tstamp", 123, 1), "tstamp"),
        (("tstampreply", 123, 1, 100, 101, 102), "tstampreply"),
    ],
)
def test_documented_textual_icmp_variants_parse(details, expected_type):
    result = parse_pfsense_filterlog_packet(make_icmp_line(*details))

    assert result["ok"] is True
    assert result["parsed"]["protocol"] == "icmp"
    assert result["parsed"]["icmp_type"] == expected_type
    assert result["parsed"]["icmp_code"] is None
    assert result["event"]["raw_payload"]["icmp_type"] == expected_type


def test_unsupported_ipv4_protocol_and_icmp_type_still_fail_cleanly():
    unsupported_protocol = parse_pfsense_filterlog_packet(make_ipv4_protocol_line("unknownproto", 253))
    unsupported_icmp = parse_pfsense_filterlog_packet(make_icmp_line("unknownicmp", "details"))

    assert unsupported_protocol["ok"] is False
    assert unsupported_protocol["error"]["reason"] == "unsupported_protocol"
    assert unsupported_icmp["ok"] is False
    assert unsupported_icmp["error"]["reason"] == "invalid_icmp_type"


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
