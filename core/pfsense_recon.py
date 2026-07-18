from __future__ import annotations

import csv
import ipaddress
from collections import Counter
from datetime import datetime
from io import StringIO
from typing import Any, Iterable

from core.soar_protected_targets import is_protected_target


PFSENSE_RECON_ACTIVITY_TYPE = "distributed_internet_reconnaissance"
PFSENSE_RECON_ACTIVITY_LABEL = "Distributed Internet Reconnaissance Activity"
PFSENSE_RECON_ACTIVITY_WINDOW_MINUTES = 30
PFSENSE_RELATED_EVENT_LIMIT = 100
PFSENSE_TARGET_SAMPLE_LIMIT = 5
PFSENSE_SERVICE_SIGNATURE_LIMIT = 24
PFSENSE_EPHEMERAL_PORT_START = 32768


def parse_port(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    port = int(text)
    if port < 1 or port > 65535:
        return None
    return port


def normalize_protocol(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def normalize_interface(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def normalize_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def normalize_action(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"block", "pass"}:
        return text
    return text or None


def normalize_tcp_flags(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    allowed = "".join(character for character in text if character in {"S", "A", "F", "R", "P", "U", "E", "W", "C"})
    return allowed or None


def classify_target_mode(distinct_destination_count: Any, distinct_port_count: Any) -> str:
    destinations = int(distinct_destination_count or 0)
    ports = int(distinct_port_count or 0)
    return "exact_target" if destinations <= 1 and ports <= 1 else "aggregate_sample"


def _to_ip_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def is_public_ip(value: Any) -> bool:
    text = _to_ip_text(value)
    if not text:
        return False
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return False
    return ip.is_global


def protected_range_key(destination_ips: Iterable[Any]) -> str | None:
    buckets: list[str] = []
    for value in destination_ips:
        text = _to_ip_text(value)
        if not text:
            continue
        try:
            ip = ipaddress.ip_address(text)
        except ValueError:
            continue
        if isinstance(ip, ipaddress.IPv4Address):
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
        else:
            network = ipaddress.ip_network(f"{ip}/64", strict=False)
        buckets.append(str(network))
    unique = sorted(set(buckets))
    if len(unique) != 1:
        return None
    return unique[0]


def summarize_reputation_bucket(score: Any) -> str:
    if score is None:
        return "unknown"
    try:
        numeric = int(score)
    except (TypeError, ValueError):
        return "unknown"
    if numeric >= 70:
        return "high"
    if numeric >= 40:
        return "medium"
    return "low"


def sample_ranked_values(
    counts: dict[Any, int] | Counter,
    *,
    key_type: str,
    limit: int = PFSENSE_TARGET_SAMPLE_LIMIT,
) -> list[Any]:
    items = []
    for key, count in dict(counts).items():
        if key in (None, ""):
            continue
        items.append((key, int(count or 0)))
    if key_type == "port":
        items.sort(key=lambda item: (-item[1], int(item[0])))
    else:
        items.sort(key=lambda item: (-item[1], str(item[0])))
    return [item[0] for item in items[:limit]]


def build_service_signature(ports: Iterable[Any]) -> list[int]:
    values = sorted({port for port in (parse_port(value) for value in ports) if port is not None})
    return values[:PFSENSE_SERVICE_SIGNATURE_LIMIT]


def format_service_signature_key(ports: Iterable[Any]) -> str | None:
    signature = build_service_signature(ports)
    if not signature:
        return None
    return ",".join(str(port) for port in signature)


def build_related_event_filter(
    *,
    event_types: list[str],
    source_ip: str | None,
    destination_ips: list[str] | None = None,
    destination_ports: list[int] | None = None,
    protocol: str | None = None,
    direction: str | None = None,
    first_seen: str | None = None,
    last_seen: str | None = None,
    limit: int = PFSENSE_RELATED_EVENT_LIMIT,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_types": [event_type for event_type in event_types if event_type],
        "limit": max(1, min(int(limit), PFSENSE_RELATED_EVENT_LIMIT)),
    }
    if source_ip:
        payload["source_ip"] = source_ip
    if destination_ips:
        payload["destination_ips"] = [str(item) for item in destination_ips if item]
    if destination_ports:
        payload["destination_ports"] = [int(item) for item in destination_ports if item is not None]
    if protocol:
        payload["protocol"] = protocol
    if direction:
        payload["direction"] = direction
    if first_seen:
        payload["first_seen"] = first_seen
    if last_seen:
        payload["last_seen"] = last_seen
    return payload


def extract_pfsense_tcp_flags(raw_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(raw_payload, dict):
        return None
    direct = normalize_tcp_flags(raw_payload.get("tcp_flags"))
    if direct:
        return direct
    raw_log = str(raw_payload.get("raw_log") or "").strip()
    if not raw_log:
        return None
    try:
        fields = next(csv.reader(StringIO(raw_log)))
    except (csv.Error, StopIteration):
        return None
    if len(fields) <= 23:
        return None
    return normalize_tcp_flags(fields[23])


def classify_pfsense_tcp_traffic_role(
    *,
    source_ip: Any,
    destination_ip: Any,
    protocol: Any,
    direction: Any,
    source_port: Any,
    destination_port: Any,
    tcp_flags: Any,
    protected_networks: Iterable[ipaddress._BaseNetwork] | None = None,
) -> dict[str, Any]:
    normalized_protocol = normalize_protocol(protocol)
    normalized_direction = normalize_direction(direction)
    normalized_flags = normalize_tcp_flags(tcp_flags)
    source_port_int = parse_port(source_port)
    destination_port_int = parse_port(destination_port)
    source_ip_text = _to_ip_text(source_ip)
    destination_ip_text = _to_ip_text(destination_ip)
    source_protected = is_protected_target(source_ip_text, protected_networks=protected_networks)
    destination_protected = is_protected_target(destination_ip_text, protected_networks=protected_networks)
    evidence = {
        "direction": normalized_direction,
        "tcp_flags": normalized_flags,
        "source_port": source_port_int,
        "destination_port": destination_port_int,
        "source_is_protected": source_protected,
        "destination_is_protected": destination_protected,
    }

    if normalized_protocol != "tcp":
        return {
            "classification": "not_applicable",
            "reason": "TCP initiator semantics do not apply to this protocol",
            "evidence": evidence,
        }
    if not normalized_flags:
        return {
            "classification": "ambiguous",
            "reason": "TCP flags were missing, so initiator role could not be determined",
            "evidence": evidence,
        }

    has_syn = "S" in normalized_flags
    has_ack = "A" in normalized_flags
    has_fin = "F" in normalized_flags
    has_rst = "R" in normalized_flags
    has_psh = "P" in normalized_flags

    if has_syn and not has_ack:
        return {
            "classification": "initiation_like",
            "reason": "TCP SYN without ACK indicates a new connection attempt",
            "evidence": evidence,
        }
    if has_syn and has_ack:
        return {
            "classification": "reply_or_teardown_like",
            "reason": "TCP SYN+ACK indicates response traffic rather than a new source-initiated connection",
            "evidence": evidence,
        }
    if not has_syn and (has_ack or has_fin or has_rst or has_psh):
        if (
            normalized_direction == "out"
            and source_protected
            and _is_probable_service_port(source_port_int)
            and _is_probable_ephemeral_port(destination_port_int)
        ):
            reason = (
                "Protected-host service traffic replied to a remote ephemeral port without a new SYN"
            )
        else:
            reason = "TCP flags indicate reply or teardown traffic rather than a new connection attempt"
        return {
            "classification": "reply_or_teardown_like",
            "reason": reason,
            "evidence": evidence,
        }
    return {
        "classification": "ambiguous",
        "reason": "TCP flags did not reliably show whether the source initiated the connection",
        "evidence": evidence,
    }


def singular_or_plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


def build_scan_description(
    *,
    distinct_port_count: int,
    distinct_destination_count: int,
    primary_destination_port: int | None,
    targets_are_public: bool,
) -> str:
    host_label = "public IPs" if targets_are_public else "destination hosts"
    port_count = int(distinct_port_count or 0)
    destination_count = int(distinct_destination_count or 0)

    if port_count == 1 and destination_count > 1 and primary_destination_port is not None:
        return f"Scanned port {primary_destination_port} across {destination_count} {host_label}."
    if destination_count == 1 and port_count > 1:
        return f"Scanned {port_count} ports on 1 destination host."
    return (
        f"Scanned {port_count} {singular_or_plural(port_count, 'port')} across "
        f"{destination_count} {singular_or_plural(destination_count, 'destination host')}."
    )


def to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def severity_rank(value: Any) -> int:
    order = {"low": 1, "medium": 2, "high": 3}
    return order.get(str(value or "").strip().lower(), 0)


def status_rank(value: Any) -> int:
    order = {"resolved": 1, "monitoring": 2, "open": 3}
    return order.get(str(value or "").strip().lower(), 0)


def _is_probable_service_port(value: int | None) -> bool:
    if value is None:
        return False
    return value <= 1024 or value in {1194, 3389, 51820, 8443}


def _is_probable_ephemeral_port(value: int | None) -> bool:
    if value is None:
        return False
    return value >= PFSENSE_EPHEMERAL_PORT_START
