import csv
import ipaddress
import re
from io import StringIO


MAX_PACKET_BYTES = 4096
MAX_SUMMARY_CHARS = 160

FILTERLOG_MARKER_PATTERN = re.compile(r"\bfilterlog(?:\[\d+\])?:\s*(?P<payload>.+)$")
UNSAFE_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

ACTION_EVENT_TYPE_CANDIDATES = {
    "block": "firewall_block",
    "pass": "firewall_allow",
}

ACTION_SEVERITIES = {
    "block": "medium",
    "pass": "low",
}

PFSENSE_INGEST_EVENT_TYPES = frozenset(ACTION_EVENT_TYPE_CANDIDATES.values())
PFSENSE_VALID_ACTIONS = frozenset(ACTION_EVENT_TYPE_CANDIDATES.keys())
PFSENSE_VALID_PROTOCOLS = frozenset({"tcp", "udp"})
PFSENSE_VALID_DIRECTIONS = frozenset({"in", "out"})
PFSENSE_VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
MAX_PFSENSE_INGEST_BYTES = 65536


def parse_pfsense_filterlog_packet(packet, *, environment="prod", event_timestamp=None, sender_ip=None):
    byte_length = _packet_byte_length(packet)
    if byte_length > MAX_PACKET_BYTES:
        return _parse_failure("size", "packet_too_large", byte_length=byte_length)

    text, utf8_replaced = _decode_packet(packet)
    sanitized_text = sanitize_pfsense_text(text)
    if not sanitized_text.strip():
        return _parse_failure("decode", "empty_input", byte_length=byte_length, summary=sanitized_text)

    payload = extract_filterlog_payload(sanitized_text)
    if payload is None:
        return _parse_failure("syslog", "missing_filterlog_payload", byte_length=byte_length, summary=sanitized_text)

    fields = _parse_csv_fields(payload)
    parsed_or_failure = parse_filterlog_fields(fields, byte_length=byte_length, summary=payload)
    if not parsed_or_failure.get("ok"):
        return parsed_or_failure

    parsed = parsed_or_failure["parsed"]
    normalized = normalize_pfsense_filterlog_event(
        parsed,
        environment=environment,
        event_timestamp=event_timestamp,
        sender_ip=sender_ip,
        sanitized_summary=payload,
        utf8_replaced=utf8_replaced,
    )
    return {
        "ok": True,
        "event": normalized,
        "parsed": parsed,
        "telemetry": {
            "input_byte_length": byte_length,
            "utf8_replaced": utf8_replaced,
        },
    }


def sanitize_pfsense_text(value):
    if value is None:
        return ""
    return UNSAFE_CONTROL_PATTERN.sub("", str(value)).strip()


def extract_filterlog_payload(syslog_text):
    text = sanitize_pfsense_text(syslog_text)
    match = FILTERLOG_MARKER_PATTERN.search(text)
    if match:
        return sanitize_pfsense_text(match.group("payload"))

    fields = _parse_csv_fields(text)
    if len(fields) >= 22 and _clean(fields[6]) in ACTION_EVENT_TYPE_CANDIDATES:
        return text

    return None


def parse_filterlog_fields(fields, *, byte_length=None, summary=None):
    if len(fields) < 20:
        return _parse_failure("filterlog", "not_enough_fields", byte_length=byte_length, summary=summary)

    action = _clean(_field(fields, 6)).lower()
    direction = _clean(_field(fields, 7)).lower()
    ip_version = _clean(_field(fields, 8))
    protocol = _clean(_field(fields, 16)).lower()

    if ip_version != "4":
        return _parse_failure("filterlog", "unsupported_ip_version", byte_length=byte_length, summary=summary)

    if protocol not in {"tcp", "udp"}:
        return _parse_failure("filterlog", "unsupported_protocol", byte_length=byte_length, summary=summary)

    if action not in ACTION_EVENT_TYPE_CANDIDATES:
        return _parse_failure("filterlog", "unsupported_action", byte_length=byte_length, summary=summary)

    source_ip = _validated_ip(_field(fields, 18))
    destination_ip = _validated_ip(_field(fields, 19))
    if source_ip is None or destination_ip is None:
        return _parse_failure("filterlog", "invalid_ip_address", byte_length=byte_length, summary=summary)

    source_port = _optional_port(_field(fields, 20))
    destination_port = _optional_port(_field(fields, 21))
    if source_port is None or destination_port is None:
        return _parse_failure("filterlog", "invalid_port", byte_length=byte_length, summary=summary)

    return {
        "ok": True,
        "parsed": {
            "rule_id": _clean(_field(fields, 0)) or None,
            "tracker": _clean(_field(fields, 3)) or None,
            "interface": _clean(_field(fields, 4)) or None,
            "action": action,
            "direction": direction or None,
            "ip_version": ip_version,
            "protocol": protocol,
            "source_ip": source_ip,
            "destination_ip": destination_ip,
            "source_port": source_port,
            "destination_port": destination_port,
        },
    }


