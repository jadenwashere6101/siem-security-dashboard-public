from __future__ import annotations

from dataclasses import dataclass


INGESTION_MODE_PUSH = "push"
INGESTION_MODE_CHECKPOINT = "checkpoint"

# These thresholds describe when the SIEM can still establish ingestion
# freshness. They are intentionally centralized with the canonical source
# definitions rather than inferred by individual consumers.
PUSH_CONTINUOUS_FRESHNESS_SECONDS = 15 * 60
PUSH_APPLICATION_FRESHNESS_SECONDS = 60 * 60
PUSH_SPARSE_FRESHNESS_SECONDS = 24 * 60 * 60
AZURE_CHECKPOINT_FRESHNESS_SECONDS = 30 * 60


@dataclass(frozen=True)
class SourceDefinition:
    source: str
    source_type: str
    display_label: str
    live_logs_destination: str
    ingestion_mode: str
    freshness_threshold_seconds: int


CANONICAL_SOURCES = (
    SourceDefinition(
        "honeypot", "honeypot", "Honeypot", "live-logs-honeypot",
        INGESTION_MODE_PUSH, PUSH_SPARSE_FRESHNESS_SECONDS,
    ),
    SourceDefinition(
        "bank_app", "custom", "Bank App", "live-logs-bank-app",
        INGESTION_MODE_PUSH, PUSH_APPLICATION_FRESHNESS_SECONDS,
    ),
    SourceDefinition(
        "pfsense", "firewall", "pfSense", "live-logs-pfsense",
        INGESTION_MODE_PUSH, PUSH_CONTINUOUS_FRESHNESS_SECONDS,
    ),
    SourceDefinition(
        "nginx", "web_log", "NGINX", "live-logs-nginx",
        INGESTION_MODE_PUSH, PUSH_APPLICATION_FRESHNESS_SECONDS,
    ),
    SourceDefinition(
        "azure_insights",
        "cloud_api",
        "Azure Application Insights",
        "live-logs-azure",
        INGESTION_MODE_CHECKPOINT,
        AZURE_CHECKPOINT_FRESHNESS_SECONDS,
    ),
    SourceDefinition(
        "opentelemetry",
        "telemetry",
        "OpenTelemetry",
        "live-logs-otel",
        INGESTION_MODE_PUSH,
        PUSH_APPLICATION_FRESHNESS_SECONDS,
    ),
)

CANONICAL_SOURCE_IDS = frozenset(item.source for item in CANONICAL_SOURCES)
CANONICAL_PUSH_SOURCE_IDS = frozenset(
    item.source
    for item in CANONICAL_SOURCES
    if item.ingestion_mode == INGESTION_MODE_PUSH
)

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
