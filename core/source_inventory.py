from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDefinition:
    source: str
    source_type: str
    display_label: str
    live_logs_destination: str


CANONICAL_SOURCES = (
    SourceDefinition("honeypot", "honeypot", "Honeypot", "live-logs-honeypot"),
    SourceDefinition("bank_app", "custom", "Bank App", "live-logs-bank-app"),
    SourceDefinition("pfsense", "firewall", "pfSense", "live-logs-pfsense"),
    SourceDefinition("nginx", "web_log", "NGINX", "live-logs-nginx"),
    SourceDefinition(
        "azure_insights",
        "cloud_api",
        "Azure Application Insights",
        "live-logs-azure",
    ),
    SourceDefinition(
        "opentelemetry",
        "telemetry",
        "OpenTelemetry",
        "live-logs-otel",
    ),
)

CANONICAL_SOURCE_IDS = frozenset(item.source for item in CANONICAL_SOURCES)

# Inbound compatibility aliases only. Canonical IDs remain authoritative for
# persistence, filtering, evidence provenance, and user-visible contracts.
SOURCE_ID_ALIASES = {
    "azure": "azure_insights",
    "otlp": "opentelemetry",
    "web_log": "nginx",
}


def normalize_source_id(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = SOURCE_ID_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_SOURCE_IDS:
        raise ValueError(f"Unsupported source: {value}")
    return normalized


def source_definition(value: str) -> SourceDefinition:
    normalized = normalize_source_id(value)
    return next(item for item in CANONICAL_SOURCES if item.source == normalized)
