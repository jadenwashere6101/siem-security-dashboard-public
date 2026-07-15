from __future__ import annotations

import ipaddress
from collections import Counter
from datetime import datetime
from typing import Any, Iterable


PFSENSE_RECON_ACTIVITY_TYPE = "distributed_internet_reconnaissance"
PFSENSE_RECON_ACTIVITY_LABEL = "Distributed Internet Reconnaissance Activity"
PFSENSE_RECON_ACTIVITY_WINDOW_MINUTES = 30
PFSENSE_RELATED_EVENT_LIMIT = 100
PFSENSE_TARGET_SAMPLE_LIMIT = 5
PFSENSE_SERVICE_SIGNATURE_LIMIT = 24


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