def normalize_pfsense_filterlog_event(
    parsed,
    *,
    environment="prod",
    event_timestamp=None,
    sender_ip=None,
    sanitized_summary=None,
    utf8_replaced=False,
):
    action = parsed["action"]
    event_type = ACTION_EVENT_TYPE_CANDIDATES[action]
    raw_payload = {
        "action": action,
        "interface": parsed.get("interface"),
        "direction": parsed.get("direction"),
        "ip_version": parsed.get("ip_version"),
        "protocol": parsed.get("protocol"),
        "source_ip": parsed.get("source_ip"),
        "destination_ip": parsed.get("destination_ip"),
        "event_type_candidate": event_type,
        "utf8_replaced": bool(utf8_replaced),
    }

    for key in ("source_port", "destination_port", "rule_id", "tracker"):
        value = parsed.get(key)
        if value not in (None, ""):
            raw_payload[key] = value

    if sender_ip:
        raw_payload["pfsense_sender_ip"] = sanitize_pfsense_text(sender_ip)

    summary = _bounded_summary(sanitized_summary)
    if summary:
        raw_payload["sanitized_summary"] = summary

    return {
        "event_type": event_type,
        "severity": ACTION_SEVERITIES.get(action, "medium"),
        "source_ip": parsed["source_ip"],
        "source": "pfsense",
        "source_type": "firewall",
        "event_timestamp": event_timestamp,
        "message": _build_message(parsed, event_type),
        "app_name": "pfsense_filterlog",
        "environment": sanitize_pfsense_text(environment) or "prod",
        "raw_payload": raw_payload,
    }


def _build_message(parsed, event_type):
    action_label = "blocked" if event_type == "firewall_block" else "allowed"
    destination = parsed["destination_ip"]
    destination_port = parsed.get("destination_port")
    if destination_port is not None:
        destination = f"{destination}:{destination_port}"
    return (
        f"pfSense {parsed['protocol'].upper()} traffic {action_label} "
        f"from {parsed['source_ip']} to {destination}"
    )


def _packet_byte_length(packet):
    if isinstance(packet, bytes):
        return len(packet)
    if isinstance(packet, str):
        return len(packet.encode("utf-8", errors="replace"))
    if packet is None:
        return 0
    return len(str(packet).encode("utf-8", errors="replace"))


def _decode_packet(packet):
    if isinstance(packet, bytes):
        try:
            return packet.decode("utf-8"), False
        except UnicodeDecodeError:
            return packet.decode("utf-8", errors="replace"), True
    if packet is None:
        return "", False
    return str(packet), False


def _parse_csv_fields(payload):
    try:
        return next(csv.reader(StringIO(payload)))
    except (csv.Error, StopIteration):
        return []


def _field(fields, index):
    if index >= len(fields):
        return None
    return fields[index]


def _clean(value):
    return sanitize_pfsense_text(value)


def _validated_ip(value):
    try:
        parsed = ipaddress.ip_address(_clean(value))
    except ValueError:
        return None
    if parsed.version != 4:
        return None
    return str(parsed)


def _optional_port(value):
    text = _clean(value)
    if not text:
        return None
    try:
        port = int(text)
    except ValueError:
        return None
    if 0 <= port <= 65535:
        return port
    return None


