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

