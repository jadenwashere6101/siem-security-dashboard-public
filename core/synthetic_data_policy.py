from __future__ import annotations

import ipaddress
import os
from typing import Iterable

DOCUMENTATION_SOURCE_IP_NETWORK_EXCLUSIONS = frozenset(
    {
        "192.0.2.0/24",      # TEST-NET-1
        "198.51.100.0/24",   # TEST-NET-2
        "203.0.113.0/24",    # TEST-NET-3
        "2001:db8::/32",     # IPv6 documentation prefix
    }
)

CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS = frozenset(
    {
        "8.8.8.8",
        "12.12.12.12",
        "13.13.13.13",
        "55.55.55.55",
        "55.66.77.88",
        "66.77.88.99",
        "77.77.77.77",
        "88.88.88.88",
        "99.99.99.99",
        "101.101.101.101",
        "102.102.102.102",
        "103.103.103.103",
        "104.104.104.104",
        "105.105.105.105",
        "106.106.106.106",
        "107.107.107.107",
    }
)

CONFIRMED_SYNTHETIC_CLEANUP_SOURCE_IPS = frozenset(CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS | {"1.1.1.1"})

CONFIRMED_LEGACY_SYNTHETIC_ALERT_IDS = frozenset(
    {
        16,
        17,
        18,
        34,
        35,
        36,
        37,
        44,
        45,
        46,
        47,
    }
)

SYNTHETIC_PROVENANCE_VALUES = frozenset(
    {
        "azure_smoke",
        "demo",
        "manual_test",
        "seed",
        "seeded_test",
        "smoke",
        "simulated",
        "simulation",
        "simulator",
        "synthetic",
        "test",
    }
)

SYNTHETIC_TEXT_EVIDENCE_REGEX = (
    r"(synthetic|simulated|simulation|simulator|demo|smoke|seeded?|manual[ _-]?test|"
    r"fabricated|test[ _-]?(alert|data|user|run|batch|note)|this is a test|"
    r"azure[ _-]?smoke|dummy|fake|sample|testuser[0-9]+|user[0-9]{1,3})"
)


def load_synthetic_source_ip_exclusions(logger=None) -> tuple[set[str], set[str]]:
    raw_value = (
        os.getenv("SIEM_SYNTHETIC_SOURCE_IP_EXCLUSIONS")
        or os.getenv("SYNTHETIC_SOURCE_IP_EXCLUSIONS")
        or ""
    )
    raw_network_value = (
        os.getenv("SIEM_SYNTHETIC_SOURCE_IP_NETWORK_EXCLUSIONS")
        or os.getenv("SYNTHETIC_SOURCE_IP_NETWORK_EXCLUSIONS")
        or ""
    )
    exclusions: set[str] = set(CONFIRMED_LEGACY_SYNTHETIC_SOURCE_IPS)
    network_exclusions: set[str] = set(DOCUMENTATION_SOURCE_IP_NETWORK_EXCLUSIONS)
    for part in raw_value.split(","):
        normalized = part.strip()
        if not normalized:
            continue
        try:
            if "/" in normalized:
                network_exclusions.add(str(ipaddress.ip_network(normalized, strict=False)))
            else:
                exclusions.add(str(ipaddress.ip_address(normalized)))
        except ValueError:
            if logger:
                logger.warning("Ignoring invalid synthetic source IP exclusion: %s", normalized)
    for part in raw_network_value.split(","):
        normalized = part.strip()
        if not normalized:
            continue
        try:
            network_exclusions.add(str(ipaddress.ip_network(normalized, strict=False)))
        except ValueError:
            if logger:
                logger.warning("Ignoring invalid synthetic source IP network exclusion: %s", normalized)
    return exclusions, network_exclusions


def _sql_identifier(identifier: str) -> str:
    if not identifier:
        raise ValueError("SQL identifier cannot be empty")
    parts = identifier.split(".")
    for part in parts:
        if not part.replace("_", "").isalnum() or part[0].isdigit():
            raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return identifier


def _context_provenance_sql(context_column: str) -> str:
    context_column = _sql_identifier(context_column)
    return f"""
        LOWER(
            COALESCE(
                NULLIF({context_column}->>'data_provenance', ''),
                NULLIF({context_column}->>'telemetry_provenance', ''),
                NULLIF({context_column}->>'provenance', ''),
                NULLIF({context_column}#>>'{{provenance,classification}}', ''),
                NULLIF({context_column}#>>'{{provenance,source}}', ''),
                NULLIF({context_column}#>>'{{metadata,data_provenance}}', ''),
                ''
            )
        )
    """


def build_synthetic_json_value_sql(json_column: str) -> str:
    json_column = _sql_identifier(json_column)
    return f"""
        LOWER(
            COALESCE(
                NULLIF({json_column}->>'data_provenance', ''),
                NULLIF({json_column}->>'telemetry_provenance', ''),
                NULLIF({json_column}->>'provenance', ''),
                NULLIF({json_column}#>>'{{provenance,classification}}', ''),
                NULLIF({json_column}#>>'{{provenance,source}}', ''),
                NULLIF({json_column}#>>'{{provenance,origin}}', ''),
                NULLIF({json_column}#>>'{{metadata,data_provenance}}', ''),
                NULLIF({json_column}#>>'{{metadata,provenance}}', ''),
                ''
            )
        )
    """


def build_operational_source_ip_exclusion_sql(
    *,
    source_ip_column: str = "source_ip",
    source_column: str = "source",
    source_type_column: str = "source_type",
    context_column: str = "context",
    logger=None,
) -> tuple[str, list]:
    excluded_ips, excluded_networks = load_synthetic_source_ip_exclusions(logger=logger)
    source_ip_column = _sql_identifier(source_ip_column)
    source_column = _sql_identifier(source_column)
    source_type_column = _sql_identifier(source_type_column)
    context_column = _sql_identifier(context_column)

    clauses: list[str] = []
    params: list = []
    if excluded_ips:
        clauses.append(f"NOT (host({source_ip_column}) = ANY(%s))")
        params.append(sorted(excluded_ips))
    if excluded_networks:
        clauses.append(f"NOT ({source_ip_column} <<= ANY(%s::cidr[]))")
        params.append(sorted(excluded_networks))

    synthetic_values = sorted(SYNTHETIC_PROVENANCE_VALUES)
    clauses.append(
        f"""
        NOT (
            LOWER(COALESCE({source_column}, '')) = ANY(%s)
            OR LOWER(COALESCE({source_type_column}, '')) = ANY(%s)
            OR {_context_provenance_sql(context_column)} = ANY(%s)
        )
        """
    )
    params.extend([synthetic_values, synthetic_values, synthetic_values])
    return " AND ".join(clauses), params


def mark_payload_as_synthetic(
    payload: dict,
    *,
    origin: str,
    provenance: str = "synthetic",
) -> dict:
    enriched = dict(payload)
    enriched["data_provenance"] = provenance
    existing = enriched.get("provenance")
    provenance_payload = existing if isinstance(existing, dict) else {}
    enriched["provenance"] = {
        **provenance_payload,
        "classification": provenance,
        "origin": origin,
    }
    return enriched


def normalize_confirmed_synthetic_alert_ids(values: Iterable[int | str] | None = None) -> tuple[int, ...]:
    selected = values or CONFIRMED_LEGACY_SYNTHETIC_ALERT_IDS
    return tuple(sorted({int(value) for value in selected}))