def _parse_failure(stage, reason, *, byte_length=None, summary=None):
    return {
        "ok": False,
        "error": {
            "stage": stage,
            "reason": reason,
            "input_byte_length": byte_length,
            "summary": _bounded_summary(summary),
        },
    }


def _bounded_summary(value):
    summary = sanitize_pfsense_text(value)
    if not summary:
        return None
    return summary[:MAX_SUMMARY_CHARS]


def validate_pfsense_normalized_event(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid JSON")

    required_fields = (
        "event_type",
        "severity",
        "source_ip",
        "source",
        "source_type",
        "message",
        "app_name",
        "environment",
        "raw_payload",
    )
    for field_name in required_fields:
        value = data.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Missing required fields")

    event_type = str(data.get("event_type")).strip()
    if event_type not in PFSENSE_INGEST_EVENT_TYPES:
        raise ValueError("Invalid event_type")

    severity = str(data.get("severity")).strip().lower()
    if severity not in PFSENSE_VALID_SEVERITIES:
        raise ValueError("Invalid severity")

    source = str(data.get("source")).strip()
    source_type = str(data.get("source_type")).strip()
    if source != "pfsense" or source_type != "firewall":
        raise ValueError("Invalid source fields")

    source_ip = _validated_ip(data.get("source_ip"))
    if source_ip is None:
        raise ValueError("Invalid source_ip")

    raw_payload = data.get("raw_payload")
    if not isinstance(raw_payload, dict):
        raise ValueError("Invalid raw_payload")

    _validate_pfsense_raw_payload(raw_payload, event_type)

    return {
        "event_type": event_type,
        "severity": severity,
        "source_ip": source_ip,
        "source": source,
        "source_type": source_type,
        "event_timestamp": data.get("event_timestamp"),
        "message": str(data.get("message")).strip(),
        "app_name": str(data.get("app_name")).strip(),
        "environment": sanitize_pfsense_text(data.get("environment")) or "prod",
        "raw_payload": raw_payload,
    }


def _validate_pfsense_raw_payload(raw_payload, event_type):
    required_fields = (
        "action",
        "interface",
        "direction",
        "ip_version",
        "protocol",
        "source_ip",
        "destination_ip",
    )
    for field_name in required_fields:
        if field_name not in raw_payload:
            raise ValueError("Invalid raw_payload")

    action = _clean(raw_payload.get("action")).lower()
    if action not in PFSENSE_VALID_ACTIONS:
        raise ValueError("Invalid raw_payload")
    if ACTION_EVENT_TYPE_CANDIDATES.get(action) != event_type:
        raise ValueError("Invalid raw_payload")

    interface = _clean(raw_payload.get("interface"))
    if not interface:
        raise ValueError("Invalid raw_payload")

    direction = raw_payload.get("direction")
    if direction is not None:
        direction_text = _clean(direction).lower()
        if direction_text and direction_text not in PFSENSE_VALID_DIRECTIONS:
            raise ValueError("Invalid raw_payload")

    ip_version = _clean(raw_payload.get("ip_version"))
    if ip_version != "4":
        raise ValueError("Invalid raw_payload")

    protocol = _clean(raw_payload.get("protocol")).lower()
    if protocol not in PFSENSE_VALID_PROTOCOLS:
        raise ValueError("Invalid raw_payload")

    if _validated_ip(raw_payload.get("source_ip")) is None:
        raise ValueError("Invalid raw_payload")
    if _validated_ip(raw_payload.get("destination_ip")) is None:
        raise ValueError("Invalid raw_payload")

    for port_field in ("source_port", "destination_port"):
        if port_field not in raw_payload:
            continue
        port_value = raw_payload.get(port_field)
        if port_value is None:
            continue
        if _optional_port(port_value) is None:
            raise ValueError("Invalid raw_payload")

    for identifier_field in ("rule_id", "tracker"):
        if identifier_field not in raw_payload:
            continue
        identifier_value = raw_payload.get(identifier_field)
        if identifier_value is None:
            continue
        if not isinstance(identifier_value, (str, int)):
            raise ValueError("Invalid raw_payload")
        if isinstance(identifier_value, str) and not sanitize_pfsense_text(identifier_value):
            raise ValueError("Invalid raw_payload")
